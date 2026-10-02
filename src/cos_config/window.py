import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

from . import card, const, env, sysinfo  # noqa: E402
from .config_page import ConfigPage  # noqa: E402
from .i18n import _  # noqa: E402
from .live import LivePage  # noqa: E402
from .modules import ModuleContext  # noqa: E402


def _surface_to_texture(surface):
    """Convert a cairo ARGB32 surface to a Gdk.Texture for display."""
    surface.flush()
    w, h = surface.get_width(), surface.get_height()
    data = GLib.Bytes.new(bytes(surface.get_data()))
    return Gdk.MemoryTexture.new(
        w, h, Gdk.MemoryFormat.B8G8R8A8_PREMULTIPLIED, data, surface.get_stride()
    )


class CosConfigWindow(Adw.ApplicationWindow):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.set_title(const.APP_NAME)
        self.set_default_size(820, 720)

        self._rows = sysinfo.collect()
        self._surface = None
        self._timer_id = 0

        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        self._switcher = Adw.ViewSwitcher(policy=Adw.ViewSwitcherPolicy.WIDE)
        header.set_title_widget(self._switcher)

        menu = Gio.Menu()
        menu.append(_("Pin to desktop"), "app.pin")
        menu.append(_("About COS Config Center"), "app.about")
        menu.append(_("Quit"), "app.quit")
        menu_btn = Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu)
        header.pack_end(menu_btn)
        toolbar.add_top_bar(header)

        self._stack = Adw.ViewStack()
        self._switcher.set_stack(self._stack)
        self._live = LivePage()
        self._env = env.Environment.detect()
        self._stack.add_titled_with_icon(
            ConfigPage(ModuleContext(self._env, self)), "config", _("Settings"),
            "preferences-system-symbolic",
        )
        self._stack.add_titled_with_icon(
            self._build_system_page(), "system", _("System"), "computer-symbolic"
        )
        self._stack.add_titled_with_icon(
            self._live, "live", _("Live"), "utilities-system-monitor-symbolic"
        )
        self._stack.add_titled_with_icon(
            self._build_export_page(), "export", _("Share"), "emblem-shared-symbolic"
        )
        self._stack.add_titled_with_icon(
            self._build_about_page(), "about", "CapivaraOS", "starred-symbolic"
        )

        self._toast_overlay = Adw.ToastOverlay()
        self._toast_overlay.set_child(self._stack)
        toolbar.set_content(self._toast_overlay)
        self.set_content(toolbar)

        # Drive the live dashboard once per second; stop when the window closes.
        self._timer_id = GLib.timeout_add_seconds(1, self._live.tick)
        self.connect("close-request", self._on_close)

    def _on_close(self, *_):
        if self._timer_id:
            GLib.source_remove(self._timer_id)
            self._timer_id = 0
        return False

    def notify_toast(self, text):
        self._toast_overlay.add_toast(Adw.Toast.new(text))

    # ---- System page -----------------------------------------------------
    def _build_system_page(self):
        page = Adw.PreferencesPage()
        group = Adw.PreferencesGroup(
            title=_("System information"),
            description=_("A snapshot of this machine"),
        )
        for label, value in self._rows:
            row = Adw.ActionRow(title=label, subtitle=str(value))
            row.set_subtitle_selectable(True)
            group.add(row)
        page.add(group)
        return page

    # ---- Export / Share page --------------------------------------------
    def _build_export_page(self):
        box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=16,
            margin_top=18, margin_bottom=18, margin_start=18, margin_end=18,
        )
        self._picture = Gtk.Picture(
            can_shrink=True, content_fit=Gtk.ContentFit.CONTAIN,
        )
        self._picture.set_vexpand(True)
        frame = Gtk.Frame()
        frame.set_child(self._picture)
        box.append(frame)

        actions = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=10, halign=Gtk.Align.CENTER
        )
        save_btn = Gtk.Button(label=_("Save card…"))
        save_btn.add_css_class("suggested-action")
        save_btn.add_css_class("pill")
        save_btn.connect("clicked", self._on_save)
        actions.append(save_btn)
        box.append(actions)

        self._refresh_card()
        return box

    def _refresh_card(self):
        self._surface = card.render(self._rows)
        self._picture.set_paintable(_surface_to_texture(self._surface))

    def _on_save(self, _btn):
        dialog = Gtk.FileDialog(
            title=_("Save specs card"),
            initial_name="cos-config.png",
        )
        dialog.save(self, None, self._on_save_done)

    def _on_save_done(self, dialog, result):
        try:
            gfile = dialog.save_finish(result)
        except GLib.Error:
            return  # cancelled
        if gfile and self._surface is not None:
            card.save_png(self._surface, gfile.get_path())
            self._toast_overlay.add_toast(Adw.Toast.new(_("Card saved")))

    # ---- About / Try CapivaraOS page ------------------------------------
    def _build_about_page(self):
        status = Adw.StatusPage(
            title=_("Runs everywhere. Feels like home on CapivaraOS"),
            description=_(
                "COS Config Center is a gift from the CapivaraOS project — "
                "a friendly Linux distribution with a capybara at its heart.\n"
                "Like it? Give the whole system a try."
            ),
        )
        head = const.brand_head_png()
        tex = None
        if head:
            try:
                tex = Gdk.Texture.new_from_filename(head)
            except GLib.Error:
                tex = None
        if tex is not None:
            status.set_paintable(tex)
        else:
            status.set_icon_name("starred-symbolic")
        btns = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10,
                       halign=Gtk.Align.CENTER)
        try_btn = Gtk.Button(label=_("Try CapivaraOS"))
        try_btn.add_css_class("suggested-action")
        try_btn.add_css_class("pill")
        try_btn.connect("clicked", lambda *_: self._open_uri(const.DOWNLOAD_URL))
        site_btn = Gtk.Button(label=_("Visit capivaraos.org"))
        site_btn.add_css_class("pill")
        site_btn.connect("clicked", lambda *_: self._open_uri(const.WEBSITE_URL))
        btns.append(try_btn)
        btns.append(site_btn)
        status.set_child(btns)
        return status

    def _open_uri(self, uri):
        Gtk.UriLauncher(uri=uri).launch(self, None, None)
