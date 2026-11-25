"""Load BusyLight settings from YAML with sensible defaults."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore

DEFAULT_COLORS: Dict[str, Tuple[int, int, int]] = {
    "off": (0, 255, 0),
    "in_call_muted": (255, 200, 0),
    "in_call_quiet": (255, 255, 0),
    "mic_only": (255, 255, 0),
    "camera_only": (255, 100, 0),
    "camera_quiet": (255, 0, 0),
    "camera_and_mic": (255, 0, 0),
}

DEFAULT_STATE_EFFECTS: Dict[str, str] = {
    "off": "solid",
    "in_call_muted": "solid",
    "in_call_quiet": "solid",
    "mic_only": "breathe",
    "camera_only": "solid",
    "camera_quiet": "solid",
    "camera_and_mic": "breathe",
}

DEFAULT_EFFECTS: Dict[str, int] = {
    "solid": 0,
    "blink": 1,
    "breathe": 2,
    "wipe": 3,
    "sweep": 12,
    "chase": 28,
    "twinkle": 42,
    "colorloop": 9,
}

DEFAULTS: Dict[str, Any] = {
    "wled_host": "wled-busylight.lan",
    # Documented for Task Scheduler; not used by the monitoring loop (no in-app Wi-Fi polling).
    "home_wifi_ssid": "YourHomeWiFi",
    "app_allowlist": [
        "teams",
        "ms-teams",
        "zoom",
        "webex",
        "ringcentral",
        "skype",
    ],
    "check_interval": 1.5,
    "debug": False,
    "keep_alive_interval": 300,
    "max_retries": 3,
    "idle_timeout": 600,
    "brightness": 128,
    "effect_speed": 128,
    "effect_intensity": 128,
    "audio_threshold": 0.01,
    "audio_detection_window": 3,
    "colors": DEFAULT_COLORS,
    "state_effects": DEFAULT_STATE_EFFECTS,
    "effects": DEFAULT_EFFECTS,
}


def repo_root() -> Path:
    return Path(__file__).resolve().parent


def default_config_path() -> Path:
    return repo_root() / "config.yaml"


def _deep_merge(base: Dict[str, Any], overrides: Dict[str, Any]) -> Dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in overrides.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _normalize_tuple_colors(colors: Dict[str, Any]) -> Dict[str, Tuple[int, int, int]]:
    out: Dict[str, Tuple[int, int, int]] = {}
    for name, value in colors.items():
        if isinstance(value, (list, tuple)) and len(value) == 3:
            out[name] = (int(value[0]), int(value[1]), int(value[2]))
    return out


@dataclass
class BusyLightConfig:
    wled_host: str
    home_wifi_ssid: str
    app_allowlist: Optional[List[str]]
    check_interval: float
    debug: bool
    keep_alive_interval: int
    max_retries: int
    idle_timeout: int
    brightness: int
    effect_speed: int
    effect_intensity: int
    audio_threshold: float
    audio_detection_window: int
    colors: Dict[str, Tuple[int, int, int]] = field(default_factory=dict)
    state_effects: Dict[str, str] = field(default_factory=dict)
    effects: Dict[str, int] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BusyLightConfig":
        merged = _deep_merge(DEFAULTS, data or {})
        allowlist = merged.get("app_allowlist")
        if allowlist is not None and len(allowlist) == 0:
            allowlist = []
        colors = _normalize_tuple_colors(merged.get("colors") or DEFAULT_COLORS)
        return cls(
            wled_host=str(merged["wled_host"]),
            home_wifi_ssid=str(merged["home_wifi_ssid"]),
            app_allowlist=list(allowlist) if allowlist is not None else None,
            check_interval=float(merged["check_interval"]),
            debug=bool(merged["debug"]),
            keep_alive_interval=int(merged["keep_alive_interval"]),
            max_retries=int(merged["max_retries"]),
            idle_timeout=int(merged["idle_timeout"]),
            brightness=int(merged["brightness"]),
            effect_speed=int(merged["effect_speed"]),
            effect_intensity=int(merged["effect_intensity"]),
            audio_threshold=float(merged["audio_threshold"]),
            audio_detection_window=int(merged["audio_detection_window"]),
            colors=colors,
            state_effects=dict(merged.get("state_effects") or DEFAULT_STATE_EFFECTS),
            effects=dict(merged.get("effects") or DEFAULT_EFFECTS),
        )


def load_config(path: Optional[Path] = None) -> BusyLightConfig:
    """Load config from YAML file; missing keys use DEFAULTS."""
    config_path = Path(path) if path else default_config_path()
    raw: Dict[str, Any] = {}
    if config_path.is_file():
        if yaml is None:
            raise RuntimeError(
                "PyYAML is required to load config.yaml. Install with: pip install pyyaml"
            )
        with config_path.open(encoding="utf-8") as fh:
            loaded = yaml.safe_load(fh)
            if isinstance(loaded, dict):
                raw = loaded
    return BusyLightConfig.from_dict(raw)


def load_example_config() -> BusyLightConfig:
    """Load config.yaml.example when present (for tests/docs)."""
    example = repo_root() / "config.yaml.example"
    if example.is_file():
        return load_config(example)
    return BusyLightConfig.from_dict({})