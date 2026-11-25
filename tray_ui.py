"""System tray UI for BusyLight (Windows-friendly main-thread pattern)."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Optional, Tuple

from PIL import Image, ImageDraw
from pystray import Icon, Menu, MenuItem

from teams_light_controller import TeamsMonitor


def _rgb_image(color: Tuple[int, int, int], size: int = 64) -> Image.Image:
    image = Image.new("RGB", (size, size), color)
    draw = ImageDraw.Draw(image)
    draw.ellipse((4, 4, size - 5, size - 5), fill=color, outline=(30, 30, 30))
    return image


class TrayApp:
    def __init__(
        self,
        monitor: TeamsMonitor,
        stop_event: threading.Event,
        config_path: Optional[Path] = None,
    ):
        self.monitor = monitor
        self.stop_event = stop_event
        self.config_path = config_path
        self._status_text = "Starting..."
        initial_rgb = monitor.current_rgb
        self.icon = Icon(
            "busylight",
            _rgb_image(initial_rgb),
            "BusyLight",
            menu=self._build_menu(),
        )
        monitor.set_state_change_callback(self._on_state_change)

    def _build_menu(self) -> Menu:
        return Menu(
            MenuItem(lambda item: self._status_text, None, enabled=False),
            Menu.SEPARATOR,
            MenuItem("Exit", self._on_exit),
        )

    def _on_state_change(self, state: str, rgb: Tuple[int, int, int]) -> None:
        name = state.replace("_", " ").title()
        self._status_text = f"Status: {name}  RGB{rgb}"
        if self.icon:
            self.icon.icon = _rgb_image(rgb)
            self.icon.title = f"BusyLight - {name}"

    def _on_exit(self, icon: Icon, _item) -> None:
        self.stop_event.set()
        try:
            self.monitor.shutdown()
        except Exception:
            pass
        icon.stop()

    def run(self) -> None:
        self.icon.run()