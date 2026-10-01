"""Collect system information with graceful fallbacks.

Everything here is best-effort: on any unexpected platform quirk a field
degrades to "Unknown" rather than raising, so the UI never crashes.
"""

import os
import platform
import re
import subprocess

from .i18n import _


def _read(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


def _os_release():
    # Inside a Flatpak sandbox /etc/os-release is the *runtime's*; the real
    # host distro is exposed at /run/host/os-release. Prefer the host so the
    # app always reports the machine it actually runs on.
    data = {}
    for path in ("/run/host/os-release", "/run/host/etc/os-release", "/etc/os-release"):
        text = _read(path)
        if text:
            for line in text.splitlines():
                if "=" in line:
                    key, _, val = line.partition("=")
                    data[key.strip()] = val.strip().strip('"')
            break
    return data


def distro_name():
    rel = _os_release()
    return rel.get("PRETTY_NAME") or rel.get("NAME") or "Unknown Linux"


def kernel():
    return f"{platform.system()} {platform.release()}"


def architecture():
    return platform.machine() or "Unknown"


def hostname():
    return platform.node() or "localhost"


def desktop_environment():
    de = os.environ.get("XDG_CURRENT_DESKTOP") or os.environ.get("DESKTOP_SESSION")
    session = os.environ.get("XDG_SESSION_TYPE", "")
    if de and session:
        return f"{de} ({session})"
    return de or "Unknown"


def shell():
    sh = os.environ.get("SHELL", "")
    return os.path.basename(sh) if sh else "Unknown"


def cpu_model():
    for line in _read("/proc/cpuinfo").splitlines():
        if line.lower().startswith("model name"):
            return line.split(":", 1)[1].strip()
    return platform.processor() or "Unknown CPU"


def cpu_cores():
    try:
        return os.cpu_count() or 0
    except Exception:
        return 0


def gpu_model():
    # lspci is the most portable source; keep it optional.
    try:
        out = subprocess.run(
            ["lspci"], capture_output=True, text=True, timeout=3
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return "Unknown"
    gpus = []
    for line in out.splitlines():
        if re.search(r"VGA compatible controller|3D controller|Display controller", line):
            desc = line.split(":", 2)[-1].strip()
            # Trim the vendor bracket noise a little.
            gpus.append(desc)
    return gpus[0] if gpus else "Unknown"


def _meminfo():
    info = {}
    for line in _read("/proc/meminfo").splitlines():
        key, _, rest = line.partition(":")
        m = re.search(r"(\d+)", rest)
        if m:
            info[key.strip()] = int(m.group(1))  # kB
    return info


def memory():
    info = _meminfo()
    total = info.get("MemTotal", 0)
    avail = info.get("MemAvailable", info.get("MemFree", 0))
    used = max(total - avail, 0)
    if not total:
        return "Unknown"
    return f"{used / 1024 / 1024:.1f} GiB / {total / 1024 / 1024:.1f} GiB"


def uptime():
    raw = _read("/proc/uptime").split()
    if not raw:
        return "Unknown"
    try:
        secs = int(float(raw[0]))
    except ValueError:
        return "Unknown"
    days, rem = divmod(secs, 86400)
    hours, rem = divmod(rem, 3600)
    mins = rem // 60
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    parts.append(f"{mins}m")
    return " ".join(parts)


def collect():
    """Return an ordered list of (label, value) pairs for display/render."""
    return [
        (_("OS"), distro_name()),
        (_("Host"), hostname()),
        (_("Kernel"), kernel()),
        (_("Architecture"), architecture()),
        (_("Desktop"), desktop_environment()),
        (_("Shell"), shell()),
        (_("CPU"), _("{model} ({cores} cores)").format(model=cpu_model(), cores=cpu_cores())),
        (_("GPU"), gpu_model()),
        (_("Memory"), memory()),
        (_("Uptime"), uptime()),
    ]
