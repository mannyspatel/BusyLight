"""
Teams Status Light Controller for WLED
Monitors Windows camera and microphone usage to control WLED light colors
Includes audio level monitoring for accurate mute detection
No admin rights required - works on restricted corporate laptops
"""

__version__ = "1.2"

import winreg
import requests
import time
import json
import atexit
import threading
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from busylight_config import BusyLightConfig, load_config
from ctypes import cast, POINTER
from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, IAudioMeterInformation, IAudioEndpointVolume, ISimpleAudioVolume
from comtypes import GUID

def _subkey_matches_allowlist(subkey_path: str, allowlist: Optional[List[str]]) -> bool:
    """Return True if allowlist is empty/None or path contains any allowlist entry."""
    if not allowlist:
        return True
    path_lower = subkey_path.lower()
    return any(entry.lower() in path_lower for entry in allowlist)


class AudioMonitor:
    """Monitor microphone audio levels and mute state using Windows Core Audio API"""
    
    def __init__(self, config: BusyLightConfig):
        self.config = config
        self.meter = None
        self.endpoint_volume = None
        self.teams_session = None
        self.last_audio_time = 0
        self.first_audio_detected = False  # Track if we've ever detected audio
        self.audio_device = None
        self.initialize_audio_meter()
    
    def initialize_audio_meter(self):
        """Initialize the audio meter and endpoint volume for the default microphone"""
        try:
            # Get the default microphone device
            devices = AudioUtilities.GetMicrophone()
            if devices:
                # Initialize audio meter for level detection
                interface = devices.Activate(
                    IAudioMeterInformation._iid_, CLSCTX_ALL, None)
                self.meter = cast(interface, POINTER(IAudioMeterInformation))
                
                # Initialize endpoint volume for system-level mute state detection
                interface_volume = devices.Activate(
                    IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                self.endpoint_volume = cast(interface_volume, POINTER(IAudioEndpointVolume))
                
                # Store device for session enumeration
                self.audio_device = devices
                
                if self.config.debug:
                    print("✓ Audio monitoring initialized (level + mute detection)")
            else:
                print("⚠ Warning: Could not find default microphone for audio monitoring")
        except Exception as e:
            print(f"⚠ Warning: Could not initialize audio monitoring: {e}")
            print("  Mic mute detection will be less accurate")
    
    def get_teams_session_mute(self) -> Optional[bool]:
        """
        Get mute status from Teams audio session if available.
        This checks per-application mute state, which matches what Windows shows in system tray.
        """
        if not self.audio_device:
            return None
        
        try:
            # Get IAudioSessionManager2 interface to enumerate sessions
            # This requires accessing COM interfaces directly
            IID_IAudioSessionManager2 = GUID("{77AA99A0-1BD6-484F-8BC7-2C654C9A9B6F}")
            session_manager = self.audio_device.Activate(
                IID_IAudioSessionManager2, CLSCTX_ALL, None)
            
            if not session_manager:
                return None
            
            # Get session enumerator
            session_enumerator = session_manager.GetSessionEnumerator()
            if not session_enumerator:
                return None
            
            # Enumerate through all audio sessions
            count = session_enumerator.GetCount()
            for i in range(count):
                try:
                    session = session_enumerator.GetSession(i)
                    if not session:
                        continue
                    
                    # Get IAudioSessionControl2 to access process ID and display name
                    IID_IAudioSessionControl2 = GUID("{BFB7FF88-7239-4FC9-8FA2-07C950BE9C6D}")
                    try:
                        session_control2 = session.QueryInterface(IID_IAudioSessionControl2)
                        if session_control2:
                            # Get process ID to identify Teams
                            process_id = session_control2.GetProcessId()
                            
                            # Check if this is Teams process
                            # Try to get process name using Windows API (ctypes) to avoid psutil dependency
                            try:
                                import ctypes
                                from ctypes import wintypes
                                
                                # Open process to query name
                                PROCESS_QUERY_INFORMATION = 0x0400
                                PROCESS_VM_READ = 0x0010
                                kernel32 = ctypes.windll.kernel32
                                
                                h_process = kernel32.OpenProcess(
                                    PROCESS_QUERY_INFORMATION | PROCESS_VM_READ,
                                    False, process_id)
                                
                                if h_process:
                                    try:
                                        # Get process name
                                        MAX_PATH = 260
                                        buffer = ctypes.create_unicode_buffer(MAX_PATH)
                                        size = wintypes.DWORD(MAX_PATH)
                                        
                                        # QueryFullProcessImageNameW
                                        if kernel32.QueryFullProcessImageNameW(
                                            h_process, 0, buffer, ctypes.byref(size)):
                                            proc_path = buffer.value
                                            proc_name = proc_path.lower()
                                            
                                            # Check if this is Teams
                                            if 'teams' in proc_name or 'ms-teams' in proc_name:
                                                # Found Teams session - get mute status
                                                session_volume = session.QueryInterface(ISimpleAudioVolume._iid_)
                                                if session_volume:
                                                    muted = session_volume.GetMute()
                                                    if self.config.debug:
                                                        print(f"    Teams session mute (PID {process_id}): {muted}")
                                                    kernel32.CloseHandle(h_process)
                                                    return bool(muted)
                                    finally:
                                        kernel32.CloseHandle(h_process)
                            except Exception as e:
                                if self.config.debug:
                                    print(f"    Error checking process name: {e}")
                                continue
                    except:
                        # If we can't get IAudioSessionControl2, skip this session
                        continue
                except:
                    continue
        except Exception as e:
            if self.config.debug:
                print(f"    Error checking Teams session mute: {e}")
        
        return None
    
    def is_muted(self) -> bool:
        """
        Check if microphone is muted using multiple detection methods
        Returns True if microphone is muted
        """
        # Method 1: Check per-application audio session mute (most accurate for Teams)
        # This matches what Windows shows in the system tray
        session_muted = self.get_teams_session_mute()
        if session_muted is not None:
            if self.config.debug:
                print(f"    Application session mute: {session_muted}")
            if session_muted:
                return True
        
        # Method 2: Check system-level mute state (fallback)
        system_muted = False
        if self.endpoint_volume:
            try:
                system_muted = bool(self.endpoint_volume.GetMute())
                if self.config.debug:
                    print(f"    System-level mute: {system_muted}")
            except Exception as e:
                if self.config.debug:
                    print(f"    Error reading system mute: {e}")
        
        if system_muted:
            return True
        
        # Method 2: Enhanced heuristic for application-level mute detection
        # Teams might mute at app level, so system mute won't reflect it
        # We use: if audio has been consistently zero AND we've detected audio before
        # (meaning mic was working, now it's not), it's likely muted
        if self.meter:
            try:
                peak = self.meter.GetPeakValue()
                current_time = time.time()
                time_since_audio = current_time - self.last_audio_time
                
                # Track if we've ever detected audio (mic was working)
                if peak > self.config.audio_threshold:
                    self.first_audio_detected = True
                    self.last_audio_time = current_time
                
                # Heuristic for application-level mute:
                # Only mark as muted if:
                # 1. We've detected audio before (mic was working)
                # 2. Audio has been completely zero (not just quiet) for an extended period
                # 3. This distinguishes "muted" from "just quiet/not speaking"
                if self.first_audio_detected and peak == 0.0:
                    # Use a longer window to distinguish "muted" from "just quiet"
                    # Only mark as muted if completely silent for 15+ seconds after having detected audio
                    mute_threshold = 15  # 15 seconds of complete silence after audio was detected
                    if time_since_audio > mute_threshold:
                        if self.config.debug:
                            print(f"    Heuristic: Previously detected audio, now zero for {time_since_audio:.1f}s - likely muted")
                        return True
                    elif self.config.debug:
                        print(f"    Heuristic: Zero audio for {time_since_audio:.1f}s, but not long enough to confirm mute")
            except Exception as e:
                if self.config.debug:
                    print(f"    Error in mute heuristic: {e}")
        
        return False
    
    def is_audio_active(self) -> bool:
        """
        Check if microphone is picking up audio above threshold
        Returns True if audio detected recently
        """
        if not self.meter:
            # If we can't monitor audio, assume mic is active when device is in use
            return True
        
        try:
            # Get current audio level (0.0 to 1.0)
            peak = self.meter.GetPeakValue()
            
            if self.config.debug and peak > 0.001:
                print(f"    Audio level: {peak:.4f}")
            
            # If audio is above threshold, update last audio time
            if peak > self.config.audio_threshold:
                self.last_audio_time = time.time()
                return True
            
            # Check if we detected audio recently
            time_since_audio = time.time() - self.last_audio_time
            is_active = time_since_audio < self.config.audio_detection_window
            
            if self.config.debug:
                print(f"    Time since audio: {time_since_audio:.1f}s, Active: {is_active}")
            
            return is_active
            
        except Exception as e:
            if self.config.debug:
                print(f"    Error reading audio level: {e}")
            return True  # Assume active if we can't read


class TeamsMonitor:
    def __init__(self, config: BusyLightConfig):
        self.config = config
        self.wled_host = config.wled_host
        self.last_state: Optional[str] = None
        self._published_state: Optional[str] = "off"
        self._published_rgb: Tuple[int, int, int] = config.colors.get("off", (0, 255, 0))
        self._state_lock = threading.Lock()
        self.audio_monitor = AudioMonitor(config)
        self.session = requests.Session()  # Reuse connections for better reliability
        self.last_wled_update = 0  # Track last successful WLED update time
        self.last_check_time = time.time()  # Track last check time to detect sleep/wake
        self._on_state_change: Optional[Callable[[str, Tuple[int, int, int]], None]] = None

    @property
    def current_state(self) -> Optional[str]:
        with self._state_lock:
            return self._published_state

    @property
    def current_rgb(self) -> Tuple[int, int, int]:
        with self._state_lock:
            return self._published_rgb

    def set_state_change_callback(
        self, callback: Optional[Callable[[str, Tuple[int, int, int]], None]]
    ) -> None:
        self._on_state_change = callback

    def _publish_state(self, state: Optional[str]) -> None:
        if state is None:
            return
        rgb = self.config.colors.get(state, self.config.colors.get("off", (0, 255, 0)))
        with self._state_lock:
            changed = state != self._published_state or rgb != self._published_rgb
            self._published_state = state
            self._published_rgb = rgb
        if changed and self._on_state_change:
            try:
                self._on_state_change(state, rgb)
            except Exception:
                pass
        
    def _consent_key_device_active(
        self, registry_path: str, subkey_relative: str, path_for_allowlist: str
    ) -> bool:
        """
        Recursively walk ConsentStore subkeys; True if LastUsedTimeStop is 0 and allowlist matches.
        """
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, subkey_relative)
        except OSError:
            return False

        try:
            try:
                last_used_stop = winreg.QueryValueEx(key, "LastUsedTimeStop")[0]
                if last_used_stop == 0 and _subkey_matches_allowlist(
                    path_for_allowlist, self.config.app_allowlist
                ):
                    if self.config.debug:
                        print(f"    ✓ In use: {path_for_allowlist}")
                    return True
            except FileNotFoundError:
                pass

            i = 0
            while True:
                try:
                    child_name = winreg.EnumKey(key, i)
                    i += 1
                except OSError:
                    break

                child_relative = f"{subkey_relative}\\{child_name}"
                child_path = f"{path_for_allowlist}\\{child_name}"
                if self._consent_key_device_active(
                    registry_path, child_relative, child_path
                ):
                    return True
        finally:
            winreg.CloseKey(key)

        return False

    def is_device_in_use(self, device_type: str) -> bool:
        """
        Check if microphone or webcam is in use by an allowed application.

        Walks HKCU CapabilityAccessManager ConsentStore recursively (including
        NonPackaged and nested paths). A subkey with LastUsedTimeStop == 0 means
        the device is currently in use.
        """
        registry_path = (
            "Software\\Microsoft\\Windows\\CurrentVersion\\"
            f"CapabilityAccessManager\\ConsentStore\\{device_type}"
        )

        try:
            if self.config.debug:
                print(f"  Checking {device_type} (allowlist={self.config.app_allowlist!r}):")

            i = 0
            root_key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, registry_path)
            try:
                while True:
                    try:
                        subkey_name = winreg.EnumKey(root_key, i)
                        i += 1
                    except OSError:
                        break

                    child_relative = f"{registry_path}\\{subkey_name}"
                    if self._consent_key_device_active(
                        registry_path, child_relative, subkey_name
                    ):
                        if self.config.debug:
                            print(f"    Result: device_active=True")
                        return True
            finally:
                winreg.CloseKey(root_key)

            if self.config.debug:
                print(f"    Result: device_active=False")
            return False

        except Exception as e:
            if self.config.debug:
                print(f"Error checking {device_type}: {e}")
            return False

    def check_device_usage(self, device_type: str) -> bool:
        """Alias for is_device_in_use; kept for backward compatibility."""
        return self.is_device_in_use(device_type)
    
    def get_current_state(self) -> Optional[str]:
        """
        Determine current call state from mic/camera usage and audio levels.
        Returns state name or None.
        """
        mic_device_active = self.is_device_in_use("microphone")
        cam_device_active = self.is_device_in_use("webcam")
        
        if self.config.debug:
            print(f"\nDevice Status - Mic: {mic_device_active}, Cam: {cam_device_active}")
        
        # If neither device is active, not in a call
        if not mic_device_active and not cam_device_active:
            return 'off'
        
        # Check mic state: muted, speaking, or silent
        mic_muted = False
        mic_audio_active = False
        
        if mic_device_active:
            # Check system-level mute first (most reliable)
            system_muted = False
            if self.audio_monitor.endpoint_volume:
                try:
                    system_muted = bool(self.audio_monitor.endpoint_volume.GetMute())
                except:
                    pass
            
            # Check if audio is flowing
            mic_audio_active = self.audio_monitor.is_audio_active()
            
            # Determine mute state:
            # - If system mute is on, definitely muted
            # - If system mute is off but no audio detected, use heuristic to distinguish
            #   "muted at app level" from "just quiet"
            if system_muted:
                mic_muted = True
            else:
                # Only consider muted if heuristic strongly suggests it
                # (i.e., we've seen audio before but now it's been zero for a long time)
                mic_muted = self.audio_monitor.is_muted()
            
            if self.config.debug:
                print(f"Mic muted: {mic_muted} (system: {system_muted}), Audio flowing: {mic_audio_active}")
        
        # Determine state based on device usage, mute state, and audio activity
        if cam_device_active:
            # Camera is on
            if mic_muted:
                # Camera on, mic muted
                return 'camera_only'
            elif mic_audio_active:
                # Camera on, mic on, speaking
                return 'camera_and_mic'
            else:
                # Camera on, mic on but silent (unmuted but not speaking)
                return 'camera_quiet'
        else:
            # Camera is off
            if mic_muted:
                # Camera off, mic muted
                return 'in_call_muted'
            elif mic_audio_active:
                # Camera off, mic on, speaking
                return 'mic_only'
            else:
                # Camera off, mic on but silent (unmuted but not speaking)
                return 'in_call_quiet'
    
    def set_wled_color(self, state: str, retry_count: int = 0):
        """Send color and effect command to WLED device with retry logic"""
        color = self.config.colors[state]
        r, g, b = color
        
        # Get the effect for this state
        effect_name = self.config.state_effects.get(state, 'solid')
        effect_id = self.config.effects.get(effect_name, 0)
        
        url = f"http://{self.wled_host}/json/state"
        payload = {
            "on": True,
            "bri": self.config.brightness,
            "seg": [{
                "col": [[r, g, b]],
                "fx": effect_id,
                "sx": self.config.effect_speed,
                "ix": self.config.effect_intensity
            }]
        }
        
        for attempt in range(self.config.max_retries):
            try:
                # Use session for connection pooling and reuse
                response = self.session.post(url, json=payload, timeout=5)
                
                if response.status_code == 200:
                    self.last_wled_update = time.time()
                    return True
                else:
                    if attempt < self.config.max_retries - 1:
                        if self.config.debug:
                            print(f"  WLED returned status {response.status_code}, retrying...")
                        time.sleep(0.5 * (attempt + 1))  # Exponential backoff
                        continue
                    else:
                        print(f"WLED returned status {response.status_code}")
                        return False
                        
            except requests.exceptions.Timeout:
                if attempt < self.config.max_retries - 1:
                    if self.config.debug:
                        print(f"  WLED request timed out, retrying...")
                    time.sleep(0.5 * (attempt + 1))
                    # Reset session on timeout to clear stale connections
                    self.session.close()
                    self.session = requests.Session()
                    continue
                else:
                    print(f"Error: WLED request timed out after {self.config.max_retries} attempts")
                    return False
                    
            except requests.exceptions.ConnectionError as e:
                if attempt < self.config.max_retries - 1:
                    if self.config.debug:
                        print(f"  WLED connection error, retrying...")
                    time.sleep(0.5 * (attempt + 1))
                    # Reset session on connection error
                    self.session.close()
                    self.session = requests.Session()
                    continue
                else:
                    print(f"Error connecting to WLED: {e}")
                    return False
                    
            except requests.exceptions.RequestException as e:
                if attempt < self.config.max_retries - 1:
                    if self.config.debug:
                        print(f"  WLED request error, retrying...")
                    time.sleep(0.5 * (attempt + 1))
                    continue
                else:
                    print(f"Error connecting to WLED: {e}")
                    return False
        
        return False
    
    def turn_off_wled(self):
        """Turn the WLED light completely off"""
        url = f"http://{self.wled_host}/json/state"
        payload = {"on": False}
        
        for attempt in range(self.config.max_retries):
            try:
                response = self.session.post(url, json=payload, timeout=5)
                if response.status_code == 200:
                    return True
                else:
                    if attempt < self.config.max_retries - 1:
                        time.sleep(0.5 * (attempt + 1))
                        continue
                    else:
                        print(f"WLED returned status {response.status_code}")
                        return False
            except requests.exceptions.RequestException as e:
                if attempt < self.config.max_retries - 1:
                    time.sleep(0.5 * (attempt + 1))
                    self.session.close()
                    self.session = requests.Session()
                    continue
                else:
                    print(f"Error turning off WLED: {e}")
                    return False
        return False
    
    def shutdown(self) -> None:
        """Turn off WLED and close HTTP session."""
        try:
            self.turn_off_wled()
        finally:
            self.session.close()

    def run(
        self,
        stop_event: Optional[threading.Event] = None,
    ) -> None:
        """Main monitoring loop. Stops when stop_event is set."""
        interval = self.config.check_interval
        print("=" * 60)
        print("Teams Status Light Controller with Audio Monitoring")
        print(f"Version {__version__}")
        print("=" * 60)
        print(f"WLED host: {self.wled_host}")
        print(f"Check interval: {interval}s")
        print(f"Audio threshold: {self.config.audio_threshold}")
        print(f"Audio detection window: {self.config.audio_detection_window}s")
        print("\nColor and Effect scheme:")
        for state, color in self.config.colors.items():
            effect = self.config.state_effects.get(state, "solid")
            state_name = state.replace("_", " ").title()
            print(f"  {state_name}: RGB{color} - {effect}")
        print("\nMonitoring started. Press Ctrl+C to stop.")
        print("=" * 60)

        print("\nTesting WLED connection...")
        if self.set_wled_color("off"):
            print("WLED connection successful (light should be GREEN)\n")
            self.last_wled_update = time.time()
            self._publish_state("off")
        else:
            print("Could not connect to WLED. Check wled_host in config.yaml.\n")
            self.last_wled_update = time.time()
            self._publish_state("off")

        try:
            while True:
                if stop_event and stop_event.is_set():
                    break

                current_time = time.time()
                time_since_last_check = current_time - self.last_check_time

                wake_detected = False
                if time_since_last_check > (interval * 2):
                    wake_detected = True
                    if self.config.debug:
                        timestamp = datetime.now().strftime("%H:%M:%S")
                        print(
                            f"[{timestamp}] Detected system wake (gap: {time_since_last_check:.1f}s) - refreshing state"
                        )

                self.last_check_time = current_time
                current_state = self.get_current_state()
                if current_state:
                    self._publish_state(current_state)

                if wake_detected and current_state == "off":
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    print(f"[{timestamp}] System woke - turning off light (not in call)")
                    self.turn_off_wled()
                    self.last_state = None

                time_since_update = current_time - self.last_wled_update

                if self.config.idle_timeout > 0 and time_since_update >= self.config.idle_timeout:
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    print(
                        f"[{timestamp}] Idle timeout ({self.config.idle_timeout}s) - turning off light"
                    )
                    if self.turn_off_wled():
                        self.last_wled_update = time.time()

                state_changed = current_state != self.last_state
                keep_alive_needed = time_since_update >= self.config.keep_alive_interval

                if state_changed or keep_alive_needed:
                    if state_changed and current_state:
                        timestamp = datetime.now().strftime("%H:%M:%S")
                        effect = self.config.state_effects.get(current_state, "solid")
                        state_name = current_state.replace("_", " ").title()
                        print(f"[{timestamp}] State: {state_name} (effect: {effect})")
                    elif self.config.debug:
                        timestamp = datetime.now().strftime("%H:%M:%S")
                        print(f"[{timestamp}] Keep-alive: Refreshing WLED state")

                    if current_state and self.set_wled_color(current_state):
                        self.last_state = current_state
                    else:
                        if state_changed:
                            print("  Failed to update WLED")
                        elif self.config.debug:
                            print("  Keep-alive failed, will retry on next interval")

                if stop_event:
                    if stop_event.wait(interval):
                        break
                else:
                    time.sleep(interval)

        except KeyboardInterrupt:
            print("\n\nStopping monitor...")

        self.shutdown()
        print("Light turned OFF. Goodbye!")


def create_monitor(config_path: Optional[Path] = None) -> TeamsMonitor:
    config = load_config(config_path)
    return TeamsMonitor(config)


if __name__ == "__main__":
    print("\nInitializing...")
    monitor = create_monitor()

    def cleanup():
        try:
            monitor.shutdown()
        except Exception:
            pass

    atexit.register(cleanup)

    monitor.run()
