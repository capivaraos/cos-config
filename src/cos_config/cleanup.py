"""Disk clean-up: what can be freed, and the user-level part of doing it.

System items are measured here (reading sizes needs no root) and removed by
the root helper (ops/cleanup.py). User items are both measured and removed
here. Everything listed rebuilds itself or is re-downloadable; the user's
whole ~/.cache is deliberately not offered, since tools keep expensive data
there (models, toolchains).
"""

import json
import os
import re
import subprocess

from .ops import cleanup as rootops

USER_ITEMS = ("trash", "thumbnails", "flatpak-user", "podman")
SYSTEM_ITEMS = rootops.ITEMS
# Checked by default; the others are listed but left for the user to tick.
DEFAULT_ON = ("trash", "thumbnails", "flatpak-user", "pkgcache", "coredumps", "flatpak")

_UNITS = {"B": 1, "K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4}


def human(size):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1000 or unit == "TB":
            return f"{size:.0f} {unit}" if unit in ("B", "KB") else f"{size:.1f} {unit}"
        size /= 1000


def dir_size(path):
    """Disk space used under *path*; unreadable parts count as zero."""
    total = 0
    for root, _dirs, files in os.walk(path, onerror=lambda _e: None):
        for name in files:
            try:
                total += os.lstat(os.path.join(root, name)).st_blocks * 512
            except OSError:
                pass
    return total


def parse_journal_usage(text):
    """Bytes from `journalctl --disk-usage` ("... take up 2.2G in ...")."""
    match = re.search(r"take up ([\d.]+)\s*([BKMGT])", text)
    return int(float(match.group(1)) * _UNITS[match.group(2)]) if match else 0


def parse_flatpak_unused(text):
    """How many refs `flatpak uninstall --unused` would remove (numbered rows)."""
    return len(re.findall(r"^\s*\d+\.\s", text, re.M))


def parse_podman_reclaimable(text):
    try:
        return sum(int(row.get("RawReclaimable", 0)) for row in json.loads(text)
                   if row.get("Type") == "Images")
    except (ValueError, TypeError, AttributeError):
        return 0


def _out(argv):
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=30,
                              stdin=subprocess.DEVNULL).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def thumbnails_dir():
    return os.path.join(os.path.expanduser("~"), ".cache", "thumbnails")


def trash_dir():
    return os.path.join(os.path.expanduser("~"), ".local", "share", "Trash")


def measure():
    """{item: ("bytes", n) | ("count", n)} for every item."""
    unused = lambda scope: parse_flatpak_unused(  # noqa: E731
        _out(["flatpak", "uninstall", scope, "--unused"]))
    return {
        "trash": ("bytes", dir_size(trash_dir())),
        "thumbnails": ("bytes", dir_size(thumbnails_dir())),
        "flatpak-user": ("count", unused("--user")),
        "podman": ("bytes", parse_podman_reclaimable(
            _out(["podman", "system", "df", "--format", "json"]))),
        "pkgcache": ("bytes", sum(dir_size(d) for d in rootops.PKG_CACHE_DIRS)),
        "journal": ("bytes", parse_journal_usage(_out(["journalctl", "--disk-usage"]))),
        "coredumps": ("bytes", dir_size(rootops.COREDUMP_DIR)),
        "flatpak": ("count", unused("--system")),
    }


def user_steps(items):
    """Steps for subproc.run_sequence: argv lists or callables."""
    steps = []
    if "trash" in items:
        steps.append(["gio", "trash", "--empty"])
    if "thumbnails" in items:
        steps.append(lambda: rootops.empty_dir(thumbnails_dir()))
    if "flatpak-user" in items:
        steps.append(["flatpak", "uninstall", "--user", "--unused", "-y", "--noninteractive"])
    if "podman" in items:
        steps.append(["podman", "image", "prune", "-a", "-f"])
    return steps


def describe_user(items):
    lines = []
    for step in user_steps(items):
        lines.append("rm -rf ~/.cache/thumbnails/*" if callable(step) else " ".join(step))
    return lines


def free_space(path="/"):
    stat = os.statvfs(path)
    return stat.f_bavail * stat.f_frsize
