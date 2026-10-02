"""The "Settings" tab: modules grouped by category, with search.

Picking a module pushes its page on a navigation stack; the header there
has the usual back button.
"""

from gi.repository import Adw, Gtk

from . import modules
from .i18n import _


def _page(title, content, title_widget=None):
    header = Adw.HeaderBar(show_start_title_buttons=False, show_end_title_buttons=False)
    header.add_css_class("flat")
    if title_widget is not None:
        header.set_title_widget(title_widget)
    toolbar = Adw.ToolbarView(content=content)
    toolbar.add_top_bar(header)
    return Adw.NavigationPage(title=title, child=toolbar)


class ConfigPage(Adw.Bin):
    def __init__(self, ctx):
        super().__init__()
        self._ctx = ctx
        self._nav = Adw.NavigationView()  # a final type: wrapped, not subclassed
        self.set_child(self._nav)
        self._groups = []  # (PreferencesGroup, [(ActionRow, haystack)])

        self._search = Gtk.SearchEntry(placeholder_text=_("Search settings"), hexpand=True)
        self._search.connect("search-changed", self._on_search)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        if ctx.env.in_flatpak:
            box.append(Adw.Banner(
                title=_("Settings that change the system need the full version, "
                        "installed from your distribution's packages."),
                revealed=True,
            ))
        mods = modules.visible_modules(ctx.env)
        if mods:
            box.append(self._build_list(mods))
            title_widget = Adw.Clamp(maximum_size=420, child=self._search)
        else:
            box.append(Adw.StatusPage(
                icon_name="preferences-system-symbolic",
                title=_("No settings available here yet"),
                description=_("More settings for this system are on the way."),
                vexpand=True,
            ))
            title_widget = None
        self._nav.add(_page(_("Settings"), box, title_widget))

    def _build_list(self, mods):
        prefs = Adw.PreferencesPage(vexpand=True)
        for cat in modules.categories():
            members = [m for m in mods if m.category == cat.id]
            if not members:
                continue
            group = Adw.PreferencesGroup(title=cat.title)
            rows = []
            for mod in members:
                row = Adw.ActionRow(title=mod.title, subtitle=mod.subtitle, activatable=True)
                row.add_prefix(Gtk.Image(icon_name=mod.icon_name))
                row.add_suffix(Gtk.Image(icon_name="go-next-symbolic"))
                row.connect("activated", self._on_open, mod)
                group.add(row)
                haystack = " ".join([mod.title, mod.subtitle, cat.title, *mod.keywords])
                rows.append((row, haystack.casefold()))
            prefs.add(group)
            self._groups.append((group, rows))
        return prefs

    def _on_open(self, _row, mod):
        # Build fresh each time so the page always shows the current state.
        self._nav.push(_page(mod.title, mod.build(self._ctx)))

    def _on_search(self, entry):
        terms = entry.get_text().casefold().split()
        for group, rows in self._groups:
            shown = 0
            for row, haystack in rows:
                match = all(t in haystack for t in terms)
                row.set_visible(match)
                shown += match
            group.set_visible(shown > 0)
