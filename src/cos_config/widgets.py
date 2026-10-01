"""Cairo-drawn dashboard widgets: arc gauge, sparkline, per-core bars.

All are Gtk.DrawingArea subclasses that redraw on queue_draw(). Text ink is
taken from the widget's current CSS color (get_color) so they follow the
active light/dark theme; series colors come from the validated categorical
palette in const.py.
"""

import math

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402


def _rgba(area):
    c = area.get_color()
    return c.red, c.green, c.blue, c.alpha


class Gauge(Gtk.DrawingArea):
    """A 270° arc gauge for a 0–100 value with a big centered number."""

    def __init__(self, color, unit="%"):
        super().__init__()
        self._value = 0.0
        self._color = color
        self._unit = unit
        self.set_content_height(170)
        self.set_hexpand(True)
        self.set_draw_func(self._draw)

    def set_value(self, value):
        self._value = max(0.0, min(100.0, float(value)))
        self.queue_draw()

    def _draw(self, area, ctx, w, h):
        cx, cy = w / 2, h * 0.60
        r = max(min(w, h * 1.15) / 2 - 16, 8)
        start = math.radians(135)
        end = math.radians(405)  # 270° sweep
        ctx.set_line_cap(1)  # ROUND
        ctx.set_line_width(14)

        ctx.set_source_rgba(0.5, 0.5, 0.5, 0.20)
        ctx.arc(cx, cy, r, start, end)
        ctx.stroke()

        frac = self._value / 100.0
        ctx.set_source_rgb(*self._color)
        ctx.arc(cx, cy, r, start, start + (end - start) * frac)
        ctx.stroke()

        tr, tg, tb, ta = _rgba(area)
        ctx.set_source_rgba(tr, tg, tb, ta)
        big = f"{self._value:.0f}{self._unit}"
        ctx.select_font_face("sans-serif", 0, 1)
        ctx.set_font_size(max(min(w, h) * 0.26, 12))
        ext = ctx.text_extents(big)
        ctx.move_to(cx - ext.width / 2 - ext.x_bearing, cy + 4)
        ctx.show_text(big)


class Sparkline(Gtk.DrawingArea):
    """Auto-scaling multi-series line chart backed by deques.

    series: list of (color_rgb, deque_of_floats). The first series is filled
    faintly under its line. y-axis auto-scales to the visible maximum.
    """

    def __init__(self, series, min_top=1.0):
        super().__init__()
        self._series = series
        self._min_top = min_top
        self.set_content_height(120)
        self.set_hexpand(True)
        self.set_draw_func(self._draw)

    def _draw(self, area, ctx, w, h):
        pad = 8
        x0, y0 = pad, pad
        x1, y1 = w - pad, h - pad
        plot_w = max(x1 - x0, 1)
        plot_h = max(y1 - y0, 1)

        # baseline
        tr, tg, tb, _ = _rgba(area)
        ctx.set_source_rgba(tr, tg, tb, 0.12)
        ctx.set_line_width(1)
        ctx.move_to(x0, y1)
        ctx.line_to(x1, y1)
        ctx.stroke()

        top = self._min_top
        for _, data in self._series:
            if data:
                top = max(top, max(data))
        top *= 1.15  # headroom

        n = max(max((len(d) for _, d in self._series), default=0), 2)

        def pt(i, v, count):
            x = x0 + plot_w * (i / (count - 1)) if count > 1 else x0
            y = y1 - plot_h * (v / top if top else 0)
            return x, y

        for idx, (color, data) in enumerate(self._series):
            if not data:
                continue
            count = len(data)
            pts = [pt(i, v, count) for i, v in enumerate(data)]

            if idx == 0:  # faint fill under the primary series
                ctx.move_to(pts[0][0], y1)
                for x, y in pts:
                    ctx.line_to(x, y)
                ctx.line_to(pts[-1][0], y1)
                ctx.close_path()
                ctx.set_source_rgba(*color, 0.12)
                ctx.fill()

            ctx.set_source_rgb(*color)
            ctx.set_line_width(2)
            ctx.set_line_join(1)  # ROUND
            ctx.move_to(*pts[0])
            for x, y in pts[1:]:
                ctx.line_to(x, y)
            ctx.stroke()

        _ = n  # (kept for clarity; count derived per-series)


class CoreBars(Gtk.DrawingArea):
    """One vertical bar per CPU core, height = usage %."""

    def __init__(self, color):
        super().__init__()
        self._values = []
        self._color = color
        self.set_content_height(96)
        self.set_hexpand(True)
        self.set_draw_func(self._draw)

    def set_values(self, values):
        self._values = list(values)
        self.queue_draw()

    def _draw(self, area, ctx, w, h):
        if not self._values:
            return
        n = len(self._values)
        gap = 4
        bw = max((w - gap * (n - 1)) / n, 1)
        for i, v in enumerate(self._values):
            x = i * (bw + gap)
            bh = h * (max(0.0, min(100.0, v)) / 100.0)
            # track
            ctx.set_source_rgba(0.5, 0.5, 0.5, 0.15)
            ctx.rectangle(x, 0, bw, h)
            ctx.fill()
            # value (opacity rises with load for a subtle heat cue)
            ctx.set_source_rgba(*self._color, 0.55 + 0.45 * (v / 100.0))
            ctx.rectangle(x, h - bh, bw, bh)
            ctx.fill()
