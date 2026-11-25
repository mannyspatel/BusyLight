# Task Scheduler setup

BusyLight can start automatically at Windows logon when your home Wi-Fi is available.

## 1. Configure `config.yaml`

Copy `config.yaml.example` to `config.yaml` and set:

- `home_wifi_ssid` - the SSID you connect to at home
- `wled_host` - hostname or IP of your WLED device

## 2. Map SSID to Task Scheduler network name

Task Scheduler uses the **saved Windows network profile name**, which is usually the same as the Wi-Fi SSID but not always.

1. Open **Settings** -> **Network & Internet** -> **Wi-Fi** -> **Manage known networks**
2. Select your home network and note the profile name
3. Set that name in the imported task **Conditions** -> **Start only if the following network connection is available**

Keep `home_wifi_ssid` in `config.yaml` aligned with what `netsh wlan show interfaces` reports for **SSID**.

## 3. Import the task XML

Task definitions use schema **version 1.4** with **Conditions** nested under **Settings** (as exported by current Windows). Older hand-edited XML that places `<Conditions>` as a sibling after `</Settings>` fails to import with error **(37,5):Conditions**.

1. Open **Task Scheduler**
2. **Action** -> **Import Task...**
3. Choose one of:
   - `tasks/BusyLight-HomeWiFi-Logon.xml` — logon trigger plus **Network** condition (home profile must be available)
   - `tasks/BusyLight-Logon-NoCondition.xml` — logon only; SSID gating is handled entirely by `scripts/run-busylight.ps1` (easier import if you do not need the scheduler network check)
4. Edit the task:
   - **Actions**: set **Start in** and the script path to your clone folder (replace `REPLACE_WITH_REPO`)
   - For the Home Wi-Fi XML only: **Conditions** -> set **Network** to your Windows profile name (replace `REPLACE_WITH_WINDOWS_NETWORK_PROFILE_NAME`)
5. Save and run once to test

The **Network** condition uses the saved Windows **connection profile name** from Settings -> **Manage known networks**, not necessarily the same spelling or casing as the **SSID** field from `netsh wlan show interfaces`. Configure both the task profile name and `home_wifi_ssid` in `config.yaml` so they match your real home network.

Alternatively, double-click `scripts/run-busylight.cmd` from Explorer after editing paths in the XML, or schedule that `.cmd` file.

## 4. Stopping when you leave home

You do not need a separate disconnect task. Each monitoring loop checks Wi-Fi using the same interval as status polling. When the SSID no longer matches `home_wifi_ssid`, BusyLight turns WLED off and exits.

To stop manually, run `scripts/stop-busylight.ps1` or use **Exit** on the system tray icon.