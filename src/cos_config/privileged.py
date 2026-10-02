"""Run a root helper through pkexec without blocking the UI.

Each helper lives in const.HELPER_DIR and has its own polkit action
(org.capivaraos.config.<name>), so the password prompt names what is about
to happen. The app itself never runs as root.
"""

import os

from gi.repository import Gio, GLib

from . import const
from .i18n import _

# pkexec exit codes: the user dismissed the dialog / was not authorized.
_PKEXEC_CANCELLED = 126
_PKEXEC_DENIED = 127
_HELPER_INVALID = 2


def helper_path(name):
    return os.path.join(const.HELPER_DIR, name)


def available(name):
    """True when the helper is installed (i.e. the native package is)."""
    return os.access(helper_path(name), os.X_OK)


def run(name, args, callback):
    """Run helper *name* with *args*; calls callback(ok, message) when done.

    *message* is empty on success, otherwise a short, translated reason
    followed by the helper's own error output.
    """
    argv = ["pkexec", helper_path(name), *args]
    try:
        proc = Gio.Subprocess.new(
            argv, Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_PIPE
        )
    except GLib.Error as exc:
        callback(False, _("Could not start the helper: {error}").format(error=exc.message))
        return

    def done(p, result):
        try:
            _ok, _out, err = p.communicate_utf8_finish(result)
        except GLib.Error as exc:
            callback(False, exc.message)
            return
        status = p.get_exit_status()
        if status == 0:
            callback(True, "")
        elif status in (_PKEXEC_CANCELLED, _PKEXEC_DENIED):
            callback(False, _("Authorization was cancelled or denied."))
        elif status == _HELPER_INVALID:
            callback(False, _("The request was refused as invalid.") + "\n" + (err or "").strip())
        else:
            callback(False, _("The change could not be applied.") + "\n" + (err or "").strip())

    proc.communicate_utf8_async(None, None, done)
