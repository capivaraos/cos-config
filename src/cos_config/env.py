"""Detect where the app is running: distro family, sandbox, desktop.

Modules use this to decide whether they apply to the current machine
(e.g. RPM Fusion only makes sense on the Fedora family). Parsing is kept
pure so it can be unit-tested with fixture strings.
"""

import os
from dataclasses import dataclass, field

FEDORA = "fedora"
DEBIAN = "debian"
ARCH = "arch"
SUSE = "suse"
UNKNOWN = "unknown"

# os-release ID / ID_LIKE tokens -> family. Checked in order, ID first.
_FAMILY_TOKENS = (
    (FEDORA, ("fedora", "rhel", "centos")),
    (DEBIAN, ("debian", "ubuntu")),
    (ARCH, ("arch",)),
    (SUSE, ("suse", "opensuse")),
)

# Inside a Flatpak sandbox /etc/os-release is the *runtime's*; the real host
# distro is exposed at /run/host/os-release.
OS_RELEASE_PATHS = ("/run/host/os-release", "/run/host/etc/os-release", "/etc/os-release")


def parse_os_release(text):
    data = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        data[key.strip()] = val.strip().strip('"').strip("'")
    return data


def read_os_release(paths=OS_RELEASE_PATHS):
    for path in paths:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError:
            continue
        if text:
            return parse_os_release(text)
    return {}


def detect_family(os_release):
    ids = [os_release.get("ID", "").lower()]
    ids += os_release.get("ID_LIKE", "").lower().split()
    for token in ids:
        for family, names in _FAMILY_TOKENS:
            if token in names or (family == SUSE and token.startswith("opensuse")):
                return family
    return UNKNOWN


@dataclass
class Environment:
    os_release: dict = field(default_factory=dict)
    family: str = UNKNOWN
    in_flatpak: bool = False
    desktops: tuple = ()  # lowercased XDG_CURRENT_DESKTOP entries
    session_type: str = ""

    @property
    def is_capivaraos(self):
        return self.os_release.get("ID", "").lower() == "capivaraos"

    @classmethod
    def detect(cls):
        rel = read_os_release()
        desktops = os.environ.get("XDG_CURRENT_DESKTOP", "")
        return cls(
            os_release=rel,
            family=detect_family(rel),
            in_flatpak=os.path.exists("/.flatpak-info"),
            desktops=tuple(d.lower() for d in desktops.split(":") if d),
            session_type=os.environ.get("XDG_SESSION_TYPE", "").lower(),
        )
