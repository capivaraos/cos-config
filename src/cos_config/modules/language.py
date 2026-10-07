"""Module: system language and regional formats, plus language packs."""

import os
import threading

from gi.repository import Adw, GLib, Gtk

from .. import env as envmod
from .. import keyboard as kb
from .. import language as lg
from .. import privileged, subproc
from ..i18n import _
from ..ops import langpacks
from . import Module

LANGPACK_HELPER = "langpacks"


class LanguageModule(Module):
    id = "language"
    category = "input"
    icon_name = "preferences-desktop-locale-symbolic"

    @property
    def title(self):
        return _("Language and formats")

    @property
    def subtitle(self):
        return _("System language, and dates and currency your way")

    @property
    def keywords(self):
        return (_("language"), _("date"), _("currency"), _("region"), "locale", _("spell check"))

    def supported(self, env):
        return not env.in_flatpak

    def build(self, ctx):
        return _LanguagePage(ctx)


def _region_names():
    return {
        "pt_BR": _("Brazil"),
        "en_US": _("United States"),
        "pt_PT": _("Portugal"),
        "es_ES": _("Spain"),
    }


def _radio_rows(group, items, on_toggle):
    """items: [(code, title, subtitle)] -> {code: CheckButton}."""
    checks, first = {}, None
    for code, title, subtitle in items:
        check = Gtk.CheckButton(group=first)
        first = first or check
        row = Adw.ActionRow(title=title, subtitle=subtitle, activatable_widget=check)
        row.add_prefix(check)
        check.connect("toggled", on_toggle)
        checks[code] = check
        group.add(row)
    return checks


class _LanguagePage(Adw.PreferencesPage):
    def __init__(self, ctx):
        super().__init__()
        self._ctx = ctx
        self._desktop = kb.desktop_of(ctx.env.desktops)
        self._can_install = (ctx.env.family == envmod.FEDORA
                             and privileged.available(LANGPACK_HELPER))
        self._now = (None, None)
        self._available = set()
        self._installed = set()  # language pack package names installed
        self._has_accounts = False
        self._groups = []
        self._add(Adw.PreferencesGroup(
            title=_("Loading…"), description=_("Reading the current settings.")))
        threading.Thread(target=self._load, daemon=True).start()

    def _add(self, group):
        self.add(group)
        self._groups.append(group)

    # ---- state -------------------------------------------------------------
    def _load(self):
        system = lg.system_locale()
        accounts = lg.accounts_language(os.getuid())
        self._has_accounts = accounts is not None
        now = lg.current(self._desktop, os.getuid(), system, accounts)
        available = lg.available_codes()
        installed = {pkg for pkg in langpacks.PACKAGES.values() if lg.is_installed(pkg)}
        GLib.idle_add(self._build, now, available, installed)

    def _offered(self, code):
        return code in self._available or (self._can_install and code in langpacks.PACKAGES)

    def _build(self, now, available, installed):
        self._now, self._available, self._installed = now, available, installed
        # Rebuilt from scratch each time (first load and after applying).
        for group in self._groups:
            self.remove(group)
        self._groups = []

        group = Adw.PreferencesGroup(
            title=_("Language"), description=_("The language of menus and apps."))
        langs = [(c, name, "") for c, name in lg.LANGUAGES if self._offered(c)]
        self._lang_checks = _radio_rows(group, langs, self._update)
        self._add(group)

        group = Adw.PreferencesGroup(
            title=_("Formats"), description=_("How dates, numbers and money are shown."))
        regions = _region_names()
        fmts = [(c, regions[c], lg.FORMAT_EXAMPLES[c]) for c in lg.FORMATS if self._offered(c)]
        self._fmt_checks = _radio_rows(group, fmts, self._update)
        self._add(group)

        group = Adw.PreferencesGroup()
        self._packs = Adw.SwitchRow(
            title=_("Language pack"),
            subtitle=_("Spell checking, fonts and translations for the chosen language"),
            visible=self._can_install,
        )
        self._packs.connect("notify::active", self._update)
        group.add(self._packs)
        self._add(group)

        self._add(Adw.PreferencesGroup(
            title=_("Where it applies"),
            description=_("To the whole system (including the login screen) and to "
                          "your user. It takes effect after you log out and back in."),
        ))

        self._apply_btn = Gtk.Button(label=_("Apply"), halign=Gtk.Align.END)
        self._apply_btn.add_css_class("suggested-action")
        self._apply_btn.add_css_class("pill")
        self._apply_btn.connect("clicked", self._on_apply)
        actions = Adw.PreferencesGroup()
        actions.add(self._apply_btn)
        self._add(actions)

        lang, fmt = now
        if lang in self._lang_checks:
            self._lang_checks[lang].set_active(True)
        if fmt in self._fmt_checks:
            self._fmt_checks[fmt].set_active(True)
        self._update()
        return GLib.SOURCE_REMOVE

    @staticmethod
    def _picked(checks):
        return next((c for c, chk in checks.items() if chk.get_active()), None)

    def _plan(self):
        """(lang, fmt, langpack codes, locale changed?)."""
        lang = self._picked(self._lang_checks)
        fmt = self._picked(self._fmt_checks) or lang
        packs = []
        if self._can_install and lang:
            packs = lg.langpack_codes(lang, fmt, self._available,
                                      lambda pkg: pkg in self._installed)
            if not self._packs.get_active():
                # Only what a chosen locale cannot work without.
                packs = [c for c in packs if c not in self._available]
        changed = bool(lang) and (lang, fmt) != self._now
        return lang, fmt, packs, changed

    def _update(self, *_args):
        lang = self._picked(self._lang_checks)
        if self._can_install and lang in langpacks.PACKAGES:
            have = langpacks.PACKAGES[lang] in self._installed
            self._packs.set_sensitive(not have)
            if have:
                self._packs.set_active(True)
                self._packs.set_subtitle(_("Already installed"))
            else:
                self._packs.set_subtitle(
                    _("Spell checking, fonts and translations for the chosen language"))
        _lang, _fmt, packs, changed = self._plan()
        self._apply_btn.set_sensitive(bool(changed or packs))

    # ---- apply -------------------------------------------------------------
    def _user_steps(self, lang, fmt):
        return [lg.system_argv(lang, fmt),
                *lg.user_argvs(self._desktop, lang, fmt, os.getuid(), self._has_accounts)]

    def _on_apply(self, _btn):
        lang, fmt, packs, changed = self._plan()
        commands = []
        if packs:
            commands.append("sudo " + " ".join(langpacks.install_argv(packs)))
        if changed:
            commands += [kb.quote(a) for a in self._user_steps(lang, fmt)]
        self._ctx.confirm(
            _("Change the language and formats?"),
            _("You will be asked for the administrator password. Log out and back "
              "in afterwards to see the change everywhere."),
            commands,
            lambda: self._run(lang, fmt, packs, changed),
        )

    def _run(self, lang, fmt, packs, changed):
        self._apply_btn.set_sensitive(False)

        def finished(ok, message):
            threading.Thread(target=self._load, daemon=True).start()
            if ok:
                self._ctx.toast(_("Saved. Log out and back in to see it everywhere."))
            else:
                self._ctx.error(message)

        def after_packs(ok, message):
            if not ok:
                finished(False, message)
            elif changed:
                subproc.run_sequence(self._user_steps(lang, fmt), finished)
            else:
                finished(True, "")

        if packs:
            privileged.run(LANGPACK_HELPER, ["install", *packs], after_packs)
        else:
            after_packs(True, "")
