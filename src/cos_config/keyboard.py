"""Keyboard layout and the Brazilian cedilla, at the user level (no root).

* Layout: each desktop keeps its own setting — GNOME in gsettings, KDE in
  kxkbrc, Xfce in xfconf. These helpers read it and build the argv to change
  it; nothing here talks to GTK.
* Cedilla: with the US International layout, ' + c gives "ć" unless the
  locale is one whose compose table says "ç" (pt_BR does, en_US does not).
  A managed block in ~/.XCompose fixes that for GTK, IBus, Qt/Electron
  (libxkbcommon) and X11 apps alike, on Wayland and X11.
"""

import os
import re
import shlex
import subprocess

# (id, xkb layout, xkb variant)
LAYOUTS = {
    "abnt2": ("br", ""),
    "us-intl": ("us", "intl"),
    "us": ("us", ""),
}

GNOME = "gnome"
KDE = "kde"
XFCE = "xfce"

BLOCK_BEGIN = "# >>> COS Config Center: ' + c gives ç"
BLOCK_END = "# <<< COS Config Center"
CEDILLA_RULES = (
    '<dead_acute> <c> : "ç" ccedilla',
    '<dead_acute> <C> : "Ç" Ccedilla',
)


def desktop_of(desktops):
    """Our adapter for XDG_CURRENT_DESKTOP entries, or None."""
    for d in desktops:
        if d in ("gnome", "ubuntu", "unity") or d.endswith("gnome"):
            return GNOME
        if d == "kde":
            return KDE
        if d == "xfce":
            return XFCE
    return None


def layout_id(layout, variant):
    for lid, (lay, var) in LAYOUTS.items():
        if lay == layout and var == (variant or ""):
            return lid
    return None


# ---- GNOME -------------------------------------------------------------------
_SOURCE_RE = re.compile(r"\(\s*'([^']*)'\s*,\s*'([^']*)'\s*\)")


def parse_gnome_sources(text):
    """`gsettings get org.gnome.desktop.input-sources sources` -> [(type, id)]."""
    return _SOURCE_RE.findall(text)


def gnome_current(sources):
    """(layout, variant) of the first xkb source, or None."""
    for kind, ident in sources:
        if kind == "xkb":
            layout, _, variant = ident.partition("+")
            return layout, variant
    return None


def gnome_new_sources(sources, lid):
    """The chosen layout replaces the xkb sources; input methods (ibus) stay."""
    layout, variant = LAYOUTS[lid]
    ident = f"{layout}+{variant}" if variant else layout
    kept = [(k, i) for k, i in sources if k != "xkb"]
    items = [("xkb", ident), *kept]
    return "[" + ", ".join(f"('{k}', '{i}')" for k, i in items) + "]"


def gnome_set_argv(sources, lid):
    return ["gsettings", "set", "org.gnome.desktop.input-sources", "sources",
            gnome_new_sources(sources, lid)]


# ---- KDE ---------------------------------------------------------------------
def kde_set_argvs(lid):
    layout, variant = LAYOUTS[lid]
    base = ["kwriteconfig6", "--file", "kxkbrc", "--group", "Layout"]
    return [
        base + ["--key", "Use", "true"],
        base + ["--key", "LayoutList", layout],
        base + ["--key", "VariantList", variant],
        ["dbus-send", "--session", "--type=signal", "/Layouts",
         "org.kde.keyboard.reloadConfig"],
    ]


# ---- Xfce --------------------------------------------------------------------
def xfce_set_argvs(lid):
    layout, variant = LAYOUTS[lid]
    base = ["xfconf-query", "-c", "keyboard-layout", "-n"]
    return [
        base + ["-p", "/Default/XkbDisable", "-t", "bool", "-s", "false"],
        base + ["-p", "/Default/XkbLayout", "-t", "string", "-s", layout],
        base + ["-p", "/Default/XkbVariant", "-t", "string", "-s", variant],
    ]


def login_screen_argv(lid):
    """System-wide layout (login screen, console): localectl asks polkit."""
    layout, variant = LAYOUTS[lid]
    return ["localectl", "set-x11-keymap", layout, "pc105", variant]


# ---- reading the current state ----------------------------------------------
def _out(argv):
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def parse_localectl(text):
    """(layout, variant) from `localectl status`, first entry of each list."""
    values = {}
    for line in text.splitlines():
        key, sep, val = line.partition(":")
        if sep:
            values[key.strip()] = val.strip()
    layout = values.get("X11 Layout", "").split(",")[0]
    variant = values.get("X11 Variant", "").split(",")[0]
    return (layout, variant) if layout else None


def system_layout():
    return parse_localectl(_out(["localectl", "status"]))


def current_layout(desktop):
    """(layout, variant) the user's desktop uses now, or None."""
    if desktop == GNOME:
        return gnome_current(parse_gnome_sources(
            _out(["gsettings", "get", "org.gnome.desktop.input-sources", "sources"])))
    if desktop == KDE:
        read = ["kreadconfig6", "--file", "kxkbrc", "--group", "Layout", "--key"]
        layout = _out(read + ["LayoutList"]).strip().split(",")[0]
        variant = _out(read + ["VariantList"]).strip().split(",")[0]
        return (layout, variant) if layout else system_layout()
    if desktop == XFCE:
        query = ["xfconf-query", "-c", "keyboard-layout", "-p"]
        if _out(query + ["/Default/XkbDisable"]).strip() != "false":
            return system_layout()  # Xfce follows the system layout
        layout = _out(query + ["/Default/XkbLayout"]).strip().split(",")[0]
        variant = _out(query + ["/Default/XkbVariant"]).strip().split(",")[0]
        return (layout, variant) if layout else system_layout()
    return None


def gnome_sources():
    return parse_gnome_sources(
        _out(["gsettings", "get", "org.gnome.desktop.input-sources", "sources"]))


def ibus_running():
    try:
        return subprocess.run(["pgrep", "-x", "ibus-daemon"], capture_output=True).returncode == 0
    except OSError:
        return False


# ---- cedilla (~/.XCompose) ---------------------------------------------------
def compose_path():
    return os.path.join(os.path.expanduser("~"), ".XCompose")


def has_cedilla_block(text):
    return BLOCK_BEGIN in text


def _block():
    return "\n".join([BLOCK_BEGIN, *CEDILLA_RULES, BLOCK_END]) + "\n"


def with_cedilla(text):
    """*text* (the current ~/.XCompose, "" if none) with our block at the end.

    A new file starts with include "%L" so every other compose sequence of
    the locale keeps working; ours come after it, so they win.
    """
    if has_cedilla_block(text):
        return text
    if not text.strip():
        return '# Compose sequences. Keep the locale defaults:\ninclude "%L"\n\n' + _block()
    sep = "" if text.endswith("\n") else "\n"
    return text + sep + "\n" + _block()


def without_cedilla(text):
    """*text* without our block; "" when nothing of the user's would remain."""
    lines, out, inside = text.splitlines(keepends=True), [], False
    for line in lines:
        if line.startswith(BLOCK_BEGIN):
            inside = True
            continue
        if inside:
            if line.startswith(BLOCK_END):
                inside = False
            continue
        out.append(line)
    rest = "".join(out).rstrip("\n") + "\n"
    ours_only = [l.strip() for l in rest.splitlines()
                 if l.strip() and l.strip() not in ('include "%L"',)
                 and not l.lstrip().startswith("#")]
    return "" if not ours_only else rest


def read_compose(path=None):
    try:
        with open(path or compose_path(), encoding="utf-8") as fh:
            return fh.read()
    except FileNotFoundError:
        return ""


def write_compose(text, path=None):
    path = path or compose_path()
    if text:
        tmp = path + ".cos-config.tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    elif os.path.exists(path):
        os.unlink(path)


def describe(lid, desktop, cedilla, login_lid=None, sources=()):
    """Equivalent commands for the chosen changes.

    lid: new desktop layout (or None); cedilla: True/False to add/remove
    the ~/.XCompose block (None = unchanged); login_lid: layout for the
    login screen (or None)."""
    cmds = []
    if lid and desktop == GNOME:
        cmds.append(quote(gnome_set_argv(sources, lid)))
    elif lid and desktop == KDE:
        cmds += [quote(a) for a in kde_set_argvs(lid)]
    elif lid and desktop == XFCE:
        cmds += [quote(a) for a in xfce_set_argvs(lid)]
    if cedilla is True:
        cmds.append("cat >> ~/.XCompose <<'EOF'\n" + _block() + "EOF")
        cmds.append("ibus restart")
    elif cedilla is False:
        cmds.append("# remove the COS Config Center block from ~/.XCompose")
        cmds.append("ibus restart")
    if login_lid:
        cmds.append(quote(login_screen_argv(login_lid)))
    return cmds


def quote(argv):
    return " ".join(_quote_arg(a) for a in argv)


def _quote_arg(arg):
    # Readable for people copying it: '[...]' lists go in double quotes.
    if "'" in arg and not re.search(r'["$`\\]', arg):
        return f'"{arg}"'
    return shlex.quote(arg)
