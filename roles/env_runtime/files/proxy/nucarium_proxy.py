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

Whatever the mode, the proxy never connects to the box itself: an address
on any of the box's interfaces (its tailnet and LAN addresses), a gateway,
loopback, link-local (169.254.0.0/16, which holds the cloud metadata
address, and fe80::/10), the unspecified address and Tailscale's own
resolver. A host named by address is refused when it asks; a name is
looked up once, as the proxy connects, refused when any address it has is
one of those, and otherwise connected to at the first address that lookup
gave, so that a second answer to the same name never decides where the
connection goes. The box's addresses are in a second file the recipe
writes, box.json, {"addresses": [...]}; the gateways the proxy reads from
its own routing table. That file is read again when it changes too, and
while it cannot be read the proxy refuses everything.

Allowed TLS is passed through unread: the proxy holds no certificate a
session trusts, and Claude Code's streams are never decrypted or buffered.

One line per decision goes to standard error: allowed or refused, the kind
of request and the host and port. Never a path, a header or a body.

The rules file is read again when it changes, so a new allow list applies
to the next request without restarting the proxy (which would cut every
open connection). A rules file that cannot be read keeps the last good
rules in force; at start, the launcher refuses to start without them.
"""

import asyncio
import ipaddress
import json
import os
import socket
import sys

MODES = ("none", "limited", "full")
RULES_FILE = os.environ.get("NUCARIUM_PROXY_RULES", "/etc/nucarium-proxy/rules.json")
BOX_FILE = os.environ.get("NUCARIUM_PROXY_BOX", "/etc/nucarium-proxy/box.json")
ROUTES = ("/proc/net/route", "/proc/net/ipv6_route")

# Never reached, whatever the box's interfaces are: loopback, the
# unspecified address (which reaches loopback), link-local, and Tailscale's
# resolver (100.100.100.100 and its IPv6 address).
NEVER = tuple(
    ipaddress.ip_network(net)
    for net in (
        "127.0.0.0/8",
        "::1/128",
        "0.0.0.0/8",
        "::/128",
        "169.254.0.0/16",
        "fe80::/10",
        "100.100.100.100/32",
        "fd7a:115c:a1e0::53/128",
    )
)
# The most addresses box.json may list.
BOX_MAX = 4096
# How long a name may take to look up before the connection is refused.
LOOKUP_SECONDS = 10


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


def address(host):
    """host as an IP address, or None when it is a name."""
    host = normal_host(host).partition("%")[0]
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        return None


def is_box(box, ip):
    """Whether ip is one of the box's own addresses. box is a list of
    networks, from box_networks()."""
    candidates = [ip]
    if ip.version == 6 and ip.ipv4_mapped is not None:
        candidates.append(ip.ipv4_mapped)
    return any(c in net for c in candidates for net in box if c.version == net.version)


def parse_box(text):
    """The box's addresses from box.json's text; ValueError when it is not."""
    box = json.loads(text)
    if not isinstance(box, dict) or set(box) != {"addresses"}:
        raise ValueError("the box file must have exactly the key addresses")
    entries = box["addresses"]
    if not isinstance(entries, list) or len(entries) > BOX_MAX or not all(isinstance(e, str) for e in entries):
        raise ValueError(f"addresses must be a list of at most {BOX_MAX} addresses")
    out = []
    for entry in entries:
        ip = address(entry)
        if ip is None:
            raise ValueError(f"not an address: {entry!r}")
        out.append(ip)
    return out


def gateways(paths=ROUTES):
    """Every gateway in the proxy's own routing tables, IPv4 and IPv6: the
    egress network's among them. OSError when the IPv4 table cannot be read;
    a box without IPv6 has no IPv6 table."""
    found = []
    v4, v6 = paths
    with open(v4, encoding="ascii") as f:
        for line in f.read().splitlines()[1:]:
            fields = line.split()
            if len(fields) > 2 and fields[2] != "00000000":
                found.append(ipaddress.IPv4Address(bytes.fromhex(fields[2])[::-1]))
    try:
        with open(v6, encoding="ascii") as f:
            for line in f.read().splitlines():
                fields = line.split()
                if len(fields) > 4 and fields[4].strip("0"):
                    found.append(ipaddress.IPv6Address(bytes.fromhex(fields[4])))
    except FileNotFoundError:
        pass
    return found


def box_networks(addresses, routes):
    """Everything the proxy never connects to: the fixed list, the box's
    addresses and the gateways."""
    return list(NEVER) + [ipaddress.ip_network(ip) for ip in addresses + routes]


async def look_up(host, port):
    """Every address host has, in the order the resolver gave them."""
    infos = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return [info[4][0] for info in infos]


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


def stamp_of(path):
    try:
        st = os.stat(path)
        return (st.st_ino, st.st_mtime_ns, st.st_size)
    except OSError:
        return None


class NucariumProxy:
    def __init__(self, path=RULES_FILE, box_path=BOX_FILE, routes=ROUTES, resolve=look_up):
        self.path = path
        self.rules = None
        self.stamp = ()
        self.box_path = box_path
        self.routes = routes
        self.resolve = resolve
        self.box = None
        self.box_stamp = ()

    def current_rules(self):
        """The rules in force, read again when the file has changed."""
        stamp = stamp_of(self.path)
        if stamp != self.stamp:
            # Once per change of the file, read or not.
            self.stamp = stamp
            try:
                self.rules = load_rules(self.path)
                log(f"rules: mode {self.rules['mode']}, {len(self.rules['allow'])} allowed, {len(self.rules['always'])} always")
            except (OSError, ValueError) as e:
                log(f"rules: cannot read {self.path}, keeping the rules in force: {e}")
        return self.rules

    def current_box(self):
        """What the proxy never connects to, None while the box file cannot
        be read: then every connection is refused, never allowed."""
        stamp = stamp_of(self.box_path)
        if stamp != self.box_stamp:
            self.box_stamp = stamp
            try:
                with open(self.box_path, encoding="utf-8") as f:
                    addresses = parse_box(f.read())
                self.box = box_networks(addresses, gateways(self.routes))
                log(f"box: {len(addresses)} addresses of this box")
            except (OSError, ValueError) as e:
                self.box = None
                log(f"box: cannot read {self.box_path}, refusing everything until it can: {e}")
        return self.box

    def decide(self, flow, kind):
        host, port = flow.request.host, flow.request.port
        rules = self.current_rules()
        box = self.current_box()
        # No rules at all (never read), or no box file: refuse everything.
        # An error here refuses too: mitmproxy would log it and let the
        # request through. A host named by address is refused here when it
        # is the box's; a name is looked up as the proxy connects.
        try:
            ip = address(host)
            ok = rules is not None and box is not None and not (ip is not None and is_box(box, ip)) and allowed(rules, host, port)
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

    async def pin(self, server):
        """Look the server's host up once and connect to the address that
        gave, unless any of its addresses is the box's. Every connection the
        proxy makes passes here, after its request was allowed."""
        host, port = server.address[0], server.address[1]
        try:
            box = self.current_box()
            if box is None:
                raise ValueError("no box file")
            ip = address(host)
            if ip is not None:
                found = [ip]
            else:
                found = [address(a) for a in await asyncio.wait_for(self.resolve(host, port), LOOKUP_SECONDS)]
                if not found or None in found:
                    raise ValueError("no address")
            mine = [str(a) for a in found if is_box(box, a)]
            if mine:
                log(f"refused connect {host}:{port}: {mine[0]} is this box")
                server.error = f"Refused by this environment's network settings: {host} is this box"
                return
            server.address = (str(found[0]), port)
        except Exception as e:
            log(f"refused connect {host}:{port}: {e!r}")
            server.error = f"Refused by this environment's network settings: {host}"

    # mitmproxy's hooks.

    def load(self, loader):
        self.current_rules()
        self.current_box()

    def http_connect(self, flow):
        self.decide(flow, "CONNECT")

    def requestheaders(self, flow):
        # Plain HTTP sent to the proxy, and HTTP inside an allowed tunnel
        # (whose host is the tunnel's, so the answer is the same).
        self.decide(flow, flow.request.scheme)

    async def server_connect(self, data):
        await self.pin(data.server)

    def tls_clienthello(self, data):
        address = data.context.server.address
        rules = self.current_rules()
        data.ignore_connection = not (
            address is not None and rules is not None and decrypts(rules, *address[:2])
        )


addons = [NucariumProxy()]
