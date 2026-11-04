"""
Teams Status Light Controller for WLED

Monitors Windows camera and microphone usage to control WLED light colors.
Includes audio level monitoring for mute detection.
No admin rights required - works on restricted corporate laptops.
"""

import winreg
import time
from ctypes import cast, POINTER
from datetime import datetime
from typing import NamedTuple, Optional

import requests
from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, IAudioMeterInformation, IAudioEndpointVolume

__version__ = "1.1.0"

# ============= CONFIGURATION =============
WLED_HOST = "wled-busylight.lan"  # Your WLED device hostname or IP
CHECK_INTERVAL = 1.5  # Seconds between checks
REQUEST_TIMEOUT = 2  # Seconds to wait for WLED to respond
DEBUG_MODE = False  # Set to True to see detailed debug output

# Color definitions (RGB format)
COLORS = {
    'off': (0, 255, 0),                  # Green - not in a call
    'in_call_muted': (255, 200, 0),      # Orange - in call, mic muted
    'in_call_quiet': (255, 255, 0),      # Yellow - in call, unmuted but quiet
    'mic_only': (255, 255, 0),           # Yellow - in call, unmuted and speaking
    'camera_only': (255, 100, 0),        # Dark orange - camera on, mic muted
    'camera_quiet': (255, 0, 0),         # Red - camera on, unmuted but quiet
    'camera_and_mic': (255, 0, 0),       # Red - camera on, unmuted and speaking
}

# WLED Effect IDs
EFFECTS = {
    'solid': 0,           # Solid color
    'blink': 1,           # Blink effect
    'breathe': 2,         # Breathe effect
    'wipe': 3,            # Color wipe
    'sweep': 12,          # Sweep effect
    'chase': 28,          # Chase effect
    'twinkle': 42,        # Twinkle effect
    'colorloop': 9,       # Colorloop
}

# State-to-effect mapping
STATE_EFFECTS = {
    'off': 'solid',
    'in_call_muted': 'solid',           # Muted - solid orange
    'in_call_quiet': 'solid',           # Unmuted but quiet - solid yellow
    'mic_only': 'breathe',              # Speaking - breathing yellow
    'camera_only': 'solid',             # Camera on, muted - solid dark orange
    'camera_quiet': 'solid',            # Camera on, unmuted but quiet - solid red
    'camera_and_mic': 'breathe',        # Camera on, speaking - breathing red
}

BRIGHTNESS = 128  # 0-255, adjust brightness level
EFFECT_SPEED = 128  # 0-255, speed of effects (higher = faster)
EFFECT_INTENSITY = 128  # 0-255, intensity of effects

# Audio detection settings
AUDIO_THRESHOLD = 0.01  # Minimum peak level to consider the mic "active" (0.0-1.0)
AUDIO_DETECTION_WINDOW = 3  # Seconds - audio heard within this window counts as "speaking"
# Seconds of exact silence (after audio was previously heard) before assuming the mic
# is muted inside Teams. Teams' mute button does not change the Windows system mute.
MUTE_SILENCE_SECONDS = 15
# =========================================

CONSENT_STORE = r"Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore"


def debug(message: str) -> None:
    """Print a message only when DEBUG_MODE is on."""
    if DEBUG_MODE:
        print(message)


class MicStatus(NamedTuple):
    muted: bool
    speaking: bool


class AudioMonitor:
    """Monitor microphone audio level and mute state using the Windows Core Audio API."""

    def __init__(self):
        self.meter = None
        self.endpoint_volume = None
        self.last_audio_time = 0.0
        self.heard_audio = False  # True once we've ever heard audio (mic is known to work)
        self._initialize_audio()

    def _initialize_audio(self) -> None:
        """Attach to the default microphone's level meter and endpoint volume."""
        try:
            device = AudioUtilities.GetMicrophone()
            if not device:
                print("⚠ Warning: Could not find default microphone for audio monitoring")
                return

            interface = device.Activate(IAudioMeterInformation._iid_, CLSCTX_ALL, None)
            self.meter = cast(interface, POINTER(IAudioMeterInformation))

            interface = device.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            self.endpoint_volume = cast(interface, POINTER(IAudioEndpointVolume))

            debug("✓ Audio monitoring initialized (level + mute detection)")
        except Exception as e:  # COM errors have no common base class
            print(f"⚠ Warning: Could not initialize audio monitoring: {e}")
            print("  Mic mute detection will be less accurate")

    def _system_muted(self) -> bool:
        """True if the Windows system-level mute for the microphone is on."""
        if not self.endpoint_volume:
            return False
        try:
            muted = bool(self.endpoint_volume.GetMute())
            debug(f"    System-level mute: {muted}")
            return muted
        except Exception as e:
            debug(f"    Error reading system mute: {e}")
            return False

    def read_status(self) -> MicStatus:
        """
        Sample the microphone once and report whether it is muted and whether
        the user is speaking.
        """
        if self._system_muted():
            return MicStatus(muted=True, speaking=False)

        if not self.meter:
            # Can't monitor audio: assume an unmuted, active mic while the device is in use.
            return MicStatus(muted=False, speaking=True)

        try:
            peak = self.meter.GetPeakValue()
        except Exception as e:
            debug(f"    Error reading audio level: {e}")
            return MicStatus(muted=False, speaking=True)  # Assume active if we can't read

        now = time.time()
        if peak > 0.001:
            debug(f"    Audio level: {peak:.4f}")

        if peak > AUDIO_THRESHOLD:
            self.heard_audio = True
            self.last_audio_time = now

        since_audio = now - self.last_audio_time
        speaking = since_audio < AUDIO_DETECTION_WINDOW
        debug(f"    Time since audio: {since_audio:.1f}s, speaking: {speaking}")

        # Application-level mute heuristic: the mic worked before, and is now
        # completely silent (not just quiet) for an extended period.
        muted = (
            self.heard_audio
            and peak == 0.0
            and since_audio > MUTE_SILENCE_SECONDS
        )
        if muted:
            debug(f"    Heuristic: silent for {since_audio:.1f}s after audio - likely muted")

        return MicStatus(muted=muted, speaking=speaking and not muted)


def is_teams_using_device(device_type: str) -> bool:
    """
    Check whether Teams is currently using a device ("microphone" or "webcam").

    Windows records per-app usage under the CapabilityAccessManager consent store;
    a LastUsedTimeStop of 0 means the app is using the device right now.
    """
    registry_path = f"{CONSENT_STORE}\\{device_type}"
    debug(f"  Checking {device_type}:")

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, registry_path) as key:
            index = 0
            while True:
                try:
                    app_name = winreg.EnumKey(key, index)
                except OSError:
                    break  # No more subkeys
                index += 1

                if 'teams' not in app_name.lower():
                    continue

                try:
                    with winreg.OpenKey(key, app_name) as app_key:
                        last_used_stop = winreg.QueryValueEx(app_key, "LastUsedTimeStop")[0]
                except OSError:
                    continue  # Key vanished or has no LastUsedTimeStop

                if last_used_stop == 0:
                    debug(f"    ✓ Teams is using {device_type}")
                    return True
    except OSError as e:
        debug(f"Error checking {device_type}: {e}")

    return False


class TeamsMonitor:
    def __init__(self, wled_host: str):
        self.wled_url = f"http://{wled_host}/json/state"
        self.wled_host = wled_host
        self.last_state: Optional[str] = None
        self.audio_monitor = AudioMonitor()
        self.session = requests.Session()

    def get_current_state(self) -> str:
        """Determine the current Teams call state."""
        mic_device_active = is_teams_using_device("microphone")
        cam_device_active = is_teams_using_device("webcam")

        debug(f"\nDevice Status - Mic: {mic_device_active}, Cam: {cam_device_active}")

        if not mic_device_active and not cam_device_active:
            return 'off'

        if mic_device_active:
            mic = self.audio_monitor.read_status()
            debug(f"Mic muted: {mic.muted}, speaking: {mic.speaking}")
        else:
            # Mic not in use by Teams: nothing to read.
            mic = MicStatus(muted=False, speaking=False)

        if cam_device_active:
            if mic.muted:
                return 'camera_only'
            return 'camera_and_mic' if mic.speaking else 'camera_quiet'

        if mic.muted:
            return 'in_call_muted'
        return 'mic_only' if mic.speaking else 'in_call_quiet'

    def _post(self, payload: dict) -> bool:
        """POST a state payload to WLED. Returns True on success."""
        try:
            response = self.session.post(self.wled_url, json=payload, timeout=REQUEST_TIMEOUT)
        except requests.exceptions.RequestException as e:
            print(f"Error connecting to WLED: {e}")
            return False

        if response.status_code != 200:
            print(f"WLED returned status {response.status_code}")
            return False
        return True

    def set_wled_color(self, state: str) -> bool:
        """Send the color and effect for a state to the WLED device."""
        r, g, b = COLORS[state]
        effect_id = EFFECTS[STATE_EFFECTS.get(state, 'solid')]

        return self._post({
            "on": True,
            "bri": BRIGHTNESS,
            "seg": [{
                "col": [[r, g, b]],
                "fx": effect_id,
                "sx": EFFECT_SPEED,
                "ix": EFFECT_INTENSITY,
            }],
        })

    def turn_off_wled(self) -> bool:
        """Turn the WLED light completely off."""
        return self._post({"on": False})

    def _print_banner(self) -> None:
        print("=" * 60)
        print(f"Teams Status Light Controller v{__version__}")
        print("=" * 60)
        print(f"WLED host: {self.wled_host}")
        print(f"Check interval: {CHECK_INTERVAL}s")
        print(f"Audio threshold: {AUDIO_THRESHOLD}")
        print(f"Audio detection window: {AUDIO_DETECTION_WINDOW}s")
        print("\nColor and effect scheme:")
        for state, color in COLORS.items():
            effect = STATE_EFFECTS.get(state, 'solid')
            print(f"  {state.replace('_', ' ').title()}: RGB{color} - {effect}")
        print("\nMonitoring started. Press Ctrl+C to stop.")
        print("=" * 60)

    def run(self) -> None:
        """Main monitoring loop. Turns the light off when it exits."""
        self._print_banner()

        print("\nTesting WLED connection...")
        if self.set_wled_color('off'):
            self.last_state = 'off'
            print("✓ WLED connection successful (light should be GREEN)\n")
        else:
            print("✗ Could not connect to WLED. Check the hostname. Will keep retrying.\n")

        try:
            while True:
                current_state = self.get_current_state()

                # Only update when the state changes (or the last update failed)
                if current_state != self.last_state:
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    effect = STATE_EFFECTS.get(current_state, 'solid')
                    print(f"[{timestamp}] State: {current_state.replace('_', ' ').title()} "
                          f"(effect: {effect})")

                    if self.set_wled_color(current_state):
                        self.last_state = current_state
                    else:
                        print("  Failed to update WLED")

                time.sleep(CHECK_INTERVAL)

        except KeyboardInterrupt:
            print("\n\nStopping monitor...")
        finally:
            self.turn_off_wled()
            print("Light turned OFF. Goodbye!")


def main() -> None:
    print("\nInitializing...")
    TeamsMonitor(WLED_HOST).run()


if __name__ == "__main__":
    main()
