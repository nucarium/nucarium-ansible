"""What the environment proxy allows, from its rules and the box's own
addresses (the env_runtime role's files/proxy/nucarium_proxy.py). Runs
without mitmproxy: the decision is a plain function of the rules, the box's
addresses, the host and the port, and a name's addresses come from a
stand-in resolver.

    python3 -m unittest discover -s tests
"""
import asyncio
import ipaddress
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
from nucarium_proxy import allowed, decrypts, gateways, is_box, parse_box, parse_rules  # noqa: E402

ALWAYS = ["api.anthropic.com", "claude.ai", "*.frame.claudeusercontent.com"]
ALLOW = ["registry.npmjs.org", "*.example.com", "git.example.org:8443", "10.1.2.3", "[2001:db8::1]:443"]


def rules(mode, allow=ALLOW):
    return {"mode": mode, "allow": allow, "always": ALWAYS}


# The box: a LAN address, a tailnet address and its IPv6 one, as the recipe
# writes them from the box's facts.
LAN = "192.168.1.20"
TAILNET = "100.101.102.103"
TAILNET6 = "fd7a:115c:a1e0::1234"
BOX = {"addresses": [LAN, TAILNET, TAILNET6, "fe80::5054:ff:fe12:3456"]}
# The proxy's routing tables, as /proc/net/route and /proc/net/ipv6_route
# print them: a default route through the egress network's gateway,
# 10.89.1.1, and an IPv6 one through fd00:89:1::1.
ROUTE = """Iface\tDestination\tGateway \tFlags\tRefCnt\tUse\tMetric\tMask\t\tMTU\tWindow\tIRTT
eth1\t00000000\t0101590A\t0003\t0\t0\t0\t00000000\t0\t0\t0
eth1\t0001590A\t00000000\t0001\t0\t0\t0\t00FFFFFF\t0\t0\t0
nucarium0\t0000590A\t00000000\t0001\t0\t0\t0\t00FFFFFF\t0\t0\t0
"""
ROUTE6 = """00000000000000000000000000000000 00 00000000000000000000000000000000 00 fd000089000100000000000000000001 00000400 00000001 00000000 00000003     eth1
fd000089000100000000000000000000 40 00000000000000000000000000000000 00 00000000000000000000000000000000 00000100 00000001 00000000 00000001     eth1
"""
GATEWAY = "10.89.1.1"
GATEWAY6 = "fd00:89:1::1"
# Every kind of address of the box, as a host would name it.
BOX_HOSTS = [
    LAN, TAILNET, "[" + TAILNET6 + "]", GATEWAY, "[" + GATEWAY6 + "]",
    "127.0.0.1", "127.8.9.10", "[::1]", "0.0.0.0", "[::]",
    "169.254.169.254", "169.254.1.2", "[fe80::1]", "[fe80::5054:ff:fe12:3456]",
    "100.100.100.100", "[fd7a:115c:a1e0::53]", "[::ffff:" + TAILNET + "]",
]
PUBLIC = "198.51.100.7"


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


class Box(unittest.TestCase):
    """What counts as the box's own address."""

    def networks(self):
        return nucarium_proxy.box_networks(parse_box(json.dumps(BOX)), [ipaddress.ip_address(GATEWAY), ipaddress.ip_address(GATEWAY6)])

    def test_every_kind_of_box_address(self):
        box = self.networks()
        for host in BOX_HOSTS:
            with self.subTest(host=host):
                self.assertTrue(is_box(box, nucarium_proxy.address(host)))

    def test_other_addresses_are_not_the_box(self):
        box = self.networks()
        for host in (PUBLIC, "100.101.102.104", "192.168.1.21", "10.89.2.1", "[2001:db8::1]", "8.8.8.8"):
            with self.subTest(host=host):
                self.assertFalse(is_box(box, nucarium_proxy.address(host)))

    def test_gateways_from_the_routing_tables(self):
        with tempfile.TemporaryDirectory() as d:
            v4, v6 = os.path.join(d, "route"), os.path.join(d, "ipv6_route")
            pathlib.Path(v4).write_text(ROUTE)
            pathlib.Path(v6).write_text(ROUTE6)
            self.assertEqual([str(g) for g in gateways((v4, v6))], [GATEWAY, GATEWAY6])
            # A box with no IPv6 has no IPv6 table.
            os.remove(v6)
            self.assertEqual([str(g) for g in gateways((v4, v6))], [GATEWAY])
            # With no IPv4 table there is no knowing the gateways.
            os.remove(v4)
            with self.assertRaises(OSError):
                gateways((v4, v6))

    def test_refuses_what_is_not_a_box_file(self):
        bad = [
            "not json",
            json.dumps([LAN]),
            json.dumps({"addresses": LAN}),
            json.dumps({"addresses": ["box.example.com"]}),
            json.dumps({"addresses": [LAN, 7]}),
            json.dumps({"addresses": [LAN], "extra": 1}),
            json.dumps({"addresses": [LAN] * (nucarium_proxy.BOX_MAX + 1)}),
        ]
        for text in bad:
            with self.subTest(text=text[:60]):
                with self.assertRaises(ValueError):
                    parse_box(text)


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


class AddonCase(unittest.TestCase):
    """The addon as mitmproxy drives it, with stand-ins for its flows."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.dir.name, "rules.json")
        self.box_path = os.path.join(self.dir.name, "box.json")
        routes = (os.path.join(self.dir.name, "route"), os.path.join(self.dir.name, "ipv6_route"))
        pathlib.Path(routes[0]).write_text(ROUTE)
        pathlib.Path(routes[1]).write_text(ROUTE6)
        self.write(rules("none"))
        self.write(BOX, self.box_path)
        # The stand-in resolver: each name's answers, one per lookup, the
        # last one again once they run out.
        self.answers = {"api.anthropic.com": [[PUBLIC]], "registry.npmjs.org": [[PUBLIC]], "example.org": [[PUBLIC]]}
        self.lookups = []
        self.addon = nucarium_proxy.NucariumProxy(self.path, self.box_path, routes, self.resolve)
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

    def write(self, r, path=None):
        path = path or self.path
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(r, f)
        os.replace(tmp, path)
        # A new stamp even within the clock's resolution.
        time.sleep(0.01)

    async def resolve(self, host, port):
        self.lookups.append(host)
        answers = self.answers.get(host)
        if not answers:
            raise OSError(f"{host} does not resolve")
        return answers.pop(0) if len(answers) > 1 else answers[0]

    def connect(self, host, port=443):
        flow = SimpleNamespace(request=SimpleNamespace(host=host, port=port, scheme="http"), response=None)
        self.addon.http_connect(flow)
        return flow.response

    def server(self, host, port=443):
        """The connection the proxy is about to make, after server_connect:
        where it goes, and why it does not, if it does not."""
        server = SimpleNamespace(address=(host, port), error=None)
        asyncio.run(self.addon.server_connect(SimpleNamespace(server=server, client=None)))
        return server

    def through(self, host, port=443):
        """The whole way: the CONNECT, then the connection if it was allowed.
        The server's address and error, or the refusal's status."""
        response = self.connect(host, port)
        if response is not None:
            return response.status_code
        server = self.server(host, port)
        return server.error or server.address


class Addon(AddonCase):
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


class BoxRefusals(AddonCase):
    """No mode reaches the box: by address, by a name that resolves to it,
    or by a name that resolves to it the second time it is asked."""

    def test_box_addresses_are_refused_in_every_mode(self):
        box_hosts = [h.strip("[]") for h in BOX_HOSTS]
        for mode in ("none", "limited", "full"):
            # limited allows every one of them by its list: refused anyway.
            self.write(rules(mode, allow=box_hosts))
            for host in BOX_HOSTS:
                with self.subTest(mode=mode, host=host):
                    response = self.connect(host, 21003)
                    self.assertEqual(response.status_code, 403)
                    self.assertIn(host, response.body)
                    # And at the connect step too, should a request get there.
                    self.assertIn("this box", self.server(host, 21003).error)
        self.assertEqual(self.lookups, [])

    def test_a_name_that_resolves_to_the_box_is_refused_in_every_mode(self):
        for mode in ("none", "limited", "full"):
            self.write(rules(mode, allow=["box.example.com"]))
            for ip in (TAILNET, LAN, GATEWAY, "127.0.0.1", "169.254.169.254", "100.100.100.100", "::1", TAILNET6):
                self.answers["box.example.com"] = [[ip]]
                # Claude Code's own host, allowed in every mode.
                self.answers["api.anthropic.com"] = [[ip]]
                for host in ("api.anthropic.com", "box.example.com"):
                    if mode == "none" and host == "box.example.com":
                        continue
                    with self.subTest(mode=mode, host=host, ip=ip):
                        self.assertIsNone(self.connect(host))
                        server = self.server(host)
                        self.assertIn("this box", server.error)
                        self.assertIn(host, server.error)

    def test_a_name_with_any_box_address_is_refused(self):
        self.write(rules("full"))
        self.answers["mixed.example.com"] = [[PUBLIC, TAILNET]]
        self.assertIn("this box", self.through("mixed.example.com"))

    def test_rebinding_never_reaches_the_box(self):
        # Public at the first lookup, the box's tailnet address after it.
        self.write(rules("full"))
        self.answers["rebind.example.com"] = [[PUBLIC], [TAILNET]]
        self.assertEqual(self.through("rebind.example.com", 21003), (PUBLIC, 21003))
        # One lookup, and its answer is where the connection goes.
        self.assertEqual(self.lookups, ["rebind.example.com"])
        # The next connection asks again, gets the box, and is refused.
        self.assertIn("this box", self.through("rebind.example.com", 21003))
        self.assertEqual(self.lookups, ["rebind.example.com"] * 2)

    def test_allowed_hosts_still_pass(self):
        for mode, host in (("none", "api.anthropic.com"), ("limited", "api.anthropic.com"),
                           ("limited", "registry.npmjs.org"), ("full", "example.org")):
            self.write(rules(mode))
            with self.subTest(mode=mode, host=host):
                self.assertEqual(self.through(host), (PUBLIC, 443))
        # An allowed address is connected to as it is, with no lookup.
        self.write(rules("limited"))
        self.lookups.clear()
        self.assertEqual(self.through("10.1.2.3", 22), ("10.1.2.3", 22))
        self.write(rules("full"))
        self.assertEqual(self.through("[2001:db8::1]"), ("2001:db8::1", 443))
        self.assertEqual(self.lookups, [])

    def test_a_name_that_does_not_resolve_is_refused(self):
        self.write(rules("full"))
        self.assertIn("Refused", self.server("nowhere.example.com").error)

    def test_a_new_box_address_applies_to_the_next_request(self):
        self.write(rules("full"))
        self.assertIsNone(self.connect(PUBLIC))
        self.write({"addresses": BOX["addresses"] + [PUBLIC]}, self.box_path)
        self.assertEqual(self.connect(PUBLIC).status_code, 403)
        self.assertIn("this box", self.server("api.anthropic.com").error)

    def test_no_box_file_refuses_everything(self):
        self.write(rules("full"))
        for broken in ("{broken", None):
            # Read and in force first: what was good before is not kept.
            self.write(BOX, self.box_path)
            self.assertEqual(self.through("api.anthropic.com"), (PUBLIC, 443))
            if broken is None:
                os.remove(self.box_path)
            else:
                with open(self.box_path, "w") as f:
                    f.write(broken)
            with self.subTest(broken=broken):
                self.assertEqual(self.connect("api.anthropic.com").status_code, 403)
                self.assertIsNotNone(self.server("api.anthropic.com").error)
        # Back again, the next request is decided as before.
        self.write(BOX, self.box_path)
        self.assertEqual(self.through("api.anthropic.com"), (PUBLIC, 443))

    def test_no_routing_table_refuses_everything(self):
        os.remove(self.addon.routes[0])
        self.addon.box_stamp = ()
        self.assertEqual(self.connect("api.anthropic.com").status_code, 403)
        self.assertIsNotNone(self.server("api.anthropic.com").error)


class FakeResponse:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self.body = body

    @classmethod
    def make(cls, status_code, body, headers):
        return cls(status_code, body)


if __name__ == "__main__":
    unittest.main()
