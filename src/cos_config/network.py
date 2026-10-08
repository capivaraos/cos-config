"""Computer name, SSH and DNS: the user-level side and state reading.

The computer name goes through hostnamectl (systemd-hostnamed asks polkit
itself), and the SSH key is created in the user's own ~/.ssh. Turning the
SSH server on and changing DNS need root: see ops/network.py.
"""

import getpass
import os
import re
import subprocess

from .ops import network as rootops

_HOST_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")


def valid_hostname(name):
    """Lower-cased single-label name (letters, digits, hyphens), or ValueError."""
    name = (name or "").strip().lower()
    if not _HOST_RE.match(name):
        raise ValueError("use letters, digits and hyphens; start and end with a letter or digit")
    return name


def hostname_argv(name):
    return ["hostnamectl", "set-hostname", valid_hostname(name)]


def _out(argv):
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def current_hostname():
    return _out(["hostnamectl", "--static"]).strip() or _out(["hostname"]).strip()


def ssh_state():
    """{"unit": name or None, "enabled": bool, "active": bool}."""
    unit = rootops.parse_ssh_unit(_out(["systemctl", "list-unit-files", "ssh*", "--no-legend"]))
    if unit is None:
        return {"unit": None, "enabled": False, "active": False}
    return {
        "unit": unit,
        "enabled": _out(["systemctl", "is-enabled", unit]).strip() == "enabled",
        "active": _out(["systemctl", "is-active", unit]).strip() == "active",
    }


# ---- the user's SSH key ----------------------------------------------------------
def key_path():
    return os.path.join(os.path.expanduser("~"), ".ssh", "id_ed25519")


def public_key(path=None):
    """Contents of the public key file, or None when there is no key yet."""
    try:
        with open((path or key_path()) + ".pub", encoding="utf-8") as fh:
            return fh.read().strip() or None
    except OSError:
        return None


def keygen_argv(path=None, comment=None):
    comment = comment or f"{getpass.getuser()}@{current_hostname() or 'computer'}"
    return ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", path or key_path(), "-C", comment]


def key_summary(public):
    """'ssh-ed25519 …AbCd comment' shortened for display."""
    parts = public.split()
    if len(parts) < 2:
        return public
    tail = f" {parts[2]}" if len(parts) > 2 else ""
    return f"{parts[0]} …{parts[1][-8:]}{tail}"


def dns_provider():
    return rootops.read_provider()


def dns_available():
    """Encrypted DNS is set through systemd-resolved; without it, no DNS group."""
    return rootops.resolved_active()
