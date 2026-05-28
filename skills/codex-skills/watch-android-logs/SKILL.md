---
name: watch-android-logs
description: Start or restart an Android app on a connected phone and record live logcat output for that app's process, similar to watching filtered Logcat in Android Studio. Use when the user asks to launch a phone app/package/APK, collect startup logs, continuously observe process logs, follow logs for a package, capture crash/error logs, or save Android logs for an installed APK.
---

# Watch Android Logs

## Workflow

Use `scripts/watch-android-process-logcat.ps1` for deterministic Android log capture. It:

- resolves `adb` from PATH or common Android SDK paths
- optionally resolves package name and launch Activity from an APK with `aapt`
- optionally clears logcat and starts/restarts the app
- polls the app's current process IDs and filters logcat by PID
- writes matching logs to a file while also printing them live
- rebinds when the process PID changes

Prefer this script over ad hoc `adb logcat` commands.

## Quick Commands

Start a package, clear old logs, and follow only that process:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "<skill-dir>\scripts\watch-android-process-logcat.ps1" -Package "com.example.app" -Activity "com.example.MainActivity" -Clear -Start
```

Start from an APK path by parsing package and launch Activity:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "<skill-dir>\scripts\watch-android-process-logcat.ps1" -ApkPath "E:\Downloads\app.apk" -Clear -Start
```

Follow an already-running package without showing old buffered logs:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "<skill-dir>\scripts\watch-android-process-logcat.ps1" -Package "com.example.app"
```

Capture only matching lines:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File "<skill-dir>\scripts\watch-android-process-logcat.ps1" -Package "com.example.app" -Match "FATAL EXCEPTION","AndroidRuntime","Unity","Exception","Error"
```

Use `Ctrl+C` to stop an ongoing watch. For validation or short captures, pass `-DurationSeconds <n>`.

## Parameters

- `-Device <serial>`: use when more than one device is connected.
- `-Package <package>`: Android package name to watch.
- `-Activity <activity>`: explicit launch Activity. If omitted with `-Start`, the script uses `monkey` launcher start.
- `-ApkPath <apk>`: parse package and launch Activity from an APK. Requires `aapt`.
- `-Start`: force-stop and launch the app before watching.
- `-Clear`: clear logcat before watching. Use with `-Start` for clean startup logs.
- `-IncludeExisting`: include existing buffered logs on first pass.
- `-Output <path>`: write logs to a specific file. If omitted, writes under the current directory's `logs`.
- `-PollSeconds <n>`: polling interval. Default is `1`.
- `-TailLines <n>`: number of recent logcat lines to scan each poll. Default is `5000`.
- `-Match <patterns>`: optional regex filters applied after PID filtering.

## Execution Notes

Before running, confirm `adb devices -l` shows exactly one usable device or pass `-Device`.

For startup investigation, use `-Clear -Start` so the saved file contains logs from the new launch rather than stale buffer output.

When a user says "all logs for this app/process", capture unfiltered PID logs first. Add `-Match` only for a focused follow-up.

After a run, report the package, device serial, output log path, whether the process stayed alive, and any obvious crash indicators such as `FATAL EXCEPTION`, `AndroidRuntime`, `SIGSEGV`, `SIGABRT`, or `ANR`.
