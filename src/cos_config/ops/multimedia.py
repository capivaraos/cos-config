"""Complete multimedia support on the Fedora family.

Steps, always run in this order and each skipped when already done:

  rpmfusion  RPM Fusion free + nonfree release packages
  openh264   Cisco's OpenH264 repository (shipped with Fedora, may be off)
  codecs     full FFmpeg (swap of ffmpeg-free) + GStreamer plugins
  hwaccel    full VA-API video driver for the GPU (Intel, AMD)
  flathub    Flathub system remote, without Fedora's filter

Checked against Fedora 45 + RPM Fusion: only the FFmpeg swap uses
--allowerasing (it replaces the 8 "-free" libraries one for one). Every
other step fails instead of removing packages; in particular AMD gets the
freeworld VA driver *next to* mesa-dri-drivers, because swapping it would
remove the 3D driver.
"""

import re
import subprocess

from . import common

STEPS = ("rpmfusion", "openh264", "codecs", "hwaccel", "flathub")
NEEDS_RPMFUSION = ("codecs", "hwaccel")

INTEL = "intel"
AMD = "amd"
NVIDIA = "nvidia"
_VENDOR_IDS = {"8086": INTEL, "1002": AMD, "10de": NVIDIA}
# lspci -n: "00:02.0 0300: 8086:3e9b (rev 02)"; display classes 0300/0302/0380.
_LSPCI_RE = re.compile(r"^\S+\s+03(?:00|02|80):\s+([0-9a-f]{4}):[0-9a-f]{4}", re.M)

RPMFUSION_URL = "https://mirrors.rpmfusion.org/{kind}/fedora/rpmfusion-{kind}-release-{rel}.noarch.rpm"
FLATHUB_URL = "https://dl.flathub.org/repo/flathub.flatpakrepo"
OPENH264_REPO = "fedora-cisco-openh264"
GSTREAMER = (
    "gstreamer1-plugins-bad-freeworld",
    "gstreamer1-plugins-ugly",
    "gstreamer1-plugin-libav",
    "gstreamer1-plugin-openh264",
    "gstreamer1-plugin-dav1d",
)
CODEC_MARKERS = ("ffmpeg-libs", "gstreamer1-plugins-bad-freeworld", "gstreamer1-plugins-ugly")


# ---- parsing (pure) --------------------------------------------------------
def parse_gpu_vendors(lspci_n):
    vendors = []
    for vid in _LSPCI_RE.findall(lspci_n.lower()):
        vendor = _VENDOR_IDS.get(vid)
        if vendor and vendor not in vendors:
            vendors.append(vendor)
    return vendors


def parse_enabled_repos(repo_list):
    """Repo ids from `dnf repo list --enabled` (first column, header skipped)."""
    ids = []
    for line in repo_list.splitlines():
        cols = line.split()
        if cols and cols[0] != "repo":
            ids.append(cols[0])
    return ids


def parse_flathub_filtered(remotes):
    """From `flatpak remotes --system --columns=name,filter`:
    None when there is no flathub remote, else whether it is filtered."""
    for line in remotes.splitlines():
        cols = line.split(None, 1)
        if cols and cols[0] == "flathub":
            return len(cols) > 1 and cols[1].strip() not in ("", "-")
    return None


def plan(requested, done):
    """Steps to run, in order: *requested* minus *done*, plus RPM Fusion when
    a step needs it and it is not there yet."""
    requested = set(requested)
    unknown = requested - set(STEPS)
    if unknown or not requested:
        raise common.ValidationError(f"steps must be among {', '.join(STEPS)}")
    if requested & set(NEEDS_RPMFUSION) and "rpmfusion" not in done:
        requested.add("rpmfusion")
    return [s for s in STEPS if s in requested and s not in done]


def hwaccel_commands(vendors, installed):
    """dnf argv lists for the video driver, given GPU vendors and a predicate
    telling whether a package is installed."""
    cmds = []
    if INTEL in vendors and not installed("intel-media-driver"):
        if installed("libva-intel-media-driver"):
            cmds.append(["dnf", "swap", "-y", "libva-intel-media-driver", "intel-media-driver"])
        else:
            cmds.append(["dnf", "install", "-y", "intel-media-driver"])
    if AMD in vendors and not installed("mesa-va-drivers-freeworld"):
        cmds.append(["dnf", "install", "-y", "mesa-va-drivers-freeworld.x86_64"])
    return cmds


def step_commands(step, release, vendors, installed):
    if step == "rpmfusion":
        return [["dnf", "install", "-y",
                 RPMFUSION_URL.format(kind="free", rel=release),
                 RPMFUSION_URL.format(kind="nonfree", rel=release)]]
    if step == "openh264":
        return [["dnf", "config-manager", "setopt", f"{OPENH264_REPO}.enabled=1"]]
    if step == "codecs":
        cmds = []
        if not installed("ffmpeg-libs"):
            # The one place --allowerasing is used: full FFmpeg replaces the
            # "-free" libraries one for one (RPM Fusion's documented step).
            if installed("ffmpeg-free"):
                cmds.append(["dnf", "swap", "-y", "ffmpeg-free", "ffmpeg", "--allowerasing"])
            else:
                cmds.append(["dnf", "install", "-y", "ffmpeg", "--allowerasing"])
        cmds.append(["dnf", "install", "-y", *GSTREAMER])
        return cmds
    if step == "hwaccel":
        return hwaccel_commands(vendors, installed)
    if step == "flathub":
        return [["flatpak", "remote-add", "--system", "--if-not-exists", "flathub", FLATHUB_URL],
                ["flatpak", "remote-modify", "--system", "--no-filter", "--enable", "flathub"]]
    raise common.ValidationError(f"unknown step {step!r}")


# ---- reading the machine (unprivileged) ------------------------------------
def _out(argv):
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=20).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def is_installed(package):
    try:
        return subprocess.run(["rpm", "-q", "--quiet", package], timeout=10).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def gpu_vendors():
    return parse_gpu_vendors(_out(["lspci", "-n"]))


def fedora_release():
    rel = _out(["rpm", "-E", "%fedora"]).strip()
    if not rel.isdigit():
        raise RuntimeError(f"could not find the Fedora release (got {rel!r})")
    return rel


def state(vendors=None):
    """{step: done?} for this machine. hwaccel is None when the GPU has no
    driver handled here (e.g. NVIDIA only, or no GPU found)."""
    vendors = gpu_vendors() if vendors is None else vendors
    accel = hwaccel_commands(vendors, is_installed)
    handled = INTEL in vendors or AMD in vendors
    return {
        "rpmfusion": is_installed("rpmfusion-free-release") and is_installed("rpmfusion-nonfree-release"),
        "openh264": OPENH264_REPO in parse_enabled_repos(_out(["dnf", "repo", "list", "--enabled"])),
        "codecs": all(is_installed(p) for p in CODEC_MARKERS),
        "hwaccel": (not accel) if handled else None,
        "flathub": parse_flathub_filtered(
            _out(["flatpak", "remotes", "--system", "--columns=name,filter"])) is False,
    }


def describe(steps, vendors, installed=is_installed, release="$(rpm -E %fedora)"):
    """Equivalent shell commands for *steps*, shown before applying."""
    lines = []
    for step in steps:
        for argv in step_commands(step, release, vendors, installed):
            lines.append("sudo " + " ".join(argv))
    return lines


# ---- helper entry point (root) ---------------------------------------------
def helper_main(argv):
    """argv: ["enable", STEP, ...]."""
    if len(argv) < 2 or argv[0] != "enable":
        raise common.ValidationError("usage: enable STEP...")
    current = state()
    done = {s for s, ok in current.items() if ok}
    steps = plan(argv[1:], done)
    vendors = gpu_vendors()
    release = fedora_release() if "rpmfusion" in steps else None
    for step in steps:
        for cmd in step_commands(step, release, vendors, is_installed):
            common.run_cmd(cmd)
        print(f"step {step}: done", flush=True)
