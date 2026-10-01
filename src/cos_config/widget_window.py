"""Compact "pin to desktop" widget: CPU/RAM gauges + a network sparkline.

Where the compositor supports the wlr-layer-shell protocol (KDE Plasma, Xfce,
wlroots — including the CapivaraOS Marsh/Pup spins) the window is anchored to
the desktop as a background widget via gtk4-layer-shell. Everywhere else
(notably GNOME/Mutter, which does not implement layer-shell) it degrades to a
small frameless floating window the user can place and keep on top manually.
"""

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk  # noqa: E402

from . import const, metrics  # noqa: E402
from .i18n import _  # noqa: E402
from .widgets import Gauge, Sparkline  # noqa: E402


def _hex(rgb):
    return "#%02x%02x%02x" % tuple(int(round(c * 255)) for c in rgb)


def _load_layer_shell():
    """Return the Gtk4LayerShell module if usable on this compositor, else None."""
    try:
        gi.require_version("Gtk4LayerShell", "1.0")
        from gi.repository import Gtk4LayerShell as LS
    except (ValueError, ImportError):
        return None
    try:
        if LS.is_supported():
            return LS
    except Exception:
        pass
    return None


class CompactWidget(Gtk.ApplicationWindow):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.set_title(const.APP_NAME)
        self.set_resizable(False)
        self.add_css_class("capivara-widget")

        self.sampler = metrics.Sampler()
        self._timer_id = 0

        # Layer-shell must be initialised before the window is realised.
        self._ls = _load_layer_shell()
        if self._ls is not None:
            self._setup_layer_shell()

        self._build_ui()
        self.connect("close-request", self._on_close)
        self._timer_id = GLib.timeout_add_seconds(1, self._tick)

    def is_pinned_to_desktop(self):
        """True when actually anchored to the desktop (layer-shell active)."""
        return self._ls is not None

    def _setup_layer_shell(self):
        ls = self._ls
        ls.init_for_window(self)
        ls.set_namespace(self, "cos-config-widget")
        ls.set_layer(self, ls.Layer.BOTTOM)  # behind normal windows
        ls.set_anchor(self, ls.Edge.TOP, True)
        ls.set_anchor(self, ls.Edge.RIGHT, True)
        ls.set_margin(self, ls.Edge.TOP, 28)
        ls.set_margin(self, ls.Edge.RIGHT, 28)
        ls.set_keyboard_mode(self, ls.KeyboardMode.NONE)

    # ---- UI --------------------------------------------------------------
    def _build_ui(self):
        card = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=8,
            margin_top=10, margin_bottom=12, margin_start=12, margin_end=12,
        )
        card.add_css_class("card")

        # In layer-shell (pinned) mode the surface has no decorations, so add a
        # small strip with a title and a close/unpin button. In the floating
        # fallback we keep the window's own titlebar instead (that is where the
        # user finds "Always on top"), so the strip would just duplicate it.
        if self._ls is not None:
            strip = Gtk.Box(spacing=6)
            title = Gtk.Label(xalign=0, hexpand=True)
            title.set_markup(f"<b>{const.APP_NAME}</b>")
            title.add_css_class("caption")
            close = Gtk.Button(icon_name="window-close-symbolic")
            close.add_css_class("flat")
            close.add_css_class("circular")
            close.connect("clicked", lambda *_: self.close())
            strip.append(title)
            strip.append(close)
            card.append(strip)

        # CPU + RAM gauges.
        row = Gtk.Box(spacing=10, homogeneous=True)
        self.cpu_gauge = Gauge(const.CHART_BLUE)
        self.cpu_gauge.set_content_height(92)
        self.ram_gauge = Gauge(const.CHART_TEAL)
        self.ram_gauge.set_content_height(92)
        row.append(self._labeled(self.cpu_gauge, "CPU"))
        row.append(self._labeled(self.ram_gauge, "RAM"))
        card.append(row)

        # Network mini sparkline + legend.
        self.net_spark = Sparkline([
            (const.CHART_BLUE, self.sampler.net_rx_hist),
            (const.CHART_ORANGE, self.sampler.net_tx_hist),
        ], min_top=1024.0)
        self.net_spark.set_content_height(40)
        card.append(self.net_spark)
        self.net_legend = Gtk.Label(xalign=0)
        self.net_legend.add_css_class("caption")
        self.net_legend.set_use_markup(True)
        card.append(self.net_legend)

        self.set_child(card)
        self.set_default_size(260, -1)

    def _labeled(self, widget, text):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.append(widget)
        lbl = Gtk.Label(label=text)
        lbl.add_css_class("caption")
        lbl.add_css_class("dim-label")
        box.append(lbl)
        return box

    # ---- tick / teardown -------------------------------------------------
    def _tick(self):
        s = self.sampler.sample()
        self.cpu_gauge.set_value(s["cpu"])
        self.ram_gauge.set_value(s["mem"]["pct"])
        self.net_spark.queue_draw()
        self.net_legend.set_markup(
            f"<span foreground='{_hex(const.CHART_BLUE)}'>●</span> "
            + _("Download {rate}").format(rate=metrics.human_rate(s["net_rx"]))
            + f"   <span foreground='{_hex(const.CHART_ORANGE)}'>●</span> "
            + _("Upload {rate}").format(rate=metrics.human_rate(s["net_tx"]))
        )
        return True

    def _on_close(self, *_):
        if self._timer_id:
            GLib.source_remove(self._timer_id)
            self._timer_id = 0
        return False
