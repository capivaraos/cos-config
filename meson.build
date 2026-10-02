project('cos-config',
  version: '0.6.0',
  meson_version: '>= 0.62.0',
)

python = import('python').find_installation('python3')
i18n = import('i18n')
python_dir = python.get_install_dir()
datadir = get_option('prefix') / get_option('datadir')

# Python package.
install_subdir('src/cos_config',
  install_dir: python_dir,
  exclude_directories: ['__pycache__', 'ops/__pycache__', 'modules/__pycache__'],
)

# Executable launcher.
conf = configuration_data()
conf.set('PYTHON_DIR', python_dir)
configure_file(
  input: 'cos-config.in',
  output: 'cos-config',
  configuration: conf,
  install: true,
  install_dir: get_option('bindir'),
  install_mode: 'rwxr-xr-x',
)

# Desktop entry and AppStream metainfo: translatable keys/elements are merged
# from the po/ catalogs (gettext ITS rules handle .desktop and .metainfo.xml).
i18n.merge_file(
  input: 'data/org.capivaraos.Config.desktop.in',
  output: 'org.capivaraos.Config.desktop',
  type: 'desktop',
  po_dir: 'po',
  install: true,
  install_dir: datadir / 'applications',
)
i18n.merge_file(
  input: 'data/org.capivaraos.Config.metainfo.xml.in',
  output: 'org.capivaraos.Config.metainfo.xml',
  type: 'xml',
  po_dir: 'po',
  install: true,
  install_dir: datadir / 'metainfo',
)
# App icon: the "cos config" logo, shipped as PNG at several hicolor sizes.
foreach size : ['64', '128', '256', '512']
  install_data(
    'data/icons/hicolor' / size + 'x' + size / 'apps/org.capivaraos.Config.png',
    install_dir: datadir / 'icons/hicolor' / size + 'x' + size / 'apps',
  )
endforeach

# Logo bundled for the shareable card and the CapivaraOS page.
install_data('data/brand-logo.png',
  install_dir: datadir / 'org.capivaraos.Config',
)

# Root helpers + polkit policy: only for native packages. In the Flatpak
# they could never run (no way out of the sandbox), so they are left out.
if get_option('native')
  helper_dir = get_option('prefix') / get_option('libexecdir') / 'cos-config'
  helper_conf = configuration_data()
  helper_conf.set('PYTHON_DIR', python_dir)
  helper_conf.set('HELPER_DIR', helper_dir)
  foreach helper : ['journald', 'langpacks', 'multimedia']
    configure_file(
      input: 'data/helpers' / helper + '.in',
      output: helper,
      configuration: helper_conf,
      install: true,
      install_dir: helper_dir,
      install_mode: 'rwxr-xr-x',
    )
  endforeach
  # Policy strings are English for now; translations can be merged into it
  # later, like the metainfo.
  configure_file(
    input: 'data/polkit/org.capivaraos.config.policy.in',
    output: 'org.capivaraos.config.policy',
    configuration: helper_conf,
    install: true,
    install_dir: datadir / 'polkit-1' / 'actions',
  )
endif

# Translations (compiles po/<lang>.po -> share/locale/<lang>/.../<domain>.mo).
subdir('po')
