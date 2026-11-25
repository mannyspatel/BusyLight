import unittest
from unittest.mock import patch

from wifi_ssid import is_on_home_wifi, parse_netsh_wlan_interfaces


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

SAMPLE_MULTI_ONE_DUMP = """
There are 2 interfaces on the system:

    Name                   : Wi-Fi
    Description            : Intel Wireless
    State                  : disconnected
    SSID                   : CorpGuest

    Name                   : Wi-Fi 2
    Description            : USB WLAN
    State                  : connected
    SSID                   : HomeNetwork
"""

SAMPLE_WIN11_CONNECTED = """
    Name                   : Wi-Fi
    State                  : connected
    Network name (SSID)    : MyHomeWifi
"""


class TestWifiParse(unittest.TestCase):
    def test_connected_ssid(self):
        self.assertEqual(parse_netsh_wlan_interfaces(SAMPLE_CONNECTED), "HomeNetwork")

    def test_disconnected_returns_none(self):
        self.assertIsNone(parse_netsh_wlan_interfaces(SAMPLE_DISCONNECTED))

    def test_empty(self):
        self.assertIsNone(parse_netsh_wlan_interfaces(""))

    def test_multi_interface_connected_second(self):
        self.assertEqual(parse_netsh_wlan_interfaces(SAMPLE_MULTI_ONE_DUMP), "HomeNetwork")

    def test_win11_network_name_label(self):
        self.assertEqual(parse_netsh_wlan_interfaces(SAMPLE_WIN11_CONNECTED), "MyHomeWifi")


class TestIsOnHomeWifi(unittest.TestCase):
    @patch("wifi_ssid.get_connected_wifi_ssid", return_value="HomeNetwork")
    def test_case_insensitive_match(self, _mock):
        self.assertTrue(is_on_home_wifi("homenetwork"))

    @patch("wifi_ssid.get_connected_wifi_ssid", return_value="GuestWiFi")
    def test_mismatch(self, _mock):
        self.assertFalse(is_on_home_wifi("HomeNetwork"))