"""
Teams Status Light Controller for WLED
Monitors Windows camera and microphone usage to control WLED light colors
Includes audio level monitoring for accurate mute detection
No admin rights required - works on restricted corporate laptops
"""

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

# ============= CONFIGURATION =============
WLED_IP = "wled-busylight.lan"  # Your WLED device IP
CHECK_INTERVAL = 1.5  # Seconds between checks
DEBUG_MODE = False  # Set to True to see detailed debug output

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
                
                if DEBUG_MODE:
                    print("✓ Audio monitoring initialized (level + mute detection)")
            else:
                print("⚠ Warning: Could not find default microphone for audio monitoring")
        except Exception as e:
            print(f"⚠ Warning: Could not initialize audio monitoring: {e}")
            print("  Mic mute detection will be less accurate")
    
    def is_muted(self) -> bool:
        """
        Check if microphone is muted using multiple detection methods
        Returns True if microphone is muted
        """
        # Method 1: Check system-level mute state (most reliable)
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
    
    def set_wled_color(self, state: str):
        """Send color and effect command to WLED device"""
        color = COLORS[state]
        r, g, b = color
        
        # Get the effect for this state
        effect_name = STATE_EFFECTS.get(state, 'solid')
        effect_id = EFFECTS.get(effect_name, 0)
        
        try:
            # WLED JSON API
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
            
            response = requests.post(url, json=payload, timeout=2)
            
            if response.status_code == 200:
                return True
            else:
                print(f"WLED returned status {response.status_code}")
                return False
                
        except requests.exceptions.RequestException as e:
            print(f"Error connecting to WLED: {e}")
            return False
    
    def turn_off_wled(self):
        """Turn the WLED light completely off"""
        try:
            url = f"http://{self.wled_ip}/json/state"
            payload = {"on": False}
            response = requests.post(url, json=payload, timeout=2)
            if response.status_code == 200:
                return True
            else:
                print(f"WLED returned status {response.status_code}")
                return False
        except requests.exceptions.RequestException as e:
            print(f"Error turning off WLED: {e}")
            return False
    
    def run(self):
        """Main monitoring loop"""
        print("=" * 60)
        print("Teams Status Light Controller with Audio Monitoring")
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
        else:
            print("✗ Could not connect to WLED. Check IP address.\n")
        
        try:
            while True:
                current_state = self.get_current_state()
                
                # Only update if state changed
                if current_state != self.last_state:
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    effect = STATE_EFFECTS.get(current_state, 'solid')
                    state_name = current_state.replace('_', ' ').title()
                    print(f"[{timestamp}] State: {state_name} (effect: {effect})")
                    
                    if self.set_wled_color(current_state):
                        self.last_state = current_state
                    else:
                        print("  Failed to update WLED")
                
                time.sleep(CHECK_INTERVAL)
                
        except KeyboardInterrupt:
            print("\n\nStopping monitor...")
            self.turn_off_wled()
            print("Light turned OFF. Goodbye!")


if __name__ == "__main__":
    print("\nInitializing...")
    # Create and run monitor
    monitor = TeamsMonitor(WLED_IP)
    
    # Register cleanup function to turn off light on exit
    def cleanup():
        try:
            monitor.turn_off_wled()
        except:
            pass  # Ignore errors during cleanup
    
    atexit.register(cleanup)
    
    monitor.run()
