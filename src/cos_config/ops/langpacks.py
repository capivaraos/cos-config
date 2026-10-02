"""Install Fedora language packs (translations, fonts, spell checking).

`langpacks-<code>` pulls the glibc locale data, so the locale exists
afterwards; with weak dependencies on (the default) it also brings the
Hunspell dictionary and the LibreOffice translation when those are
installed. Checked on Fedora 45.
"""

from . import common

PACKAGES = {
    "pt_BR": "langpacks-pt_BR",
    "pt_PT": "langpacks-pt",
    "en_US": "langpacks-en",
    "en_GB": "langpacks-en_GB",
    "es_ES": "langpacks-es",
}


def install_argv(codes):
    codes = list(dict.fromkeys(codes))
    if not codes or any(c not in PACKAGES for c in codes):
        raise common.ValidationError(f"languages must be among {', '.join(PACKAGES)}")
    return ["dnf", "install", "-y", *(PACKAGES[c] for c in codes)]


def helper_main(argv):
    """argv: ["install", CODE, ...]."""
    if len(argv) < 2 or argv[0] != "install":
        raise common.ValidationError("usage: install CODE...")
    common.run_cmd(install_argv(argv[1:]))
