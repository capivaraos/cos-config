"""The Live dashboard page: real-time gauges, per-core bars and sparklines.

The page owns a metrics.Sampler; the window drives it by calling tick() on a
1-second timer. Widgets read the sampler's rolling histories directly, so
tick() just refreshes values and redraws.
"""

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from . import const, metrics  # noqa: E402
from .i18n import _  # noqa: E402
from .widgets import CoreBars, Gauge, Sparkline  # noqa: E402


def _hex(rgb):
    return "#%02x%02x%02x" % tuple(int(round(c * 255)) for c in rgb)


def _card(title_text):
    outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    outer.add_css_class("card")
    outer.set_hexpand(True)
    inner = Gtk.Box(
        orientation=Gtk.Orientation.VERTICAL, spacing=8,
        margin_top=14, margin_bottom=14, margin_start=16, margin_end=16,
    )
    title = Gtk.Label(xalign=0)
    title.set_markup(f"<b>{title_text}</b>")
    title.add_css_class("dim-label")
    inner.append(title)
    outer.append(inner)
    return outer, inner


def _muted(text=""):
    lbl = Gtk.Label(xalign=0, label=text)
    lbl.add_css_class("caption")
    lbl.set_wrap(True)
    return lbl


class LivePage(Gtk.ScrolledWindow):
    def __init__(self):
        super().__init__()
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.sampler = metrics.Sampler()
        s = self.sampler

        root = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=14,
            margin_top=18, margin_bottom=18, margin_start=18, margin_end=18,
        )
        self.set_child(root)

        # Row A — CPU + Memory gauges.
        row_a = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14,
                        homogeneous=True)
        cpu_card, cpu_in = _card(_("Processor"))
        self.cpu_gauge = Gauge(const.CHART_BLUE)
        self.cpu_caption = _muted()
        cpu_in.append(self.cpu_gauge)
        cpu_in.append(self.cpu_caption)

        mem_card, mem_in = _card(_("Memory"))
        self.mem_gauge = Gauge(const.CHART_TEAL)
        self.mem_caption = _muted()
        mem_in.append(self.mem_gauge)
        mem_in.append(self.mem_caption)

        row_a.append(cpu_card)
        row_a.append(mem_card)
        root.append(row_a)

        # Row B — per-core bars.
        core_card, core_in = _card(_("Per-core usage"))
        self.corebars = CoreBars(const.CHART_BLUE)
        core_in.append(self.corebars)
        root.append(core_card)

        # Row C — Network + Disk sparklines.
        row_c = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14,
                        homogeneous=True)
        net_card, net_in = _card(_("Network"))
        self.net_spark = Sparkline([
            (const.CHART_BLUE, s.net_rx_hist),
            (const.CHART_ORANGE, s.net_tx_hist),
        ], min_top=1024.0)
        self.net_legend = _muted()
        self.net_legend.set_use_markup(True)
        net_in.append(self.net_spark)
        net_in.append(self.net_legend)

        disk_card, disk_in = _card(_("Disk I/O"))
        self.disk_spark = Sparkline([
            (const.CHART_BLUE, s.disk_rd_hist),
            (const.CHART_ORANGE, s.disk_wr_hist),
        ], min_top=1024.0)
        self.disk_legend = _muted()
        self.disk_legend.set_use_markup(True)
        disk_in.append(self.disk_spark)
        disk_in.append(self.disk_legend)

        row_c.append(net_card)
        row_c.append(disk_card)
        root.append(row_c)

        # Row D — load average.
        load_card, load_in = _card(_("Load average"))
        self.load_spark = Sparkline([(const.CHART_PURPLE, s.load_hist)],
                                    min_top=float(s.ncpu))
        self.load_caption = _muted()
        load_in.append(self.load_spark)
        load_in.append(self.load_caption)
        root.append(load_card)

    def tick(self):
        s = self.sampler.sample()

        blue = f"<span foreground='{_hex(const.CHART_BLUE)}'>●</span> "
        orange = f"<span foreground='{_hex(const.CHART_ORANGE)}'>●</span> "

        self.cpu_gauge.set_value(s["cpu"])
        self.cpu_caption.set_label(
            _("{cores} cores · load {load:.2f}").format(
                cores=self.sampler.ncpu, load=s["load"][0])
        )

        mem = s["mem"]
        self.mem_gauge.set_value(mem["pct"])
        swap = ""
        if mem["swap_total_gib"] > 0.05:
            swap = "  ·  " + _("swap {pct:.0f}%").format(pct=mem["swap_pct"])
        self.mem_caption.set_label(
            _("{used:.1f} / {total:.1f} GiB").format(
                used=mem["used_gib"], total=mem["total_gib"]) + swap
        )

        self.corebars.set_values(self.sampler.percore)

        self.net_spark.queue_draw()
        self.net_legend.set_markup(
            blue + _("Download {rate}").format(rate=metrics.human_rate(s["net_rx"]))
            + "   " + orange
            + _("Upload {rate}").format(rate=metrics.human_rate(s["net_tx"]))
        )

        self.disk_spark.queue_draw()
        self.disk_legend.set_markup(
            blue + _("Read {rate}").format(rate=metrics.human_rate(s["disk_rd"]))
            + "   " + orange
            + _("Write {rate}").format(rate=metrics.human_rate(s["disk_wr"]))
        )

        self.load_spark.queue_draw()
        load = s["load"]
        self.load_caption.set_label(
            _("1 min {a:.2f}   ·   5 min {b:.2f}   ·   15 min {c:.2f}").format(
                a=load[0], b=load[1], c=load[2])
        )
        return True  # keep the GLib timer alive
