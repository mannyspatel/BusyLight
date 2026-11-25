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
- **YAML configuration**: `config.yaml` for WLED host, allowlist, and tunables
- **Home start via Task Scheduler**: Use the imported XML **Network** condition; no in-app Wi-Fi polling
- **System tray** (Windows): Tray icon color matches current busy-state color
- **Task Scheduler kit**: Importable XML plus PowerShell start/stop scripts
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
- **Python 3.10–3.12** (**3.12 recommended** on Windows). Python **3.13+ is not supported yet** (dependencies such as `pycaw` often lack wheels).
- WLED device on your local network
- Non-administrative user account

## Installation

### One-click setup (Windows)

Double-click setup installs **Python (when needed) and all pip packages in one run**:

Save edited `.ps1` files as **UTF-8 with BOM** (or use ASCII punctuation only) so Windows PowerShell 5.1 parses them correctly.

1. Download or clone this repository.
2. Double-click **`install-busylight.cmd`** in the project folder (or run **`Install-BusyLight.ps1`**). The `.cmd` file opens a **PowerShell** window titled **BusyLight Setup** and runs the installer there.
3. If Python is missing, the script offers to install **Python 3.12 via winget** (default yes). **Installer v1.5.1** prefers `py -3.12` when multiple versions are installed, warns if the default interpreter is **3.13 or newer**, installs pip packages **one at a time** for clearer errors, and prints full **pip output** when a install fails. It also tries a per-user (`--scope user`) winget install first, then offers a silent [python.org](https://www.python.org/downloads/) download if winget fails or you skipped it.
4. Follow the on-screen messages. The installer skips packages that are already installed with a sufficient version, so it is safe to run again.

After pulling the latest `main`, run `git pull`, then confirm the setup window shows **installer v1.5.1**.

If `python --version` shows **3.13, 3.14, or 3.15**, install [Python 3.12](https://www.python.org/downloads/) (or run `py -3.12` if it is already installed) before installing packages—otherwise `pip install` may fail building `pycaw` and related dependencies.

If both winget and the automatic python.org step fail, install Python manually from [python.org](https://www.python.org/downloads/), not the Microsoft Store shortcut—then run the installer again. If Windows still says Python is missing after you install, open **Settings → Apps → Advanced app settings → App execution aliases** and turn off the **python.exe** / **python3.exe** stubs so the real interpreter is used.

When setup finishes, copy `config.yaml.example` to `config.yaml`, edit it, then run BusyLight (see [Running BusyLight](#running-busylight)).

### 1. Install Python

On Windows, download and install **Python 3.12** from [python.org](https://www.python.org/downloads/) (versions 3.10–3.12 work; avoid 3.13+ until dependency wheels are available). During installation, **make sure to check "Add Python to PATH"**.

### 2. Install Required Packages

Open Command Prompt or PowerShell in the project directory and run:

```bash
pip install -r requirements.txt
```

Or install packages individually:

```bash
pip install -r requirements.txt
```

### 3. Configure `config.yaml`

Copy the example file and edit settings (local `config.yaml` is gitignored):

```bash
copy config.yaml.example config.yaml
```

Minimum settings:

```yaml
wled_host: wled-busylight.lan
app_allowlist:
  - teams
  - zoom
```

`home_wifi_ssid` is optional: **not used by `busylight.py`**. Task Scheduler users enforce home-only startup with the imported XML **Network** condition. Set `home_wifi_ssid` only when using `scripts/run-busylight.ps1` (non-placeholder value enables a launch-time SSID pre-check).

See `config.yaml.example` for optional tunables (intervals, colors, brightness, debug).

### Meeting app allowlist

By default the controller watches common meeting apps only. Matching is **case-insensitive substring** checks against each app's ConsentStore registry path.

- **Add apps**: See [docs/allowlist.md](docs/allowlist.md) for how to find ConsentStore paths and add substrings to `app_allowlist`.
- **Detect any app**: Set `app_allowlist: []` to treat every mic/camera client as "in a call" (more false positives).

## Running BusyLight

### Launcher (recommended on Windows)

```bash
python busylight.py
```

On Windows, **tray mode is on by default**: a system tray icon shows the current status color; use the menu for status text or **Exit** (turns WLED off).

- Console only: `python busylight.py --no-tray`
- Hidden / no console: `pythonw busylight.py` (same tray behavior)

`teams_light_controller.py` holds the `TeamsMonitor` implementation (library only). Running it directly prints a reminder to use `busylight.py`.

### One-time console test

```bash
python busylight.py
```

Press `Ctrl+C` to stop (console mode), or use the tray **Exit** menu; WLED turns off on exit.

### Start / stop scripts

```batch
scripts\run-busylight.cmd      REM pythonw busylight.py (set PYTHONW if not on PATH)
```

```powershell
.\scripts\run-busylight.ps1    # optional launch helper (SSID pre-check only if home_wifi_ssid is set)
.\scripts\stop-busylight.ps1   # stops pythonw busylight.py
```

### Run on Windows logon (Task Scheduler)

1. Import `tasks/BusyLight-HomeWiFi-Logon.xml` or `tasks/BusyLight-Logon-NoCondition.xml` in Task Scheduler.
2. Set **Program/script** to your `pythonw.exe` path (`REPLACE_WITH_PYTHONW`), **Arguments** to `busylight.py`, and **Start in** to the repo folder (`REPLACE_WITH_REPO`). See [docs/task-scheduler.md](docs/task-scheduler.md).
3. For the Home Wi-Fi template, set the **Network** condition to your Windows profile name (home-only **start** — not checked again while BusyLight runs).

BusyLight does not poll Wi-Fi or exit when SSID changes; stop it with `scripts/stop-busylight.ps1`, tray **Exit**, or sign-out as needed. You do not need `home_wifi_ssid` in `config.yaml` for this path.

## Troubleshooting

### WLED Connection Failed

- **Check hostname**: Make sure `wled_host` in `config.yaml` matches your WLED device
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
  
- **Run in debug mode**: Set `debug: true` in `config.yaml` to see detailed output
  
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

1. Edit `idle_timeout` in `config.yaml` (seconds; `0` disables)
2. Save and restart BusyLight

**Note**: This only works while the script is running. If your computer sleeps, the script also pauses.

#### Option 3: Automatic Wake Detection (Built-in)

The script now automatically detects when your system wakes from sleep and turns off the light as a safety measure. It will then check the current state and turn it back on if you're actually in a call. This works automatically - no configuration needed.

## How to Stop the Script

### If Running in a Window
Press `Ctrl+C`

The script will automatically turn the WLED light completely off when it stops.

### If Running Hidden/at Startup

Run `scripts/stop-busylight.ps1`, use **Exit** on the tray icon, or end `pythonw.exe` running `busylight.py` in Task Manager.

BusyLight turns WLED off on normal exit; forced kill may leave the light on until the next WLED idle timeout.

## Customization

### Change Colors

Override the `colors` section in `config.yaml` (RGB lists 0-255 per state). Omitted keys keep defaults from `config.yaml.example`.

RGB values range from 0-255. Some examples:
- White: `(255, 255, 255)`
- Blue: `(0, 0, 255)`
- Purple: `(128, 0, 128)`
- Orange: `(255, 165, 0)`

### Change Effects

Set `state_effects` in `config.yaml` (effect names such as `solid`, `breathe`, `blink`).

Available effects:
- `'solid'` - No animation
- `'blink'` - Quick on/off
- `'breathe'` - Smooth fade in/out
- `'sweep'` - Back and forth sweep
- `'chase'` - Chase pattern
- `'twinkle'` - Random twinkle

### Adjust Sensitivity

Change these values to fine-tune behavior:

Use `audio_threshold` and `audio_detection_window` in `config.yaml`.

## Technical Details

### How It Works

1. **Registry Monitoring**: Recursively walks `HKCU\...\CapabilityAccessManager\ConsentStore\{microphone|webcam}` (including `NonPackaged` paths). When `LastUsedTimeStop` is `0`, Windows considers that app still using the device. `app_allowlist` in config filters which apps count.
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

1. **Enable Debug Mode**: Set `debug: true` in `config.yaml`
2. **Check logs**: Look for error messages in the console output
3. **Test WLED**: Make sure you can access your WLED web interface
4. **Verify your meeting app**: Make sure the app is listed in `app_allowlist` and is using the devices

## Testing (CI / Linux)

Pure-Python helpers run on Linux in CI:

```bash
pip install pyyaml
python -m unittest discover -s tests -v
```

Not covered on Linux: system tray (`pystray`) and Windows registry/audio (`pycaw`).

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Version History

- **1.2** - YAML config, system tray launcher (`busylight.py`), Task Scheduler scripts, and unit tests
- **1.1** - Added connection reliability improvements:
  - Keep-alive mechanism to prevent WLED connection timeouts
  - Connection pooling with requests Session for better reliability
  - Retry logic with exponential backoff for failed requests
  - Idle timeout to turn off light after period of inactivity
  - Automatic wake-from-sleep detection to turn off light when computer wakes
  - Improved error handling and connection recovery

- **1.0** - Initial release with camera detection, microphone mute detection, audio activity monitoring, and WLED integration