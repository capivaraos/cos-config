"""Module: Brazilian keyboard — layout (ABNT2 / US International) and ç."""

import threading

from gi.repository import Adw, GLib, Gtk

from .. import keyboard as kb
from .. import subproc
from ..i18n import _
from . import Module


class KeyboardModule(Module):
    id = "keyboard"
    category = "input"
    icon_name = "input-keyboard-symbolic"

    @property
    def title(self):
        return _("Brazilian keyboard")

    @property
    def subtitle(self):
        return _("ABNT2 or US International, and ' + c typing ç")

    @property
    def keywords(self):
        return ("abnt2", "abnt", _("cedilla"), "ç", _("accents"), _("layout"), "us intl")

    def supported(self, env):
        # Writes ~/.XCompose and runs desktop tools: not from the sandbox.
        return not env.in_flatpak

    def build(self, ctx):
        return _KeyboardPage(ctx)


def _layout_texts():
    return {
        "abnt2": (_("ABNT2 (Brazilian)"), _("Brazilian keyboard, with its own Ç key")),
        "us-intl": (_("US International"),
                    _("US keys; accents with ' ` ~ ^ \" — ' then c types ç")),
        "us": (_("US"), _("No accents")),
    }


class _KeyboardPage(Adw.PreferencesPage):
    def __init__(self, ctx):
        super().__init__()
        self._ctx = ctx
        self._desktop = kb.desktop_of(ctx.env.desktops)
        self._current = None  # layout id now in use, or None
        self._cedilla_now = False
        self._system_now = None

        # ---- layout
        self._layout_group = Adw.PreferencesGroup(
            title=_("Keyboard layout"),
            description=_("Choose the keyboard you have. It replaces the layouts you "
                          "use now; input methods (like Japanese) are kept."),
        )
        self._checks = {}
        first = None
        for lid, (title, subtitle) in _layout_texts().items():
            check = Gtk.CheckButton(group=first)
            first = first or check
            row = Adw.ActionRow(title=title, subtitle=subtitle, activatable_widget=check)
            row.add_prefix(check)
            check.connect("toggled", self._update)
            self._checks[lid] = check
            self._layout_group.add(row)
        if self._desktop is None:
            self._layout_group.set_description(
                _("Changing the layout is not supported on this desktop yet; "
                  "the ç setting below still works."))
            self._layout_group.set_sensitive(False)
        self.add(self._layout_group)

        # ---- cedilla
        group = Adw.PreferencesGroup(title=_("Cedilla"))
        self._cedilla = Adw.SwitchRow(
            title=_("' + c types ç"),
            subtitle=_("For US International. Without it, many systems type ć."),
        )
        self._cedilla.connect("notify::active", self._update)
        group.add(self._cedilla)
        self.add(group)

        # ---- login screen
        group = Adw.PreferencesGroup(title=_("Login screen"))
        self._login = Adw.SwitchRow(
            title=_("Use this layout on the login screen too"),
            subtitle=_("Also the text console. Asks for the administrator password."),
        )
        self._login.connect("notify::active", self._update)
        group.add(self._login)
        self.add(group)

        # ---- try it
        group = Adw.PreferencesGroup(
            title=_("Try it"),
            description=_("Apps that were already open may need to be restarted."),
        )
        group.add(Adw.EntryRow(title=_("Type ' and then c here")))
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
        self._apply_btn.set_sensitive(False)

        def work():
            layout = kb.current_layout(self._desktop)
            system = kb.system_layout()
            cedilla = kb.has_cedilla_block(kb.read_compose())
            GLib.idle_add(self._show, layout, system, cedilla)

        threading.Thread(target=work, daemon=True).start()

    def _show(self, layout, system, cedilla):
        self._current = kb.layout_id(*layout) if layout else None
        self._system_now = kb.layout_id(*system) if system else None
        self._cedilla_now = cedilla
        for lid, check in self._checks.items():
            check.set_active(lid == self._current)
        self._cedilla.set_active(cedilla)
        self._login.set_active(False)
        self._update()
        return GLib.SOURCE_REMOVE

    def _chosen(self):
        for lid, check in self._checks.items():
            if check.get_active():
                return lid
        return None

    def _changes(self):
        """(layout id or None, cedilla True/False/None, login screen bool)."""
        chosen = self._chosen()
        lid = chosen if self._desktop and chosen and chosen != self._current else None
        cedilla = self._cedilla.get_active()
        cedilla = None if cedilla == self._cedilla_now else cedilla
        target = chosen or self._current
        login = bool(self._login.get_active() and target and target != self._system_now)
        return lid, cedilla, login, target

    def _update(self, *_args):
        # Picking US International suggests the cedilla fix.
        if self._chosen() == "us-intl" and self._current != "us-intl" and not self._cedilla_now:
            if not self._cedilla.get_active():
                self._cedilla.set_active(True)
                return  # notify::active calls back into _update
        lid, cedilla, login, _target = self._changes()
        self._apply_btn.set_sensitive(bool(lid or cedilla is not None or login))

    # ---- apply -------------------------------------------------------------
    def _on_apply(self, _btn):
        lid, cedilla, login, target = self._changes()
        sources = kb.gnome_sources() if self._desktop == kb.GNOME and lid else ()
        commands = kb.describe(lid, self._desktop, cedilla, target if login else None, sources)
        self._ctx.confirm(
            _("Change the keyboard settings?"),
            _("Your desktop keyboard settings will change for your user. "
              "Apps that were already open may need to be restarted."),
            commands,
            lambda: self._run(lid, cedilla, login, target, sources),
        )

    def _run(self, lid, cedilla, login, target, sources):
        steps = []
        if lid:
            if self._desktop == kb.GNOME:
                steps.append(kb.gnome_set_argv(sources, lid))
            elif self._desktop == kb.KDE:
                steps += kb.kde_set_argvs(lid)
            elif self._desktop == kb.XFCE:
                steps += kb.xfce_set_argvs(lid)
        if cedilla is not None:
            text = kb.read_compose()
            new = kb.with_cedilla(text) if cedilla else kb.without_cedilla(text)
            steps.append(lambda: kb.write_compose(new))
            if kb.ibus_running():
                steps.append(["ibus", "restart"])
        if login:
            steps.append(kb.login_screen_argv(target))
        self._apply_btn.set_sensitive(False)

        def done(ok, message):
            self._refresh()
            if ok:
                self._ctx.toast(_("Keyboard settings updated"))
            else:
                self._ctx.error(message)

        subproc.run_sequence(steps, done)
