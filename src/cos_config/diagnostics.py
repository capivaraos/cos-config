"""One-click diagnosis: quick health checks and a report to paste when asking
for help.

Everything is read as the user (no root). The report is built from fields
chosen here — the host name and network addresses are never collected — and
free text that comes from logs goes through redact(), which removes the user
name, home paths, IP and MAC addresses and long identifiers.
"""

import getpass
import os
import re
import subprocess

from . import sysinfo

OK, INFO, WARN, BAD = "ok", "info", "warn", "bad"
DISK_WARN, DISK_BAD = 85, 95
MAX_LOG_LINES = 20

_IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}(?:/\d{1,2})?\b")
_MAC = re.compile(r"\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b")
# Either the "::" short form or at least five groups, so clock times
# (08:42:03) and PCI addresses (0000:00:02.0) are left alone.
_IPV6 = re.compile(
    r"(?<![0-9A-Fa-f:])(?:"
    r"(?:[0-9A-Fa-f]{1,4}:){1,6}:(?:[0-9A-Fa-f]{1,4}:){0,5}[0-9A-Fa-f]{0,4}"
    r"|(?:[0-9A-Fa-f]{1,4}:){4,7}[0-9A-Fa-f]{1,4}"
    r")(?:/\d{1,3})?")
_UUID = re.compile(r"\b[0-9A-Fa-f]{8}-(?:[0-9A-Fa-f]{4}-){3}[0-9A-Fa-f]{12}\b")
_LONG_HEX = re.compile(r"\b[0-9A-Fa-f]{24,}\b")


def redact(text, user=None, home=None):
    """Remove what identifies the person or the network from *text*."""
    user = user if user is not None else getpass.getuser()
    home = home if home is not None else os.path.expanduser("~")
    if home and home != "/":
        text = text.replace(home, "/home/USER")
    if user:
        text = re.sub(rf"(?<![A-Za-z0-9_.-]){re.escape(user)}(?![A-Za-z0-9_.-])", "USER", text)
    text = _MAC.sub("MAC", text)
    text = _UUID.sub("UUID", text)
    text = _IPV6.sub("IPV6", text)
    text = _IPV4.sub("IP", text)
    return _LONG_HEX.sub("ID", text)


# ---- parsing (pure) -------------------------------------------------------------
def parse_df(text):
    """[(mount, used %, available bytes)] from `df -P -B1`, one per device."""
    rows, seen = [], set()
    for line in text.splitlines()[1:]:
        cols = line.split()
        if len(cols) < 6 or not cols[4].endswith("%"):
            continue
        device, mount = cols[0], " ".join(cols[5:])
        if device in seen:  # btrfs subvolumes: same disk, report it once
            continue
        seen.add(device)
        rows.append((mount, int(cols[4].rstrip("%")), int(cols[3])))
    return rows


def parse_failed_units(text):
    """Unit names from `systemctl --failed --no-legend --plain`."""
    units = []
    for line in text.splitlines():
        cols = line.split()
        if cols and "." in cols[0]:
            units.append(cols[0])
    return units


def parse_gpus(text):
    """[(name, driver or None)] from `lspci -k`."""
    gpus, current = [], None
    for line in text.splitlines():
        if line and not line[0].isspace():
            current = None
            match = re.match(r"^\S+\s+(VGA compatible controller|3D controller|Display controller):\s+(.*)$", line)
            if match:
                current = [re.sub(r"\s*\(rev \w+\)$", "", match.group(2)), None]
                gpus.append(current)
        elif current is not None and "Kernel driver in use:" in line:
            current[1] = line.split(":", 1)[1].strip()
    return [tuple(g) for g in gpus]


# ---- checks ---------------------------------------------------------------------
def disk_checks(rows):
    out = []
    for mount, pct, avail in rows:
        level = BAD if pct >= DISK_BAD else WARN if pct >= DISK_WARN else OK
        out.append({"id": f"disk:{mount}", "level": level, "kind": "disk",
                    "mount": mount, "percent": pct, "available": avail})
    return out


def service_check(system_units, user_units):
    failed = list(system_units) + [f"{u} (user)" for u in user_units]
    return {"id": "services", "level": BAD if failed else OK, "kind": "services", "failed": failed}


def gpu_checks(gpus):
    out = []
    for name, driver in gpus:
        out.append({"id": f"gpu:{name}", "level": OK if driver else BAD, "kind": "gpu",
                    "name": name, "driver": driver})
    return out


def log_check(error_lines):
    return {"id": "bootlog", "level": INFO if error_lines else OK, "kind": "bootlog",
            "count": len(error_lines)}


def worst(checks):
    order = {OK: 0, INFO: 1, WARN: 2, BAD: 3}
    return max((c["level"] for c in checks), key=order.get, default=OK)


# ---- reading the machine ----------------------------------------------------------
def _out(argv, timeout=15):
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=timeout,
                              stdin=subprocess.DEVNULL).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def collect():
    """Everything the page and the report need: {"checks", "facts", "errors"}."""
    df = parse_df(_out(["df", "-P", "-B1", "-x", "tmpfs", "-x", "devtmpfs",
                        "-x", "efivarfs", "-x", "overlay", "-x", "squashfs"]))
    system_failed = parse_failed_units(_out(["systemctl", "--failed", "--no-legend", "--plain"]))
    user_failed = parse_failed_units(
        _out(["systemctl", "--user", "--failed", "--no-legend", "--plain"]))
    gpus = parse_gpus(_out(["lspci", "-k"]))
    errors = [line for line in _out(
        ["journalctl", "-b", "-p", "err", "--no-pager", "-q", "-o", "cat"]).splitlines()
        if line.strip()]
    secure_boot = _out(["mokutil", "--sb-state"]).strip().splitlines()[:1]
    checks = disk_checks(df) + [service_check(system_failed, user_failed)] \
        + gpu_checks(gpus) + [log_check(errors)]
    # Fixed English labels (the report is pasted in forums); no host name.
    facts = [
        ("OS", sysinfo.distro_name()),
        ("Kernel", sysinfo.kernel()),
        ("Architecture", sysinfo.architecture()),
        ("Desktop", sysinfo.desktop_environment()),
        ("CPU", f"{sysinfo.cpu_model()} ({sysinfo.cpu_cores()} cores)"),
        ("GPU", sysinfo.gpu_model()),
        ("Memory", sysinfo.memory()),
        ("Uptime", sysinfo.uptime()),
        ("Secure Boot", secure_boot[0] if secure_boot else "unknown"),
    ]
    return {"checks": checks, "facts": facts, "errors": errors}


def report(data, version):
    """Plain-text report, already redacted."""
    lines = [f"COS Config Center {version} - system report", ""]
    lines += [f"{label}: {value}" for label, value in data["facts"]]
    lines += ["", "Checks:"]
    for check in data["checks"]:
        mark = {OK: "ok", INFO: "info", WARN: "WARNING", BAD: "PROBLEM"}[check["level"]]
        kind = check["kind"]
        if kind == "disk":
            text = f"disk {check['mount']}: {check['percent']}% used"
        elif kind == "services":
            text = "failed services: " + (", ".join(check["failed"]) or "none")
        elif kind == "gpu":
            text = f"graphics {check['name']}: driver {check['driver'] or 'NOT LOADED'}"
        else:
            text = f"errors in this boot's log: {check['count']}"
        lines.append(f"  [{mark}] {text}")
    if data["errors"]:
        lines += ["", f"Last errors of this boot (up to {MAX_LOG_LINES}):"]
        lines += ["  " + line for line in data["errors"][-MAX_LOG_LINES:]]
    return redact("\n".join(lines)) + "\n"
