"""Module: free disk space (caches, old logs, trash, unused runtimes)."""

import threading

from gi.repository import Adw, GLib, Gtk

from .. import cleanup as cl
from .. import privileged, subproc
from ..i18n import _
from ..ops import cleanup as rootops
from . import Module


class CleanupModule(Module):
    id = "cleanup"
    category = "storage"
    icon_name = "user-trash-symbolic"
    helper = "cleanup"

    @property
    def title(self):
        return _("Free disk space")

    @property
    def subtitle(self):
        return _("Remove caches, old logs and other things that rebuild themselves")

    @property
    def keywords(self):
        return (_("clean"), _("disk full"), _("cache"), _("trash"), _("space"))

    def build(self, ctx):
        return _CleanupPage(ctx)


def _texts():
    return {
        "trash": (_("Trash"), _("Files you already deleted")),
        "thumbnails": (_("Image thumbnails"),
                       _("Previews of pictures and videos, created again when needed")),
        "flatpak-user": (_("Unused Flatpak runtimes (yours)"),
                         _("Support files that no installed app uses")),
        "podman": (_("Unused container images"),
                   _("Images no container uses; they are downloaded again when needed")),
        "pkgcache": (_("Downloaded packages"),
                     _("Copies of updates already installed, and package lists")),
        "journal": (_("Old system logs"), _("Keeps the last two weeks")),
        "coredumps": (_("Crash dumps"), _("Memory saved when a program crashed")),
        "flatpak": (_("Unused Flatpak runtimes (system)"),
                    _("Support files that no installed app uses")),
    }


class _CleanupPage(Adw.PreferencesPage):
    def __init__(self, ctx):
        super().__init__()
        self._ctx = ctx
        self._sizes = {}
        self._checks = {}
        self._labels = {}
        texts = _texts()

        for title, description, items in (
            (_("Your files"), _("No password needed."), cl.USER_ITEMS),
            (_("System"), _("Asks for the administrator password."), cl.SYSTEM_ITEMS),
        ):
            group = Adw.PreferencesGroup(title=title, description=description)
            for item in items:
                check = Gtk.CheckButton(valign=Gtk.Align.CENTER)
                check.connect("toggled", self._update)
                label = Gtk.Label(label="…")
                label.add_css_class("dim-label")
                row = Adw.ActionRow(title=texts[item][0], subtitle=texts[item][1],
                                    activatable_widget=check, sensitive=False)
                row.add_prefix(check)
                row.add_suffix(label)
                group.add(row)
                self._checks[item] = (check, row)
                self._labels[item] = label
            self.add(group)

        self._free = Adw.ActionRow(title=_("Free space on the system disk"), subtitle="…")
        group = Adw.PreferencesGroup()
        group.add(self._free)
        self.add(group)

        self._button = Gtk.Button(label=_("Clean selected"), halign=Gtk.Align.END, sensitive=False)
        self._button.add_css_class("suggested-action")
        self._button.add_css_class("pill")
        self._button.connect("clicked", self._on_clean)
        actions = Adw.PreferencesGroup()
        actions.add(self._button)
        self.add(actions)

        self._measure(first=True)

    # ---- state -------------------------------------------------------------
    def _measure(self, first=False):
        def work():
            sizes = cl.measure()
            GLib.idle_add(self._show, sizes, cl.free_space(), first)

        threading.Thread(target=work, daemon=True).start()

    def _show(self, sizes, free, first):
        self._sizes = sizes
        for item, (check, row) in self._checks.items():
            kind, amount = sizes[item]
            if kind == "count":
                text = _("{n} unused").format(n=amount) if amount else _("None")
            elif item == "journal":
                text = _("{size} of logs").format(size=cl.human(amount))
            else:
                text = cl.human(amount) if amount else _("Empty")
            self._labels[item].set_label(text)
            row.set_sensitive(amount > 0)
            if amount <= 0:
                check.set_active(False)
            elif first:
                check.set_active(item in cl.DEFAULT_ON)
        self._free.set_subtitle(cl.human(free))
        self._update()
        return GLib.SOURCE_REMOVE

    def _selected(self):
        return [item for item, (check, _row) in self._checks.items() if check.get_active()]

    def _update(self, *_args):
        selected = self._selected()
        total = sum(self._sizes[i][1] for i in selected
                    if i in self._sizes and self._sizes[i][0] == "bytes" and i != "journal")
        label = _("Clean selected")
        if total:
            label = _("Clean selected ({size})").format(size=cl.human(total))
        self._button.set_label(label)
        self._button.set_sensitive(bool(selected))

    # ---- clean -------------------------------------------------------------
    def _on_clean(self, _btn):
        selected = self._selected()
        user = [i for i in selected if i in cl.USER_ITEMS]
        system = [i for i in selected if i in cl.SYSTEM_ITEMS]
        commands = cl.describe_user(user) + rootops.describe(system, self._ctx.env.family)
        self._ctx.confirm(
            _("Clean the selected items?"),
            _("They are removed for good. Everything listed is created or downloaded "
              "again when it is needed."),
            commands,
            lambda: self._run(user, system),
        )

    def _run(self, user, system):
        self._button.set_sensitive(False)
        before = cl.free_space()

        def finished(ok, message):
            freed = max(0, cl.free_space() - before)
            self._measure()
            if ok:
                self._ctx.toast(_("Done: {size} freed").format(size=cl.human(freed)))
            else:
                self._ctx.error(message)

        def after_user(ok, message):
            if not ok or not system:
                finished(ok, message)
            else:
                privileged.run(CleanupModule.helper, ["clean", *system], finished)

        if user:
            subproc.run_sequence(cl.user_steps(user), after_user)
        else:
            after_user(True, "")
