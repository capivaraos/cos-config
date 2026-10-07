import json
import os
import tempfile
import unittest
from unittest import mock

from cos_config.ops import automount as am, common

SYSTEM_FSTAB = """UUID=968cb5cb-84e9-48b7-8354-4ca7ce5e5ded / btrfs subvol=root 0 0
UUID=426e1a2a-f1c6-47d8-9c17-fea847584563 /boot ext4 defaults 1 2
UUID=957D-101E /boot/efi vfat umask=0077 0 2
UUID=968cb5cb-84e9-48b7-8354-4ca7ce5e5ded /home btrfs subvol=home 0 0
PARTUUID=aaaa-02 /mnt/win ntfs3 defaults 0 0
"""

LSBLK = json.dumps({"blockdevices": [
    {"name": "nvme0n1", "type": "disk", "fstype": None, "uuid": None, "children": [
        {"name": "nvme0n1p1", "path": "/dev/nvme0n1p1", "type": "part", "fstype": "vfat",
         "uuid": "957D-101E", "label": None, "size": 600000000, "mountpoints": ["/boot/efi"]},
        {"name": "nvme0n1p3", "path": "/dev/nvme0n1p3", "type": "part", "fstype": "crypto_LUKS",
         "uuid": "54bd-luks", "children": [
             {"name": "luks-x", "path": "/dev/mapper/luks-x", "type": "crypt", "fstype": "btrfs",
              "uuid": "968cb5cb-84e9-48b7-8354-4ca7ce5e5ded", "mountpoints": ["/home", "/"]}]}]},
    {"name": "sdb", "type": "disk", "fstype": None, "children": [
        {"name": "sdb1", "path": "/dev/sdb1", "type": "part", "fstype": "ext4",
         "uuid": "1111-aaaa-2222", "label": "Backup HD", "size": 1000000000000, "mountpoints": [None]},
        {"name": "sdb2", "path": "/dev/sdb2", "type": "part", "fstype": "ntfs", "partuuid": "aaaa-02",
         "uuid": "3333BBBB", "label": "Windows", "size": 500000000000, "mountpoints": []},
        {"name": "sdb3", "path": "/dev/sdb3", "type": "part", "fstype": "swap", "uuid": "sw-1"}]},
]})


class FstabTest(unittest.TestCase):
    def test_parse_marks_managed(self):
        text = am.with_entry(SYSTEM_FSTAB, "UUID=1111-aaaa-2222 /mnt/Backup ext4 defaults 0 0")
        entries = am.parse_fstab("# comment\n" + text)
        self.assertEqual(entries[-1], ("UUID=1111-aaaa-2222", "/mnt/Backup", "ext4", True))
        self.assertFalse(any(m for *_x, m in entries[:-1]))

    def test_add_remove_roundtrip(self):
        line = "UUID=1111-aaaa-2222 /mnt/Backup ext4 defaults 0 0"
        added = am.with_entry(SYSTEM_FSTAB, line)
        self.assertTrue(added.startswith(SYSTEM_FSTAB))
        self.assertEqual(am.without_entry(added, "1111-aaaa-2222"), SYSTEM_FSTAB)
        # someone else's identical-looking entry without our marker stays
        self.assertEqual(am.without_entry(SYSTEM_FSTAB + line + "\n", "1111-aaaa-2222"),
                         SYSTEM_FSTAB + line + "\n")

    def test_entry_line_rejects_bad_fields(self):
        for bad in (("u u", "/mnt/a", "ext4", "o"), ("u", "/mnt/a b", "ext4", "o"),
                    ("u", "/mnt/a", "", "o"), ("u", "/mnt/a", "ext4", "#x"), ("u", "/mnt/a\n/", "ext4", "o")):
            with self.assertRaises(common.ValidationError):
                am.entry_line(*bad)


class OptionsTest(unittest.TestCase):
    def test_options_always_safe(self):
        for fs in am.SUPPORTED:
            fstype, opts = am.mount_options(fs, 1000, 1000)
            self.assertIn("nofail", opts)
            self.assertIn("x-systemd.device-timeout=10s", opts)
        self.assertEqual(am.mount_options("ntfs", 1000, 1000)[0], "ntfs3")
        self.assertIn("uid=1000,gid=1000", am.mount_options("exfat", 1000, 1000)[1])

    def test_owner_needed_for_windows_filesystems(self):
        self.assertEqual(am.mount_options("ext4", None, None)[0], "ext4")
        with self.assertRaises(common.ValidationError):
            am.mount_options("ntfs", None, None)
        with self.assertRaises(common.ValidationError):
            am.mount_options("zfs", 1000, 1000)

    def test_mount_name(self):
        self.assertEqual(am.mount_name("Backup HD", "1111", set()), "/mnt/Backup-HD")
        self.assertEqual(am.mount_name("../../etc", "1111", set()), "/mnt/etc")
        self.assertEqual(am.mount_name("", "abcdef123456", set()), "/mnt/disk-abcdef12")
        self.assertEqual(am.mount_name("Data", "1", {"/mnt/Data", "/mnt/Data-2"}), "/mnt/Data-3")


class VerifyOutputTest(unittest.TestCase):
    def test_clean_table_has_no_counts(self):
        self.assertEqual(am.parse_verify(0, "Success, no errors or warnings detected\n"), 0)

    def test_counts(self):
        self.assertEqual(am.parse_verify(0, "0 parse errors, 0 errors, 4 warnings\n"), 0)
        self.assertEqual(am.parse_verify(1, "/mnt/x\n   [E] unreachable\n\n0 parse errors, 2 errors, 4 warnings\n"), 2)
        self.assertEqual(am.parse_verify(1, "0 parse errors, 1 error, 5 warnings\n"), 1)

    def test_not_trustworthy(self):
        self.assertIsNone(am.parse_verify(139, ""))        # findmnt segfault
        self.assertIsNone(am.parse_verify(-11, ""))
        self.assertIsNone(am.parse_verify(1, "1 parse error, 0 errors, 0 warnings\n"))
        self.assertIsNone(am.parse_verify(1, "something unexpected\n"))


class PartitionsTest(unittest.TestCase):
    def test_statuses(self):
        parts = {p["path"] or p["uuid"]: p for p in am.partitions(LSBLK, SYSTEM_FSTAB)}
        self.assertEqual(parts["/dev/nvme0n1p1"]["status"], "system")
        self.assertNotIn("/dev/mapper/luks-x", parts)  # unlocked LUKS: needs crypttab, not listed
        self.assertEqual(parts["/dev/sdb1"]["status"], "available")
        self.assertEqual(parts["/dev/sdb1"]["target"], "/mnt/Backup-HD")
        self.assertEqual(parts["/dev/sdb2"]["status"], "elsewhere")  # via PARTUUID
        self.assertNotIn("/dev/sdb3", parts)  # swap
        self.assertNotIn("/dev/nvme0n1p3", parts)  # LUKS container

    def test_managed_and_missing(self):
        fstab = am.with_entry(SYSTEM_FSTAB, "UUID=1111-aaaa-2222 /mnt/Backup-HD ext4 defaults 0 0")
        fstab = am.with_entry(fstab, "UUID=9999-gone /mnt/Old ext4 defaults 0 0")
        parts = {p["uuid"]: p for p in am.partitions(LSBLK, fstab)}
        self.assertEqual(parts["1111-aaaa-2222"]["status"], "managed")
        self.assertEqual(parts["9999-gone"]["status"], "missing")
        self.assertEqual(parts["9999-gone"]["target"], "/mnt/Old")


class AddRemoveTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = self.tmp.name
        self.fstab = os.path.join(d, "fstab")
        with open(self.fstab, "w") as fh:
            fh.write(SYSTEM_FSTAB)
        mnt = os.path.join(d, "mnt")
        os.mkdir(mnt)
        self.patches = [
            mock.patch.object(am, "FSTAB", self.fstab),
            mock.patch.object(am, "MNT", mnt),
            mock.patch.object(am, "read_lsblk", return_value=LSBLK),
            mock.patch.object(am, "_owner", return_value=(1000, 1000)),
            mock.patch.object(common, "log"),
        ]
        for p in self.patches:
            p.start()
        self.mnt = mnt

    def tearDown(self):
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def fstab_text(self):
        with open(self.fstab) as fh:
            return fh.read()

    def test_refuses_when_verify_gets_worse(self):
        with mock.patch.object(am, "verify_errors", side_effect=[0, 1]), \
                mock.patch.object(common, "run_cmd") as run:
            with self.assertRaises(RuntimeError):
                am.add("1111-aaaa-2222")
        run.assert_not_called()
        self.assertEqual(self.fstab_text(), SYSTEM_FSTAB)
        self.assertEqual(os.listdir(self.mnt), [])

    def test_mount_failure_restores_fstab(self):
        def run(cmd):
            if cmd[0] == "mount":
                raise RuntimeError("mount: wrong fs type")
        with mock.patch.object(am, "verify_errors", return_value=0), \
                mock.patch.object(common, "run_cmd", side_effect=run):
            with self.assertRaises(RuntimeError) as ctx:
                am.add("1111-aaaa-2222")
        self.assertIn("restored", str(ctx.exception))
        self.assertEqual(self.fstab_text(), SYSTEM_FSTAB)
        self.assertTrue(os.path.exists(self.fstab + common.BACKUP_SUFFIX))

    def test_success_then_remove(self):
        cmds = []
        with mock.patch.object(am, "verify_errors", return_value=0), \
                mock.patch.object(common, "run_cmd", side_effect=cmds.append):
            am.add("1111-aaaa-2222")
            target = os.path.join(self.mnt, "Backup-HD")
            self.assertIn(f"UUID=1111-aaaa-2222 {target} ext4 defaults,nofail", self.fstab_text())
            self.assertIn(["mount", target], cmds)
            with self.assertRaises(common.ValidationError):
                am.add("1111-aaaa-2222")  # already managed
            am.remove("1111-aaaa-2222")
        self.assertEqual(self.fstab_text(), SYSTEM_FSTAB)
        self.assertFalse(os.path.exists(target))

    def test_refuses_system_and_foreign_entries(self):
        for uuid in ("957D-101E", "968cb5cb-84e9-48b7-8354-4ca7ce5e5ded", "3333BBBB"):
            with self.assertRaises(common.ValidationError):
                am.add(uuid)
        with self.assertRaises(common.ValidationError):
            am.remove("957D-101E")  # not ours
        for bad in ("../../x", "a b", ""):
            with self.assertRaises(common.ValidationError):
                am.helper_main(["add", bad])


if __name__ == "__main__":
    unittest.main()
