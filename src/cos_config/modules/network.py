"""Module: computer name, remote login (SSH) and encrypted DNS."""

import getpass
import os
import shutil
import threading

from gi.repository import Adw, GLib, Gtk

from .. import network as net
from .. import privileged, subproc
from ..i18n import _
from ..ops import network as rootops
from . import Module


class NetworkModule(Module):
    id = "network"
    category = "network"
    icon_name = "network-workgroup-symbolic"
    helper = "network"

    @property
    def title(self):
        return _("Remote access and network")

    @property
    def subtitle(self):
        return _("Computer name, remote login (SSH) and private DNS")

    @property
    def keywords(self):
        return ("ssh", "dns", "hostname", _("computer name"), _("remote"), "cloudflare", "quad9")

    def supported(self, env):
        return shutil.which("hostnamectl") is not None

    def build(self, ctx):
        return _NetworkPage(ctx)


def _dns_choices():
    # (id, name, what it does). The first one removes our setting.
    return [
        (rootops.AUTO, _("Automatic"), _("The DNS your network gives you, usually not encrypted")),
        ("cloudflare", "Cloudflare", _("1.1.1.1, encrypted, no filtering")),
        ("quad9", "Quad9", _("Encrypted, blocks known malicious sites")),
        ("google", "Google", _("8.8.8.8, encrypted, no filtering")),
        ("adguard", "AdGuard", _("Encrypted, blocks ads and trackers")),
    ]


class _NetworkPage(Adw.PreferencesPage):
    def __init__(self, ctx):
        super().__init__()
        self._ctx = ctx
        self._loading = True
        self._ssh_on = False
        self._dns_now = rootops.AUTO
        self._public = None
        self._hostname = ""

        # ---- computer name
        group = Adw.PreferencesGroup(
            title=_("Computer name"),
            description=_("How this computer shows up on the network. Letters, digits "
                          "and hyphens only."))
        self._name = Adw.EntryRow(title=_("Name"), show_apply_button=True)
        self._name.connect("apply", self._on_name)
        group.add(self._name)
        self.add(group)

        # ---- SSH
        group = Adw.PreferencesGroup(
            title=_("Remote login (SSH)"),
            description=_("Lets you open a terminal on this computer from another one. "
                          "Anyone who knows a user's password can try to log in, so "
                          "leave it off if you do not use it."))
        self._ssh = Adw.SwitchRow(title=_("Allow remote login"))
        self._ssh.connect("notify::active", self._on_ssh)
        group.add(self._ssh)
        self._key = Adw.ActionRow(title=_("Your SSH key"))
        self._key_btn = Gtk.Button(valign=Gtk.Align.CENTER)
        self._key_btn.connect("clicked", self._on_key)
        self._key.add_suffix(self._key_btn)
        group.add(self._key)
        self.add(group)

        # ---- DNS
        group = Adw.PreferencesGroup(
            title=_("Private DNS"),
            description=_("DNS turns site names into addresses. An encrypted DNS keeps "
                          "others on the network from seeing which sites you look up."))
        self._choices = _dns_choices()
        self._dns = Adw.ComboRow(
            title=_("DNS service"),
            model=Gtk.StringList.new([choice[1] for choice in self._choices]))
        self._dns.connect("notify::selected", self._update_dns_button)
        group.add(self._dns)
        self._dns_btn = Gtk.Button(label=_("Apply"), halign=Gtk.Align.END, margin_top=12)
        self._dns_btn.add_css_class("suggested-action")
        self._dns_btn.add_css_class("pill")
        self._dns_btn.connect("clicked", self._on_dns)
        self._dns_btn.set_sensitive(False)
        group.add(self._dns_btn)
        if net.dns_available():
            self.add(group)

        self._refresh()

    # ---- state -----------------------------------------------------------------
    def _refresh(self):
        def work():
            state = (net.current_hostname(), net.ssh_state(), net.public_key(), net.dns_provider())
            GLib.idle_add(self._show, *state)

        threading.Thread(target=work, daemon=True).start()

    def _show(self, hostname, ssh, public, provider):
        self._loading = True
        self._hostname = hostname
        # Off and on again: otherwise the apply button shows for our own text.
        self._name.set_show_apply_button(False)
        self._name.set_text(hostname)
        self._name.set_show_apply_button(True)
        self._ssh_on = ssh["enabled"] or ssh["active"]
        self._ssh.set_active(self._ssh_on)
        user = getpass.getuser()
        self._ssh.set_subtitle(
            _("On. From another computer: ssh {user}@{host}").format(user=user, host=hostname)
            if self._ssh_on else _("Off"))
        self._public = public
        if public:
            self._key.set_subtitle(net.key_summary(public))
            self._key_btn.set_label(_("Copy public key"))
        else:
            self._key.set_subtitle(_("None yet. A key lets you log in to servers and "
                                     "sites like GitHub without a password."))
            self._key_btn.set_label(_("Create key"))
        self._dns_now = provider or rootops.AUTO
        ids = [choice[0] for choice in self._choices]
        self._dns.set_selected(ids.index(self._dns_now))
        self._loading = False
        self._update_dns_button()
        return GLib.SOURCE_REMOVE

    def _done(self, success_text):
        def callback(ok, message):
            self._refresh()
            if ok:
                self._ctx.toast(success_text)
            else:
                self._ctx.error(message)
        return callback

    # ---- computer name -----------------------------------------------------------
    def _on_name(self, entry):
        try:
            name = net.valid_hostname(entry.get_text())
        except ValueError:
            self._ctx.toast(_("Use only letters, digits and hyphens (no spaces)"))
            return
        if name == self._hostname:
            self._refresh()
            return
        argv = net.hostname_argv(name)
        self._ctx.confirm(
            _("Change the computer name?"),
            _("The computer will be called {name}. Some apps only notice after you "
              "log out and back in.").format(name=name),
            [" ".join(argv)],
            lambda: subproc.run_sequence([argv], self._done(_("Computer name changed"))),
            on_cancel=self._refresh,
        )

    # ---- SSH ---------------------------------------------------------------------
    def _on_ssh(self, row, _pspec):
        if self._loading or row.get_active() == self._ssh_on:
            return
        enable = row.get_active()
        state = net.ssh_state()
        zone = rootops._firewall_zone() if enable else None
        commands = ["sudo " + " ".join(cmd) for cmd in
                    rootops.ssh_commands(enable, state["unit"], self._ctx.env.family, zone)]
        if enable:
            heading = _("Allow remote login?")
            body = _("The SSH server will start now and with the computer. People on your "
                     "network will be able to try to log in with a user name and password.")
        else:
            heading = _("Turn remote login off?")
            body = _("The SSH server will stop and no longer start with the computer. Sessions that are already open continue until they end.")
        self._ctx.confirm(
            heading, body, commands,
            lambda: privileged.run(NetworkModule.helper, ["ssh", "on" if enable else "off"],
                                   self._done(_("Remote login updated"))),
            on_cancel=self._refresh,
        )

    def _on_key(self, _btn):
        if self._public:
            self.get_clipboard().set(self._public)
            self._ctx.toast(_("Public key copied"))
            return
        argv = net.keygen_argv()
        self._ctx.confirm(
            _("Create an SSH key?"),
            _("A key pair is created in your .ssh folder, with no passphrase. Keep the "
              "private file to yourself; the public one is what you give to servers."),
            [" ".join(argv[:5] + ['""'] + argv[6:])],
            lambda: subproc.run_sequence(
                [lambda: os.makedirs(os.path.dirname(net.key_path()), mode=0o700, exist_ok=True),
                 argv],
                self._done(_("SSH key created"))),
        )

    # ---- DNS ---------------------------------------------------------------------
    def _selected_dns(self):
        return self._choices[self._dns.get_selected()][0]

    def _update_dns_button(self, *_args):
        self._dns.set_subtitle(self._choices[self._dns.get_selected()][2])
        if not self._loading:
            self._dns_btn.set_sensitive(self._selected_dns() != self._dns_now)

    def _on_dns(self, _btn):
        provider = self._selected_dns()
        label = self._choices[self._dns.get_selected()][1]
        if provider == rootops.AUTO:
            body = _("The DNS your network gives you will be used again.")
        else:
            body = _("All name lookups will go, encrypted, to {service}. Names that only "
                     "exist on your local network may stop working. If no name resolves, "
                     "the previous setting is restored automatically.").format(service=label)
        self._ctx.confirm(
            _("Change the DNS service?"), body, rootops.describe_dns(provider),
            lambda: self._run_dns(provider),
        )

    def _run_dns(self, provider):
        self._dns_btn.set_sensitive(False)
        privileged.run(NetworkModule.helper, ["dns", provider], self._done(_("DNS updated")))
