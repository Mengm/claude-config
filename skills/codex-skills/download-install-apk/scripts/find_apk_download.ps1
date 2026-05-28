param(
    [Parameter(Mandatory = $true)]
    [string]$FileName,

    [string[]]$DownloadDirs,

    [int]$TimeoutSeconds = 900
)

$ErrorActionPreference = 'Stop'

function Get-DefaultDownloadDirs {
    $dirs = @()
    if (Test-Path 'E:\Downloads') { $dirs += 'E:\Downloads' }
    if ($env:USERPROFILE) {
        $userDownloads = Join-Path $env:USERPROFILE 'Downloads'
        if (Test-Path $userDownloads) { $dirs += $userDownloads }
    }
    return @($dirs | Select-Object -Unique)
}

function Find-ByFilesystem {
    param([string[]]$Dirs, [string]$Name)
    foreach ($dir in $Dirs) {
        if (-not (Test-Path -LiteralPath $dir)) { continue }
        $path = Join-Path $dir $Name
        $partial = "$path.crdownload"
        if (Test-Path -LiteralPath $partial) {
            $partialItem = Get-Item -LiteralPath $partial
            Write-Output ("Partial download still present: {0} ({1:N0} bytes)" -f $partial, $partialItem.Length)
            continue
        }
        if (Test-Path -LiteralPath $path) {
            $item = Get-Item -LiteralPath $path
            if ($item.Length -gt 0) {
                return $item.FullName
            }
        }
    }
    return $null
}

function Find-ByChromeHistory {
    param([string]$Name)
    $sqlite = Get-Command sqlite3 -ErrorAction SilentlyContinue
    if (-not $sqlite) {
        return $null
    }
    $roots = @(
        (Join-Path $env:LOCALAPPDATA 'Google\Chrome\User Data'),
        (Join-Path $env:LOCALAPPDATA 'Microsoft\Edge\User Data')
    )
    foreach ($root in $roots) {
        if (-not (Test-Path -LiteralPath $root)) { continue }
        $profiles = Get-ChildItem -LiteralPath $root -Directory -ErrorAction SilentlyContinue
        foreach ($profile in $profiles) {
            $history = Join-Path $profile.FullName 'History'
            if (-not (Test-Path -LiteralPath $history)) { continue }
            $tmp = Join-Path $env:TEMP ("browser_history_{0}.sqlite" -f ([guid]::NewGuid().ToString('N')))
            try {
                Copy-Item -LiteralPath $history -Destination $tmp -Force -ErrorAction Stop
                $safe = $Name.Replace("'", "''")
                $query = "select target_path from downloads where target_path like '%$safe%' and state=1 order by start_time desc limit 1;"
                $path = & sqlite3 $tmp $query 2>$null | Select-Object -First 1
                if ($path -and (Test-Path -LiteralPath $path)) {
                    $item = Get-Item -LiteralPath $path
                    if ($item.Length -gt 0) {
                        return $item.FullName
                    }
                }
            } finally {
                Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue
            }
        }
    }
    return $null
}

if (-not $DownloadDirs -or $DownloadDirs.Count -eq 0) {
    $DownloadDirs = Get-DefaultDownloadDirs
}
if (-not $DownloadDirs -or $DownloadDirs.Count -eq 0) {
    throw 'No download directories were found. Pass -DownloadDirs explicitly.'
}

$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
Write-Output "Waiting for APK: $FileName"
Write-Output "Download dirs: $($DownloadDirs -join ', ')"

while ((Get-Date) -lt $deadline) {
    $path = Find-ByFilesystem -Dirs $DownloadDirs -Name $FileName
    if (-not $path) {
        $path = Find-ByChromeHistory -Name $FileName
    }
    if ($path) {
        Write-Output "APK_PATH=$path"
        exit 0
    }
    Start-Sleep -Seconds 3
}

Write-Error "Timed out waiting for completed APK: $FileName"
exit 1
