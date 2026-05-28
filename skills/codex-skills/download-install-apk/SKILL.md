---
name: download-install-apk
description: Safely download one Android APK from a browser page and optionally install it onto a connected Android phone with adb. Use when the user provides an APK filename plus a web page URL, asks to download an APK from ADP/JN Workflow or another authenticated page, or asks to install/reinstall/downgrade-install an APK after download. Enforces single-click download handling to avoid duplicate browser downloads.
---

# Download And Install APK

## Core Rule

Trigger a given APK download at most once unless the user explicitly approves another click.

Do not treat a missing browser `download` event as proof that no download started. Some internal pages hand the download to Chrome without exposing a standard event to the automation layer.

## Workflow

1. Identify the exact APK filename and page URL.
2. For ADP/JN Workflow app detail URLs, prefer the authenticated API path over coordinate clicking:
   - Extract the numeric app id from `/apps/<id>`.
   - In the already logged-in Chrome page, execute JavaScript to fetch `https://api.jn.bytedance.net/adp/v1/projects/apps/<id>` with `credentials:"include"`.
   - Find the file object whose `fullName` matches the requested APK.
   - Fetch `https://api.jn.bytedance.net/adp/v1/projects/apps/<id>/file-objects/<fileObjectId>/url` with `credentials:"include"`.
   - Download the returned temporary `payload.url` with `curl.exe -L --fail -o <Downloads>\<filename> <url>`. Do not print the URL because it contains a temporary credential.
3. If the API path is unavailable, start `scripts/download_and_install_apk.ps1` before clicking anything. Use `-OpenPage` only if the page is not already open.
4. In Chrome, locate the row or control for the exact filename. Prefer the row-specific download icon for that file.
5. Click one download control exactly once.
6. Stop clicking. Let the script monitor the download folders and Chrome history until the completed APK appears.
7. If the script times out, report that no completed APK was detected and ask before trying another control.
8. Install with `adb` only after the completed APK path is reported.

```powershell
powershell -ExecutionPolicy Bypass -File "$env:CODEX_HOME\skills\download-install-apk\scripts\download_and_install_apk.ps1" `
  -PageUrl "https://jn-workflow.bytedance.net/adp/projects/atom/apps/137619" `
  -FileName "Atom_publication_cn_trunk_v0.0.2173.7022289_upgrade-2022.3.67-auto.apk" `
  -OpenPage
```

Use `-Serial <device-serial>` when multiple devices are attached. Use `-AllowDowngrade` only when installing an older version is intended. Use `-DryRunInstall` to locate the APK and check device readiness without installing.

## Browser Guardrails

- Never click the page-level download button, row download icon, and batch download in sequence for the same filename.
- Never use batch download unless the user asks for batch behavior or explicitly approves it after the row-specific button fails.
- If batch download is approved, first ensure only the target APK checkbox is selected.
- After the single click, wait for local evidence: a completed `.apk`, an in-progress `.crdownload`, or a Chrome history record.
- If a partial download is visible, keep waiting. Do not click again.
- If there is no local evidence after the timeout, ask the user whether to inspect Chrome downloads or try one alternative control.

## ADP/JN Workflow Notes

Do not expect the APK URL to be present in the original HTML. ADP/JN Workflow pages often generate temporary authenticated URLs only after the logged-in frontend download button is clicked, for example:

```text
https://jn-p-api.bytedance.net/adp/v1/objects/single/.../<file>.apk?credential=...
```

If command-line requests return `401`, use the logged-in browser/plugin path. Do not scrape or handle cookies manually.

To execute JavaScript in a logged-in Chrome tab without DevTools, type `java` in the address bar and paste the rest beginning with `script:`. Chrome strips fully pasted `javascript:` URLs, but the split `java` + pasted `script:...` form runs in the current page context.

## Scripts

- `scripts/download_and_install_apk.ps1`: opens the page optionally, waits for the APK, then installs it unless `-DryRunInstall` is set.
- `scripts/find_apk_download.ps1`: waits for the completed APK, reports in-progress `.crdownload` files, and checks Chrome/Edge history when available.
- `scripts/install_apk.ps1`: validates `adb`, checks connected devices, and runs `adb install -r --user 0`.

For a dry run:

```powershell
powershell -ExecutionPolicy Bypass -File "$env:CODEX_HOME\skills\download-install-apk\scripts\download_and_install_apk.ps1" `
  -FileName "app.apk" -DryRunInstall
```
