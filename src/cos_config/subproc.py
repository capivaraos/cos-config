"""Run user-level commands one after another without blocking the UI."""

from gi.repository import Gio, GLib


def run_sequence(steps, callback):
    """Run *steps* in order; callback(ok, error_text) at the end.

    Each step is an argv list, or a Python callable for in-process work
    (e.g. writing a file). The first failure stops the sequence.
    """
    steps = list(steps)

    def next_step():
        if not steps:
            callback(True, "")
            return
        step = steps.pop(0)
        if callable(step):
            try:
                step()
            except Exception as exc:
                callback(False, str(exc))
                return
            next_step()
            return
        try:
            proc = Gio.Subprocess.new(
                step, Gio.SubprocessFlags.STDOUT_SILENCE | Gio.SubprocessFlags.STDERR_PIPE)
        except GLib.Error as exc:
            callback(False, f"{step[0]}: {exc.message}")
            return

        def done(p, result):
            try:
                _ok, _out, err = p.communicate_utf8_finish(result)
            except GLib.Error as exc:
                callback(False, exc.message)
                return
            if p.get_exit_status() != 0:
                callback(False, f"{' '.join(step)}\n{(err or '').strip()}")
                return
            next_step()

        proc.communicate_utf8_async(None, None, done)

    next_step()
