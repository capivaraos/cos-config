"""System language and regional formats, separately.

The system setting (localectl, /etc/locale.conf) is what the login screen,
Xfce and new users follow. GNOME and KDE also keep a per-user choice that
wins over it, so both are set: GNOME through AccountsService (language)
and gsettings (formats), KDE through plasma-localerc.
"""

import subprocess

from .ops import langpacks

# Locale codes offered. Native language names are not translated.
LANGUAGES = (
    ("pt_BR", "Português (Brasil)"),
    ("en_US", "English (US)"),
    ("es_ES", "Español"),
)
FORMATS = ("pt_BR", "en_US", "pt_PT", "es_ES")
# How each format looks (glibc output for 2026-12-31 and 1234.56).
FORMAT_EXAMPLES = {
    "pt_BR": "31/12/2026 · R$ 1.234,56",
    "en_US": "12/31/2026 · $1,234.56",
    "pt_PT": "31/12/2026 · 1.234,56 €",
    "es_ES": "31/12/26 · 1.234,56 €",
}
# Format categories moved together when formats differ from the language.
FORMAT_VARS = ("LC_TIME", "LC_NUMERIC", "LC_MONETARY", "LC_MEASUREMENT", "LC_PAPER")


def utf8(code):
    return f"{code}.UTF-8"


def code_of(value):
    """'pt_BR.UTF-8' / 'pt_BR.utf8' / 'pt_BR' -> 'pt_BR'; '' or C -> None."""
    code = (value or "").split(".")[0].split("@")[0]
    return code if code and code not in ("C", "POSIX") else None


def parse_locale_a(text):
    """Codes with a UTF-8 locale available, from `locale -a`."""
    codes = set()
    for line in text.split():
        name, _, enc = line.partition(".")
        if enc.lower().replace("-", "") == "utf8":
            codes.add(name)
    return codes


def parse_system_locale(text):
    """{VAR: value} from the `System Locale:` lines of `localectl status`."""
    values, in_block = {}, False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("System Locale:"):
            in_block = True
            stripped = stripped.split(":", 1)[1].strip()
        elif in_block and (":" in stripped.split("=")[0] or not stripped):
            break
        if in_block and "=" in stripped:
            key, _, val = stripped.partition("=")
            values[key] = val
    return values


def system_argv(lang, fmt):
    args = [f"LANG={utf8(lang)}"]
    if fmt and fmt != lang:
        args += [f"{var}={utf8(fmt)}" for var in FORMAT_VARS]
    return ["localectl", "set-locale", *args]


def gnome_argvs(lang, fmt, uid):
    path = f"/org/freedesktop/Accounts/User{uid}"
    region = utf8(fmt) if fmt and fmt != lang else ""
    return [
        ["busctl", "call", "org.freedesktop.Accounts", path,
         "org.freedesktop.Accounts.User", "SetLanguage", "s", utf8(lang)],
        ["gsettings", "set", "org.gnome.system.locale", "region", region],
    ]


def kde_argvs(lang, fmt):
    base = ["kwriteconfig6", "--file", "plasma-localerc", "--group"]
    return [
        base + ["Translations", "--key", "LANGUAGE", lang],
        base + ["Formats", "--key", "LANG", utf8(fmt or lang)],
    ]


def langpack_codes(lang, fmt, available, installed):
    """Codes whose language pack to install: the chosen language when its
    pack is missing, plus any chosen locale that does not exist yet."""
    codes = []
    for code in (lang, fmt):
        if not code or code not in langpacks.PACKAGES or code in codes:
            continue
        if code not in available or (code == lang and not installed(langpacks.PACKAGES[code])):
            codes.append(code)
    return codes


# ---- reading the machine -----------------------------------------------------
def _out(argv):
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def available_codes():
    return parse_locale_a(_out(["locale", "-a"]))


def system_locale():
    return parse_system_locale(_out(["localectl", "status"]))


def is_installed(package):
    try:
        return subprocess.run(["rpm", "-q", "--quiet", package], timeout=10).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def current(desktop, uid, system):
    """(language code, formats code) the user sees now."""
    lang = code_of(system.get("LANG"))
    fmt = code_of(system.get("LC_TIME")) or lang
    if desktop == "gnome":
        out = _out(["busctl", "get-property", "org.freedesktop.Accounts",
                    f"/org/freedesktop/Accounts/User{uid}",
                    "org.freedesktop.Accounts.User", "Language"])
        user_lang = code_of(out.strip().removeprefix("s ").strip('"'))
        lang = user_lang or lang
        region = code_of(_out(["gsettings", "get", "org.gnome.system.locale", "region"]).strip().strip("'"))
        fmt = region or lang
    elif desktop == "kde":
        read = ["kreadconfig6", "--file", "plasma-localerc", "--group"]
        lang = code_of(_out(read + ["Translations", "--key", "LANGUAGE"]).strip().split(":")[0]) or lang
        fmt = code_of(_out(read + ["Formats", "--key", "LANG"]).strip()) or lang
    return lang, fmt
