# Security Policy

## Supported versions

| Version | Support |
|---|---|
| 0.11.x | Supported |
| < 0.11 | Not supported |

---

## How to report a vulnerability

**Do not open a public issue for security flaws.** Use a private channel:

1. **GitHub — _Report a vulnerability_** (recommended): in this repository's
   **Security** tab, click *Report a vulnerability* (Private Vulnerability
   Reporting). It is private and structured.
2. **Alternative:** if you don't use GitHub, reach out via our
   [contact form](https://capivaraos.org/en/contact.html) **only to establish
   contact** — do not include the technical details of the flaw there; we'll
   agree on a private channel for the specifics.

Helpful details: the COS Config Center version (`rpm -q cos-config`, or the
menu entry *About COS Config Center*), your distribution
(`cat /etc/os-release`), steps to reproduce, impact and, if possible, a proof
of concept.

**What matters most here:** the app is designed to run as your user and never
asks for root. Settings that change the system go through small helpers in
`/usr/libexec/cos-config/`, started with `pkexec` and allowed by the polkit
policy `org.capivaraos.config.policy`. Anything that lets a user or another
program make those helpers do more than the app asked for is in scope. The
Flatpak build has no helpers and no policy.

**What to expect:** we acknowledge reports as soon as possible, assess them and,
if confirmed, work on a fix and coordinate **responsible disclosure** with you.
As a community project, we respond on a **best-effort** basis — please allow a
reasonable time before public disclosure.
