import ctypes
import ctypes.util
import os
import tempfile
import unittest

from cos_config import keyboard as kb

DEAD_ACUTE, KEY_c, KEY_C, KEY_e = 0xFE51, 0x63, 0x43, 0x65
_XKB = ctypes.util.find_library("xkbcommon")
_LOCALE_DIR = "/usr/share/X11/locale/en_US.UTF-8/Compose"


def compose(text, keysyms, locale="en_US.UTF-8"):
    """Feed *keysyms* to a libxkbcommon compose table built from *text*."""
    lib = ctypes.CDLL(_XKB)
    lib.xkb_context_new.restype = ctypes.c_void_p
    lib.xkb_compose_table_new_from_buffer.restype = ctypes.c_void_p
    lib.xkb_compose_table_new_from_buffer.argtypes = [
        ctypes.c_void_p, ctypes.c_char_p, ctypes.c_size_t, ctypes.c_char_p, ctypes.c_int, ctypes.c_int]
    lib.xkb_compose_state_new.restype = ctypes.c_void_p
    lib.xkb_compose_state_new.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.xkb_compose_state_feed.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    lib.xkb_compose_state_get_status.argtypes = [ctypes.c_void_p]
    lib.xkb_compose_state_get_utf8.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_size_t]
    ctx = lib.xkb_context_new(0)
    data = text.encode()
    table = lib.xkb_compose_table_new_from_buffer(ctx, data, len(data), locale.encode(), 1, 0)
    assert table, "compose table failed to load"
    state = lib.xkb_compose_state_new(table, 0)
    for ks in keysyms:
        lib.xkb_compose_state_feed(state, ks)
    buf = ctypes.create_string_buffer(16)
    lib.xkb_compose_state_get_utf8(state, buf, 16)
    return buf.value.decode()


@unittest.skipUnless(_XKB and os.path.exists(_LOCALE_DIR), "libxkbcommon / X11 compose data missing")
class RealComposeTest(unittest.TestCase):
    def test_baseline_en_us_gives_c_acute(self):
        self.assertEqual(compose('include "%L"\n', [DEAD_ACUTE, KEY_c]), "ć")

    def test_our_block_gives_cedilla_and_keeps_the_rest(self):
        text = kb.with_cedilla("")
        self.assertEqual(compose(text, [DEAD_ACUTE, KEY_c]), "ç")
        self.assertEqual(compose(text, [DEAD_ACUTE, KEY_C]), "Ç")
        self.assertEqual(compose(text, [DEAD_ACUTE, KEY_e]), "é")


class DesktopTest(unittest.TestCase):
    def test_desktop_of(self):
        self.assertEqual(kb.desktop_of(("gnome",)), kb.GNOME)
        self.assertEqual(kb.desktop_of(("ubuntu", "gnome")), kb.GNOME)
        self.assertEqual(kb.desktop_of(("kde",)), kb.KDE)
        self.assertEqual(kb.desktop_of(("xfce",)), kb.XFCE)
        self.assertIsNone(kb.desktop_of(("sway",)))
        self.assertIsNone(kb.desktop_of(()))

    def test_layout_id(self):
        self.assertEqual(kb.layout_id("br", ""), "abnt2")
        self.assertEqual(kb.layout_id("us", "intl"), "us-intl")
        self.assertEqual(kb.layout_id("us", None), "us")
        self.assertIsNone(kb.layout_id("de", ""))


class GnomeTest(unittest.TestCase):
    SOURCES = "[('xkb', 'us'), ('xkb', 'br'), ('ibus', 'anthy')]"

    def test_parse_and_current(self):
        src = kb.parse_gnome_sources(self.SOURCES)
        self.assertEqual(src, [("xkb", "us"), ("xkb", "br"), ("ibus", "anthy")])
        self.assertEqual(kb.gnome_current(src), ("us", ""))
        self.assertEqual(kb.gnome_current(kb.parse_gnome_sources("[('xkb', 'us+intl')]")), ("us", "intl"))
        self.assertIsNone(kb.gnome_current(kb.parse_gnome_sources("@a(ss) []")))

    def test_new_sources_keep_input_methods(self):
        src = kb.parse_gnome_sources(self.SOURCES)
        self.assertEqual(kb.gnome_new_sources(src, "us-intl"), "[('xkb', 'us+intl'), ('ibus', 'anthy')]")
        self.assertEqual(kb.gnome_new_sources([], "abnt2"), "[('xkb', 'br')]")


class OtherDesktopsTest(unittest.TestCase):
    def test_kde(self):
        argvs = kb.kde_set_argvs("us-intl")
        self.assertIn(["kwriteconfig6", "--file", "kxkbrc", "--group", "Layout", "--key", "LayoutList", "us"], argvs)
        self.assertIn(["kwriteconfig6", "--file", "kxkbrc", "--group", "Layout", "--key", "VariantList", "intl"], argvs)
        self.assertEqual(argvs[-1][0], "dbus-send")

    def test_xfce(self):
        argvs = kb.xfce_set_argvs("abnt2")
        self.assertIn(["xfconf-query", "-c", "keyboard-layout", "-n", "-p", "/Default/XkbLayout", "-t", "string", "-s", "br"], argvs)
        self.assertIn(["xfconf-query", "-c", "keyboard-layout", "-n", "-p", "/Default/XkbVariant", "-t", "string", "-s", ""], argvs)

    def test_login_screen(self):
        self.assertEqual(kb.login_screen_argv("abnt2"), ["localectl", "set-x11-keymap", "br", "pc105", ""])


class DescribeTest(unittest.TestCase):
    def test_parse_localectl(self):
        text = ("   System Locale: LANG=en_US.UTF-8\n       VC Keymap: us-acentos\n"
                "      X11 Layout: us,br\n       X11 Model: pc105\n     X11 Variant: intl,\n")
        self.assertEqual(kb.parse_localectl(text), ("us", "intl"))
        self.assertIsNone(kb.parse_localectl("System Locale: LANG=C\n"))

    def test_describe_combinations(self):
        cmds = kb.describe("abnt2", kb.GNOME, None, None, [("xkb", "us")])
        self.assertEqual(cmds, ['gsettings set org.gnome.desktop.input-sources sources "[(\'xkb\', \'br\')]"'])
        cmds = kb.describe(None, kb.GNOME, True, "us-intl")
        self.assertTrue(cmds[0].startswith("cat >> ~/.XCompose"))
        self.assertIn('<dead_acute> <c> : "ç" ccedilla', cmds[0])
        self.assertEqual(cmds[1], "ibus restart")
        self.assertEqual(cmds[2], "localectl set-x11-keymap us pc105 intl")
        self.assertEqual(kb.describe(None, None, None, None), [])


class ComposeFileTest(unittest.TestCase):
    def test_new_file_keeps_locale_defaults(self):
        text = kb.with_cedilla("")
        self.assertIn('include "%L"', text)
        self.assertTrue(text.index('include "%L"') < text.index(kb.BLOCK_BEGIN))
        self.assertEqual(kb.with_cedilla(text), text)  # idempotent

    def test_existing_user_file_is_preserved(self):
        user = 'include "%L"\n<Multi_key> <h> <h> : "♥"\n'
        added = kb.with_cedilla(user)
        self.assertTrue(added.startswith(user))
        self.assertEqual(kb.without_cedilla(added), user)

    def test_removing_our_only_content_deletes_the_file(self):
        self.assertEqual(kb.without_cedilla(kb.with_cedilla("")), "")

    def test_read_write_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, ".XCompose")
            self.assertEqual(kb.read_compose(path), "")
            kb.write_compose(kb.with_cedilla(""), path)
            self.assertTrue(kb.has_cedilla_block(kb.read_compose(path)))
            kb.write_compose("", path)
            self.assertFalse(os.path.exists(path))


if __name__ == "__main__":
    unittest.main()
