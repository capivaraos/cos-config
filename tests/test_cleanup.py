import os
import tempfile
import unittest
from unittest import mock

from cos_config import cleanup as cl, distro, env
from cos_config.ops import cleanup as rootops, common


class ParseTest(unittest.TestCase):
    def test_journal_usage(self):
        self.assertEqual(cl.parse_journal_usage(
            "Archived and active journals take up 2G in the file system."), 2 * 1024**3)
        self.assertEqual(cl.parse_journal_usage("take up 512.5M in"), int(512.5 * 1024**2))
        self.assertEqual(cl.parse_journal_usage("No journal files"), 0)

    def test_flatpak_unused_counts_numbered_rows(self):
        table = ("        ID                        Branch  Op\n"
                 " 1.     org.gnome.Platform        48      r\n"
                 " 2.     org.kde.Platform          6.8     r\n")
        self.assertEqual(cl.parse_flatpak_unused(table), 2)
        self.assertEqual(cl.parse_flatpak_unused("Nothing unused to uninstall\n"), 0)
        pinned = ("These runtimes in installation 'user' are pinned and won't be removed:\n"
                  "  runtime/org.gnome.Platform/x86_64/49\n")
        self.assertEqual(cl.parse_flatpak_unused(pinned), 0)

    def test_podman_reclaimable(self):
        out = ('[{"Type":"Images","RawReclaimable":578225038},'
               '{"Type":"Containers","RawReclaimable":99}]')
        self.assertEqual(cl.parse_podman_reclaimable(out), 578225038)
        self.assertEqual(cl.parse_podman_reclaimable(""), 0)
        self.assertEqual(cl.parse_podman_reclaimable("not json"), 0)

    def test_human(self):
        self.assertEqual(cl.human(0), "0 B")
        self.assertEqual(cl.human(233_300_000), "233.3 MB")
        self.assertEqual(cl.human(2_100_000_000), "2.1 GB")


class FilesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_empty_dir_keeps_the_dir_and_never_follows_symlinks(self):
        outside = os.path.join(self.dir, "outside")
        os.mkdir(outside)
        keep = os.path.join(outside, "keep.txt")
        open(keep, "w").write("x")
        cache = os.path.join(self.dir, "cache")
        os.makedirs(os.path.join(cache, "sub", "deep"))
        open(os.path.join(cache, "a"), "w").write("x")
        open(os.path.join(cache, "sub", "deep", "b"), "w").write("x")
        os.symlink(outside, os.path.join(cache, "link-to-outside"))
        rootops.empty_dir(cache)
        self.assertEqual(os.listdir(cache), [])
        self.assertTrue(os.path.exists(keep))  # the link target is untouched
        rootops.empty_dir(os.path.join(self.dir, "missing"))  # no error

    def test_dir_size(self):
        d = os.path.join(self.dir, "d")
        os.mkdir(d)
        with open(os.path.join(d, "f"), "wb") as fh:
            fh.write(b"x" * 100_000)
        self.assertGreaterEqual(cl.dir_size(d), 100_000)
        self.assertEqual(cl.dir_size(os.path.join(self.dir, "missing")), 0)


class CommandsTest(unittest.TestCase):
    def test_package_cache_per_family(self):
        self.assertEqual(rootops.commands("pkgcache", env.FEDORA), [["dnf", "clean", "all"]])
        self.assertEqual(rootops.commands("pkgcache", env.DEBIAN), [["apt-get", "clean"]])
        self.assertEqual(rootops.commands("pkgcache", env.ARCH), [["pacman", "-Sc", "--noconfirm"]])
        self.assertEqual(distro.Zypper().clean_cache(), ["zypper", "--non-interactive", "clean", "--all"])
        self.assertEqual(rootops.commands("pkgcache", env.UNKNOWN), [])

    def test_helper_only_accepts_known_items(self):
        for bad in ([], ["clean"], ["clean", "home"], ["clean", "pkgcache", "/etc"], ["rm", "pkgcache"]):
            with self.assertRaises(common.ValidationError):
                rootops.helper_main(bad)

    def test_clean_runs_in_fixed_order(self):
        ran, emptied = [], []
        with mock.patch.object(common, "run_cmd", side_effect=ran.append), \
                mock.patch.object(rootops.shutil, "which", return_value="/usr/bin/x"), \
                mock.patch.object(rootops, "empty_dir", side_effect=emptied.append):
            rootops.clean(["coredumps", "journal", "pkgcache"], env.FEDORA)
        self.assertEqual(ran, [["dnf", "clean", "all"], ["journalctl", "--vacuum-time=2weeks"]])
        self.assertEqual(emptied, [rootops.PACKAGEKIT_CACHE, rootops.COREDUMP_DIR])

    def test_missing_tool_is_skipped(self):
        with mock.patch.object(common, "run_cmd") as run, \
                mock.patch.object(rootops.shutil, "which", return_value=None):
            rootops.clean(["flatpak"], env.FEDORA)
        run.assert_not_called()

    def test_user_steps_and_describe(self):
        steps = cl.user_steps(["trash", "podman"])
        self.assertEqual(steps, [["gio", "trash", "--empty"], ["podman", "image", "prune", "-a", "-f"]])
        self.assertEqual(cl.describe_user(["thumbnails"]), ["rm -rf ~/.cache/thumbnails/*"])
        self.assertEqual(cl.user_steps([]), [])
        lines = rootops.describe(["pkgcache", "coredumps"], env.FEDORA)
        self.assertIn("sudo dnf clean all", lines)
        self.assertTrue(all(line.startswith("sudo ") for line in lines))


if __name__ == "__main__":
    unittest.main()
