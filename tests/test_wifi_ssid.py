import unittest

from wifi_ssid import parse_netsh_wlan_interfaces


SAMPLE_CONNECTED = """
    Name                   : Wi-Fi
    Description            : Intel Wireless
    GUID                   : {00000000-0000-0000-0000-000000000000}
    Physical address       : 00:11:22:33:44:55
    Interface type         : Primary
    State                  : connected
    SSID                   : HomeNetwork
    BSSID                  : aa:bb:cc:dd:ee:ff
"""

SAMPLE_DISCONNECTED = """
    Name                   : Wi-Fi
    State                  : disconnected
    SSID                   :
"""


class TestWifiParse(unittest.TestCase):
    def test_connected_ssid(self):
        self.assertEqual(parse_netsh_wlan_interfaces(SAMPLE_CONNECTED), "HomeNetwork")

    def test_disconnected_returns_none(self):
        self.assertIsNone(parse_netsh_wlan_interfaces(SAMPLE_DISCONNECTED))

    def test_empty(self):
        self.assertIsNone(parse_netsh_wlan_interfaces(""))


if __name__ == "__main__":
    unittest.main()