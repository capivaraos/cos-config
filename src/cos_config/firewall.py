"""Read the firewall (firewalld) in terms a person can follow.

Fedora Workstation's default zone opens every port above 1024, so most
"open a port for this app" requests are already satisfied there; what the
page adds is showing that plainly, the low ports that are closed (file
sharing, SSH, web, printers), and a strict mode that closes the high range.
"""

import re
import subprocess

from .ops import firewall as rootops

HIGH_RANGE = rootops.HIGH_RANGE

# (id, firewalld services, needs a low port?) in display order.
PRESETS = (
    ("samba", ("samba",), True),
    ("ssh", ("ssh",), True),
    ("web", ("http", "https"), True),
    ("ipp", ("ipp",), True),
    ("kdeconnect", ("kdeconnect",), False),
    ("syncthing", ("syncthing",), False),
    ("steam", ("steam-streaming",), False),
    ("minecraft", ("minecraft",), False),
    ("remote-desktop", ("rdp", "vnc-server"), False),
)


def parse_list_all(text):
    """{"zone", "services", "ports"} from `firewall-cmd --list-all`."""
    info = {"zone": "", "services": set(), "ports": set()}
    lines = text.splitlines()
    if lines:
        info["zone"] = lines[0].split()[0] if lines[0].split() else ""
    for line in lines[1:]:
        key, sep, value = line.strip().partition(":")
        if sep and key in ("services", "ports"):
            info[key] = set(value.split())
    return info


def high_ports_open(ports):
    return {f"{HIGH_RANGE}/tcp", f"{HIGH_RANGE}/udp"} <= set(ports)


def custom_ports(ports):
    """Single ports the user added (the high range is shown on its own)."""
    def key(spec):
        number, _, proto = spec.partition("/")
        return (int(number) if number.isdigit() else 0, proto)
    return sorted((p for p in ports if not p.startswith(HIGH_RANGE + "/")), key=key)


def preset_state(preset, info):
    """"on" (allowed by name), "open" (reachable only because the high
    ports are open) or "off"."""
    _pid, services, low = preset
    if all(s in info["services"] for s in services):
        return "on"
    if not low and high_ports_open(info["ports"]):
        return "open"
    return "off"


def preset_changes(preset, enable):
    action = "add" if enable else "remove"
    return [("service", action, s) for s in preset[1]]


def strict_changes(enable):
    """Strict mode on = close the high range; off = open it again."""
    action = "remove" if enable else "add"
    return [("port", action, f"{HIGH_RANGE}/{proto}") for proto in rootops.PROTOCOLS]


def helper_args(zone, changes):
    return [zone, *(f"{kind}:{action}:{value}" for kind, action, value in changes)]


# ---- reading the machine -------------------------------------------------------
def _out(argv):
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def running():
    return _out(["firewall-cmd", "--state"]).strip() == "running"


def default_route_interface(route_text=None):
    text = route_text if route_text is not None else _out(["ip", "-4", "route", "show", "default"])
    match = re.search(r"\bdev\s+(\S+)", text)
    return match.group(1) if match else None


def current_zone():
    """The zone of the interface the computer reaches the network through."""
    iface = default_route_interface()
    zone = _out(["firewall-cmd", f"--get-zone-of-interface={iface}"]).strip() if iface else ""
    if not zone or " " in zone:
        zone = _out(["firewall-cmd", "--get-default-zone"]).strip()
    return zone


def read():
    """State of the current zone, or None when firewalld is not running."""
    if not running():
        return None
    zone = current_zone()
    info = parse_list_all(_out(["firewall-cmd", f"--zone={zone}", "--list-all"]))
    info["zone"] = zone
    return info
