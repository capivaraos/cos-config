"""Configuration modules: the contract every module follows + the registry.

A module is one page in the "Settings" tab. It declares where it applies
(supported()), builds its own page (build()), and — when it changes the
system — goes through a polkit helper named in `helper`. Before any change
the page shows what will be done, including the equivalent commands, via
ModuleContext.confirm().
"""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk, Pango  # noqa: E402

from .. import privileged  # noqa: E402
from ..i18n import _  # noqa: E402


class Category:
    def __init__(self, cid, title, icon_name):
        self.id = cid
        self.title = title
        self.icon_name = icon_name


def categories():
    # Order here is the order on screen; empty categories are hidden.
    return [
        Category("software", _("Software and drivers"), "application-x-addon-symbolic"),
        Category("storage", _("Disks and maintenance"), "drive-harddisk-symbolic"),
        Category("boot", _("Startup and dual boot"), "system-reboot-symbolic"),
        Category("hardware", _("Hardware"), "computer-symbolic"),
        Category("input", _("Keyboard and language"), "input-keyboard-symbolic"),
        Category("network", _("Network and security"), "network-workgroup-symbolic"),
        Category("users", _("Users and services"), "system-users-symbolic"),
        Category("capivaraos", "CapivaraOS", "starred-symbolic"),
    ]


class Module:
    id = ""
    category = ""
    icon_name = "emblem-system-symbolic"
    # Name of the root helper in const.HELPER_DIR, or None for user-level
    # modules (those also work in the Flatpak).
    helper = None

    @property
    def title(self):
        raise NotImplementedError

    @property
    def subtitle(self):
        return ""

    @property
    def keywords(self):
        """Extra search terms (translated), besides title and subtitle."""
        return ()

    def supported(self, env):
        """Whether this module applies to *env* (distro, desktop, hardware)."""
        return True

    def build(self, ctx):
        """Return the page content widget."""
        raise NotImplementedError


def visible_modules(env, registry=None):
    """Modules to list on this machine.

    Unsupported modules are simply not shown. Modules that need root are
    left out of the Flatpak and when their helper is not installed.
    """
    mods = registry if registry is not None else all_modules()
    out = []
    for mod in mods:
        if not mod.supported(env):
            continue
        if mod.helper and (env.in_flatpak or not privileged.available(mod.helper)):
            continue
        out.append(mod)
    return out


def all_modules():
    from . import journald, keyboard, multimedia

    return [multimedia.MultimediaModule(), journald.JournaldModule(), keyboard.KeyboardModule()]


class ModuleContext:
    """What a module page may use from the app."""

    def __init__(self, env, window):
        self.env = env
        self.window = window

    def toast(self, text):
        self.window.notify_toast(text)

    def error(self, message):
        dialog = Adw.AlertDialog(heading=_("The change was not applied"), body=message)
        dialog.add_response("close", _("Close"))
        dialog.present(self.window)

    def confirm(self, heading, body, commands, on_confirm):
        """Ask before changing the system, listing the equivalent commands."""
        dialog = Adw.AlertDialog(heading=heading, body=body)
        if commands:
            label = Gtk.Label(
                label="\n".join(commands), xalign=0, selectable=True, wrap=True,
                wrap_mode=Pango.WrapMode.WORD_CHAR,  # long paths still fit
            )
            label.add_css_class("monospace")
            label.add_css_class("dim-label")
            expander = Gtk.Expander(label=_("Equivalent commands"), child=label)
            dialog.set_extra_child(expander)
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("apply", _("Apply"))
        dialog.set_response_appearance("apply", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")

        def on_response(_dialog, response):
            if response == "apply":
                on_confirm()

        dialog.connect("response", on_response)
        dialog.present(self.window)
