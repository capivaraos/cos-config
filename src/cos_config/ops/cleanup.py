"""Free disk space from system-wide caches that rebuild themselves.

Only things that are safe to lose: downloaded packages (fetched again when
needed), old journal entries, crash dumps and Flatpak runtimes no app uses.
Directories are fixed here; nothing is deleted by a path from the caller,
and symlinks are never followed.
"""

import os
import shutil

from .. import distro, env
from . import common

ITEMS = ("pkgcache", "journal", "coredumps", "flatpak")
PKG_CACHE_DIRS = ("/var/cache/libdnf5", "/var/cache/dnf", "/var/cache/PackageKit",
                  "/var/cache/apt/archives", "/var/cache/pacman/pkg", "/var/cache/zypp")
PACKAGEKIT_CACHE = "/var/cache/PackageKit"
COREDUMP_DIR = "/var/lib/systemd/coredump"
JOURNAL_KEEP = "2weeks"


def empty_dir(path):
    """Delete what is inside *path* (not the directory itself, no symlink hops)."""
    try:
        entries = list(os.scandir(path))
    except FileNotFoundError:
        return
    for entry in entries:
        if entry.is_dir(follow_symlinks=False):
            shutil.rmtree(entry.path)
        else:
            os.unlink(entry.path)


def commands(item, family):
    """argv lists for *item* (the directory clean-ups are done in Python)."""
    if item == "pkgcache":
        manager = distro.for_family(family)
        return [manager.clean_cache()] if manager else []
    if item == "journal":
        return [["journalctl", f"--vacuum-time={JOURNAL_KEEP}"]]
    if item == "flatpak":
        return [["flatpak", "uninstall", "--system", "--unused", "-y", "--noninteractive"]]
    if item == "coredumps":
        return []
    raise common.ValidationError(f"unknown item {item!r}")


def describe(items, family):
    lines = []
    for item in items:
        lines += ["sudo " + " ".join(cmd) for cmd in commands(item, family)]
        if item == "pkgcache":
            lines.append(f"sudo rm -rf {PACKAGEKIT_CACHE}/*")
        elif item == "coredumps":
            lines.append(f"sudo rm -f {COREDUMP_DIR}/*")
    return lines


def clean(items, family):
    for item in ITEMS:  # fixed order, whatever the caller's
        if item not in items:
            continue
        for cmd in commands(item, family):
            if shutil.which(cmd[0]):  # e.g. no flatpak on this machine
                common.run_cmd(cmd)
        if item == "pkgcache":
            empty_dir(PACKAGEKIT_CACHE)
        elif item == "coredumps":
            empty_dir(COREDUMP_DIR)
        print(f"cleaned {item}", flush=True)


def helper_main(argv):
    """argv: ["clean", ITEM, ...]."""
    if len(argv) < 2 or argv[0] != "clean" or any(i not in ITEMS for i in argv[1:]):
        raise common.ValidationError(f"usage: clean ITEM... (items: {', '.join(ITEMS)})")
    clean(argv[1:], env.detect_family(env.read_os_release()))
