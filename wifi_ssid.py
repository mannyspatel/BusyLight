"""Home Wi-Fi SSID detection on Windows (no admin)."""

from __future__ import annotations

import locale
import re
import subprocess
import sys
from typing import Any, List, Optional

_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)


def _decode_subprocess_output(data: bytes) -> str:
    if not data:
        return ""
    encodings: List[str] = []
    try:
        enc = locale.getpreferredencoding(False)
        if enc:
            encodings.append(enc)
    except (OSError, ValueError):
        pass
    for enc in ("cp1252", "cp850", "utf-8"):
        if enc not in encodings:
            encodings.append(enc)
    for enc in encodings:
        try:
            return data.decode(enc, errors="replace")
        except LookupError:
            continue
    return data.decode("utf-8", errors="replace")


def parse_netsh_wlan_interfaces(output: str) -> Optional[str]:
    """
    Parse `netsh wlan show interfaces` text.

    Returns the SSID of the connected interface, or None if not connected.
    """
    if not output.strip():
        return None

    sections: List[List[str]] = []
    current: List[str] = []

    for line in output.splitlines():
        if re.match(r"^\s*Name\s*:", line, re.IGNORECASE):
            if current:
                sections.append(current)
            current = [line]
        else:
            current.append(line)
    if current:
        sections.append(current)

    if not sections:
        sections = [output.splitlines()]

    for section in sections:
        block = "\n".join(section)
        if not re.search(r"(?im)^\s*State\s*:\s*connected\s*$", block):
            continue
        for pattern in (
            r"(?im)^\s*Network name \(SSID\)\s*:\s*(.+)$",
            r"(?im)^\s*SSID\s*:\s*(.+)$",
        ):
            match = re.search(pattern, block)
            if match:
                ssid = match.group(1).strip()
                if ssid:
                    return ssid
    return None


def get_connected_wifi_ssid() -> Optional[str]:
    """Return current Wi-Fi SSID on Windows, or None if unavailable."""
    if sys.platform != "win32":
        return None

    run_kwargs: dict[str, Any] = {"creationflags": _CREATE_NO_WINDOW}

    try:
        completed = subprocess.run(
            ["netsh", "wlan", "show", "interfaces"],
            capture_output=True,
            timeout=10,
            check=False,
            **run_kwargs,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    text = _decode_subprocess_output(completed.stdout or b"")
    if completed.stderr:
        text += "\n" + _decode_subprocess_output(completed.stderr)
    return parse_netsh_wlan_interfaces(text)


def is_on_home_wifi(home_ssid: str) -> bool:
    """True if connected to home_ssid; False if wrong SSID or no Wi-Fi."""
    if not home_ssid:
        return True
    current = get_connected_wifi_ssid()
    if current is None:
        return False
    return current.strip().casefold() == home_ssid.strip().casefold()