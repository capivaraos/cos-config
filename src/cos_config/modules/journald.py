"""Module: cap how much disk the system logs (journal) may use."""

import re

from gi.repository import Adw, Gio, GLib, Gtk

from .. import privileged
from ..i18n import _
from ..ops import journald as ops
from . import Module

_SIZE_LABELS = {
    "100M": "100 MB",
    "250M": "250 MB",
    "500M": "500 MB",
    "1G": "1 GB",
    "2G": "2 GB",
}
# "Archived and active journals take up 2.2G in the file system."
_USAGE_RE = re.compile(r"take up ([\d.,]+)\s*([KMGT])?")


class JournaldModule(Module):
    id = "journald"
    category = "storage"
    icon_name = "text-x-generic-symbolic"
    helper = "journald"

    @property
    def title(self):
        return _("System log size")

    @property
    def subtitle(self):
        return _("Keep system logs from filling up the disk")

    @property
    def keywords(self):
        return (_("journal"), _("logs"), _("disk space"), "journald")

    def build(self, ctx):
        return _JournaldPage(ctx)


class _JournaldPage(Adw.PreferencesPage):
    def __init__(self, ctx):
        super().__init__()
        self._ctx = ctx
        # Index 0 = no drop-in (distribution default); then ops.SIZES.
        self._choices = [None, *ops.SIZES]

        group = Adw.PreferencesGroup(
            title=_("System logs"),
            description=_(
                "Linux keeps a log of what happens on the system. It is useful "
                "for finding problems, but it can grow to several gigabytes. "
                "Choose the most it may use."
            ),
        )
        self._usage_row = Adw.ActionRow(title=_("Space used now"), subtitle="…")
        group.add(self._usage_row)

        labels = [_("Distribution default")] + [_SIZE_LABELS[s] for s in ops.SIZES]
        self._combo = Adw.ComboRow(
            title=_("Maximum size"), model=Gtk.StringList.new(labels)
        )
        self._combo.connect("notify::selected", self._update_button)
        group.add(self._combo)
        self.add(group)

        self._apply_btn = Gtk.Button(label=_("Apply"), halign=Gtk.Align.END)
        self._apply_btn.add_css_class("suggested-action")
        self._apply_btn.add_css_class("pill")
        self._apply_btn.connect("clicked", self._on_apply)
        actions = Adw.PreferencesGroup()
        actions.add(self._apply_btn)
        self.add(actions)

        self._refresh()

    # ---- state -------------------------------------------------------------
    def _refresh(self):
        current = ops.read_limit()
        self._current_index = self._choices.index(current) if current in self._choices else 0
        self._combo.set_selected(self._current_index)
        self._update_button()
        self._load_usage()

    def _update_button(self, *_):
        self._apply_btn.set_sensitive(self._combo.get_selected() != self._current_index)

    def _load_usage(self):
        try:
            proc = Gio.Subprocess.new(
                ["journalctl", "--disk-usage"],
                Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_SILENCE,
            )
        except GLib.Error:
            self._usage_row.set_subtitle(_("Unknown"))
            return

        def done(p, result):
            try:
                _ok, out, _err = p.communicate_utf8_finish(result)
            except GLib.Error:
                out = ""
            match = _USAGE_RE.search(out or "")
            if match:
                usage = f"{match.group(1)} {match.group(2) or ''}B"
            else:
                usage = _("Unknown")
            self._usage_row.set_subtitle(usage)

        proc.communicate_utf8_async(None, None, done)

    # ---- apply -------------------------------------------------------------
    def _on_apply(self, _btn):
        size = self._choices[self._combo.get_selected()]
        if size is None:
            args, body = ["reset"], _(
                "The log size limit set by COS Config Center will be removed and "
                "the distribution default will apply again."
            )
            commands = ops.describe("reset")
        else:
            args, body = ["set", size], _(
                "System logs will be limited to {size}. Older entries are deleted "
                "first when the limit is reached."
            ).format(size=_SIZE_LABELS[size])
            commands = ops.describe("set", size)
        self._ctx.confirm(
            _("Change the system log size?"), body, commands,
            lambda: self._run(args),
        )

    def _run(self, args):
        self._apply_btn.set_sensitive(False)

        def done(ok, message):
            self._refresh()
            if ok:
                self._ctx.toast(_("Log size updated"))
            else:
                self._ctx.error(message)

        privileged.run(JournaldModule.helper, args, done)
