"""Module: mount extra disks automatically at startup (no fstab editing)."""

import os
import threading

from gi.repository import Adw, Gio, GLib, Gtk

from .. import privileged
from ..i18n import _
from ..ops import automount as ops
from . import Module


class DisksModule(Module):
    id = "disks"
    category = "storage"
    icon_name = "drive-harddisk-symbolic"
    helper = "automount"

    @property
    def title(self):
        return _("Disks at startup")

    @property
    def subtitle(self):
        return _("Mount your extra disks automatically when the computer starts")

    @property
    def keywords(self):
        return (_("disk"), _("partition"), "hd", "ssd", "ntfs", "fstab", _("mount"))

    def build(self, ctx):
        return _DisksPage(ctx)


def _size(n):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1000 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1000


class _DisksPage(Adw.PreferencesPage):
    def __init__(self, ctx):
        super().__init__()
        self._ctx = ctx
        self._groups = []
        self._busy = False
        self._reload()

    def _reload(self):
        def work():
            parts = ops.partitions(ops.read_lsblk(), ops.read_fstab())
            GLib.idle_add(self._show, parts)

        threading.Thread(target=work, daemon=True).start()

    def _clear(self):
        for group in self._groups:
            self.remove(group)
        self._groups = []

    def _add(self, group):
        self.add(group)
        self._groups.append(group)

    def _show(self, parts):
        self._clear()
        listed = [p for p in parts if p["status"] != "system"]
        group = Adw.PreferencesGroup(
            title=_("Extra disks and partitions"),
            description=_(
                "Turn a disk on to have it ready every time the computer starts. "
                "If the disk is not connected, the computer still starts normally."
            ),
        )
        if not listed:
            group.add(Adw.ActionRow(
                title=_("No extra disks found"),
                subtitle=_("Only the system's own partitions are on this computer."),
            ))
        for part in listed:
            group.add(self._row(part))
        self._add(group)
        self._add(Adw.PreferencesGroup(
            description=_("Encrypted disks and swap are not listed. System partitions are "
                          "always mounted already.")))
        return GLib.SOURCE_REMOVE

    def _row(self, part):
        name = part["label"] or _("{fs} partition").format(fs=part["fstype"].upper())
        details = [part["fstype"], _size(part["size"])] if part["size"] else [part["fstype"]]
        if part["path"]:
            details.append(part["path"])
        status = part["status"]
        if status == "managed":
            where = _("Mounted at {path}") if os.path.ismount(part["target"]) else _("Goes to {path}")
            details.append(where.format(path=part["target"]))
        elif status == "missing":
            details = [_("Not connected now · goes to {path}").format(path=part["target"])]
        elif status == "elsewhere":
            details.append(_("Already set up by the system"))
        else:
            details.append(_("Would go to {path}").format(path=part["target"]))

        row = Adw.SwitchRow(title=name, subtitle=" · ".join(details))
        row.set_active(status in ("managed", "missing"))
        row.set_sensitive(status != "elsewhere")
        if status == "managed" and os.path.ismount(part["target"]):
            open_btn = Gtk.Button(icon_name="folder-open-symbolic", valign=Gtk.Align.CENTER,
                                  tooltip_text=_("Open"))
            open_btn.add_css_class("flat")
            open_btn.connect("clicked", lambda *_: Gio.AppInfo.launch_default_for_uri(
                GLib.filename_to_uri(part["target"]), None))
            row.add_suffix(open_btn)
        row.connect("notify::active", self._on_toggle, part)
        return row

    # ---- apply -------------------------------------------------------------
    def _on_toggle(self, row, _pspec, part):
        if self._busy:
            return
        adding = row.get_active()

        def undo():
            self._busy = True
            row.set_active(not adding)
            self._busy = False

        if adding:
            heading = _("Mount this disk at startup?")
            body = _("It will be mounted now and every time the computer starts, at {path}. "
                     "/etc/fstab is checked before saving, and a copy of the original is kept."
                     ).format(path=part["target"])
        else:
            heading = _("Stop mounting this disk at startup?")
            body = _("It will be unmounted and removed from /etc/fstab. "
                     "Files on the disk are not touched.")
        commands = ops.describe(part, os.getuid(), os.getgid(), adding)
        self._ctx.confirm(heading, body, commands,
                          lambda: self._run(part, adding, undo), on_cancel=undo)

    def _run(self, part, adding, undo):
        def done(ok, message):
            if ok:
                self._ctx.toast(_("Disk mounted") if adding else _("Disk removed from startup"))
            else:
                undo()
                self._ctx.error(message)
            self._reload()

        privileged.run(DisksModule.helper, ["add" if adding else "remove", part["uuid"]], done)
