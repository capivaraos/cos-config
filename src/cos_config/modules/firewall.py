"""Module: a simple firewall page (what is open, allow an app, strict mode)."""

import shutil
import threading

from gi.repository import Adw, GLib, Gtk

from .. import firewall as fw
from .. import privileged
from ..i18n import _
from ..ops import common
from ..ops import firewall as rootops
from . import Module


class FirewallModule(Module):
    id = "firewall"
    category = "network"
    icon_name = "security-high-symbolic"
    helper = "firewall"

    @property
    def title(self):
        return _("Firewall")

    @property
    def subtitle(self):
        return _("See what is open to the network and allow an app or a port")

    @property
    def keywords(self):
        return (_("port"), _("network"), "firewalld", "samba", "ssh", "kde connect", "steam")

    def supported(self, env):
        return shutil.which("firewall-cmd") is not None

    def build(self, ctx):
        return _FirewallPage(ctx)


def _preset_texts():
    return {
        "samba": (_("Share folders on the network"),
                  _("Other computers can open the folders you share (Samba)")),
        "ssh": (_("Remote terminal access (SSH)"),
                _("Log in to this computer from another one")),
        "web": (_("Web server"), _("Serve a site from this computer (ports 80 and 443)")),
        "ipp": (_("Share this computer's printer"), _("Other computers can print through it")),
        "kdeconnect": (_("Phone link (KDE Connect, GSConnect)"),
                       _("Notifications, files and clipboard between phone and computer")),
        "syncthing": ("Syncthing", _("Keep folders in sync between your devices")),
        "steam": ("Steam Remote Play", _("Stream games from this computer to another device")),
        "minecraft": (_("Minecraft server"), _("Friends on your network can join your world")),
        "remote-desktop": (_("Remote desktop (RDP, VNC)"),
                           _("See and control this screen from another computer")),
    }


class _FirewallPage(Adw.PreferencesPage):
    def __init__(self, ctx):
        super().__init__()
        self._ctx = ctx
        self._info = None
        self._groups = []
        self._switches = {}
        self._strict = None
        self._to_add = []      # port specs waiting to be applied
        self._to_remove = set()
        self._loading = False
        self._reload()

    def _add(self, group):
        self.add(group)
        self._groups.append(group)

    def _reload(self):
        self._to_add, self._to_remove = [], set()

        def work():
            GLib.idle_add(self._show, fw.read())

        threading.Thread(target=work, daemon=True).start()

    # ---- build ---------------------------------------------------------------
    def _show(self, info):
        for group in self._groups:
            self.remove(group)
        self._groups, self._switches, self._info = [], {}, info
        if info is None:
            self._add(Adw.PreferencesGroup(
                title=_("The firewall is not running"),
                description=_("firewalld is installed but stopped, so nothing is being "
                              "filtered and there is nothing to configure here."),
            ))
            return GLib.SOURCE_REMOVE
        self._loading = True
        high_open = fw.high_ports_open(info["ports"])

        group = Adw.PreferencesGroup(title=_("Firewall"))
        group.add(Adw.ActionRow(
            title=_("Firewall on"),
            subtitle=_("Profile of this network: {zone}").format(zone=info["zone"])))
        group.add(Adw.ActionRow(
            title=_("Ports above 1024"),
            subtitle=_("Open: any app can receive connections there. This is the default "
                       "on Fedora Workstation.") if high_open
            else _("Closed: only what is allowed below can be reached.")))
        self._add(group)

        group = Adw.PreferencesGroup(
            title=_("Allow from the network"),
            description=_("Turn on what other devices should be able to reach on this computer."))
        texts = _preset_texts()
        for preset in fw.PRESETS:
            state = fw.preset_state(preset, info)
            title, subtitle = texts[preset[0]]
            if state == "open":
                subtitle = _("Reachable now only because ports above 1024 are open")
            row = Adw.SwitchRow(title=title, subtitle=subtitle, active=state == "on")
            row.connect("notify::active", self._update)
            self._switches[preset[0]] = (row, preset, state)
            group.add(row)
        self._add(group)

        group = Adw.PreferencesGroup(title=_("Strict mode"))
        self._strict = Adw.SwitchRow(
            title=_("Close the ports above 1024"),
            subtitle=_("Only what is turned on above, and the ports listed below, stay reachable."),
            active=not high_open)
        self._strict.connect("notify::active", self._update)
        group.add(self._strict)
        self._add(group)

        self._ports_group = Adw.PreferencesGroup(
            title=_("Other ports"),
            description=_("For an app that is not in the list. Type the number, "
                          "or number/udp (for example 8080 or 5000/udp)."))
        self._entry = Adw.EntryRow(title=_("Port to open"), show_apply_button=True)
        self._entry.connect("apply", self._on_add_port)
        self._ports_group.add(self._entry)
        self._port_rows = []
        self._add(self._ports_group)
        self._fill_ports()

        self._apply_btn = Gtk.Button(label=_("Apply"), halign=Gtk.Align.END)
        self._apply_btn.add_css_class("suggested-action")
        self._apply_btn.add_css_class("pill")
        self._apply_btn.connect("clicked", self._on_apply)
        actions = Adw.PreferencesGroup()
        actions.add(self._apply_btn)
        self._add(actions)

        self._loading = False
        self._update()
        return GLib.SOURCE_REMOVE

    def _fill_ports(self):
        for row in self._port_rows:
            self._ports_group.remove(row)
        self._port_rows = []
        current = fw.custom_ports(self._info["ports"])
        for spec in current + [p for p in self._to_add if p not in current]:
            pending_add = spec not in current
            pending_remove = spec in self._to_remove
            subtitle = (_("Will be opened") if pending_add
                        else _("Will be closed") if pending_remove else _("Open now"))
            row = Adw.ActionRow(title=spec, subtitle=subtitle)
            button = Gtk.Button(valign=Gtk.Align.CENTER,
                                icon_name="edit-undo-symbolic" if (pending_add or pending_remove)
                                else "user-trash-symbolic")
            button.add_css_class("flat")
            button.connect("clicked", self._on_port_button, spec, pending_add)
            row.add_suffix(button)
            self._ports_group.add(row)
            self._port_rows.append(row)

    # ---- pending changes -------------------------------------------------------
    def _on_add_port(self, entry):
        text = entry.get_text().strip().lower()
        spec = text if "/" in text else f"{text}/tcp"
        try:
            spec = rootops.validate_port(spec)
        except common.ValidationError:
            self._ctx.toast(_("Type a port number from 1 to 65535, optionally with /udp"))
            return
        if spec.startswith(fw.HIGH_RANGE) or spec in self._info["ports"] or spec in self._to_add:
            self._ctx.toast(_("That port is already in the list"))
            return
        if self._covered(spec):
            self._ctx.toast(_("Port {port} is already open: the ports above 1024 are open")
                            .format(port=spec))
            return
        self._to_add.append(spec)
        entry.set_text("")
        self._fill_ports()
        self._update()

    def _on_port_button(self, _btn, spec, pending_add):
        if pending_add:
            self._to_add.remove(spec)
        elif spec in self._to_remove:
            self._to_remove.discard(spec)
        else:
            self._to_remove.add(spec)
        self._fill_ports()
        self._update()

    def _covered(self, spec):
        """Open anyway once the changes apply (high range stays open)?"""
        return (not self._strict.get_active()
                and fw.covered_by_high_range(spec, self._info["ports"]))

    def _changes(self):
        changes = []
        for row, preset, state in self._switches.values():
            if row.get_active() != (state == "on"):
                changes += fw.preset_changes(preset, row.get_active())
        if self._strict.get_active() == fw.high_ports_open(self._info["ports"]):
            changes += fw.strict_changes(self._strict.get_active())
        # With strict mode going on, the range is closed first (above), so a
        # high port added now is stored; otherwise firewalld would ignore it.
        changes += [("port", "add", spec) for spec in self._to_add if not self._covered(spec)]
        changes += [("port", "remove", spec) for spec in sorted(self._to_remove)]
        return changes

    def _update(self, *_args):
        if self._loading:
            return
        # Strict mode turned back off: pending high ports would be no-ops.
        stale = [spec for spec in self._to_add if self._covered(spec)]
        if stale:
            self._to_add = [spec for spec in self._to_add if spec not in stale]
            self._fill_ports()
        self._apply_btn.set_sensitive(bool(self._changes()))

    # ---- apply -----------------------------------------------------------------
    def _on_apply(self, _btn):
        changes = self._changes()
        zone = self._info["zone"]
        self._ctx.confirm(
            _("Change the firewall?"),
            _("The changes apply now and are kept after restarting."),
            rootops.describe(changes, zone),
            lambda: self._run(zone, changes),
        )

    def _run(self, zone, changes):
        self._apply_btn.set_sensitive(False)

        def done(ok, message):
            self._reload()
            if ok:
                self._ctx.toast(_("Firewall updated"))
            else:
                self._ctx.error(message)

        privileged.run(FirewallModule.helper, fw.helper_args(zone, changes), done)
