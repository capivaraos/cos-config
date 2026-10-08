"""Module: complete multimedia support (codecs, RPM Fusion, Flathub)."""

import os
import shutil
import threading

from gi.repository import Adw, GLib, Gtk

from .. import env as envmod
from .. import privileged
from ..i18n import _
from ..ops import multimedia as ops
from . import Module


class MultimediaModule(Module):
    id = "multimedia"
    category = "software"
    icon_name = "applications-multimedia-symbolic"
    helper = "multimedia"

    @property
    def title(self):
        return _("Codecs and extra repositories")

    @property
    def subtitle(self):
        return _("Play any video or music, and get every app on Flathub")

    @property
    def keywords(self):
        return (_("video"), _("music"), "mp4", "h264", "h265", "rpm fusion", "flathub", "ffmpeg")

    def supported(self, env):
        # dnf-based Fedora family only; Fedora Atomic (rpm-ostree) is not.
        return (env.family == envmod.FEDORA
                and not os.path.exists("/run/ostree-booted")
                and shutil.which("dnf") is not None)

    def build(self, ctx):
        return _MultimediaPage(ctx)


def _rows_text():
    return {
        "rpmfusion": (_("RPM Fusion repositories"),
                      _("Community repositories with software Fedora cannot ship")),
        "openh264": (_("Cisco OpenH264"), _("H.264 video for browsers and calls")),
        "codecs": (_("Complete codecs"),
                   _("Full FFmpeg and GStreamer plugins (MP4, H.265, AAC and more)")),
        "flathub": (_("All Flathub apps"),
                    _("Remove Fedora's filter so every Flathub app shows up")),
    }


class _MultimediaPage(Adw.PreferencesPage):
    def __init__(self, ctx):
        super().__init__()
        self._ctx = ctx
        self._state = {}
        self._syncing = False

        group = Adw.PreferencesGroup(
            title=_("Multimedia support"),
            description=_(
                "Many videos and songs use formats that Fedora cannot include "
                "because of patents. Turn on what you want and apply."
            ),
        )
        self._rows = {}
        for step, (title, subtitle) in _rows_text().items():
            row = Adw.SwitchRow(title=title, subtitle=_("Checking…"), sensitive=False)
            row.connect("notify::active", self._sync)
            self._rows[step] = (row, subtitle)
            group.add(row)
        self.add(group)

        self.add(Adw.PreferencesGroup(
            title=_("About these sources"),
            description=_(
                "RPM Fusion and Flathub are run by their own communities, not by "
                "CapivaraOS or Fedora. Some of these formats are covered by "
                "patents in a few countries: check what applies where you live."
            ),
        ))

        self._apply_btn = Gtk.Button(label=_("Apply"))
        self._apply_btn.add_css_class("suggested-action")
        self._apply_btn.add_css_class("pill")
        self._apply_btn.connect("clicked", self._on_apply)
        self._spinner = Gtk.Spinner(spinning=True, visible=False)
        self._status = Gtk.Label(visible=False, wrap=True)
        self._status.add_css_class("dim-label")
        box = Gtk.Box(spacing=12, halign=Gtk.Align.END)
        box.append(self._status)
        box.append(self._spinner)
        box.append(self._apply_btn)
        actions = Adw.PreferencesGroup()
        actions.add(box)
        self.add(actions)

        self._refresh()

    # ---- state -------------------------------------------------------------
    def _refresh(self):
        self._apply_btn.set_sensitive(False)

        def work():
            GLib.idle_add(self._show_state, ops.state())

        threading.Thread(target=work, daemon=True).start()

    def _show_state(self, state):
        self._state = state
        self._syncing = True
        for step, (row, subtitle) in self._rows.items():
            done = state.get(step)
            row.set_sensitive(not done)
            row.set_active(True)  # done: shown on; missing: proposed on
            row.set_subtitle(_("Already enabled") if done else subtitle)
        self._syncing = False
        self._sync()
        return GLib.SOURCE_REMOVE

    def _selected(self):
        return [s for s, (row, _sub) in self._rows.items()
                if row.get_active() and not self._state.get(s)]

    def _sync(self, *_args):
        """RPM Fusion is required by the codecs."""
        if self._syncing or not self._state:
            return
        self._syncing = True
        row, subtitle = self._rows["rpmfusion"]
        if not self._state.get("rpmfusion"):
            needed = any(s in self._selected() for s in ops.NEEDS_RPMFUSION)
            if needed:
                row.set_active(True)
            row.set_sensitive(not needed)
            row.set_subtitle(_("Needed for the codecs") if needed else subtitle)
        self._syncing = False
        self._apply_btn.set_sensitive(bool(self._selected()))

    # ---- apply -------------------------------------------------------------
    def _on_apply(self, _btn):
        selected = self._selected()
        done = {s for s, ok in self._state.items() if ok}
        steps = ops.plan(selected, done)
        self._ctx.confirm(
            _("Enable multimedia support?"),
            _("Packages will be downloaded and installed. This can take several "
              "minutes, depending on your connection."),
            ops.describe(steps),
            lambda: self._run(selected),
        )

    def _run(self, steps):
        self._busy(True)

        def done(ok, message):
            self._busy(False)
            self._refresh()
            if ok:
                self._ctx.toast(_("Multimedia support enabled"))
            else:
                self._ctx.error(message)

        privileged.run(MultimediaModule.helper, ["enable", *steps], done)

    def _busy(self, busy):
        self._spinner.set_visible(busy)
        self._status.set_visible(busy)
        self._status.set_label(_("Installing… this can take a few minutes"))
        self._apply_btn.set_sensitive(not busy)
        for row, _sub in self._rows.values():
            if busy:
                row.set_sensitive(False)
