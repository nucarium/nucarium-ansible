"""The network proxy of one container environment, as a mitmproxy addon.

A container environment's sessions have no route out: their network is
internal. Their one way out is this proxy, which sits on that network and
on an egress network of its own. For each CONNECT and each plain HTTP
request it decides from the environment's rules whether the host may be
reached, and refuses the rest with a 403 whose body names the host.

The rules are a JSON file the recipe writes:

    {"mode": "none" | "limited" | "full",
     "allow": the hosts limited reaches,
     "always": Claude Code's own hosts, reached in every mode}

An entry is a host ("example.com"), a wildcard ("*.example.com": every
subdomain, not example.com itself) or an address, each optionally with a
port ("example.com:8443"). An entry without a port matches every port.

Allowed TLS is passed through unread: the proxy holds no certificate a
session trusts, and Claude Code's streams are never decrypted or buffered.

One line per decision goes to standard error: allowed or refused, the kind
of request and the host and port. Never a path, a header or a body.

The rules file is read again when it changes, so a new allow list applies
to the next request without restarting the proxy (which would cut every
open connection). A rules file that cannot be read keeps the last good
rules in force; at start, the launcher refuses to start without them.
"""

import json
import os
import sys

MODES = ("none", "limited", "full")
RULES_FILE = os.environ.get("NUCARIUM_PROXY_RULES", "/etc/nucarium-proxy/rules.json")


def split_entry(entry):
    """An allow-list entry as (host, port), port None when it has none."""
    entry = entry.strip().lower()
    if entry.startswith("["):
        # [2001:db8::1] or [2001:db8::1]:443
        host, _, rest = entry[1:].partition("]")
        port = rest[1:] if rest.startswith(":") else ""
    elif entry.count(":") == 1:
        host, _, port = entry.partition(":")
    else:
        # A name, or an IPv6 address without brackets (and so without a port).
        host, port = entry, ""
    return host.rstrip("."), (int(port) if port.isdigit() else None)


def normal_host(host):
    """A request's host as entries are compared with it."""
    host = host.strip().lower()
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]
    return host.rstrip(".")


def matches(entry, host, port):
    """Whether one entry covers host:port. host is already normal_host()."""
    want_host, want_port = split_entry(entry)
    if want_port is not None and want_port != port:
        return False
    if want_host.startswith("*."):
        return host.endswith(want_host[1:]) and len(host) > len(want_host) - 1
    return host == want_host


def allowed(rules, host, port):
    """Whether the environment may reach host:port. The proxy's one decision."""
    if rules["mode"] == "full":
        return True
    host = normal_host(host)
    if any(matches(entry, host, port) for entry in rules["always"]):
        return True
    return rules["mode"] == "limited" and any(
        matches(entry, host, port) for entry in rules["allow"]
    )


def decrypts(rules, host, port):
    """Whether to open the TLS to host:port rather than pass it through.

    Never, for now. The place where a host that has a network secret will
    be decrypted, to add its header, and only such a host; every other
    allowed connection stays passed through.
    """
    return False


def parse_rules(text):
    """The rules from the file's text; ValueError when they are not rules."""
    rules = json.loads(text)
    if not isinstance(rules, dict) or set(rules) != {"mode", "allow", "always"}:
        raise ValueError("rules must have exactly the keys mode, allow and always")
    if rules["mode"] not in MODES:
        raise ValueError(f"mode must be one of {', '.join(MODES)}")
    for key in ("allow", "always"):
        if not isinstance(rules[key], list) or not all(
            isinstance(entry, str) and entry.strip() for entry in rules[key]
        ):
            raise ValueError(f"{key} must be a list of hosts")
    return rules


def load_rules(path):
    with open(path, encoding="utf-8") as f:
        return parse_rules(f.read())


def log(line):
    print(f"nucarium-proxy: {line}", file=sys.stderr, flush=True)


class NucariumProxy:
    def __init__(self, path=RULES_FILE):
        self.path = path
        self.rules = None
        self.stamp = ()

    def current_rules(self):
        """The rules in force, read again when the file has changed."""
        try:
            st = os.stat(self.path)
            stamp = (st.st_ino, st.st_mtime_ns, st.st_size)
        except OSError:
            stamp = None
        if stamp != self.stamp:
            # Once per change of the file, read or not.
            self.stamp = stamp
            try:
                self.rules = load_rules(self.path)
                log(f"rules: mode {self.rules['mode']}, {len(self.rules['allow'])} allowed, {len(self.rules['always'])} always")
            except (OSError, ValueError) as e:
                log(f"rules: cannot read {self.path}, keeping the rules in force: {e}")
        return self.rules

    def decide(self, flow, kind):
        host, port = flow.request.host, flow.request.port
        rules = self.current_rules()
        # No rules at all (never read): refuse everything. An error here
        # refuses too: mitmproxy would log it and let the request through.
        try:
            ok = rules is not None and allowed(rules, host, port)
        except Exception as e:
            log(f"error deciding on {host}:{port}: {e!r}")
            ok = False
        log(f"{'allowed' if ok else 'refused'} {kind} {host}:{port}")
        if not ok:
            from mitmproxy import http

            flow.response = http.Response.make(
                403,
                f"Refused by this environment's network settings: {host}\n",
                {"Content-Type": "text/plain; charset=utf-8"},
            )

    # mitmproxy's hooks.

    def load(self, loader):
        self.current_rules()

    def http_connect(self, flow):
        self.decide(flow, "CONNECT")

    def requestheaders(self, flow):
        # Plain HTTP sent to the proxy, and HTTP inside an allowed tunnel
        # (whose host is the tunnel's, so the answer is the same).
        self.decide(flow, flow.request.scheme)

    def tls_clienthello(self, data):
        address = data.context.server.address
        rules = self.current_rules()
        data.ignore_connection = not (
            address is not None and rules is not None and decrypts(rules, *address[:2])
        )


addons = [NucariumProxy()]
