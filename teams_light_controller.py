"""
Teams Status Light Controller for WLED
Monitors Windows camera and microphone usage to control WLED light colors
Includes audio level monitoring for accurate mute detection
No admin rights required - works on restricted corporate laptops
"""

__version__ = "1.1"

import winreg
import requests
import time
import json
import atexit
from datetime import datetime
from typing import Tuple, Optional
from ctypes import cast, POINTER
from comtypes import CLSCTX_ALL
from pycaw.pycaw import AudioUtilities, IAudioMeterInformation, IAudioEndpointVolume, ISimpleAudioVolume
from comtypes import GUID

# ============= CONFIGURATION =============
WLED_IP = "192.168.1.153"  # Your WLED device IP "wled-busylight.lan"
CHECK_INTERVAL = 1.5  # Seconds between checks
DEBUG_MODE = False  # Set to True to see detailed debug output
KEEP_ALIVE_INTERVAL = 300  # Seconds - send keep-alive request even if state unchanged
MAX_RETRIES = 3  # Number of retries for failed requests
IDLE_TIMEOUT = 600  # Seconds - turn off light if no successful updates for this long (0 = disabled)

# Color definitions (RGB format)
COLORS = {
    'off': (0, 255, 0),                  # Green - not in a call
    'in_call_muted': (255, 200, 0),      # Orange - in call, mic muted
    'in_call_quiet': (255, 255, 0),      # Yellow - in call, unmuted but quiet
    'mic_only': (255, 255, 0),           # Yellow - breathe - unmuted and speaking
    'camera_only': (255, 100, 0),        # Dark orange - camera on, mic muted
    'camera_quiet': (255, 0, 0),         # Red - camera on, unmuted but quiet
    'camera_and_mic': (255, 0, 0),       # Red - breathe - camera on and speaking
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
AUDIO_THRESHOLD = 0.01  # Minimum audio level to consider mic "active" (0.0-1.0)
AUDIO_DETECTION_WINDOW = 3  # Seconds - if audio detected within this window, mic is "on"
# =========================================


class AudioMonitor:
    """Monitor microphone audio levels and mute state using Windows Core Audio API"""
    
    def __init__(self):
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
                
                if DEBUG_MODE:
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
                                                    if DEBUG_MODE:
                                                        print(f"    Teams session mute (PID {process_id}): {muted}")
                                                    kernel32.CloseHandle(h_process)
                                                    return bool(muted)
                                    finally:
                                        kernel32.CloseHandle(h_process)
                            except Exception as e:
                                if DEBUG_MODE:
                                    print(f"    Error checking process name: {e}")
                                continue
                    except:
                        # If we can't get IAudioSessionControl2, skip this session
                        continue
                except:
                    continue
        except Exception as e:
            if DEBUG_MODE:
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
            if DEBUG_MODE:
                print(f"    Application session mute: {session_muted}")
            if session_muted:
                return True
        
        # Method 2: Check system-level mute state (fallback)
        system_muted = False
        if self.endpoint_volume:
            try:
                system_muted = bool(self.endpoint_volume.GetMute())
                if DEBUG_MODE:
                    print(f"    System-level mute: {system_muted}")
            except Exception as e:
                if DEBUG_MODE:
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
                if peak > AUDIO_THRESHOLD:
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
                        if DEBUG_MODE:
                            print(f"    Heuristic: Previously detected audio, now zero for {time_since_audio:.1f}s - likely muted")
                        return True
                    elif DEBUG_MODE:
                        print(f"    Heuristic: Zero audio for {time_since_audio:.1f}s, but not long enough to confirm mute")
            except Exception as e:
                if DEBUG_MODE:
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
            
            if DEBUG_MODE and peak > 0.001:
                print(f"    Audio level: {peak:.4f}")
            
            # If audio is above threshold, update last audio time
            if peak > AUDIO_THRESHOLD:
                self.last_audio_time = time.time()
                return True
            
            # Check if we detected audio recently
            time_since_audio = time.time() - self.last_audio_time
            is_active = time_since_audio < AUDIO_DETECTION_WINDOW
            
            if DEBUG_MODE:
                print(f"    Time since audio: {time_since_audio:.1f}s, Active: {is_active}")
            
            return is_active
            
        except Exception as e:
            if DEBUG_MODE:
                print(f"    Error reading audio level: {e}")
            return True  # Assume active if we can't read


class TeamsMonitor:
    def __init__(self, wled_ip: str):
        self.wled_ip = wled_ip
        self.last_state = None
        self.audio_monitor = AudioMonitor()
        self.session = requests.Session()  # Reuse connections for better reliability
        self.last_wled_update = 0  # Track last successful WLED update time
        self.last_check_time = time.time()  # Track last check time to detect sleep/wake
        
    def check_device_usage(self, device_type: str) -> bool:
        """
        Check if a device (microphone or webcam) is in use by Teams
        Returns: is_teams_using_device
        """
        registry_path = f"Software\\Microsoft\\Windows\\CurrentVersion\\CapabilityAccessManager\\ConsentStore\\{device_type}"
        
        try:
            # Open the main key
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, registry_path)
            
            teams_in_use = False
            
            if DEBUG_MODE:
                print(f"  Checking {device_type}:")
            
            i = 0
            while True:
                try:
                    subkey_name = winreg.EnumKey(key, i)
                    i += 1
                    
                    # Check if this is a Teams process
                    is_teams = 'teams' in subkey_name.lower() or 'ms-teams' in subkey_name.lower()
                    
                    if is_teams:
                        # Open the subkey to check LastUsedTimeStop
                        try:
                            subkey_path = f"{registry_path}\\{subkey_name}"
                            subkey = winreg.OpenKey(winreg.HKEY_CURRENT_USER, subkey_path)
                            
                            try:
                                last_used_stop = winreg.QueryValueEx(subkey, "LastUsedTimeStop")[0]
                                
                                # If LastUsedTimeStop is 0, the device is currently in use
                                if last_used_stop == 0:
                                    teams_in_use = True
                                    if DEBUG_MODE:
                                        print(f"    ✓ Teams is using {device_type}")
                                        
                            except FileNotFoundError:
                                pass
                            
                            winreg.CloseKey(subkey)
                        except:
                            pass
                        
                except OSError:
                    # No more subkeys
                    break
            
            winreg.CloseKey(key)
            
            if DEBUG_MODE:
                print(f"    Result: teams_active={teams_in_use}")
            
            return teams_in_use
            
        except Exception as e:
            if DEBUG_MODE:
                print(f"Error checking {device_type}: {e}")
            return False
    
    def get_current_state(self) -> Optional[str]:
        """
        Determine current Teams call state
        Returns state name or None
        """
        # Check if Teams is using the devices
        mic_device_active = self.check_device_usage("microphone")
        cam_device_active = self.check_device_usage("webcam")
        
        if DEBUG_MODE:
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
            
            if DEBUG_MODE:
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
        color = COLORS[state]
        r, g, b = color
        
        # Get the effect for this state
        effect_name = STATE_EFFECTS.get(state, 'solid')
        effect_id = EFFECTS.get(effect_name, 0)
        
        url = f"http://{self.wled_ip}/json/state"
        payload = {
            "on": True,
            "bri": BRIGHTNESS,
            "seg": [{
                "col": [[r, g, b]],
                "fx": effect_id,
                "sx": EFFECT_SPEED,
                "ix": EFFECT_INTENSITY
            }]
        }
        
        for attempt in range(MAX_RETRIES):
            try:
                # Use session for connection pooling and reuse
                response = self.session.post(url, json=payload, timeout=5)
                
                if response.status_code == 200:
                    self.last_wled_update = time.time()
                    return True
                else:
                    if attempt < MAX_RETRIES - 1:
                        if DEBUG_MODE:
                            print(f"  WLED returned status {response.status_code}, retrying...")
                        time.sleep(0.5 * (attempt + 1))  # Exponential backoff
                        continue
                    else:
                        print(f"WLED returned status {response.status_code}")
                        return False
                        
            except requests.exceptions.Timeout:
                if attempt < MAX_RETRIES - 1:
                    if DEBUG_MODE:
                        print(f"  WLED request timed out, retrying...")
                    time.sleep(0.5 * (attempt + 1))
                    # Reset session on timeout to clear stale connections
                    self.session.close()
                    self.session = requests.Session()
                    continue
                else:
                    print(f"Error: WLED request timed out after {MAX_RETRIES} attempts")
                    return False
                    
            except requests.exceptions.ConnectionError as e:
                if attempt < MAX_RETRIES - 1:
                    if DEBUG_MODE:
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
                if attempt < MAX_RETRIES - 1:
                    if DEBUG_MODE:
                        print(f"  WLED request error, retrying...")
                    time.sleep(0.5 * (attempt + 1))
                    continue
                else:
                    print(f"Error connecting to WLED: {e}")
                    return False
        
        return False
    
    def turn_off_wled(self):
        """Turn the WLED light completely off"""
        url = f"http://{self.wled_ip}/json/state"
        payload = {"on": False}
        
        for attempt in range(MAX_RETRIES):
            try:
                response = self.session.post(url, json=payload, timeout=5)
                if response.status_code == 200:
                    return True
                else:
                    if attempt < MAX_RETRIES - 1:
                        time.sleep(0.5 * (attempt + 1))
                        continue
                    else:
                        print(f"WLED returned status {response.status_code}")
                        return False
            except requests.exceptions.RequestException as e:
                if attempt < MAX_RETRIES - 1:
                    time.sleep(0.5 * (attempt + 1))
                    self.session.close()
                    self.session = requests.Session()
                    continue
                else:
                    print(f"Error turning off WLED: {e}")
                    return False
        return False
    
    def run(self):
        """Main monitoring loop"""
        print("=" * 60)
        print("Teams Status Light Controller with Audio Monitoring")
        print(f"Version {__version__}")
        print("=" * 60)
        print(f"WLED IP: {self.wled_ip}")
        print(f"Check interval: {CHECK_INTERVAL}s")
        print(f"Audio threshold: {AUDIO_THRESHOLD}")
        print(f"Audio detection window: {AUDIO_DETECTION_WINDOW}s")
        print("\nColor and Effect scheme:")
        for state, color in COLORS.items():
            effect = STATE_EFFECTS.get(state, 'solid')
            state_name = state.replace('_', ' ').title()
            print(f"  {state_name}: RGB{color} - {effect}")
        print("\nMonitoring started. Press Ctrl+C to stop.")
        print("=" * 60)
        
        # Test WLED connection
        print("\nTesting WLED connection...")
        if self.set_wled_color('off'):
            print("✓ WLED connection successful (light should be GREEN)\n")
            self.last_wled_update = time.time()  # Initialize update time
        else:
            print("✗ Could not connect to WLED. Check IP address.\n")
            self.last_wled_update = time.time()  # Initialize anyway to prevent immediate timeout
        
        try:
            while True:
                current_time = time.time()
                time_since_last_check = current_time - self.last_check_time
                
                # Detect if system was asleep (large time gap between checks)
                # If more than 2x CHECK_INTERVAL has passed, system likely slept
                wake_detected = False
                if time_since_last_check > (CHECK_INTERVAL * 2):
                    wake_detected = True
                    if DEBUG_MODE:
                        timestamp = datetime.now().strftime("%H:%M:%S")
                        print(f"[{timestamp}] Detected system wake (gap: {time_since_last_check:.1f}s) - refreshing state")
                
                self.last_check_time = current_time
                current_state = self.get_current_state()
                
                # If we detected a wake and not in a call, turn off the light
                if wake_detected and current_state == 'off':
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    print(f"[{timestamp}] System woke - turning off light (not in call)")
                    self.turn_off_wled()
                    self.last_state = None  # Force state update on next check if needed
                time_since_update = current_time - self.last_wled_update
                
                # Check for idle timeout (if enabled)
                if IDLE_TIMEOUT > 0 and time_since_update >= IDLE_TIMEOUT:
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    print(f"[{timestamp}] Idle timeout ({IDLE_TIMEOUT}s) - turning off light")
                    if self.turn_off_wled():
                        self.last_wled_update = time.time()  # Reset timer after successful off command
                    # Continue monitoring - light will turn back on when state changes
                
                # Update if state changed OR if keep-alive interval has passed
                state_changed = current_state != self.last_state
                keep_alive_needed = time_since_update >= KEEP_ALIVE_INTERVAL
                
                if state_changed or keep_alive_needed:
                    if state_changed:
                        timestamp = datetime.now().strftime("%H:%M:%S")
                        effect = STATE_EFFECTS.get(current_state, 'solid')
                        state_name = current_state.replace('_', ' ').title()
                        print(f"[{timestamp}] State: {state_name} (effect: {effect})")
                    elif DEBUG_MODE:
                        timestamp = datetime.now().strftime("%H:%M:%S")
                        print(f"[{timestamp}] Keep-alive: Refreshing WLED state")
                    
                    if self.set_wled_color(current_state):
                        self.last_state = current_state
                    else:
                        if state_changed:
                            print("  Failed to update WLED")
                        elif DEBUG_MODE:
                            print("  Keep-alive failed, will retry on next interval")
                
                time.sleep(CHECK_INTERVAL)
                
        except KeyboardInterrupt:
            print("\n\nStopping monitor...")
            self.turn_off_wled()
            self.session.close()
            print("Light turned OFF. Goodbye!")


if __name__ == "__main__":
    print("\nInitializing...")
    # Create and run monitor
    monitor = TeamsMonitor(WLED_IP)
    
    # Register cleanup function to turn off light on exit
    def cleanup():
        try:
            monitor.turn_off_wled()
            monitor.session.close()
        except:
            pass  # Ignore errors during cleanup
    
    atexit.register(cleanup)
    
    monitor.run()
