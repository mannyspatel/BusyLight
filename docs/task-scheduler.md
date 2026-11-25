# Task Scheduler setup

**Recommended path:** import a task XML that runs **`pythonw.exe`** with argument **`busylight.py`** and **Start in** set to the repo folder. That is the only launcher Task Scheduler needs; no PowerShell wrapper is required for logon startup (execution policy cannot block it).

`teams_light_controller.py` is a **library module** (`TeamsMonitor`); do not point Task Scheduler at it.

**Home Wi-Fi gating** is the task **Conditions → Network** entry (“Start only if the following network connection is available”). BusyLight does **not** poll Wi-Fi, watch SSID changes, or exit the monitor loop when you leave home.

Optional: **`scripts/run-busylight.ps1`** adds a launch-time SSID pre-check (inline `netsh`, not Python), single-instance locking, and extra logging. The XML templates do **not** use it by default.

## 1. Configure `config.yaml`

Copy `config.yaml.example` to `config.yaml` and set:

- `wled_host` - hostname or IP of your WLED device
- `home_wifi_ssid` - **optional for Task Scheduler-only users** (placeholder `YourHomeWiFi` or empty is fine); required only if you want `run-busylight.ps1` to verify SSID before launch

## 2. Find `pythonw.exe`

Typical path (adjust for your user and Python version):

`C:\Users\<you>\AppData\Local\Programs\Python\Python312\pythonw.exe`

Or run `where pythonw` in Command Prompt after Python is on PATH.

## 3. Map profile name to Task Scheduler network condition

Task Scheduler uses the **saved Windows network profile name**, which is usually the same as the Wi-Fi SSID but not always.

1. Open **Settings** -> **Network & Internet** -> **Wi-Fi** -> **Manage known networks**
2. Select your home network and note the profile name
3. Set that name in the imported task **Conditions** -> **Start only if the following network connection is available**

Scheduler-only: you can skip editing `home_wifi_ssid` and rely on the task **Network** condition alone. If you use `run-busylight.ps1`, set `home_wifi_ssid` to the SSID reported by `netsh wlan show interfaces` (may differ from the Windows profile name above).

## 4. Import the task XML

Task definitions use schema **version 1.4** with **Conditions** nested under **Settings** (as exported by current Windows). Older hand-edited XML that places `<Conditions>` as a sibling after `</Settings>` fails to import with error **(37,5):Conditions**.

1. Open **Task Scheduler**
2. **Action** -> **Import Task...**
3. Choose one of:
   - `tasks/BusyLight-HomeWiFi-Logon.xml` — logon trigger plus **Network** condition (home profile must be available) **(recommended)**
   - `tasks/BusyLight-Logon-NoCondition.xml` — logon only; no network gate (use only for testing)
4. Edit the task **Actions** tab:
   - **Program/script** (`Command` in XML): full path to `pythonw.exe` (replace `REPLACE_WITH_PYTHONW`)
   - **Add arguments**: `busylight.py`
   - **Start in**: your repo folder (replace `REPLACE_WITH_REPO`)
5. For the Home Wi-Fi XML only: **Conditions** -> set **Network** to your Windows profile name (replace `REPLACE_WITH_WINDOWS_NETWORK_PROFILE_NAME`)
6. Save and run once to test

The **Network** condition uses the saved Windows **connection profile name** from Settings -> **Manage known networks**, not necessarily the same spelling or casing as the **SSID** field from `netsh wlan show interfaces`.

### Quick manual start (no Task Scheduler)

- Double-click `scripts/run-busylight.cmd` (uses `pythonw` on PATH, or set `PYTHONW` first)
- Or: `pythonw busylight.py` from the repo folder in Command Prompt

## 5. Stopping BusyLight

There is no automatic stop when you leave home Wi-Fi. To stop manually, run `scripts/stop-busylight.ps1` or use **Exit** on the system tray icon.

## Troubleshooting

### Use pythonw.exe (not python.exe)

Schedule **pythonw.exe** so BusyLight runs without a console window. Using **python.exe** opens a visible console that flashes or stays on screen.

### General tab

Set **Configure for** to your Windows version and choose **Run only when user is logged on** so the tray icon behaves as expected.

### Delays at logon

If the tray icon does not appear, the task may have started before the shell is ready; optionally set **Delay task for** to **30 seconds** on the logon trigger.

### Restart on failure

Avoid aggressive **Restart the task on failure** settings that retry every second; use a reasonable interval (for example, several minutes) so a failing start does not loop rapidly.

### Multiple instances

On the **Settings** tab, set **If the task is already running** to **Do not start a new instance** so only one BusyLight process runs.