import os
import stat
import tempfile
import unittest
from unittest import mock

from cos_config.ops import common, journald


class CommonTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_atomic_write_replaces_and_sets_mode(self):
        path = os.path.join(self.dir, "f.conf")
        common.atomic_write(path, "one\n")
        common.atomic_write(path, "two\n", mode=0o600)
        with open(path) as fh:
            self.assertEqual(fh.read(), "two\n")
        self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
        self.assertEqual(os.listdir(self.dir), ["f.conf"])  # no temp files left

    def test_backup_keeps_the_pristine_copy(self):
        path = os.path.join(self.dir, "fstab")
        self.assertIsNone(common.backup(path))
        with open(path, "w") as fh:
            fh.write("original\n")
        bak = common.backup(path)
        with open(path, "w") as fh:
            fh.write("edited\n")
        common.backup(path)  # second call must not overwrite
        with open(bak) as fh:
            self.assertEqual(fh.read(), "original\n")

    def test_run_helper_exit_codes(self):
        def invalid(_argv):
            raise common.ValidationError("nope")

        def boom(_argv):
            raise RuntimeError("disk on fire")

        with mock.patch("os.geteuid", return_value=1000):
            self.assertEqual(common.run_helper(lambda a: None, []), common.EXIT_NOT_ROOT)
        with mock.patch("os.geteuid", return_value=0), mock.patch.object(common, "log"):
            self.assertEqual(common.run_helper(lambda a: None, []), common.EXIT_OK)
            self.assertEqual(common.run_helper(invalid, []), common.EXIT_INVALID)
            self.assertEqual(common.run_helper(boom, []), common.EXIT_FAILED)


class JournaldTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_apply_read_reset(self):
        self.assertIsNone(journald.read_limit(self.root))
        journald.apply("500M", root=self.root, restart=False)
        self.assertEqual(journald.read_limit(self.root), "500M")
        journald.apply("1G", root=self.root, restart=False)
        self.assertEqual(journald.read_limit(self.root), "1G")
        journald.reset(root=self.root, restart=False)
        self.assertIsNone(journald.read_limit(self.root))
        journald.reset(root=self.root, restart=False)  # idempotent

    def test_failed_restart_restores_previous_state(self):
        journald.apply("500M", root=self.root, restart=False)
        with mock.patch.object(journald, "_restart", side_effect=RuntimeError("no systemd")):
            with self.assertRaises(RuntimeError):
                journald.apply("2G", root=self.root)
            self.assertEqual(journald.read_limit(self.root), "500M")
            with self.assertRaises(RuntimeError):
                journald.reset(root=self.root)
            self.assertEqual(journald.read_limit(self.root), "500M")
        journald.reset(root=self.root, restart=False)
        with mock.patch.object(journald, "_restart", side_effect=RuntimeError("no systemd")):
            with self.assertRaises(RuntimeError):
                journald.apply("1G", root=self.root)
        self.assertFalse(os.path.exists(journald.dropin_path(self.root)))

    def test_rejects_sizes_outside_the_list(self):
        for bad in ("5G", "1", "500M\nStorage=none", "", "../x"):
            with self.assertRaises(common.ValidationError):
                journald.apply(bad, root=self.root, restart=False)
        self.assertFalse(os.path.exists(journald.dropin_path(self.root)))

    def test_helper_main_argument_shapes(self):
        with mock.patch.object(journald, "apply") as apply, \
                mock.patch.object(journald, "reset") as reset:
            journald.helper_main(["set", "250M"])
            apply.assert_called_once_with("250M")
            journald.helper_main(["reset"])
            reset.assert_called_once_with()
            for bad in ([], ["set"], ["reset", "x"], ["rm", "-rf"]):
                with self.assertRaises(common.ValidationError):
                    journald.helper_main(bad)

    def test_describe_matches_the_dropin(self):
        cmds = journald.describe("set", "2G")
        self.assertIn("SystemMaxUse=2G", cmds[1])
        self.assertIn(journald.DROPIN_DIR, cmds[0])
        self.assertEqual(journald.describe("reset")[-1], "sudo systemctl restart systemd-journald")


if __name__ == "__main__":
    unittest.main()
