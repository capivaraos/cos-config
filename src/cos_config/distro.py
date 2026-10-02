"""Package-manager layer: one small class per distro family.

These only *build* argv lists; nothing here runs a command. Privileged
helpers execute them as root, the UI shows them as the "equivalent command",
and tests check them directly. Package names are validated so a helper can
never be tricked into passing an option or a shell fragment.
"""

import re

from . import env

_PKG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9+._:@-]*$")


def validate_packages(packages):
    packages = list(packages)
    if not packages:
        raise ValueError("no packages given")
    for name in packages:
        if not isinstance(name, str) or not _PKG_RE.match(name):
            raise ValueError(f"invalid package name: {name!r}")
    return packages


class PackageManager:
    name = ""

    def install(self, packages):
        raise NotImplementedError

    def remove(self, packages):
        raise NotImplementedError

    def is_installed(self, package):
        """argv that exits 0 when *package* is installed (runs unprivileged)."""
        raise NotImplementedError


class Dnf(PackageManager):
    name = "dnf"

    def install(self, packages):
        return ["dnf", "install", "-y", *validate_packages(packages)]

    def remove(self, packages):
        return ["dnf", "remove", "-y", *validate_packages(packages)]

    def is_installed(self, package):
        return ["rpm", "-q", *validate_packages([package])]


class Apt(PackageManager):
    name = "apt"

    def install(self, packages):
        return ["apt-get", "install", "-y", *validate_packages(packages)]

    def remove(self, packages):
        return ["apt-get", "remove", "-y", *validate_packages(packages)]

    def is_installed(self, package):
        return ["dpkg-query", "-W", "-f=${Status}", *validate_packages([package])]


class Pacman(PackageManager):
    name = "pacman"

    def install(self, packages):
        return ["pacman", "-S", "--needed", "--noconfirm", *validate_packages(packages)]

    def remove(self, packages):
        return ["pacman", "-R", "--noconfirm", *validate_packages(packages)]

    def is_installed(self, package):
        return ["pacman", "-Q", *validate_packages([package])]


class Zypper(PackageManager):
    name = "zypper"

    def install(self, packages):
        return ["zypper", "--non-interactive", "install", *validate_packages(packages)]

    def remove(self, packages):
        return ["zypper", "--non-interactive", "remove", *validate_packages(packages)]

    def is_installed(self, package):
        return ["rpm", "-q", *validate_packages([package])]


_BY_FAMILY = {
    env.FEDORA: Dnf,
    env.DEBIAN: Apt,
    env.ARCH: Pacman,
    env.SUSE: Zypper,
}


def for_family(family):
    """The PackageManager for *family*, or None when it is not supported."""
    cls = _BY_FAMILY.get(family)
    return cls() if cls else None
