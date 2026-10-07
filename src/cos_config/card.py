"""Render the shareable specs card with Cairo.

Produces a cairo.ImageSurface that can be both saved as PNG (write_to_png)
and shown in the UI as a Gdk.Texture. This is the app's viral hook: the
card carries the CapivaraOS branding wherever it is shared.
"""

import cairo

from . import const
from .i18n import _

WIDTH = 1000
PADDING = 56
ROW_H = 62
HEADER_H = 200
FOOTER_H = 84


def _rounded_rect(ctx, x, y, w, h, r):
    ctx.new_sub_path()
    ctx.arc(x + w - r, y + r, r, -1.5708, 0)
    ctx.arc(x + w - r, y + h - r, r, 0, 1.5708)
    ctx.arc(x + r, y + h - r, r, 1.5708, 3.1416)
    ctx.arc(x + r, y + r, r, 3.1416, 4.7124)
    ctx.close_path()


def render(rows):
    """rows: list of (label, value). Returns a cairo.ImageSurface."""
    height = HEADER_H + ROW_H * len(rows) + FOOTER_H + PADDING
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, WIDTH, height)
    ctx = cairo.Context(surface)

    # Vertical brand gradient background.
    grad = cairo.LinearGradient(0, 0, 0, height)
    grad.add_color_stop_rgb(0, *const.BRAND_NAVY)
    grad.add_color_stop_rgb(1, *const.BRAND_NAVY_2)
    _rounded_rect(ctx, 0, 0, WIDTH, height, 28)
    ctx.set_source(grad)
    ctx.fill()

    # Header: logo + title, vertically centered in the header band.
    logo_drawn_w = 0
    target = 108
    head = const.brand_head_png()
    if head:
        try:
            logo = cairo.ImageSurface.create_from_png(head)
            scale = target / max(logo.get_width(), logo.get_height())
            ctx.save()
            ctx.translate(PADDING, PADDING - 4)
            ctx.scale(scale, scale)
            ctx.set_source_surface(logo, 0, 0)
            ctx.paint()
            ctx.restore()
            logo_drawn_w = target + 28
        except Exception:
            logo_drawn_w = 0

    text_x = PADDING + logo_drawn_w
    ctx.select_font_face("sans-serif", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
    ctx.set_font_size(48)
    ctx.set_source_rgb(*const.BRAND_CREAM)
    ctx.move_to(text_x, PADDING + 56)
    ctx.show_text(const.APP_NAME)

    ctx.select_font_face("sans-serif", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
    ctx.set_font_size(21)
    ctx.set_source_rgb(*const.BRAND_BROWN)
    ctx.move_to(text_x, PADDING + 90)
    ctx.show_text(_("System snapshot"))

    # Rows.
    y = HEADER_H
    label_x = PADDING
    value_x = 300
    for i, (label, value) in enumerate(rows):
        if i % 2 == 0:
            _rounded_rect(ctx, PADDING - 16, y - 34, WIDTH - 2 * (PADDING - 16), ROW_H - 12, 12)
            ctx.set_source_rgba(1, 1, 1, 0.04)
            ctx.fill()

        ctx.select_font_face("sans-serif", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        ctx.set_font_size(22)
        ctx.set_source_rgb(*const.BRAND_MUTED)
        ctx.move_to(label_x, y)
        ctx.show_text(label)

        ctx.select_font_face("sans-serif", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
        ctx.set_source_rgb(*const.BRAND_CREAM)
        value = _ellipsize(ctx, str(value), WIDTH - value_x - PADDING)
        ctx.move_to(value_x, y)
        ctx.show_text(value)
        y += ROW_H

    # Footer: project name and website.
    ctx.set_source_rgba(1, 1, 1, 0.08)
    ctx.rectangle(PADDING, y - 20, WIDTH - 2 * PADDING, 2)
    ctx.fill()
    ctx.select_font_face("sans-serif", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
    ctx.set_font_size(22)
    ctx.set_source_rgb(*const.BRAND_BROWN)
    ctx.move_to(PADDING, y + 24)
    ctx.show_text("Powered by CapivaraOS")
    ctx.select_font_face("sans-serif", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
    ctx.set_source_rgb(*const.BRAND_MUTED)
    ctx.set_font_size(20)
    tail = "  ·  capivaraos.org"
    ctx.show_text(tail)

    surface.flush()
    return surface


def _ellipsize(ctx, text, max_w):
    if ctx.text_extents(text).width <= max_w:
        return text
    while text and ctx.text_extents(text + "…").width > max_w:
        text = text[:-1]
    return text + "…"


def save_png(surface, path):
    surface.write_to_png(path)
