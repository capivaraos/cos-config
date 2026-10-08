"""Module: one-click diagnosis (health checks + a report to ask for help)."""

import threading

from gi.repository import Adw, GLib, Gtk

from .. import const, icons
from .. import diagnostics as dg
from ..i18n import _
from . import Module

def _icon(level):
    """(icon name, css class) for a check level."""
    return {
        dg.OK: (icons.pick("object-select-symbolic", "emblem-ok-symbolic",
                           "emblem-default-symbolic"), "success"),
        dg.INFO: ("dialog-information-symbolic", "accent"),
        dg.WARN: ("dialog-warning-symbolic", "warning"),
        dg.BAD: ("dialog-error-symbolic", "error"),
    }[level]


class DiagnosticsModule(Module):
    id = "diagnostics"
    category = "storage"
    icon_name = "dialog-question-symbolic"

    @property
    def title(self):
        return _("System check")

    @property
    def subtitle(self):
        return _("Quick health checks and a report to share when asking for help")

    @property
    def keywords(self):
        return (_("diagnosis"), _("problem"), _("help"), _("report"), _("error"))

    def supported(self, env):
        # Needs the host's systemctl/journalctl/lspci: not from the sandbox.
        return not env.in_flatpak

    def build(self, ctx):
        return _DiagnosticsPage(ctx)


def _row_texts(check):
    kind = check["kind"]
    if kind == "disk":
        free = f"{check['available'] / 1e9:.1f} GB"
        return (_("Disk {mount}").format(mount=check["mount"]),
                _("{percent}% used, {free} free").format(percent=check["percent"], free=free))
    if kind == "services":
        if check["failed"]:
            return _("Services"), _("Failed: {names}").format(names=", ".join(check["failed"]))
        return _("Services"), _("All running")
    if kind == "gpu":
        if check["driver"]:
            return check["name"], _("Driver in use: {driver}").format(driver=check["driver"])
        return check["name"], _("No driver loaded")
    if check["count"]:
        return (_("Errors since startup"),
                _("{n} lines. Often harmless, but useful when asking for help.").format(n=check["count"]))
    return _("Errors since startup"), _("None")


class _DiagnosticsPage(Adw.PreferencesPage):
    def __init__(self, ctx):
        super().__init__()
        self._ctx = ctx
        self._report = ""
        self._groups = []
        group = Adw.PreferencesGroup(title=_("Checking…"))
        self.add(group)
        self._groups.append(group)
        threading.Thread(target=self._load, daemon=True).start()

    def _load(self):
        data = dg.collect()
        GLib.idle_add(self._show, data, dg.report(data, const.VERSION))

    def _add(self, group):
        self.add(group)
        self._groups.append(group)

    def _show(self, data, report):
        for group in self._groups:
            self.remove(group)
        self._groups = []
        self._report = report

        headline = {
            dg.OK: _("Everything looks fine"),
            dg.INFO: _("Everything looks fine"),
            dg.WARN: _("Something needs attention"),
            dg.BAD: _("A problem was found"),
        }[dg.worst(data["checks"])]
        group = Adw.PreferencesGroup(title=headline)
        for check in data["checks"]:
            title, subtitle = _row_texts(check)
            row = Adw.ActionRow(title=title, subtitle=subtitle)
            icon_name, css = _icon(check["level"])
            icon = Gtk.Image(icon_name=icon_name)
            icon.add_css_class(css)
            row.add_prefix(icon)
            group.add(row)
        self._add(group)

        group = Adw.PreferencesGroup(
            title=_("Report"),
            description=_("To paste in a forum or chat when you ask for help. It does not "
                          "include your name, the computer's name or network addresses."),
        )
        buttons = Gtk.Box(spacing=12, halign=Gtk.Align.START)
        copy_btn = Gtk.Button(label=_("Copy report"))
        copy_btn.add_css_class("suggested-action")
        copy_btn.add_css_class("pill")
        copy_btn.connect("clicked", self._on_copy)
        save_btn = Gtk.Button(label=_("Save report…"))
        save_btn.add_css_class("pill")
        save_btn.connect("clicked", self._on_save)
        buttons.append(copy_btn)
        buttons.append(save_btn)
        group.add(buttons)
        self._add(group)

        label = Gtk.Label(label=report, xalign=0, selectable=True, wrap=True)
        label.add_css_class("monospace")
        label.add_css_class("caption")
        expander = Gtk.Expander(label=_("See the report"), child=label)
        group = Adw.PreferencesGroup()
        group.add(expander)
        self._add(group)
        return GLib.SOURCE_REMOVE

    def _on_copy(self, _btn):
        self.get_clipboard().set(self._report)
        self._ctx.toast(_("Report copied"))

    def _on_save(self, _btn):
        dialog = Gtk.FileDialog(title=_("Save report"), initial_name="cos-config-report.txt")
        dialog.save(self._ctx.window, None, self._on_save_done)

    def _on_save_done(self, dialog, result):
        try:
            gfile = dialog.save_finish(result)
        except GLib.Error:
            return  # cancelled
        try:
            with open(gfile.get_path(), "w", encoding="utf-8") as fh:
                fh.write(self._report)
        except OSError as exc:
            self._ctx.error(str(exc))
            return
        self._ctx.toast(_("Report saved"))
