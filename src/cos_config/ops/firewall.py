"""Open or close things in firewalld, for the zone the user is in.

Runs firewall-cmd as root so one password covers the runtime and the
permanent change. What may be touched is fixed here: a short list of
firewalld's own service definitions, single ports, and the one "all high
ports" range that Fedora Workstation opens by default.
"""

import re
import subprocess

from . import common

# firewalld service names the UI offers (their port lists are firewalld's).
SERVICES = ("ssh", "samba", "ipp", "http", "https", "mdns", "kdeconnect",
            "syncthing", "steam-streaming", "minecraft", "rdp", "vnc-server")
HIGH_RANGE = "1025-65535"
PROTOCOLS = ("tcp", "udp")
_ZONE_RE = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
_PORT_RE = re.compile(r"^(\d{1,5})/(tcp|udp)$")


def validate_port(spec):
    """'8080/tcp' (1-65535) or the high range '1025-65535/tcp|udp'."""
    for proto in PROTOCOLS:
        if spec == f"{HIGH_RANGE}/{proto}":
            return spec
    match = _PORT_RE.match(spec or "")
    if not match or not 1 <= int(match.group(1)) <= 65535:
        raise common.ValidationError("port must be like 8080/tcp (1-65535, tcp or udp)")
    return f"{int(match.group(1))}/{match.group(2)}"


def validate_service(name):
    if name not in SERVICES:
        raise common.ValidationError(f"service must be one of {', '.join(SERVICES)}")
    return name


def commands(kind, action, zone, value):
    """The runtime and the permanent firewall-cmd argv for one change."""
    if action not in ("add", "remove"):
        raise common.ValidationError("action must be add or remove")
    if not _ZONE_RE.match(zone or ""):
        raise common.ValidationError("bad zone name")
    if kind == "service":
        option = f"--{action}-service={validate_service(value)}"
    elif kind == "port":
        option = f"--{action}-port={validate_port(value)}"
    else:
        raise common.ValidationError("kind must be service or port")
    base = ["firewall-cmd", f"--zone={zone}", option]
    return [base, base + ["--permanent"]]


def describe(changes, zone):
    """Equivalent commands for [(kind, action, value)]."""
    lines = []
    for kind, action, value in changes:
        lines += ["sudo " + " ".join(cmd) for cmd in commands(kind, action, zone, value)]
    return lines


def known_zones():
    out = subprocess.run(["firewall-cmd", "--get-zones"], capture_output=True, text=True).stdout
    return out.split()


def helper_main(argv):
    """argv: ZONE then one or more KIND:ACTION:VALUE, e.g. service:add:ssh."""
    if len(argv) < 2:
        raise common.ValidationError("usage: ZONE KIND:ACTION:VALUE...")
    zone, specs = argv[0], argv[1:]
    todo = []
    for spec in specs:
        parts = spec.split(":", 2)
        if len(parts) != 3:
            raise common.ValidationError(f"bad change {spec!r}")
        todo += commands(parts[0], parts[1], zone, parts[2])
    if zone not in known_zones():
        raise common.ValidationError(f"no such zone {zone!r}")
    for cmd in todo:
        common.run_cmd(cmd)
