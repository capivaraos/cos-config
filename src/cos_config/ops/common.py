"""Shared plumbing for the privileged helpers.

Each helper is a tiny script that calls run_helper() with its module's
entry point. Rules every helper follows:

* arguments come from an allowlist (ValidationError otherwise), never a shell;
* every action is logged to the journal (syslog identifier cos-config-helper);
* a system file that is not ours is backed up before the first edit;
* files are written atomically, so a crash never leaves half a config.
"""

import os
import shutil
import subprocess
import sys
import syslog
import tempfile

BACKUP_SUFFIX = ".cos-config.bak"

# Exit codes the UI understands (pkexec itself uses 126/127).
EXIT_OK = 0
EXIT_FAILED = 1
EXIT_INVALID = 2
EXIT_NOT_ROOT = 3


class ValidationError(Exception):
    """Bad arguments: the helper refuses to act."""


def log(message):
    syslog.openlog("cos-config-helper", syslog.LOG_PID, syslog.LOG_AUTHPRIV)
    syslog.syslog(syslog.LOG_NOTICE, message)


def run_cmd(argv, tail=15):
    """Run *argv* (never through a shell); raise with its last output lines."""
    log("running " + " ".join(argv))
    proc = subprocess.run(argv, capture_output=True, text=True)
    if proc.returncode != 0:
        output = (proc.stderr.strip() or proc.stdout.strip()).splitlines()
        raise RuntimeError(
            f"{' '.join(argv)} exited with {proc.returncode}:\n" + "\n".join(output[-tail:])
        )
    return proc.stdout


def rooted(root, path):
    """Join an absolute system *path* under *root* ("/" in production)."""
    return os.path.join(root, path.lstrip("/"))


def atomic_write(path, content, mode=0o644):
    directory = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".cos-config-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def backup(path):
    """Keep the pristine copy of *path* the first time we touch it.

    Returns the backup path, or None when there was nothing to back up.
    Later edits never overwrite the first backup, so it always holds the
    file as it was before COS Config Center changed anything.
    """
    if not os.path.exists(path):
        return None
    dest = path + BACKUP_SUFFIX
    if not os.path.exists(dest):
        shutil.copy2(path, dest)
    return dest


def run_helper(entry, argv):
    """Run a helper *entry(argv)*, mapping errors to exit codes."""
    if os.geteuid() != 0:
        print("this helper must run as root (via pkexec)", file=sys.stderr)
        return EXIT_NOT_ROOT
    caller = os.environ.get("PKEXEC_UID", "?")
    try:
        entry(argv)
    except ValidationError as exc:
        print(f"invalid request: {exc}", file=sys.stderr)
        log(f"refused {argv!r} from uid {caller}: {exc}")
        return EXIT_INVALID
    except Exception as exc:  # report, never leave a traceback to the UI only
        print(f"failed: {exc}", file=sys.stderr)
        log(f"failed {argv!r} from uid {caller}: {exc}")
        return EXIT_FAILED
    log(f"done {argv!r} for uid {caller}")
    return EXIT_OK
