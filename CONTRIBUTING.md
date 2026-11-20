# Contributing

## How to contribute

- **Found a bug or have an idea?** Open an
  [issue](https://github.com/capivaraos/cos-config/issues).
- **Security vulnerability?** Do **not** open a public issue — follow
  [SECURITY.md](SECURITY.md).
- **Want to send code?** Fork, branch from `main`, make focused changes and
  open a pull request. A maintainer will review.

### Before you open a pull request

- Run the tests: `python3 -m unittest discover -s tests -t .`
- Try the app from the source tree: `python3 run.py` (see the
  [README](README.md) for requirements and for testing a helper without
  installing it).
- **User-interface text** is written in English and wrapped in `_()`. If you add
  or change strings, refresh the template and the translation:
  `meson compile -C builddir org.capivaraos.Config-update-po`, then translate the
  new entries in `po/pt_BR.po` or say in the pull request that they still need
  translating.
- **Code that runs as root** lives in `src/cos_config/ops/` (no GTK, unit-tested)
  and runs as root only through the helpers in `data/helpers/` and the polkit
  policy. Changes there get a security review before merging: keep them small,
  validate every argument, and add tests.

### Writing commits, comments and pull requests

**Commit messages** say what changed, in English, in the imperative, in a
subject line of at most 72 characters. An optional short body describes the
effect for users and how the change was tested.

**Code comments** explain what the code cannot show by itself. Do not use
comments for change history, dates, or who asked for what.

**Branch names** follow `type/short-description`, where type is one of `feat`,
`fix`, `docs`, `chore`, `build`, `test`, `release`.

**Pull requests** do one thing. The description has three short sections:
*What changes*, *Effect for users* and *How it was tested*.

**Never commit** secrets, personal data, e-mail addresses, or paths and user
names from your own machine. Use placeholders such as `/home/USER`.

A `Guards` check runs on every pull request. If it reports that a file, message
or name does not follow these guidelines, rewrite it and push again.

### License

By contributing, you agree to license your code under **GPL-3.0-or-later**
(see [COPYING](COPYING)). The "CapivaraOS" and "COS Config Center" names, logos
and icons are trademarks of the project (see [TRADEMARK.md](TRADEMARK.md)).
Please follow our [Code of Conduct](CODE_OF_CONDUCT.md).
