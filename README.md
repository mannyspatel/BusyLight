# Teams Status Light Controller for WLED

A Python application that monitors video-call status (Teams, Zoom, Webex, and other meeting apps) and controls a WLED smart light to display your availability at a glance.

## Features

- **Multi-App Call Detection**: Detects mic/camera use from Teams, Zoom, Webex, RingCentral, Skype, and more via Windows ConsentStore
- **Configurable App Allowlist**: Limit which apps trigger the busy light, or allow any app
- **Camera Detection**: Automatically detects when your camera is active
- **Microphone Mute Detection**: Accurately detects when your microphone is muted (not just silent)
- **Audio Activity Detection**: Shows when you're actively speaking
- **Color-Coded Status**: Visual indicators for different call states
- **No Admin Rights Required**: Works on restricted corporate laptops without elevated privileges
- **Hostname Support**: Uses mDNS hostname instead of IP for reliability
- **Low Resource Usage**: Minimal CPU and memory footprint (~0.3-0.5% CPU)

## Status Indicators

| Status | Color | Effect | Meaning |
|--------|-------|--------|---------|
| Not In Call | Green | Solid | You're offline/not in a call |
| In Call - Muted | Orange | Solid | In a call, camera off, microphone is muted |
| In Call - Quiet | Yellow | Solid | In a call, camera off, unmuted but not speaking |
| In Call - Talking | Yellow | Breathe | In a call, camera off, actively speaking |
| Camera On - Muted | Dark Orange | Solid | Camera is on, microphone is muted |
| Camera On - Quiet | Red | Solid | Camera is on, unmuted but not speaking |
| Camera On - Talking | Red | Breathe | Camera is on and you're actively speaking |

## Requirements

- Windows 11 (or Windows 10)
- Python 3.7+
- WLED device on your local network
- Non-administrative user account

## Installation

### One-click setup (Windows)

If you already have [Python](https://www.python.org/downloads/) on your PATH (or the Windows `py` launcher), you can install all Python dependencies in one step:

1. Download or clone this repository.
2. Double-click **`install-busylight.cmd`** in the project folder (or run **`Install-BusyLight.ps1`**).
3. Follow the on-screen messages. The installer skips packages that are already installed with a sufficient version, so it is safe to run again.

When setup finishes, run the controller (see [Running the Script](#running-the-script)).

### 1. Install Python

Download and install Python from [python.org](https://www.python.org/downloads/). During installation, **make sure to check "Add Python to PATH"**.

### 2. Install Required Packages

Open Command Prompt or PowerShell in the project directory and run:

```bash
pip install -r requirements.txt
```

Or install packages individually:

```bash
pip install requests comtypes pycaw
```

### 3. Download the Script

Save the `teams_light_controller.py` file to a location on your computer (e.g., `C:\Scripts\` or your Documents folder).

### 4. Configure the Script

Open `teams_light_controller.py` in a text editor and verify/update these settings:

```python
WLED_IP = "wled-busylight.lan"  # Your WLED device hostname
CHECK_INTERVAL = 1.5              # Seconds between checks
BRIGHTNESS = 128                  # Light brightness (0-255)
EFFECT_SPEED = 128                # Animation speed (0-255)
```

### Meeting app allowlist (optional)

By default the script watches common meeting apps only (reduces false positives from random mic/camera access):

```python
APP_ALLOWLIST = [
    "teams",
    "ms-teams",
    "zoom",
    "webex",
    "ringcentral",
    "skype",
]
```

Matching is **case-insensitive** and uses **substring** checks against each app's ConsentStore registry path (including `NonPackaged` entries such as `Zoom.exe`).

**Zoom example:** No extra setup is needed if `"zoom"` stays in the list. Join a Zoom call; when Zoom uses your mic or camera, the light leaves the green "not in call" state.

**Detect any app:** Set `APP_ALLOWLIST = []` or `APP_ALLOWLIST = None` to treat every application that holds the mic or camera as "in a call" (useful for custom clients; may react to browsers or system apps).

## Running the Script

### One-Time Test

Open Command Prompt in the script's directory and run:

```bash
python teams_light_controller.py
```

You should see output like:
```
============================================================
Teams Status Light Controller
============================================================
WLED Host: wled-busylight.lan
Check interval: 1.5s

Testing WLED connection...
✓ WLED connection successful (light should be GREEN)

Monitoring started. Press Ctrl+C to stop.
```

Press `Ctrl+C` to stop the script.

### Run on Windows Startup (No Window)

#### Option 1: Using VBScript (Simplest)

1. Create a file called `start_teams_light.vbs` with this content:
   ```vbscript
   Set objShell = CreateObject("WScript.Shell")
   objShell.Run "pythonw C:\path\to\teams_light_controller.py", 0, False
   ```
   Replace `C:\path\to\` with the actual path to your script.

2. Place this `.vbs` file in your Windows Startup folder:
   - Press `Win+R`, type `shell:startup`, press Enter
   - Copy the `.vbs` file into this folder

3. Restart your computer - the script will start automatically with no window

#### Option 2: Using Task Scheduler (More Reliable)

1. Open **Task Scheduler** (search in Start menu)
2. Click **Create Basic Task** on the right
3. Set up as follows:
   - **Name**: Teams Status Light
   - **Trigger**: "When I log on"
   - **Action**: "Start a program"
   - **Program**: `C:\Users\YourUsername\AppData\Local\Programs\Python\Python3XX\pythonw.exe`
   - **Arguments**: `C:\path\to\teams_light_controller.py`
4. Finish and restart your computer

## Troubleshooting

### WLED Connection Failed

- **Check hostname**: Make sure `wled-busylight.lan` matches your WLED device's name
- **Check network**: Ensure your WLED device is on the same network as your laptop
- **Find WLED hostname**: 
  - Open your WLED web interface (via IP address in your browser)
  - Go to Settings → Network
  - Note the hostname

### Audio Detection Not Working

- **Set default microphone**: Make sure the microphone you're using in Teams is set as your Windows default
  1. Right-click the speaker icon in your system tray
  2. Click "Open Sound settings"
  3. Scroll to "Input"
  4. Select your Teams microphone as default
  
- **Check microphone access**: Ensure Teams has permission to access your microphone
  1. Go to Settings → Privacy & security → Microphone
  2. Make sure Teams is allowed

### Mute Detection

The script now properly distinguishes between different microphone states:
- **Muted**: When you press the mute button in Teams, the script detects this and shows orange/dark orange
- **Unmuted but Quiet**: When unmuted but not speaking, it shows yellow/red (solid)
- **Speaking**: When unmuted and actively producing sound, the "breathe" effect activates

The script uses Windows Core Audio API to check the system-level mute state, which works without admin rights or Teams API access. It can now visually distinguish between "muted" and "unmuted but quiet" states.

### Script Keeps Crashing or Not Starting

- **Check Python path**: Make sure Python is in your PATH
  - Open Command Prompt and type `python --version` - if it works, Python is in your PATH
  
- **Run in debug mode**: Change `DEBUG_MODE = True` in the script to see detailed output
  
- **Check for error log**: Run the script manually to see any error messages

## How to Stop the Script

### If Running in a Window
Press `Ctrl+C`

The script will automatically turn the WLED light completely off when it stops.

### If Running Hidden/at Startup
1. Open Task Manager (`Ctrl+Shift+Esc`)
2. Go to the **Details** tab
3. Find `pythonw.exe`
4. Right-click and select **End Task**

The script will automatically turn the WLED light completely off when it exits, even if terminated unexpectedly.

## Customization

### Change Colors

Edit the `COLORS` dictionary in the script:

```python
COLORS = {
    'off': (0, 255, 0),                  # Green - not in a call
    'in_call_muted': (255, 200, 0),     # Orange - in call, mic muted
    'in_call_quiet': (255, 255, 0),     # Yellow - in call, unmuted but quiet
    'mic_only': (255, 255, 0),          # Yellow - speaking
    'camera_only': (255, 100, 0),       # Dark orange - camera on, mic muted
    'camera_quiet': (255, 0, 0),        # Red - camera on, unmuted but quiet
    'camera_and_mic': (255, 0, 0),      # Red - camera on and speaking
}
```

RGB values range from 0-255. Some examples:
- White: `(255, 255, 255)`
- Blue: `(0, 0, 255)`
- Purple: `(128, 0, 128)`
- Orange: `(255, 165, 0)`

### Change Effects

Edit the `STATE_EFFECTS` dictionary to change animations:

```python
STATE_EFFECTS = {
    'off': 'solid',
    'in_call_muted': 'solid',
    'in_call_quiet': 'solid',
    'mic_only': 'breathe',              # Change to 'blink', 'sweep', etc.
    'camera_only': 'solid',
    'camera_quiet': 'solid',
    'camera_and_mic': 'breathe',         # Change to 'blink', 'sweep', etc.
}
```

Available effects:
- `'solid'` - No animation
- `'blink'` - Quick on/off
- `'breathe'` - Smooth fade in/out
- `'sweep'` - Back and forth sweep
- `'chase'` - Chase pattern
- `'twinkle'` - Random twinkle

### Adjust Sensitivity

Change these values to fine-tune behavior:

```python
AUDIO_THRESHOLD = 0.001          # Lower = more sensitive (picks up quieter sounds)
AUDIO_DETECTION_WINDOW = 2       # Seconds to keep "talking" state after sound stops
```

## Technical Details

### How It Works

1. **Registry Monitoring**: Recursively walks `HKCU\...\CapabilityAccessManager\ConsentStore\{microphone|webcam}` (including `NonPackaged` paths). When `LastUsedTimeStop` is `0`, Windows considers that app still using the device. Optional `APP_ALLOWLIST` filters which apps count.
2. **Mute Detection**: Uses Windows Core Audio API (IAudioEndpointVolume) to detect if microphone is muted at system level
3. **Audio Detection**: Uses Windows Core Audio API (IAudioMeterInformation) to monitor if sound is being transmitted
4. **WLED Communication**: Sends commands to your WLED device via HTTP JSON API
5. **Polling**: Checks device status every 1.5 seconds and only updates the light when status changes
6. **Cleanup on Exit**: Automatically turns the WLED light completely off when the script stops (via `atexit` handler and shutdown signal)

### No Admin Rights Needed

This script uses only:
- User registry keys (HKEY_CURRENT_USER) - no admin access required
- Windows Core Audio API (IAudioMeterInformation, IAudioEndpointVolume) - standard user access
- Network requests (no special permissions)

It does not require admin privileges to run and works on Windows 11 with standard user accounts.

## Support & Issues

If you encounter issues:

1. **Enable Debug Mode**: Set `DEBUG_MODE = True` in the script and run it to see detailed output
2. **Check logs**: Look for error messages in the console output
3. **Test WLED**: Make sure you can access your WLED web interface
4. **Verify your meeting app**: Make sure the app is allowed in `APP_ALLOWLIST` (if configured) and is using the devices

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Version History

- **1.0** - Initial release with camera detection, microphone mute detection, audio activity monitoring, and WLED integration