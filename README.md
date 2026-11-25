# Teams Status Light Controller for WLED

A Python application that monitors your Microsoft Teams call status and controls a WLED smart light to display your availability at a glance.

## Features

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
| Not In Call | Green | Solid | You're offline/not in a Teams call |
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
WLED_HOST = "wled-busylight.lan"  # Your WLED device hostname
CHECK_INTERVAL = 1.5              # Seconds between checks
BRIGHTNESS = 128                  # Light brightness (0-255)
EFFECT_SPEED = 128                # Animation speed (0-255)
```

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

### Light Stays On When Computer Sleeps

If your light stays on when your laptop goes to sleep or hibernates, you have several options:

#### Option 1: Upgrade WLED Firmware (Recommended)

WLED v0.15.0-b5 doesn't include the "Idle Timeout" feature. This feature was added in later versions (v0.14.0+ stable releases). If possible, upgrade your WLED firmware to a newer version that includes idle timeout:

1. Open your WLED web interface
2. Go to **Settings** → **LED Preferences** (or **Time & Macros** in newer versions)
3. Find **"Idle Timeout"** or **"Idle Time"**
4. Set it to your desired timeout (e.g., 10 minutes = 600 seconds)
5. Enable the option if it's a toggle
6. Save settings

This is the best solution because it works even if the Python script crashes or stops running.

#### Option 2: Python Script Timeout

The script has an `IDLE_TIMEOUT` setting that will turn off the light if no successful updates are sent for a specified period:

1. Open `teams_light_controller.py` in a text editor
2. Find the line: `IDLE_TIMEOUT = 600  # Seconds - turn off light if no successful updates for this long (0 = disabled)`
3. Set it to your desired timeout in seconds (e.g., `600` for 10 minutes, `0` to disable)
4. Save and restart the script

**Note**: This only works while the script is running. If your computer sleeps, the script also pauses.

#### Option 3: Automatic Wake Detection (Built-in)

The script now automatically detects when your system wakes from sleep and turns off the light as a safety measure. It will then check the current state and turn it back on if you're actually in a call. This works automatically - no configuration needed.

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

1. **Registry Monitoring**: Checks Windows registry to detect when Teams is using your camera and microphone
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
4. **Verify Teams**: Make sure Teams is actually running and using the devices

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Version History

- **1.1** - Added connection reliability improvements:
  - Keep-alive mechanism to prevent WLED connection timeouts
  - Connection pooling with requests Session for better reliability
  - Retry logic with exponential backoff for failed requests
  - Idle timeout to turn off light after period of inactivity
  - Automatic wake-from-sleep detection to turn off light when computer wakes
  - Improved error handling and connection recovery

- **1.0** - Initial release with camera detection, microphone mute detection, audio activity monitoring, and WLED integration