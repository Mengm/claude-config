param(
    [Parameter(Mandatory = $true)]
    [string]$ApkPath,

    [string]$Serial,

    [switch]$AllowDowngrade,

    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'

function Fail {
    param([string]$Message)
    Write-Error $Message
    exit 1
}

function Get-AdbPath {
    $cmd = Get-Command adb -ErrorAction SilentlyContinue
    if ($cmd) {
        return $cmd.Source
    }
    Fail "adb was not found in PATH. Install Android platform-tools or add adb.exe to PATH."
}

function Get-ConnectedDevices {
    param([string]$Adb)
    $lines = & $Adb devices -l
    if ($LASTEXITCODE -ne 0) {
        Fail "Failed to run adb devices."
    }

    $devices = @()
    foreach ($line in $lines) {
        if ($line -match '^\s*$' -or $line -match '^List of devices') {
            continue
        }
        $parts = $line -split '\s+'
        if ($parts.Count -lt 2) {
            continue
        }
        $devices += [pscustomobject]@{
            Serial = $parts[0]
            State = $parts[1]
            Raw = $line
        }
    }
    return $devices
}

function Select-Device {
    param(
        [object[]]$Devices,
        [string]$RequestedSerial
    )

    if ($RequestedSerial) {
        $match = $Devices | Where-Object { $_.Serial -eq $RequestedSerial } | Select-Object -First 1
        if (-not $match) {
            Fail "Device '$RequestedSerial' was not found. Connected devices:`n$($Devices.Raw -join "`n")"
        }
        if ($match.State -ne 'device') {
            Fail "Device '$RequestedSerial' is '$($match.State)'. If it is unauthorized, approve USB debugging on the phone."
        }
        return $match
    }

    $ready = @($Devices | Where-Object { $_.State -eq 'device' })
    if ($ready.Count -eq 0) {
        $summary = if ($Devices.Count) { $Devices.Raw -join "`n" } else { '(none)' }
        Fail "No authorized Android device is connected. Check USB, enable USB debugging, and approve the RSA prompt. Connected devices:`n$summary"
    }
    if ($ready.Count -gt 1) {
        Fail "Multiple devices are connected. Re-run with -Serial <serial>. Devices:`n$($ready.Raw -join "`n")"
    }
    return $ready[0]
}

$resolved = Resolve-Path -LiteralPath $ApkPath -ErrorAction SilentlyContinue
if (-not $resolved) {
    Fail "APK not found: $ApkPath"
}
$apk = $resolved.ProviderPath
if ([IO.Path]::GetExtension($apk).ToLowerInvariant() -ne '.apk') {
    Fail "Expected an .apk file, got: $apk"
}

$apkItem = Get-Item -LiteralPath $apk
$adb = Get-AdbPath
$devices = @(Get-ConnectedDevices -Adb $adb)
$device = Select-Device -Devices $devices -RequestedSerial $Serial

Write-Output "APK: $apk"
Write-Output ("Size: {0:N0} bytes" -f $apkItem.Length)
Write-Output "adb: $adb"
Write-Output "Device: $($device.Raw)"

$adbArgs = @()
if ($device.Serial) {
    $adbArgs += @('-s', $device.Serial)
}
$adbArgs += @('install', '-r')
if ($AllowDowngrade) {
    $adbArgs += '-d'
}
$adbArgs += @('--user', '0', $apk)

Write-Output "Command: adb $($adbArgs -join ' ')"
if ($DryRun) {
    Write-Output 'Dry run: install not executed.'
    exit 0
}

$output = & $adb @adbArgs 2>&1
$code = $LASTEXITCODE
$output | ForEach-Object { Write-Output $_ }

if ($code -eq 0 -and ($output -match 'Success')) {
    Write-Output 'Install succeeded.'
    exit 0
}

$joined = $output -join "`n"
if ($joined -match 'INSTALL_FAILED_VERSION_DOWNGRADE') {
    Fail "Install failed because the APK version is lower than the installed app. Re-run with -AllowDowngrade if that is intended."
}
if ($joined -match 'INSTALL_FAILED_INSUFFICIENT_STORAGE') {
    Fail "Install failed because the device has insufficient storage."
}
if ($joined -match 'INSTALL_FAILED_NO_MATCHING_ABIS') {
    Fail "Install failed because the APK ABI is incompatible with the device CPU architecture."
}
if ($joined -match 'INSTALL_PARSE_FAILED|Failure \[INSTALL_FAILED_INVALID_APK') {
    Fail "Install failed because the APK is invalid or cannot be parsed."
}
if ($joined -match 'device unauthorized|unauthorized') {
    Fail "Install failed because the device is unauthorized. Approve USB debugging on the phone and retry."
}

Fail "adb install failed with exit code $code."
