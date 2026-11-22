"""What the environment proxy allows, from its rules (the env_runtime role's
files/proxy/nucarium_proxy.py). Runs without mitmproxy: the decision is a
plain function of the rules, the host and the port.

    python3 -m unittest discover -s tests
"""
import json
import os
import pathlib
import sys
import tempfile
import time
import unittest
from unittest import mock
from types import SimpleNamespace

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "roles/env_runtime/files/proxy"))

import nucarium_proxy  # noqa: E402
from nucarium_proxy import allowed, decrypts, parse_rules  # noqa: E402

ALWAYS = ["api.anthropic.com", "claude.ai", "*.frame.claudeusercontent.com"]
ALLOW = ["registry.npmjs.org", "*.example.com", "git.example.org:8443", "10.1.2.3", "[2001:db8::1]:443"]


def rules(mode):
    return {"mode": mode, "allow": ALLOW, "always": ALWAYS}


class Decisions(unittest.TestCase):
    def test_claude_code_hosts_in_every_mode(self):
        for mode in ("none", "limited", "full"):
            with self.subTest(mode=mode):
                self.assertTrue(allowed(rules(mode), "api.anthropic.com", 443))
                self.assertTrue(allowed(rules(mode), "claude.ai", 443))
                self.assertTrue(allowed(rules(mode), "abc.frame.claudeusercontent.com", 443))

    def test_none_reaches_nothing_else(self):
        for host in ("registry.npmjs.org", "example.com", "a.example.com", "10.1.2.3"):
            with self.subTest(host=host):
                self.assertFalse(allowed(rules("none"), host, 443))

    def test_limited_reaches_its_list_and_nothing_else(self):
        r = rules("limited")
        self.assertTrue(allowed(r, "registry.npmjs.org", 443))
        self.assertTrue(allowed(r, "registry.npmjs.org", 80))
        self.assertTrue(allowed(r, "10.1.2.3", 22))
        self.assertFalse(allowed(r, "example.org", 443))
        self.assertFalse(allowed(r, "npmjs.org", 443))
        self.assertFalse(allowed(r, "registry.npmjs.org.evil.test", 443))
        self.assertFalse(allowed(r, "evilregistry.npmjs.org", 443))

    def test_full_reaches_anything(self):
        self.assertTrue(allowed(rules("full"), "example.org", 443))
        self.assertTrue(allowed(rules("full"), "192.0.2.7", 25))

    def test_wildcard_is_subdomains_not_the_domain(self):
        r = rules("limited")
        self.assertTrue(allowed(r, "a.example.com", 443))
        self.assertTrue(allowed(r, "a.b.example.com", 443))
        self.assertFalse(allowed(r, "example.com", 443))
        self.assertFalse(allowed(r, "badexample.com", 443))
        self.assertFalse(allowed(r, "frame.claudeusercontent.com", 443))

    def test_an_entry_with_a_port_is_that_port_only(self):
        r = rules("limited")
        self.assertTrue(allowed(r, "git.example.org", 8443))
        self.assertFalse(allowed(r, "git.example.org", 443))
        self.assertTrue(allowed(r, "2001:db8::1", 443))
        self.assertTrue(allowed(r, "[2001:db8::1]", 443))
        self.assertFalse(allowed(r, "2001:db8::1", 80))

    def test_case_and_trailing_dot_do_not_matter(self):
        r = rules("limited")
        self.assertTrue(allowed(r, "Registry.NPMJS.org", 443))
        self.assertTrue(allowed(r, "registry.npmjs.org.", 443))
        self.assertTrue(allowed(rules("none"), "API.anthropic.com.", 443))

    def test_nothing_is_decrypted_yet(self):
        for mode in ("none", "limited", "full"):
            self.assertFalse(decrypts(rules(mode), "api.anthropic.com", 443))
            self.assertFalse(decrypts(rules(mode), "registry.npmjs.org", 443))


class Rules(unittest.TestCase):
    def test_valid_rules(self):
        self.assertEqual(parse_rules(json.dumps(rules("none")))["mode"], "none")

    def test_refuses_what_is_not_rules(self):
        bad = [
            "not json",
            json.dumps([]),
            json.dumps({"mode": "open", "allow": [], "always": []}),
            json.dumps({"mode": "full", "allow": []}),
            json.dumps({"mode": "full", "allow": [], "always": [], "extra": 1}),
            json.dumps({"mode": "limited", "allow": "example.com", "always": []}),
            json.dumps({"mode": "limited", "allow": [3], "always": []}),
            json.dumps({"mode": "limited", "allow": [""], "always": []}),
        ]
        for text in bad:
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    parse_rules(text)


class Addon(unittest.TestCase):
    """The addon as mitmproxy drives it, with stand-ins for its flows."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.dir.name, "rules.json")
        self.write(rules("none"))
        self.addon = nucarium_proxy.NucariumProxy(self.path)
        fake = SimpleNamespace(http=SimpleNamespace(Response=FakeResponse))
        patcher = mock.patch.dict(sys.modules, {"mitmproxy": fake})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.logged = []
        quiet = mock.patch.object(nucarium_proxy, "log", self.logged.append)
        quiet.start()
        self.addCleanup(quiet.stop)

    def tearDown(self):
        self.dir.cleanup()

    def write(self, r):
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(r, f)
        os.replace(tmp, self.path)

    def connect(self, host, port=443):
        flow = SimpleNamespace(request=SimpleNamespace(host=host, port=port, scheme="http"), response=None)
        self.addon.http_connect(flow)
        return flow.response

    def test_refusal_is_403_naming_the_host(self):
        response = self.connect("example.com")
        self.assertEqual(response.status_code, 403)
        self.assertIn("example.com", response.body)
        self.assertIsNone(self.connect("api.anthropic.com"))

    def test_plain_http_is_decided_too(self):
        flow = SimpleNamespace(request=SimpleNamespace(host="example.com", port=80, scheme="http"), response=None)
        self.addon.requestheaders(flow)
        self.assertEqual(flow.response.status_code, 403)

    def test_changed_rules_apply_to_the_next_request(self):
        self.assertEqual(self.connect("example.com").status_code, 403)
        time.sleep(0.01)
        self.write(rules("full"))
        self.assertIsNone(self.connect("example.com"))

    def test_unreadable_rules_keep_the_last_good_ones(self):
        self.assertIsNone(self.connect("api.anthropic.com"))
        with open(self.path, "w") as f:
            f.write("{broken")
        self.assertEqual(self.connect("example.com").status_code, 403)
        self.assertIsNone(self.connect("api.anthropic.com"))
        # Said once, not at every request.
        self.assertEqual(len([line for line in self.logged if "cannot read" in line]), 1)

    def test_decisions_are_logged_by_host_only(self):
        self.connect("example.com")
        self.connect("api.anthropic.com")
        self.assertIn("refused CONNECT example.com:443", self.logged)
        self.assertIn("allowed CONNECT api.anthropic.com:443", self.logged)

    def test_no_rules_at_all_refuses_everything(self):
        addon = nucarium_proxy.NucariumProxy(os.path.join(self.dir.name, "missing.json"))
        flow = SimpleNamespace(request=SimpleNamespace(host="api.anthropic.com", port=443), response=None)
        addon.http_connect(flow)
        self.assertEqual(flow.response.status_code, 403)

    def test_allowed_tls_is_passed_through(self):
        data = SimpleNamespace(context=SimpleNamespace(server=SimpleNamespace(address=("api.anthropic.com", 443))), ignore_connection=False)
        self.addon.tls_clienthello(data)
        self.assertTrue(data.ignore_connection)


class FakeResponse:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self.body = body

    @classmethod
    def make(cls, status_code, body, headers):
        return cls(status_code, body)


if __name__ == "__main__":
    unittest.main()
