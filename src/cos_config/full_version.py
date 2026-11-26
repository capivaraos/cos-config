"""What the Flatpak build lists, and how to get the full version.

Inside the sandbox no setting can change the system, so every module that
would apply on the host is listed, locked. The hint only gives a command
where the full version is installed already.
No GTK here, so it can be unit-tested.
"""

from .i18n import _

# The CapivaraOS desktop editions ship the native package. A Flatpak with
# the same app id takes its place in the app menu, so the way back to the
# full version is to remove the Flatpak, from the installation it is in.
APP_ID = "org.capivaraos.Config"
FLATPAK_INFO = "/.flatpak-info"


def installation_from_info(text):
    """'user', 'system' or None, from the app-path in /.flatpak-info."""
    for line in text.splitlines():
        key, _sep, value = line.partition("=")
        if key.strip() != "app-path":
            continue
        path = value.strip()
        if "/.local/share/flatpak/" in path:
            return "user"
        if path.startswith("/var/lib/flatpak/"):
            return "system"
    return None


def read_installation(path=FLATPAK_INFO):
    try:
        with open(path, encoding="utf-8") as fh:
            return installation_from_info(fh.read())
    except OSError:
        return None


def removal_command(installation):
    if installation in ("user", "system"):
        return f"flatpak uninstall --{installation} {APP_ID}"
    return f"flatpak uninstall {APP_ID}"


def listing(environment, mods, helper_available):
    """(module, locked) pairs to show on the Settings tab.

    Outside the Flatpak: a module is shown when it applies and, if it needs
    root, when its helper is installed; nothing is locked. Inside the
    Flatpak: every module relevant to the host is shown, all locked.
    """
    out = []
    for mod in mods:
        if environment.in_flatpak:
            if mod.host_relevant(environment):
                out.append((mod, True))
            continue
        if not mod.supported(environment):
            continue
        if mod.helper and not helper_available(mod.helper):
            continue
        out.append((mod, False))
    return out


def install_hint(environment, installation=None):
    """(text, command or None) explaining how to get the full version."""
    if environment.ships_full_version:
        return (_("The CapivaraOS desktop editions include the full version. "
                  "Remove this Flatpak to use it:"),
                removal_command(installation))
    if environment.is_capivaraos:
        # Series 1: removing the Flatpak would leave no copy of the app.
        return (_("The full version comes with CapivaraOS 2.0 and later."),
                None)
    name = environment.os_release.get("NAME", "").strip()
    if name:
        text = _("The full version is not available for {name} yet. "
                 "It already comes with CapivaraOS 2.0 and later.")
        return (text.format(name=name), None)
    return (_("The full version is not available for this system yet. "
              "It already comes with CapivaraOS 2.0 and later."),
            None)
