import unittest

from cos_config import env

FEDORA = 'NAME="Fedora Linux"\nID=fedora\nVERSION_ID=45\n'
CAPIVARAOS = 'NAME="CapivaraOS Marsh"\nID=capivaraos\nID_LIKE=fedora\n'
UBUNTU = 'NAME="Ubuntu"\nID=ubuntu\nID_LIKE=debian\n'
MINT = "ID=linuxmint\nID_LIKE='ubuntu debian'\n"
ARCH = "ID=arch\n"
ENDEAVOUR = "ID=endeavouros\nID_LIKE=arch\n"
TUMBLEWEED = 'ID="opensuse-tumbleweed"\nID_LIKE="opensuse suse"\n'
ALMA = 'ID="almalinux"\nID_LIKE="rhel centos fedora"\n'


class ParseTest(unittest.TestCase):
    def test_quotes_comments_and_blank_lines(self):
        data = env.parse_os_release('# comment\n\nNAME="Fedora Linux"\nID=fedora\nBAD LINE\n')
        self.assertEqual(data, {"NAME": "Fedora Linux", "ID": "fedora"})

    def test_single_quotes(self):
        self.assertEqual(env.parse_os_release(MINT)["ID_LIKE"], "ubuntu debian")


class FamilyTest(unittest.TestCase):
    def check(self, text, family):
        self.assertEqual(env.detect_family(env.parse_os_release(text)), family)

    def test_families(self):
        self.check(FEDORA, env.FEDORA)
        self.check(CAPIVARAOS, env.FEDORA)
        self.check(ALMA, env.FEDORA)
        self.check(UBUNTU, env.DEBIAN)
        self.check(MINT, env.DEBIAN)
        self.check(ARCH, env.ARCH)
        self.check(ENDEAVOUR, env.ARCH)
        self.check(TUMBLEWEED, env.SUSE)

    def test_unknown(self):
        self.check("ID=gentoo\n", env.UNKNOWN)
        self.check("", env.UNKNOWN)

    def test_is_capivaraos(self):
        e = env.Environment(os_release=env.parse_os_release(CAPIVARAOS))
        self.assertTrue(e.is_capivaraos)
        self.assertFalse(env.Environment(os_release=env.parse_os_release(FEDORA)).is_capivaraos)


class ReadTest(unittest.TestCase):
    def test_first_existing_path_wins(self):
        import tempfile, os
        with tempfile.TemporaryDirectory() as d:
            host = os.path.join(d, "host")
            local = os.path.join(d, "local")
            with open(local, "w") as fh:
                fh.write(UBUNTU)
            self.assertEqual(env.read_os_release((host, local))["ID"], "ubuntu")
            with open(host, "w") as fh:
                fh.write(FEDORA)
            self.assertEqual(env.read_os_release((host, local))["ID"], "fedora")


if __name__ == "__main__":
    unittest.main()
