# COS Config Center

**COS Config Center** (formerly *Capivara Fetch*) is the configuration center of
the [CapivaraOS](https://capivaraos.org) project for any Linux desktop: a
friendly place to get to know your system and tune it without typing commands.

Today it shows your distro, kernel, desktop, CPU, GPU, memory and uptime in a
clean GTK4 / libadwaita window, exports a good-looking **card** you can share,
and has a **Live** dashboard with real-time gauges and charts (CPU incl.
per-core, memory, network and disk I/O, load average). It can also be **pinned
to the desktop** as a compact widget where the compositor supports it (KDE,
Xfce, wlroots). The **Settings** tab lists configuration modules by category;
the first one caps how much disk the system logs may use.

> Built with GTK4 + libadwaita (Python). English source with a `pt_BR`
> translation. Ships preinstalled on upcoming CapivaraOS releases.

## Run from source (development)

No build step needed — the GNOME runtime provides GTK4, libadwaita and pycairo:

```bash
python3 run.py
```

Requirements: `python3-gobject`, `gtk4`, `libadwaita`, `python3-cairo`
(on Fedora: `sudo dnf install python3-gobject gtk4 libadwaita`).

## Build & install (meson)

```bash
meson setup builddir
meson install -C builddir
cos-config
```

Installed this way (`-Dnative=true`, the default) you also get the root
helpers in `libexec/cos-config/` and their polkit policy. Settings that change
the system run only through those helpers, via `pkexec`; the app itself never
runs as root.

## Tests

```bash
python3 -m unittest discover -s tests -t .
```

To try a privileged module from the source tree without installing, point the
app at a configured copy of the helper (polkit then asks for the generic admin
password, since the policy is not installed):

```bash
mkdir -p /tmp/cos-helpers
sed "s#@PYTHON_DIR@#$PWD/src#" data/helpers/journald.in > /tmp/cos-helpers/journald
chmod +x /tmp/cos-helpers/journald
COS_CONFIG_HELPER_DIR=/tmp/cos-helpers python3 run.py
```

## Build as Flatpak

```bash
flatpak-builder --user --install --force-clean \
    build-dir build-aux/flatpak/org.capivaraos.Config.yml
flatpak run org.capivaraos.Config
```

The Flatpak is built with `-Dnative=false`: no helpers or policy (they could
never leave the sandbox), so only modules that work for the user are listed.

## Project layout

| Path | What |
|------|------|
| `src/cos_config/sysinfo.py` | Collects system facts (best-effort, never crashes) |
| `src/cos_config/card.py` | Renders the shareable Cairo card |
| `src/cos_config/metrics.py` | Live `/proc` sampler (CPU, mem, net, disk, load) |
| `src/cos_config/widgets.py` | Cairo gauge / sparkline / per-core bar widgets |
| `src/cos_config/live.py` | The Live dashboard page (1s refresh) |
| `src/cos_config/widget_window.py` | Compact "pin to desktop" widget (layer-shell + fallback) |
| `src/cos_config/window.py` | libadwaita UI: Settings / System / Live / Share / CapivaraOS pages |
| `src/cos_config/config_page.py` | Settings tab: modules by category, search, module pages |
| `src/cos_config/modules/` | Module contract + registry (`__init__.py`) and one file per module |
| `src/cos_config/ops/` | Root-side operations run by the helpers (no GTK; unit-tested) |
| `src/cos_config/privileged.py` | Runs a helper through `pkexec` without blocking the UI |
| `src/cos_config/env.py` | Distro family (os-release `ID`/`ID_LIKE`), Flatpak and desktop detection |
| `src/cos_config/distro.py` | dnf / apt / pacman / zypper command builders |
| `src/cos_config/main.py` | `Adw.Application` entry point |
| `data/` | `.desktop`, AppStream metainfo, icons, bundled logo, helpers, polkit policy |
| `tests/` | Unit tests (`unittest`) |
| `build-aux/flatpak/` | Flathub manifest (bundles gtk4-layer-shell) |

## Status / TODO

- [x] System info page + shareable card
- [x] Correct host distro detection inside the Flatpak sandbox
- [x] Branding on the card and the CapivaraOS page
- [x] Toast overlay for "card saved" feedback
- [x] Live dashboard (gauges, per-core bars, network/disk/load sparklines)
- [x] "Pin to desktop" compact widget (layer-shell where supported, fallback elsewhere)
- [x] GPU probe works inside the Flatpak sandbox (GNOME runtime ships `lspci`)
- [x] Store screenshots in the AppStream metainfo
- [x] Renamed to COS Config Center, with the "cos config" logo as icon and in-app art
- [x] gettext with a `pt_BR` translation (English-first source)
- [x] Translate the `.desktop`/metainfo strings too (merged from po via ITS)
- [ ] Verify the pinned-widget mode visually on a KDE/Xfce (Marsh/Pup) session
- [ ] Submit to Flathub; then package as RPM to preinstall on CapivaraOS spins

## License

App code: **GPL-3.0-or-later**. CapivaraOS brand assets (the "cos config" logo)
remain © 2026 CapivaraOS Project under their own brand license.
