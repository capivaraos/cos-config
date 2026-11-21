import unittest

from cos_config import env

try:
    import gi
    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from cos_config.modules.firewall import FirewallModule
    from cos_config.modules.multimedia import MultimediaModule
except (ImportError, ValueError):  # no GTK 4 / libadwaita on this machine
    FirewallModule = MultimediaModule = None

FEDORA = 'NAME="Fedora Linux"\nID=fedora\nVERSION_ID=45\n'
SILVERBLUE = FEDORA + "VARIANT_ID=silverblue\nOSTREE_VERSION='45.20261120.0'\n"
UBUNTU = 'NAME="Ubuntu"\nID=ubuntu\nID_LIKE=debian\n'


def host(text):
    rel = env.parse_os_release(text)
    return env.Environment(os_release=rel, family=env.detect_family(rel), in_flatpak=True)


@unittest.skipIf(FirewallModule is None, "GTK 4 and libadwaita are not available")
class HostRelevantTest(unittest.TestCase):
    def test_firewall_only_on_the_fedora_family(self):
        self.assertTrue(FirewallModule().host_relevant(host(FEDORA)))
        self.assertFalse(FirewallModule().host_relevant(host(UBUNTU)))

    def test_multimedia_needs_a_dnf_based_fedora(self):
        self.assertTrue(MultimediaModule().host_relevant(host(FEDORA)))
        self.assertFalse(MultimediaModule().host_relevant(host(SILVERBLUE)))
        self.assertFalse(MultimediaModule().host_relevant(host(UBUNTU)))


if __name__ == "__main__":
    unittest.main()
