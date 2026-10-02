Name:           cos-config
Version:        0.7.0
Release:        1%{?dist}
Summary:        COS Config Center: get to know and tune your Linux system

# App code is GPLv3; the logo and icons are CapivaraOS trademarks.
License:        GPL-3.0-or-later AND LicenseRef-CapivaraOS-Trademark
URL:            https://github.com/capivaraos/cos-config
Source0:        %{url}/archive/v%{version}/%{name}-%{version}.tar.gz
BuildArch:      noarch

BuildRequires:  meson
BuildRequires:  python3-devel
BuildRequires:  gettext
BuildRequires:  desktop-file-utils
BuildRequires:  appstream

Requires:       python3-gobject
Requires:       python3-cairo
Requires:       gtk4
Requires:       libadwaita
# Settings that change the system run through pkexec + our polkit actions.
Requires:       polkit
# journalctl/systemctl, used by the system log module.
Requires:       systemd
# lspci, for the GPU line of the system information.
Requires:       pciutils
# Optional: pins the compact widget to the desktop where supported.
Recommends:     gtk4-layer-shell

%description
COS Config Center is the configuration center of the CapivaraOS project: a
friendly place to get to know your system and tune it without typing
commands. Settings are grouped by category, and every change shows what will
be done (with the equivalent commands) before asking for the administrator
password. It also shows system information, a live dashboard and a card to
share your specs.

This is the full (native) version, with the privileged helpers and their
polkit policy.

%prep
%autosetup -n %{name}-%{version}

%build
%meson
%meson_build

%install
%meson_install
%find_lang org.capivaraos.Config

%check
desktop-file-validate %{buildroot}%{_datadir}/applications/org.capivaraos.Config.desktop
appstreamcli validate --no-net %{buildroot}%{_metainfodir}/org.capivaraos.Config.metainfo.xml
%{python3} -m unittest discover -s tests -t .

%files -f org.capivaraos.Config.lang
%license COPYING TRADEMARK.md
%doc README.md
%{_bindir}/cos-config
%{python3_sitelib}/cos_config/
%{_libexecdir}/cos-config/
%{_datadir}/polkit-1/actions/org.capivaraos.config.policy
%{_datadir}/applications/org.capivaraos.Config.desktop
%{_metainfodir}/org.capivaraos.Config.metainfo.xml
%{_datadir}/icons/hicolor/*/apps/org.capivaraos.Config.png
%{_datadir}/org.capivaraos.Config/

%changelog
* Fri Oct 02 2026 CapivaraOS Project <capivaraos-bot@users.noreply.github.com> - 0.7.0-1
- New module: disks at startup (fstab entries with nofail, checked with
  findmnt --verify, mounted right away and rolled back on failure)

* Fri Oct 02 2026 CapivaraOS Project <capivaraos-bot@users.noreply.github.com> - 0.6.0-1
- New module: language and formats (system + GNOME/KDE user settings,
  separate regional formats, Fedora language packs)

* Fri Oct 02 2026 CapivaraOS Project <capivaraos-bot@users.noreply.github.com> - 0.5.0-1
- New module: Brazilian keyboard (ABNT2 / US International layout on
  GNOME, KDE and Xfce; ' + c typing ç; layout on the login screen)

* Fri Oct 02 2026 CapivaraOS Project <capivaraos-bot@users.noreply.github.com> - 0.4.0-1
- New module: codecs and extra repositories (RPM Fusion, OpenH264,
  full FFmpeg/GStreamer, VA-API driver for Intel/AMD, unfiltered Flathub)

* Fri Oct 02 2026 CapivaraOS Project <capivaraos-bot@users.noreply.github.com> - 0.3.0-1
- First native package: Settings tab, module architecture, polkit helpers
- First module: system log size
