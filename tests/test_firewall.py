import unittest
from unittest import mock

from cos_config import firewall as fw
from cos_config.ops import common, firewall as rootops

LIST_ALL = """FedoraWorkstation (default, active)
  target: default
  interfaces: wlo1
  sources: 
  services: dhcpv6-client samba-client ssh
  ports: 1025-65535/udp 1025-65535/tcp 80/tcp
  protocols: 
  rich rules: 
"""
STRICT = """public (active)
  services: ssh kdeconnect
  ports: 8080/tcp 443/tcp 5000/udp
"""


class ParseTest(unittest.TestCase):
    def test_list_all(self):
        info = fw.parse_list_all(LIST_ALL)
        self.assertEqual(info["zone"], "FedoraWorkstation")
        self.assertEqual(info["services"], {"dhcpv6-client", "samba-client", "ssh"})
        self.assertTrue(fw.high_ports_open(info["ports"]))
        self.assertEqual(fw.custom_ports(info["ports"]), ["80/tcp"])

    def test_strict_zone_and_port_order(self):
        info = fw.parse_list_all(STRICT)
        self.assertFalse(fw.high_ports_open(info["ports"]))
        self.assertEqual(fw.custom_ports(info["ports"]), ["443/tcp", "5000/udp", "8080/tcp"])
        self.assertFalse(fw.high_ports_open({"1025-65535/tcp"}))  # udp half only

    def test_covered_by_high_range(self):
        ports = fw.parse_list_all(LIST_ALL)["ports"]
        self.assertTrue(fw.covered_by_high_range("8080/tcp", ports))
        self.assertTrue(fw.covered_by_high_range("1025/udp", ports))
        self.assertFalse(fw.covered_by_high_range("1024/tcp", ports))   # just below
        self.assertFalse(fw.covered_by_high_range("443/tcp", ports))
        self.assertFalse(fw.covered_by_high_range("8080/tcp", fw.parse_list_all(STRICT)["ports"]))
        self.assertFalse(fw.covered_by_high_range("8080/tcp", {"1025-65535/udp"}))  # other protocol

    def test_empty(self):
        self.assertEqual(fw.parse_list_all(""), {"zone": "", "services": set(), "ports": set()})

    def test_default_route_interface(self):
        self.assertEqual(fw.default_route_interface(
            "default via 192.168.1.1 dev wlo1 proto dhcp src 192.168.1.5 metric 600\n"), "wlo1")
        self.assertIsNone(fw.default_route_interface(""))


class PresetTest(unittest.TestCase):
    def state(self, pid, text):
        preset = next(p for p in fw.PRESETS if p[0] == pid)
        return fw.preset_state(preset, fw.parse_list_all(text))

    def test_states(self):
        self.assertEqual(self.state("ssh", LIST_ALL), "on")
        self.assertEqual(self.state("samba", LIST_ALL), "off")      # low port: range does not help
        self.assertEqual(self.state("kdeconnect", LIST_ALL), "open")  # only via the high range
        self.assertEqual(self.state("kdeconnect", STRICT), "on")
        self.assertEqual(self.state("syncthing", STRICT), "off")
        self.assertEqual(self.state("web", LIST_ALL), "off")        # needs http AND https

    def test_every_preset_service_is_allowlisted(self):
        for _pid, services, _low in fw.PRESETS:
            for service in services:
                self.assertIn(service, rootops.SERVICES)

    def test_changes(self):
        web = next(p for p in fw.PRESETS if p[0] == "web")
        self.assertEqual(fw.preset_changes(web, True),
                         [("service", "add", "http"), ("service", "add", "https")])
        self.assertEqual(fw.strict_changes(True),
                         [("port", "remove", "1025-65535/tcp"), ("port", "remove", "1025-65535/udp")])
        self.assertEqual(fw.strict_changes(False)[0], ("port", "add", "1025-65535/tcp"))
        self.assertEqual(fw.helper_args("public", [("port", "add", "8080/tcp")]),
                         ["public", "port:add:8080/tcp"])


class RootSideTest(unittest.TestCase):
    def test_port_validation(self):
        self.assertEqual(rootops.validate_port("8080/tcp"), "8080/tcp")
        self.assertEqual(rootops.validate_port("0080/udp"), "80/udp")
        self.assertEqual(rootops.validate_port("1025-65535/udp"), "1025-65535/udp")
        for bad in ("0/tcp", "65536/tcp", "80", "80/sctp", "1-65535/tcp", "22-80/tcp",
                    "80/tcp --permanent", "", "80/tcp;reboot", "-1/tcp"):
            with self.assertRaises(common.ValidationError, msg=bad):
                rootops.validate_port(bad)

    def test_commands_runtime_and_permanent(self):
        cmds = rootops.commands("service", "add", "FedoraWorkstation", "samba")
        self.assertEqual(cmds, [
            ["firewall-cmd", "--zone=FedoraWorkstation", "--add-service=samba"],
            ["firewall-cmd", "--zone=FedoraWorkstation", "--add-service=samba", "--permanent"],
        ])
        self.assertEqual(rootops.commands("port", "remove", "public", "8080/tcp")[0][-1],
                         "--remove-port=8080/tcp")

    def test_commands_reject(self):
        for args in (("service", "add", "public", "telnet"),
                     ("service", "add", "public", "ssh --permanent"),
                     ("service", "drop", "public", "ssh"),
                     ("rich-rule", "add", "public", "x"),
                     ("port", "add", "public; reboot", "80/tcp"),
                     ("port", "add", "--zone=x", "80/tcp"),
                     ("port", "add", "", "80/tcp")):
            with self.assertRaises(common.ValidationError, msg=args):
                rootops.commands(*args)

    def test_helper_validates_everything_before_running_anything(self):
        with mock.patch.object(common, "run_cmd") as run, \
                mock.patch.object(rootops, "known_zones", return_value=["public"]):
            with self.assertRaises(common.ValidationError):
                rootops.helper_main(["public", "service:add:ssh", "service:add:telnet"])
            with self.assertRaises(common.ValidationError):
                rootops.helper_main(["nozone", "service:add:ssh"])
            with self.assertRaises(common.ValidationError):
                rootops.helper_main(["public"])
            run.assert_not_called()
            rootops.helper_main(["public", "service:add:ssh", "port:remove:8080/tcp"])
            self.assertEqual(run.call_count, 4)  # 2 changes x (runtime + permanent)

    def test_describe(self):
        lines = rootops.describe([("port", "add", "8080/tcp")], "public")
        self.assertEqual(lines, ["sudo firewall-cmd --zone=public --add-port=8080/tcp",
                                 "sudo firewall-cmd --zone=public --add-port=8080/tcp --permanent"])


if __name__ == "__main__":
    unittest.main()
