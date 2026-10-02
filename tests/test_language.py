import unittest
from unittest import mock

from cos_config import language as lg
from cos_config.ops import common, langpacks

LOCALECTL = """   System Locale: LANG=en_US.UTF-8
                  LC_TIME=pt_BR.UTF-8
       VC Keymap: us-acentos
      X11 Layout: us,br
"""


class ParseTest(unittest.TestCase):
    def test_code_of(self):
        self.assertEqual(lg.code_of("pt_BR.UTF-8"), "pt_BR")
        self.assertEqual(lg.code_of("pt_BR.utf8"), "pt_BR")
        self.assertEqual(lg.code_of("es_ES@euro"), "es_ES")
        self.assertIsNone(lg.code_of("C.UTF-8"))
        self.assertIsNone(lg.code_of(""))

    def test_locale_a_keeps_utf8_only(self):
        out = "C\nC.utf8\nPOSIX\nen_US\nen_US.iso88591\nen_US.utf8\npt_BR.UTF-8\nes_ES@euro\n"
        self.assertEqual(lg.parse_locale_a(out), {"C", "en_US", "pt_BR"})

    def test_system_locale_block(self):
        self.assertEqual(lg.parse_system_locale(LOCALECTL),
                         {"LANG": "en_US.UTF-8", "LC_TIME": "pt_BR.UTF-8"})
        self.assertEqual(lg.parse_system_locale("System Locale: n/a\n"), {})


class ArgvTest(unittest.TestCase):
    def test_system_same_and_split(self):
        self.assertEqual(lg.system_argv("pt_BR", "pt_BR"), ["localectl", "set-locale", "LANG=pt_BR.UTF-8"])
        argv = lg.system_argv("en_US", "pt_BR")
        self.assertEqual(argv[:3], ["localectl", "set-locale", "LANG=en_US.UTF-8"])
        self.assertIn("LC_MONETARY=pt_BR.UTF-8", argv)
        self.assertIn("LC_TIME=pt_BR.UTF-8", argv)
        self.assertNotIn("LC_MESSAGES=pt_BR.UTF-8", argv)

    def test_gnome_and_kde(self):
        gn = lg.gnome_argvs("en_US", "pt_BR", 1000)
        self.assertEqual(gn[0][-2:], ["s", "en_US.UTF-8"])
        self.assertIn("/org/freedesktop/Accounts/User1000", gn[0])
        self.assertEqual(gn[1][-1], "pt_BR.UTF-8")
        self.assertEqual(lg.gnome_argvs("pt_BR", "pt_BR", 1000)[1][-1], "")  # follow the language
        kde = lg.kde_argvs("pt_BR", "en_US")
        self.assertEqual(kde[0][-1], "pt_BR")
        self.assertEqual(kde[1][-1], "en_US.UTF-8")


class LangpackTest(unittest.TestCase):
    def test_codes(self):
        none = lambda pkg: False
        everything = lambda pkg: True
        self.assertEqual(lg.langpack_codes("pt_BR", "pt_BR", {"pt_BR"}, everything), [])
        self.assertEqual(lg.langpack_codes("pt_BR", "pt_BR", {"pt_BR"}, none), ["pt_BR"])
        # formats locale missing -> its pack too; present -> not needed
        self.assertEqual(lg.langpack_codes("en_US", "pt_PT", {"en_US"}, everything), ["pt_PT"])
        self.assertEqual(lg.langpack_codes("en_US", "pt_BR", {"en_US", "pt_BR"}, everything), [])

    def test_install_argv_allowlist(self):
        self.assertEqual(langpacks.install_argv(["pt_BR", "pt_BR", "es_ES"]),
                         ["dnf", "install", "-y", "langpacks-pt_BR", "langpacks-es"])
        for bad in ([], ["fr_FR"], ["pt_BR", "--allowerasing"]):
            with self.assertRaises(common.ValidationError):
                langpacks.install_argv(bad)

    def test_helper_main(self):
        with mock.patch.object(common, "run_cmd") as run:
            langpacks.helper_main(["install", "pt_BR"])
            run.assert_called_once_with(["dnf", "install", "-y", "langpacks-pt_BR"])
        for bad in ([], ["install"], ["remove", "pt_BR"]):
            with self.assertRaises(common.ValidationError):
                langpacks.helper_main(bad)


if __name__ == "__main__":
    unittest.main()
