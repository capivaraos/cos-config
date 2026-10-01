"""Gettext setup. Import `_` from here in every module with UI strings.

Importing this module binds the text domain, so `_` is ready before any
string is translated. The .mo files are installed under share/locale; in the
Flatpak that is /app/share/locale, otherwise gettext's default path is used.
"""

import gettext
import os

from .const import APP_ID

_localedir = "/app/share/locale" if os.path.isdir("/app/share/locale") else None
gettext.bindtextdomain(APP_ID, _localedir)
gettext.textdomain(APP_ID)

_ = gettext.gettext
