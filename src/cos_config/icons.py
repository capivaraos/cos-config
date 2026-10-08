"""Pick icons that the current icon theme really has.

Symbolic icon names differ between themes: Adwaita (GNOME) lacks some that
Breeze (KDE) ships, and the other way round. A missing icon renders as a
faint placeholder, so callers list candidates in order of preference.
"""

from gi.repository import Gdk, Gtk


def pick(*names):
    """The first of *names* present in the theme (the last one as a fallback)."""
    display = Gdk.Display.get_default()
    if display is not None:
        theme = Gtk.IconTheme.get_for_display(display)
        for name in names:
            if theme.has_icon(name):
                return name
    return names[-1]
