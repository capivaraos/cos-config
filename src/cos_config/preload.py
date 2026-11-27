"""Load gtk4-layer-shell before Wayland, so the widget can pin to the desktop.

gtk4-layer-shell only works when it is loaded before libwayland-client,
and a Python program cannot control that order. So on Wayland the
launcher starts the app again with the library in LD_PRELOAD, and the
new process takes it back out of its environment, so the programs the
app runs (lspci, journalctl and so on) do not inherit it.

No GTK here: this runs before gi is imported.
"""

import ctypes
import os
import sys

LIBRARY = "libgtk4-layer-shell.so.0"
MARKER = "COS_CONFIG_LAYER_SHELL"


def wants_preload(environ):
    """True on Wayland when this process was not started with the preload."""
    if environ.get(MARKER):
        return False
    if LIBRARY in environ.get("LD_PRELOAD", "").split():
        return False
    return bool(environ.get("WAYLAND_DISPLAY")) or \
        environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"


def preload_env(environ):
    """Copy of environ with the library first in LD_PRELOAD, and the marker."""
    env = dict(environ)
    env["LD_PRELOAD"] = " ".join([LIBRARY] + env.get("LD_PRELOAD", "").split())
    env[MARKER] = "1"
    return env


def restored_env(environ):
    """Copy of environ without the library and the marker."""
    env = dict(environ)
    env.pop(MARKER, None)
    rest = [p for p in env.get("LD_PRELOAD", "").split() if p != LIBRARY]
    if rest:
        env["LD_PRELOAD"] = " ".join(rest)
    else:
        env.pop("LD_PRELOAD", None)
    return env


def available():
    try:
        ctypes.CDLL(LIBRARY)
    except OSError:
        return False
    return True


def ensure():
    """Called by the launcher before anything imports gi."""
    if os.environ.get(MARKER):
        clean = restored_env(os.environ)
        os.environ.clear()
        os.environ.update(clean)
        return
    if wants_preload(os.environ) and available():
        sys.stdout.flush()
        sys.stderr.flush()
        try:
            os.execve(sys.executable, [sys.executable] + sys.argv,
                      preload_env(os.environ))
        except OSError:
            pass  # start without it: the widget falls back to a window
