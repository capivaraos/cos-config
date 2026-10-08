"""Remote login (SSH server) and encrypted DNS, the root side.

* SSH: enable or disable the distro's own sshd unit; nothing in
  sshd_config is edited.
* DNS over TLS: a drop-in for systemd-resolved that only COS Config Center
  owns, from a fixed list of public resolvers. Broken DNS means no
  internet, so after restarting resolved a name is looked up; if that
  fails the previous configuration is put back.
"""

import os
import shutil
import subprocess

from .. import distro, env
from . import common

DROPIN_DIR = "/etc/systemd/resolved.conf.d"
DROPIN_NAME = "cos-config.conf"
PROBE_NAME = "example.com"
AUTO = "auto"

# id -> servers as address#tls-name (the name is checked against the certificate).
PROVIDERS = {
    "cloudflare": ("1.1.1.1#cloudflare-dns.com", "1.0.0.1#cloudflare-dns.com"),
    "quad9": ("9.9.9.9#dns.quad9.net", "149.112.112.112#dns.quad9.net"),
    "google": ("8.8.8.8#dns.google", "8.8.4.4#dns.google"),
    "adguard": ("94.140.14.14#dns.adguard-dns.com", "94.140.15.15#dns.adguard-dns.com"),
}


# ---- DNS -----------------------------------------------------------------------
def dropin_path(root="/"):
    return common.rooted(root, os.path.join(DROPIN_DIR, DROPIN_NAME))


def render_dns(provider):
    if provider not in PROVIDERS:
        raise common.ValidationError(f"provider must be one of {', '.join(PROVIDERS)} or {AUTO}")
    return (
        f"# Managed by COS Config Center. provider: {provider}\n"
        "# Delete this file to use the DNS your network gives you.\n"
        "[Resolve]\n"
        f"DNS={' '.join(PROVIDERS[provider])}\n"
        "DNSOverTLS=yes\n"
        "Domains=~.\n"
    )


def read_provider(root="/"):
    """The provider set by our drop-in, or None (automatic)."""
    try:
        with open(dropin_path(root), encoding="utf-8") as fh:
            first = fh.readline()
    except OSError:
        return None
    provider = first.partition("provider:")[2].strip()
    return provider if provider in PROVIDERS else None


def _read(root):
    try:
        with open(dropin_path(root), encoding="utf-8") as fh:
            return fh.read()
    except FileNotFoundError:
        return None


def _write(root, content):
    if content is None:
        try:
            os.unlink(dropin_path(root))
        except FileNotFoundError:
            pass
        return
    os.makedirs(common.rooted(root, DROPIN_DIR), mode=0o755, exist_ok=True)
    common.atomic_write(dropin_path(root), content)


def _restart_resolved():
    common.run_cmd(["systemctl", "restart", "systemd-resolved"])


def _probe():
    """Raise unless a name resolves with the configuration just applied."""
    proc = subprocess.run(["resolvectl", "query", "--cache=no", PROBE_NAME],
                          capture_output=True, text=True, timeout=30)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout).strip() or "name lookup failed")


def resolved_active():
    proc = subprocess.run(["systemctl", "is-active", "systemd-resolved"],
                          capture_output=True, text=True)
    return proc.stdout.strip() == "active"


def set_dns(provider, root="/", apply=True):
    content = None if provider == AUTO else render_dns(provider)
    if apply and not resolved_active():
        raise common.ValidationError("systemd-resolved is not running on this system")
    previous = _read(root)
    _write(root, content)
    if not apply:
        return
    try:
        _restart_resolved()
        _probe()
    except Exception as exc:
        _write(root, previous)
        try:
            _restart_resolved()
        except Exception:
            pass
        raise RuntimeError(
            f"names could not be resolved with that DNS, so the previous one was restored.\n{exc}")


def describe_dns(provider):
    path = os.path.join(DROPIN_DIR, DROPIN_NAME)
    restart = "sudo systemctl restart systemd-resolved"
    if provider == AUTO:
        return [f"sudo rm -f {path}", restart]
    body = render_dns(provider).replace("\n", "\\n")
    return [f"sudo mkdir -p {DROPIN_DIR}", f"printf '{body}' | sudo tee {path}", restart]


# ---- SSH -----------------------------------------------------------------------
def parse_ssh_unit(unit_files):
    """"sshd" (Fedora, Arch, SUSE) or "ssh" (Debian, Ubuntu) from
    `systemctl list-unit-files 'ssh*'`; None when no server is installed."""
    names = {line.split()[0] for line in unit_files.splitlines() if line.split()}
    for unit in ("sshd.service", "ssh.service"):
        if unit in names:
            return unit[:-len(".service")]
    return None


def ssh_unit():
    out = subprocess.run(["systemctl", "list-unit-files", "ssh*", "--no-legend"],
                         capture_output=True, text=True).stdout
    return parse_ssh_unit(out)


def ssh_commands(enable, unit, family, firewall_zone=None):
    """argv lists to turn remote login on or off."""
    cmds = []
    if enable:
        if unit is None:
            manager = distro.for_family(family)
            if manager is None:
                raise common.ValidationError("no SSH server installed and no known package manager")
            cmds.append(manager.install(["openssh-server"]))
            unit = "ssh" if family == env.DEBIAN else "sshd"
        cmds.append(["systemctl", "enable", "--now", unit])
        if firewall_zone:
            base = ["firewall-cmd", f"--zone={firewall_zone}", "--add-service=ssh"]
            cmds += [base, base + ["--permanent"]]
    elif unit is not None:
        cmds.append(["systemctl", "disable", "--now", unit])
    return cmds


def _firewall_zone():
    if not shutil.which("firewall-cmd"):
        return None
    run = lambda *args: subprocess.run(  # noqa: E731
        ["firewall-cmd", *args], capture_output=True, text=True).stdout.strip()
    return run("--get-default-zone") if run("--state") == "running" else None


def set_ssh(enable):
    family = env.detect_family(env.read_os_release())
    for cmd in ssh_commands(enable, ssh_unit(), family, _firewall_zone() if enable else None):
        common.run_cmd(cmd)


def helper_main(argv):
    """argv: ["ssh", "on"|"off"] or ["dns", PROVIDER|"auto"]."""
    if len(argv) == 2 and argv[0] == "ssh" and argv[1] in ("on", "off"):
        set_ssh(argv[1] == "on")
    elif len(argv) == 2 and argv[0] == "dns" and (argv[1] == AUTO or argv[1] in PROVIDERS):
        set_dns(argv[1])
    else:
        raise common.ValidationError("usage: ssh on|off | dns PROVIDER|auto")
