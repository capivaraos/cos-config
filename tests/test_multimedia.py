import unittest
from unittest import mock

from cos_config.ops import common, multimedia as mm

LSPCI = """00:00.0 0600: 8086:3ec4 (rev 0d)
00:02.0 0300: 8086:3e9b (rev 02)
01:00.0 0302: 10de:1f91 (rev a1)
02:00.0 0380: 1002:73ff (rev c1)
03:00.0 0108: 144d:a808
"""


def installed_set(*names):
    return lambda pkg: pkg in names


class ParseTest(unittest.TestCase):
    def test_gpu_vendors_only_display_classes(self):
        self.assertEqual(mm.parse_gpu_vendors(LSPCI), [mm.INTEL, mm.NVIDIA, mm.AMD])
        self.assertEqual(mm.parse_gpu_vendors("00:00.0 0600: 8086:3ec4\n"), [])

    def test_enabled_repos(self):
        out = ("repo id                repo name\n"
               "fedora                 Fedora 45 - x86_64\n"
               "fedora-cisco-openh264  Fedora 45 openh264 (From Cisco) - x86_64\n")
        self.assertEqual(mm.parse_enabled_repos(out), ["fedora", "fedora-cisco-openh264"])

    def test_flathub_filter(self):
        self.assertTrue(mm.parse_flathub_filtered(
            "fedora\t-\nflathub\t/usr/share/flatpak/fedora-flathub.filter\n"))
        self.assertFalse(mm.parse_flathub_filtered("flathub\t-\n"))
        self.assertFalse(mm.parse_flathub_filtered("flathub\n"))
        self.assertIsNone(mm.parse_flathub_filtered("fedora\t-\n"))


class PlanTest(unittest.TestCase):
    def test_order_and_skip_done(self):
        self.assertEqual(mm.plan(["flathub", "openh264"], set()), ["openh264", "flathub"])
        self.assertEqual(mm.plan(["openh264", "flathub"], {"openh264"}), ["flathub"])

    def test_rpmfusion_added_when_needed(self):
        self.assertEqual(mm.plan(["codecs"], set()), ["rpmfusion", "codecs"])
        self.assertEqual(mm.plan(["hwaccel"], {"rpmfusion"}), ["hwaccel"])

    def test_rejects_unknown_or_empty(self):
        for bad in ([], ["codecs", "--allowerasing"], ["rm"]):
            with self.assertRaises(common.ValidationError):
                mm.plan(bad, set())


class CommandsTest(unittest.TestCase):
    def test_intel_swaps_the_limited_driver(self):
        cmds = mm.hwaccel_commands([mm.INTEL], installed_set("libva-intel-media-driver"))
        self.assertEqual(cmds, [["dnf", "swap", "-y", "libva-intel-media-driver", "intel-media-driver"]])
        self.assertEqual(mm.hwaccel_commands([mm.INTEL], installed_set()),
                         [["dnf", "install", "-y", "intel-media-driver"]])
        self.assertEqual(mm.hwaccel_commands([mm.INTEL], installed_set("intel-media-driver")), [])

    def test_amd_never_removes_the_3d_driver(self):
        cmds = mm.hwaccel_commands([mm.AMD], installed_set("mesa-dri-drivers"))
        self.assertEqual(cmds, [["dnf", "install", "-y", "mesa-va-drivers-freeworld.x86_64"]])
        self.assertNotIn("swap", cmds[0])
        self.assertNotIn("--allowerasing", cmds[0])

    def test_nvidia_alone_has_nothing_here(self):
        self.assertEqual(mm.hwaccel_commands([mm.NVIDIA], installed_set()), [])

    def test_allowerasing_only_for_ffmpeg(self):
        everything = installed_set()
        for step in mm.STEPS:
            for cmd in mm.step_commands(step, "45", [mm.INTEL, mm.AMD], everything):
                if "--allowerasing" in cmd:
                    self.assertEqual(step, "codecs")
                    self.assertIn("ffmpeg", cmd)

    def test_codecs_swap_or_install(self):
        swap = mm.step_commands("codecs", "45", [], installed_set("ffmpeg-free"))[0]
        self.assertEqual(swap[:3], ["dnf", "swap", "-y"])
        fresh = mm.step_commands("codecs", "45", [], installed_set())[0]
        self.assertEqual(fresh[:4], ["dnf", "install", "-y", "ffmpeg"])
        done = mm.step_commands("codecs", "45", [], installed_set("ffmpeg-libs"))
        self.assertEqual(len(done), 1)  # only the GStreamer plugins
        self.assertEqual(done[0][:3], ["dnf", "install", "-y"])

    def test_rpmfusion_urls_use_the_release(self):
        cmd = mm.step_commands("rpmfusion", "45", [], installed_set())[0]
        self.assertIn("https://mirrors.rpmfusion.org/free/fedora/rpmfusion-free-release-45.noarch.rpm", cmd)
        self.assertIn("https://mirrors.rpmfusion.org/nonfree/fedora/rpmfusion-nonfree-release-45.noarch.rpm", cmd)

    def test_describe_prefixes_sudo(self):
        lines = mm.describe(["openh264", "flathub"], [], installed=installed_set())
        self.assertEqual(lines[0], "sudo dnf config-manager setopt fedora-cisco-openh264.enabled=1")
        self.assertTrue(all(line.startswith("sudo ") for line in lines))


class HelperTest(unittest.TestCase):
    def test_argument_shapes(self):
        for bad in ([], ["enable"], ["install", "codecs"]):
            with self.assertRaises(common.ValidationError):
                mm.helper_main(bad)

    def test_runs_planned_steps_in_order(self):
        state = dict.fromkeys(mm.STEPS, False)
        state["openh264"] = True
        ran = []
        with mock.patch.object(mm, "state", return_value=state), \
                mock.patch.object(mm, "gpu_vendors", return_value=[mm.AMD]), \
                mock.patch.object(mm, "fedora_release", return_value="45"), \
                mock.patch.object(mm, "is_installed", return_value=False), \
                mock.patch.object(common, "run_cmd", side_effect=lambda c: ran.append(c)):
            mm.helper_main(["enable", "hwaccel", "openh264"])
        self.assertEqual(ran[0][:3], ["dnf", "install", "-y"])  # rpmfusion first
        self.assertIn("rpmfusion-free-release-45", ran[0][3])
        self.assertEqual(ran[1], ["dnf", "install", "-y", "mesa-va-drivers-freeworld.x86_64"])
        self.assertEqual(len(ran), 2)  # openh264 already on


if __name__ == "__main__":
    unittest.main()
