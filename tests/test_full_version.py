import unittest

from cos_config import env, full_version


class FakeModule:
    def __init__(self, name, helper=None, supported=True, relevant=True):
        self.name = name
        self.helper = helper
        self._supported = supported
        self._relevant = relevant

    def supported(self, _env):
        return self._supported

    def host_relevant(self, _env):
        return self._relevant


def environment(os_release_text, in_flatpak):
    rel = env.parse_os_release(os_release_text)
    return env.Environment(os_release=rel, family=env.detect_family(rel), in_flatpak=in_flatpak)


CAPIVARAOS = 'NAME="CapivaraOS Snout"\nID=capivaraos\nID_LIKE=fedora\nVERSION_ID=45\n'
SERIES_1 = 'NAME="CapivaraOS Marsh"\nID=capivaraos\nID_LIKE=fedora\nVERSION_ID=44\n'
FEDORA = 'NAME="Fedora Linux"\nID=fedora\n'
UBUNTU = 'NAME="Ubuntu"\nID=ubuntu\nID_LIKE=debian\n'

MODS = [
    FakeModule("root", helper="firewall"),
    FakeModule("user"),
    FakeModule("sandbox-blind", supported=False),
    FakeModule("fedora-only", helper="multimedia", relevant=False),
]


def names(listed):
    return [(m.name, locked) for m, locked in listed]


class ListingTest(unittest.TestCase):
    def test_native_hides_unsupported_and_missing_helpers(self):
        listed = full_version.listing(environment(FEDORA, False), MODS, lambda h: h == "firewall")
        self.assertEqual(names(listed), [("root", False), ("user", False)])

    def test_flatpak_locks_every_host_relevant_module(self):
        # Helpers are never installed inside the sandbox; locked rows ignore them.
        listed = full_version.listing(environment(UBUNTU, True), MODS, lambda h: False)
        self.assertEqual(names(listed),
                         [("root", True), ("user", True), ("sandbox-blind", True)])


USER_INFO = ("[Application]\nname=org.capivaraos.Config\n\n[Instance]\n"
             "app-path=/root/.local/share/flatpak/app/org.capivaraos.Config/"
             "x86_64/master/abc/files\n")
SYSTEM_INFO = ("[Instance]\napp-path=/var/lib/flatpak/app/org.capivaraos.Config/"
               "x86_64/master/abc/files\n")


class HintTest(unittest.TestCase):
    def test_capivaraos_gets_the_removal_command(self):
        text, command = full_version.install_hint(environment(CAPIVARAOS, True), "user")
        self.assertEqual(command, "flatpak uninstall --user org.capivaraos.Config")
        self.assertIn("CapivaraOS", text)

    def test_removal_command_follows_the_installation(self):
        self.assertEqual(full_version.removal_command("system"),
                         "flatpak uninstall --system org.capivaraos.Config")
        self.assertEqual(full_version.removal_command(None),
                         "flatpak uninstall org.capivaraos.Config")

    def test_installation_from_flatpak_info(self):
        self.assertEqual(full_version.installation_from_info(USER_INFO), "user")
        self.assertEqual(full_version.installation_from_info(SYSTEM_INFO), "system")
        self.assertIsNone(full_version.installation_from_info("[Instance]\n"))
        self.assertIsNone(full_version.read_installation("/nonexistent/flatpak-info"))

    def test_unknown_installation_gives_a_plain_command(self):
        _text, command = full_version.install_hint(environment(CAPIVARAOS, True), None)
        self.assertEqual(command, "flatpak uninstall org.capivaraos.Config")

    def test_series_1_gets_no_removal_command(self):
        # Series 1 does not ship the native package: removing the Flatpak
        # would leave no copy of the app.
        text, command = full_version.install_hint(environment(SERIES_1, True), "user")
        self.assertIsNone(command)
        self.assertIn("CapivaraOS 2.0", text)

    def test_other_systems_are_named_and_get_no_command(self):
        for rel, name in ((FEDORA, "Fedora Linux"), (UBUNTU, "Ubuntu")):
            text, command = full_version.install_hint(environment(rel, True), "user")
            self.assertIsNone(command)
            self.assertIn(f"not available for {name} yet", text)
            self.assertIn("comes with CapivaraOS 2.0 and later", text)

    def test_system_without_a_name(self):
        text, command = full_version.install_hint(environment("ID=mystery\n", True), "user")
        self.assertIsNone(command)
        self.assertIn("this system", text)

if __name__ == "__main__":
    unittest.main()
