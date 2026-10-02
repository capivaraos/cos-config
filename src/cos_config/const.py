"""Application-wide constants for COS Config Center.

Change APP_NAME / APP_ID here if the branding name is ever revisited.
(Formerly "Capivara Fetch"; renamed when it grew into a config center.)
"""

import os

APP_ID = "org.capivaraos.Config"
APP_NAME = "COS Config Center"
VERSION = "0.6.0"

# Where the "Try CapivaraOS" funnel points.
WEBSITE_URL = "https://capivaraos.org"
DOWNLOAD_URL = "https://sourceforge.net/projects/capivaraos/files/"
ISSUE_URL = "https://github.com/capivaraos/cos-config/issues"

# Privileged helpers (native package only). Overridable for development.
HELPER_DIR = os.environ.get("COS_CONFIG_HELPER_DIR", "/usr/libexec/cos-config")

# CapivaraOS brand palette (used to render the shareable card).
BRAND_NAVY = (0.086, 0.137, 0.239)      # #16233d — deep navy background
BRAND_NAVY_2 = (0.055, 0.090, 0.169)    # #0e172b — gradient bottom
BRAND_BROWN = (0.541, 0.353, 0.231)     # #8a5a3b — capybara brown accent
BRAND_CREAM = (0.960, 0.925, 0.870)     # #f5ecde — warm off-white text
BRAND_MUTED = (0.65, 0.70, 0.80)        # muted label grey-blue

# Categorical chart palette — validated colorblind-safe (dataviz validator,
# light surface): blue / orange / purple / teal. Used for the live dashboard.
CHART_BLUE = (0.208, 0.518, 0.894)      # #3584e4
CHART_ORANGE = (0.902, 0.380, 0.0)      # #e66100
CHART_PURPLE = (0.569, 0.255, 0.675)    # #9141ac
CHART_TEAL = (0.078, 0.612, 0.533)      # #149c88


def _first_existing(*paths):
    for p in paths:
        if p and os.path.exists(p):
            return p
    return None


def brand_head_png():
    """Best-effort path to the "cos config" logo PNG used on the card and the
    CapivaraOS page — the same artwork as the app icon.

    Falls back across the installed data dirs (Flatpak and native) and the
    in-repo data/ copies.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.abspath(os.path.join(here, "..", ".."))
    return _first_existing(
        os.path.join(os.sep, "app", "share", APP_ID, "brand-logo.png"),
        os.path.join(os.sep, "usr", "share", APP_ID, "brand-logo.png"),
        os.path.join(repo_root, "data", "brand-logo.png"),
        os.path.join(repo_root, "data", "icons", "hicolor", "512x512", "apps", APP_ID + ".png"),
        os.path.join(repo_root, "data", "icons", "hicolor", "256x256", "apps", APP_ID + ".png"),
    )
