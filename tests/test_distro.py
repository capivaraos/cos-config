import unittest

from cos_config import distro, env


class ForFamilyTest(unittest.TestCase):
    def test_each_family_has_a_backend(self):
        for family, name in ((env.FEDORA, "dnf"), (env.DEBIAN, "apt"),
                             (env.ARCH, "pacman"), (env.SUSE, "zypper")):
            self.assertEqual(distro.for_family(family).name, name)

    def test_unknown_family(self):
        self.assertIsNone(distro.for_family(env.UNKNOWN))


class ArgvTest(unittest.TestCase):
    def test_install_remove_query(self):
        self.assertEqual(distro.Dnf().install(["vlc", "gstreamer1-plugins-ugly"]),
                         ["dnf", "install", "-y", "vlc", "gstreamer1-plugins-ugly"])
        self.assertEqual(distro.Apt().remove(["vlc"]), ["apt-get", "remove", "-y", "vlc"])
        self.assertEqual(distro.Pacman().install(["vlc"]),
                         ["pacman", "-S", "--needed", "--noconfirm", "vlc"])
        self.assertEqual(distro.Zypper().is_installed("vlc"), ["rpm", "-q", "vlc"])
        self.assertEqual(distro.Apt().is_installed("libc6:amd64"),
                         ["dpkg-query", "-W", "-f=${Status}", "libc6:amd64"])

    def test_rejects_options_and_shell(self):
        for bad in (["-y"], ["--allowerasing"], ["vlc; rm -rf /"], ["a b"], [""], ["$(id)"], []):
            with self.assertRaises(ValueError, msg=bad):
                distro.Dnf().install(bad)
        with self.assertRaises(ValueError):
            distro.Apt().is_installed("--help")


if __name__ == "__main__":
    unittest.main()
