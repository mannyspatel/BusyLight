# App allowlist (ConsentStore)

BusyLight decides you are "in a call" when Windows shows an allowed application actively using the microphone or webcam. Detection walks the registry under:

`HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\`

## Find paths for a new app

1. Open **Registry Editor** (`regedit`) as your normal user (no admin).
2. Navigate to:
   - `HKCU\Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\microphone`
   - and `...\webcam`
3. Expand subkeys (including **NonPackaged**). Each folder name is a partial path, often containing the app name or executable (for example `...\NonPackaged\C:#Program Files#Zoom#bin#Zoom.exe`).
4. Note a **unique substring** from the path (case does not matter), such as `zoom`, `teams`, or `webex`.

While the app is using the device, `LastUsedTimeStop` under the active subkey is `0`.

## Add to `config.yaml`

```yaml
app_allowlist:
  - teams
  - zoom
  - your-app-substring
```

Matching is **case-insensitive substring** search on the full registry path.

- Use `app_allowlist: []` to treat **any** app using mic/camera as busy (more false positives).
- Omit the key or set `null` in YAML only if you extend defaults in code; the example file lists common meeting apps.