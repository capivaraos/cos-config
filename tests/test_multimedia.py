import unittest
from unittest import mock

from cos_config.ops import common, multimedia as mm

def installed_set(*names):
    return lambda pkg: pkg in names


class ParseTest(unittest.TestCase):
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
        self.assertEqual(mm.plan(["codecs"], {"rpmfusion"}), ["codecs"])

    def test_rejects_unknown_or_empty(self):
        for bad in ([], ["codecs", "--allowerasing"], ["rm"], ["hwaccel"]):
            with self.assertRaises(common.ValidationError):
                mm.plan(bad, set())


class CommandsTest(unittest.TestCase):
    def test_allowerasing_only_for_ffmpeg(self):
        everything = installed_set()
        for step in mm.STEPS:
            for cmd in mm.step_commands(step, "45", everything):
                if "--allowerasing" in cmd:
                    self.assertEqual(step, "codecs")
                    self.assertIn("ffmpeg", cmd)

    def test_codecs_swap_or_install(self):
        swap = mm.step_commands("codecs", "45", installed_set("ffmpeg-free"))[0]
        self.assertEqual(swap[:3], ["dnf", "swap", "-y"])
        fresh = mm.step_commands("codecs", "45", installed_set())[0]
        self.assertEqual(fresh[:4], ["dnf", "install", "-y", "ffmpeg"])
        done = mm.step_commands("codecs", "45", installed_set("ffmpeg-libs"))
        self.assertEqual(len(done), 1)  # only the GStreamer plugins
        self.assertEqual(done[0][:3], ["dnf", "install", "-y"])

    def test_rpmfusion_urls_use_the_release(self):
        cmd = mm.step_commands("rpmfusion", "45", installed_set())[0]
        self.assertIn("https://mirrors.rpmfusion.org/free/fedora/rpmfusion-free-release-45.noarch.rpm", cmd)
        self.assertIn("https://mirrors.rpmfusion.org/nonfree/fedora/rpmfusion-nonfree-release-45.noarch.rpm", cmd)

    def test_describe_prefixes_sudo(self):
        lines = mm.describe(["openh264", "flathub"], installed=installed_set())
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
                mock.patch.object(mm, "fedora_release", return_value="45"), \
                mock.patch.object(mm, "is_installed", return_value=False), \
                mock.patch.object(common, "run_cmd", side_effect=lambda c: ran.append(c)):
            mm.helper_main(["enable", "flathub", "openh264"])
        self.assertEqual(ran[0][:3], ["flatpak", "remote-add", "--system"])
        self.assertEqual(len(ran), 2)  # openh264 already on, flathub = 2 commands


if __name__ == "__main__":
    unittest.main()
