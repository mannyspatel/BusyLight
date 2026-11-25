"""
BusyLight launcher: system tray (Windows) + background controller loop.
"""

from __future__ import annotations

import argparse
import atexit
import sys
import threading
from pathlib import Path
from typing import Optional

from busylight_config import default_config_path, load_config
from teams_light_controller import TeamsMonitor


def _default_tray() -> bool:
    return sys.platform == "win32"


def run_headless(monitor: TeamsMonitor, stop_event: threading.Event) -> None:
    try:
        monitor.run(stop_event=stop_event)
    finally:
        stop_event.set()


def run_with_tray(
    monitor: TeamsMonitor,
    stop_event: threading.Event,
    config_path: Optional[Path],
) -> None:
    from tray_ui import TrayApp

    tray = TrayApp(monitor, stop_event, config_path)
    worker = threading.Thread(
        target=run_headless,
        args=(monitor, stop_event),
        name="busylight-controller",
        daemon=True,
    )
    worker.start()
    tray.run()


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="BusyLight WLED status controller")
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to config.yaml (default: ./config.yaml)",
    )
    parser.add_argument(
        "--no-tray",
        action="store_true",
        help="Run without system tray (console mode)",
    )
    parser.add_argument(
        "--tray",
        action="store_true",
        help="Force system tray UI (requires pystray on Windows)",
    )
    args = parser.parse_args(argv)

    config_path = args.config or default_config_path()
    if not config_path.is_file():
        print(
            f"Missing {config_path}. Copy config.yaml.example to config.yaml and edit.",
            file=sys.stderr,
        )
        return 1

    config = load_config(config_path)
    monitor = TeamsMonitor(config)
    stop_event = threading.Event()

    def cleanup():
        stop_event.set()
        try:
            monitor.shutdown()
        except Exception:
            pass

    atexit.register(cleanup)

    use_tray = args.tray or (_default_tray() and not args.no_tray)
    if use_tray:
        try:
            run_with_tray(monitor, stop_event, config_path)
            return 0
        except ImportError as exc:
            print(f"Tray mode unavailable ({exc}); falling back to console.", file=sys.stderr)
        except Exception as exc:
            print(f"Tray failed ({exc}); falling back to console.", file=sys.stderr)

    monitor.run(stop_event=stop_event)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())