param(
    [string]$PageUrl,

    [Parameter(Mandatory = $true)]
    [string]$FileName,

    [string[]]$DownloadDirs,

    [string]$Serial,

    [switch]$AllowDowngrade,

    [switch]$OpenPage,

    [switch]$DryRunInstall,

    [int]$TimeoutSeconds = 900
)

$ErrorActionPreference = 'Stop'
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

if ($OpenPage -and $PageUrl) {
    Write-Output "Opening page: $PageUrl"
    Start-Process $PageUrl
}

Write-Output 'If the page requires authentication, use the already logged-in browser/plugin to click the exact APK download button once.'
Write-Output 'After that click, do not click any other download control unless this script times out and the user approves a retry.'

$findArgs = @(
    '-ExecutionPolicy', 'Bypass',
    '-File', (Join-Path $scriptDir 'find_apk_download.ps1'),
    '-FileName', $FileName,
    '-TimeoutSeconds', $TimeoutSeconds
)
if ($DownloadDirs -and $DownloadDirs.Count -gt 0) {
    $findArgs += '-DownloadDirs'
    $findArgs += $DownloadDirs
}

$findOutput = & powershell @findArgs
$findCode = $LASTEXITCODE
$findOutput | ForEach-Object { Write-Output $_ }
if ($findCode -ne 0) {
    exit $findCode
}

$apkLine = $findOutput | Where-Object { $_ -like 'APK_PATH=*' } | Select-Object -Last 1
if (-not $apkLine) {
    Write-Error 'Download completed but APK_PATH was not reported.'
    exit 1
}
$apkPath = $apkLine.Substring('APK_PATH='.Length)

$installArgs = @(
    '-ExecutionPolicy', 'Bypass',
    '-File', (Join-Path $scriptDir 'install_apk.ps1'),
    '-ApkPath', $apkPath
)
if ($Serial) {
    $installArgs += @('-Serial', $Serial)
}
if ($AllowDowngrade) {
    $installArgs += '-AllowDowngrade'
}
if ($DryRunInstall) {
    $installArgs += '-DryRun'
}

& powershell @installArgs
exit $LASTEXITCODE
