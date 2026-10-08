import unittest
from unittest import mock

from cos_config import diagnostics as dg

DF = """Filesystem         1-blocks         Used    Available Capacity Mounted on
/dev/dm-0      509315383296 310494818304 189439414272      63% /
/dev/dm-0      509315383296 310494818304 189439414272      63% /home
/dev/nvme0n1p2   2040373248   1989000000     51373248      98% /boot
/dev/sdb1      100000000000  88000000000  12000000000      88% /mnt/My Disk
"""

LSPCI = """00:02.0 VGA compatible controller: Intel Corporation CoffeeLake-H GT2 [UHD Graphics 630] (rev 02)
\tDeviceName: Onboard - Video
\tKernel driver in use: i915
\tKernel modules: i915
01:00.0 3D controller: NVIDIA Corporation TU117M [GeForce GTX 1650 Mobile] (rev a1)
\tSubsystem: Dell Device 0919
\tKernel modules: nouveau
02:00.0 Ethernet controller: Realtek RTL8111
\tKernel driver in use: r8169
"""


class RedactTest(unittest.TestCase):
    def red(self, text):
        return dg.redact(text, user="maria", home="/home/maria")

    def test_user_and_home(self):
        self.assertEqual(self.red("open /home/maria/Documents/x.txt failed"),
                         "open /home/USER/Documents/x.txt failed")
        self.assertEqual(self.red("session opened for user maria(uid=1000)"),
                         "session opened for user USER(uid=1000)")
        # not inside other words
        self.assertEqual(self.red("mariadb.service started"), "mariadb.service started")

    def test_short_user_name_only_as_a_whole_word(self):
        out = dg.redact("dp logged in; dpkg and /home/dp/x; udp port", user="dp", home="/home/dp")
        self.assertEqual(out, "USER logged in; dpkg and /home/USER/x; udp port")

    def test_network_and_identifiers(self):
        text = ("wlo1 192.168.127.243/22 fe80::9d1b:3c84:7849:3271/64 "
                "link 3c:52:82:aa:bb:cc uuid 968cb5cb-84e9-48b7-8354-4ca7ce5e5ded "
                "machine 408ce8f1a2b3c4d5e6f708192a3b4c5d")
        out = self.red(text)
        for secret in ("192.168", "fe80", "3c:52", "968cb5cb", "408ce8f1"):
            self.assertNotIn(secret, out)
        for token in ("IP", "IPV6", "MAC", "UUID", "ID"):
            self.assertIn(token, out)

    def test_keeps_what_helps(self):
        text = ("i915 0000:00:02.0: [drm] *ERROR* Failed to probe lspcon; "
                "kernel 7.2.8-200.fc44.x86_64 at 08:42:03, usb 1-2:1.0, ratio 16:9")
        self.assertEqual(self.red(text), text)

    def test_ipv6_forms(self):
        for addr in ("fe80::9d1b:3c84:7849:3271", "2001:db8::1", "2001:0db8:85a3:0000:0000:8a2e:0370:7334"):
            self.assertEqual(self.red(f"addr {addr} up"), "addr IPV6 up")


class ParseTest(unittest.TestCase):
    def test_df_once_per_device_and_spaces_in_mount(self):
        rows = dg.parse_df(DF)
        self.assertEqual([r[0] for r in rows], ["/", "/boot", "/mnt/My Disk"])
        self.assertEqual(rows[0][1:], (63, 189439414272))

    def test_failed_units(self):
        out = "  foo.service loaded failed failed Foo\nbar.mount loaded failed failed Bar\n\n"
        self.assertEqual(dg.parse_failed_units(out), ["foo.service", "bar.mount"])
        self.assertEqual(dg.parse_failed_units(""), [])

    def test_gpus_and_driver(self):
        self.assertEqual(dg.parse_gpus(LSPCI), [
            ("Intel Corporation CoffeeLake-H GT2 [UHD Graphics 630]", "i915"),
            ("NVIDIA Corporation TU117M [GeForce GTX 1650 Mobile]", None),
        ])


class ChecksTest(unittest.TestCase):
    def test_disk_levels(self):
        levels = {c["mount"]: c["level"] for c in dg.disk_checks(dg.parse_df(DF))}
        self.assertEqual(levels, {"/": dg.OK, "/boot": dg.BAD, "/mnt/My Disk": dg.WARN})

    def test_services_gpu_log_and_worst(self):
        self.assertEqual(dg.service_check([], [])["level"], dg.OK)
        svc = dg.service_check(["foo.service"], ["bar.service"])
        self.assertEqual(svc["level"], dg.BAD)
        self.assertEqual(svc["failed"], ["foo.service", "bar.service (user)"])
        gpus = dg.gpu_checks(dg.parse_gpus(LSPCI))
        self.assertEqual([g["level"] for g in gpus], [dg.OK, dg.BAD])
        self.assertEqual(dg.log_check([])["level"], dg.OK)
        self.assertEqual(dg.log_check(["x"])["level"], dg.INFO)
        self.assertEqual(dg.worst(gpus + [dg.log_check(["x"])]), dg.BAD)
        self.assertEqual(dg.worst([]), dg.OK)


class ReportTest(unittest.TestCase):
    def test_report_is_redacted_and_has_no_host(self):
        data = {
            "facts": [("OS", "Fedora Linux 45"), ("CPU", "x86_64 (8 cores)")],
            "checks": dg.disk_checks(dg.parse_df(DF)) + [dg.service_check(["foo.service"], [])]
                      + dg.gpu_checks(dg.parse_gpus(LSPCI)) + [dg.log_check(["a"])],
            "errors": [f"line {i} from 10.0.0.{i} in /home/maria/app" for i in range(30)],
        }
        with mock.patch.object(dg.getpass, "getuser", return_value="maria"), \
                mock.patch.object(dg.os.path, "expanduser", return_value="/home/maria"):
            text = dg.report(data, "9.9")
        self.assertIn("COS Config Center 9.9", text)
        self.assertIn("[PROBLEM] disk /boot: 98% used", text)
        self.assertIn("[WARNING] disk /mnt/My Disk: 88% used", text)
        self.assertIn("[PROBLEM] failed services: foo.service", text)
        self.assertIn("driver NOT LOADED", text)
        self.assertNotIn("maria", text)
        self.assertNotIn("10.0.0.", text)
        self.assertEqual(text.count("line "), dg.MAX_LOG_LINES)  # only the last 20
        self.assertIn("line 29", text)
        self.assertNotIn("line 9 ", text)


if __name__ == "__main__":
    unittest.main()
