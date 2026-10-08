import os
import tempfile
import unittest
from unittest import mock

from cos_config import env, network as net
from cos_config.ops import common, network as rootops


class HostnameTest(unittest.TestCase):
    def test_valid_names_are_lowered(self):
        self.assertEqual(net.valid_hostname(" Meu-PC "), "meu-pc")
        self.assertEqual(net.hostname_argv("sala2"), ["hostnamectl", "set-hostname", "sala2"])

    def test_invalid_names(self):
        for bad in ("", "meu pc", "-pc", "pc-", "pc.local", "pç", "a" * 64, "pc;reboot", "$(id)"):
            with self.assertRaises(ValueError, msg=bad):
                net.valid_hostname(bad)


class KeyTest(unittest.TestCase):
    def test_public_key_and_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "id_ed25519")
            self.assertIsNone(net.public_key(path))
            with open(path + ".pub", "w", encoding="utf-8") as fh:
                fh.write("ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIabcdefgh ana@sala\n")
            public = net.public_key(path)
            self.assertEqual(net.key_summary(public), "ssh-ed25519 …abcdefgh ana@sala")

    def test_keygen_argv(self):
        argv = net.keygen_argv("/tmp/k", "ana@sala")
        self.assertEqual(argv, ["ssh-keygen", "-q", "-t", "ed25519", "-N", "",
                                "-f", "/tmp/k", "-C", "ana@sala"])


class SshTest(unittest.TestCase):
    def test_unit_name(self):
        self.assertEqual(rootops.parse_ssh_unit(
            "sshd.service disabled disabled\nsshd.socket disabled disabled\n"), "sshd")
        self.assertEqual(rootops.parse_ssh_unit("ssh.service enabled enabled\n"), "ssh")
        self.assertIsNone(rootops.parse_ssh_unit("ssh-agent.socket static -\n"))
        self.assertIsNone(rootops.parse_ssh_unit(""))

    def test_enable_with_firewall(self):
        cmds = rootops.ssh_commands(True, "sshd", env.FEDORA, "public")
        self.assertEqual(cmds[0], ["systemctl", "enable", "--now", "sshd"])
        self.assertEqual(cmds[1], ["firewall-cmd", "--zone=public", "--add-service=ssh"])
        self.assertEqual(cmds[2], cmds[1] + ["--permanent"])

    def test_enable_installs_when_missing(self):
        cmds = rootops.ssh_commands(True, None, env.DEBIAN)
        self.assertIn("openssh-server", cmds[0])
        self.assertEqual(cmds[1], ["systemctl", "enable", "--now", "ssh"])
        self.assertEqual(rootops.ssh_commands(True, None, env.FEDORA)[1][-1], "sshd")
        with self.assertRaises(common.ValidationError):
            rootops.ssh_commands(True, None, "unknown")

    def test_disable(self):
        self.assertEqual(rootops.ssh_commands(False, "sshd", env.FEDORA, "public"),
                         [["systemctl", "disable", "--now", "sshd"]])
        self.assertEqual(rootops.ssh_commands(False, None, env.FEDORA), [])


class DnsTest(unittest.TestCase):
    def test_render_and_read_back(self):
        with tempfile.TemporaryDirectory() as root:
            self.assertIsNone(rootops.read_provider(root))
            rootops.set_dns("quad9", root=root, apply=False)
            with open(rootops.dropin_path(root), encoding="utf-8") as fh:
                text = fh.read()
            self.assertIn("DNS=9.9.9.9#dns.quad9.net 149.112.112.112#dns.quad9.net\n", text)
            self.assertIn("DNSOverTLS=yes\n", text)
            self.assertEqual(rootops.read_provider(root), "quad9")
            rootops.set_dns(rootops.AUTO, root=root, apply=False)
            self.assertFalse(os.path.exists(rootops.dropin_path(root)))
            rootops.set_dns(rootops.AUTO, root=root, apply=False)  # already gone: fine

    def test_unknown_provider(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(common.ValidationError):
                rootops.set_dns("evil", root=root, apply=False)
            self.assertFalse(os.path.exists(rootops.dropin_path(root)))

    def test_foreign_file_reads_as_automatic(self):
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.dirname(rootops.dropin_path(root)))
            with open(rootops.dropin_path(root), "w", encoding="utf-8") as fh:
                fh.write("# provider: evil\n[Resolve]\nDNS=6.6.6.6\n")
            self.assertIsNone(rootops.read_provider(root))

    def _apply(self, root, provider, probe):
        with mock.patch.object(rootops, "resolved_active", return_value=True), \
             mock.patch.object(rootops, "_restart_resolved") as restart, \
             mock.patch.object(rootops, "_probe", side_effect=probe):
            try:
                rootops.set_dns(provider, root=root)
            finally:
                self.restarts = restart.call_count

    def test_probe_failure_restores_previous(self):
        with tempfile.TemporaryDirectory() as root:
            self._apply(root, "cloudflare", None)
            self.assertEqual(self.restarts, 1)
            with self.assertRaises(RuntimeError) as ctx:
                self._apply(root, "adguard", RuntimeError("timeout"))
            self.assertIn("restored", str(ctx.exception))
            self.assertEqual(self.restarts, 2)  # apply + roll back
            self.assertEqual(rootops.read_provider(root), "cloudflare")

    def test_probe_failure_with_no_previous_removes_file(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(RuntimeError):
                self._apply(root, "google", RuntimeError("timeout"))
            self.assertFalse(os.path.exists(rootops.dropin_path(root)))

    def test_refuses_without_resolved(self):
        with tempfile.TemporaryDirectory() as root, \
             mock.patch.object(rootops, "resolved_active", return_value=False):
            with self.assertRaises(common.ValidationError):
                rootops.set_dns("quad9", root=root)
            self.assertFalse(os.path.exists(rootops.dropin_path(root)))

    def test_describe(self):
        self.assertEqual(rootops.describe_dns(rootops.AUTO)[0],
                         "sudo rm -f /etc/systemd/resolved.conf.d/cos-config.conf")
        self.assertIn("tee /etc/systemd/resolved.conf.d/cos-config.conf",
                      rootops.describe_dns("google")[1])


class HelperArgsTest(unittest.TestCase):
    def test_rejects_anything_else(self):
        for argv in ([], ["ssh"], ["ssh", "maybe"], ["dns"], ["dns", "1.2.3.4"],
                     ["dns", "quad9", "x"], ["hostname", "pc"], ["ssh", "on", "--now"]):
            with mock.patch.object(rootops, "set_ssh") as ssh, \
                 mock.patch.object(rootops, "set_dns") as dns:
                with self.assertRaises(common.ValidationError, msg=argv):
                    rootops.helper_main(argv)
                ssh.assert_not_called()
                dns.assert_not_called()

    def test_dispatch(self):
        with mock.patch.object(rootops, "set_ssh") as ssh, mock.patch.object(rootops, "set_dns") as dns:
            rootops.helper_main(["ssh", "off"])
            rootops.helper_main(["dns", "auto"])
            ssh.assert_called_once_with(False)
            dns.assert_called_once_with("auto")
