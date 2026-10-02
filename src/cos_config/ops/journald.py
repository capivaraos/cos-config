"""Cap how much disk the system journal may use.

Writes a drop-in that only COS Config Center owns, so reverting is just
deleting it — the distro's own journald.conf is never edited.
"""

import os
import subprocess

from . import common

DROPIN_DIR = "/etc/systemd/journald.conf.d"
DROPIN_NAME = "cos-config.conf"
SIZES = ("100M", "250M", "500M", "1G", "2G")


def dropin_path(root="/"):
    return common.rooted(root, os.path.join(DROPIN_DIR, DROPIN_NAME))


def validate_size(size):
    if size not in SIZES:
        raise common.ValidationError(f"size must be one of {', '.join(SIZES)}")
    return size


def render(size):
    return (
        "# Managed by COS Config Center. Delete this file to go back to the\n"
        "# distribution default.\n"
        "[Journal]\n"
        f"SystemMaxUse={validate_size(size)}\n"
    )


def read_limit(root="/"):
    """The size set by our drop-in, or None when it is not present."""
    try:
        with open(dropin_path(root), encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return None
    for line in lines:
        key, sep, value = line.partition("=")
        if sep and key.strip() == "SystemMaxUse":
            return value.strip() or None
    return None


def describe(action, size=None):
    """Equivalent shell commands, shown to the user before applying."""
    path = os.path.join(DROPIN_DIR, DROPIN_NAME)
    restart = "sudo systemctl restart systemd-journald"
    if action == "set":
        return [
            f"sudo mkdir -p {DROPIN_DIR}",
            f"printf '[Journal]\\nSystemMaxUse={validate_size(size)}\\n' | sudo tee {path}",
            restart,
        ]
    if action == "reset":
        return [f"sudo rm -f {path}", restart]
    raise common.ValidationError(f"unknown action {action!r}")


def _restart():
    subprocess.run(["systemctl", "restart", "systemd-journald"], check=True)


def _read_dropin(root):
    try:
        with open(dropin_path(root), encoding="utf-8") as fh:
            return fh.read()
    except FileNotFoundError:
        return None


def _write_dropin(root, content):
    """Write *content* to the drop-in, or remove it when content is None."""
    if content is None:
        try:
            os.unlink(dropin_path(root))
        except FileNotFoundError:
            pass
        return
    os.makedirs(common.rooted(root, DROPIN_DIR), mode=0o755, exist_ok=True)
    common.atomic_write(dropin_path(root), content)


def _change(root, content, restart):
    # If journald cannot be restarted, put the previous drop-in back so the
    # file never disagrees with the "not applied" the user is shown.
    previous = _read_dropin(root)
    _write_dropin(root, content)
    if restart:
        try:
            _restart()
        except Exception:
            _write_dropin(root, previous)
            raise


def apply(size, root="/", restart=True):
    _change(root, render(size), restart)


def reset(root="/", restart=True):
    _change(root, None, restart)


def helper_main(argv):
    """argv: ["set", SIZE] or ["reset"]."""
    if len(argv) == 2 and argv[0] == "set":
        apply(argv[1])
    elif argv == ["reset"]:
        reset()
    else:
        raise common.ValidationError("usage: set SIZE | reset")
