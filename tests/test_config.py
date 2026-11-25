import unittest
from pathlib import Path

import yaml

from busylight_config import (
    DEFAULTS,
    BusyLightConfig,
    load_config,
    load_example_config,
    repo_root,
)


class TestConfig(unittest.TestCase):
    def test_example_file_loads(self):
        example = repo_root() / "config.yaml.example"
        self.assertTrue(example.is_file(), "config.yaml.example must exist")
        cfg = load_config(example)
        self.assertEqual(cfg.wled_host, "wled-busylight.lan")
        self.assertEqual(cfg.home_wifi_ssid, "YourHomeWiFi")
        self.assertIn("teams", cfg.app_allowlist or [])

    def test_defaults_when_file_missing(self):
        missing = repo_root() / "this-file-does-not-exist.yaml"
        cfg = load_config(missing)
        self.assertEqual(cfg.check_interval, DEFAULTS["check_interval"])
        self.assertEqual(cfg.colors["off"], (0, 255, 0))
        self.assertFalse(cfg.debug)

    def test_partial_yaml_merges_defaults(self):
        data = {"wled_host": "192.168.1.50", "debug": True}
        cfg = BusyLightConfig.from_dict(data)
        self.assertEqual(cfg.wled_host, "192.168.1.50")
        self.assertTrue(cfg.debug)
        self.assertEqual(cfg.check_interval, DEFAULTS["check_interval"])
        self.assertEqual(cfg.max_retries, DEFAULTS["max_retries"])

    def test_load_example_helper(self):
        cfg = load_example_config()
        self.assertIsInstance(cfg, BusyLightConfig)

    def test_example_is_valid_yaml(self):
        example = repo_root() / "config.yaml.example"
        with example.open(encoding="utf-8") as fh:
            parsed = yaml.safe_load(fh)
        self.assertIsInstance(parsed, dict)
        self.assertIn("app_allowlist", parsed)


if __name__ == "__main__":
    unittest.main()