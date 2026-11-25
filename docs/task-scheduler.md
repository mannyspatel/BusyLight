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

1. Open **Task Scheduler**
2. **Action** -> **Import Task...**
3. Choose `tasks/BusyLight-HomeWiFi-Logon.xml`
4. Edit the task:
   - **Actions**: set **Start in** and the script path to your clone folder (replace `REPLACE_WITH_REPO`)
   - **Conditions**: set **Network** to your Windows profile name (replace `REPLACE_WITH_WINDOWS_NETWORK_PROFILE_NAME`)
5. Save and run once to test

Alternatively, double-click `scripts/run-busylight.cmd` from Explorer after editing paths in the XML, or schedule that `.cmd` file.

## 4. Stopping when you leave home

You do not need a separate disconnect task. Each monitoring loop checks Wi-Fi using the same interval as status polling. When the SSID no longer matches `home_wifi_ssid`, BusyLight turns WLED off and exits.

To stop manually, run `scripts/stop-busylight.ps1` or use **Exit** on the system tray icon.