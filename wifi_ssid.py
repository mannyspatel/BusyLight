"""Home Wi-Fi SSID detection on Windows (no admin)."""

from __future__ import annotations

import re
import subprocess
import sys
from typing import Optional


def parse_netsh_wlan_interfaces(output: str) -> Optional[str]:
    """
    Parse `netsh wlan show interfaces` text.

    Returns the SSID of the connected interface, or None if not connected.
    """
    if not output.strip():
        return None

    blocks = re.split(r"\r?\n\s*\r?\n", output.strip())
    for block in blocks:
        if not re.search(r"(?im)^\s*State\s*:\s*connected", block):
            continue
        match = re.search(r"(?im)^\s*SSID\s*:\s*(.+)$", block)
        if match:
            ssid = match.group(1).strip()
            if ssid:
                return ssid
    return None


def get_connected_wifi_ssid() -> Optional[str]:
    """Return current Wi-Fi SSID on Windows, or None if unavailable."""
    if sys.platform != "win32":
        return None

    try:
        completed = subprocess.run(
            ["netsh", "wlan", "show", "interfaces"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    text = (completed.stdout or "") + "\n" + (completed.stderr or "")
    return parse_netsh_wlan_interfaces(text)


def is_on_home_wifi(home_ssid: str) -> bool:
    """True if connected to home_ssid; False if wrong SSID or no Wi-Fi."""
    if not home_ssid:
        return True
    current = get_connected_wifi_ssid()
    if current is None:
        return False
    return current == home_ssid