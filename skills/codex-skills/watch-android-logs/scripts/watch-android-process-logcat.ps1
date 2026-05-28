param(
  [string]$Device,
  [string]$Package,
  [string]$Activity,
  [string]$ApkPath,
  [switch]$Start,
  [switch]$Clear,
  [switch]$IncludeExisting,
  [string]$Output,
  [int]$PollSeconds = 1,
  [int]$DurationSeconds = 0,
  [int]$TailLines = 5000,
  [string[]]$Match
)

$ErrorActionPreference = "Stop"

function Resolve-Adb {
  $adb = Get-Command adb -ErrorAction SilentlyContinue
  if ($adb) {
    return $adb.Source
  }

  $candidates = @(
    "D:\Lib\android_sdk\platform-tools\adb.exe",
    "$env:LOCALAPPDATA\Android\Sdk\platform-tools\adb.exe"
  )

  foreach ($candidate in $candidates) {
    if (Test-Path -LiteralPath $candidate) {
      return $candidate
    }
  }

  throw "adb was not found. Add Android platform-tools to PATH or install the Android SDK."
}

function Resolve-Aapt {
  $aapt = Get-Command aapt -ErrorAction SilentlyContinue
  if ($aapt) {
    return $aapt.Source
  }

  $root = "D:\Lib\android_sdk\build-tools"
  if (Test-Path -LiteralPath $root) {
    $candidate = Get-ChildItem -Path $root -Recurse -Filter aapt.exe -ErrorAction SilentlyContinue |
      Sort-Object FullName -Descending |
      Select-Object -First 1
    if ($candidate) {
      return $candidate.FullName
    }
  }

  return $null
}

function Invoke-Adb {
  param(
    [Parameter(Mandatory = $true)]
    [string[]]$Arguments
  )

  $allArgs = @()
  if ($script:Device) {
    $allArgs += @("-s", $script:Device)
  }
  $allArgs += $Arguments
  & $script:Adb @allArgs
}

function Get-Device {
  $lines = & $script:Adb devices | Select-Object -Skip 1 | Where-Object { $_ -match "\S+\s+device\b" }
  $ids = @($lines | ForEach-Object { ($_ -split "\s+")[0] })
  if ($ids.Count -eq 0) {
    throw "No adb device is connected."
  }
  if ($ids.Count -gt 1) {
    throw "More than one adb device is connected. Re-run with -Device <serial>. Devices: $($ids -join ', ')"
  }
  return $ids[0]
}

function Read-ApkBadging {
  param([string]$Path)

  if (-not (Test-Path -LiteralPath $Path)) {
    throw "APK not found: $Path"
  }

  $aapt = Resolve-Aapt
  if (-not $aapt) {
    throw "aapt was not found, so -ApkPath cannot be inspected. Pass -Package and optionally -Activity instead."
  }

  $badging = & $aapt dump badging $Path
  $packageLine = $badging | Where-Object { $_ -like "package:*" } | Select-Object -First 1
  $activityLine = $badging | Where-Object { $_ -like "launchable-activity:*" } | Select-Object -First 1

  if (-not $packageLine -or $packageLine -notmatch "name='([^']+)'") {
    throw "Could not read package name from APK: $Path"
  }
  $pkg = $Matches[1]

  $act = $null
  if ($activityLine -and $activityLine -match "name='([^']+)'") {
    $act = $Matches[1]
  }

  [pscustomobject]@{
    Package = $pkg
    Activity = $act
  }
}

function Get-ProcessRows {
  param([string]$Pkg)

  $psLines = Invoke-Adb @("shell", "ps", "-A") 2>$null
  $rows = @()
  foreach ($line in $psLines) {
    if ($line -notmatch [regex]::Escape($Pkg)) {
      continue
    }

    $parts = ($line -replace "^\s+", "") -split "\s+"
    if ($parts.Count -lt 9 -or $parts[1] -notmatch "^\d+$") {
      continue
    }

    $name = $parts[-1]
    if ($name -ne $Pkg -and -not $name.StartsWith("${Pkg}:")) {
      continue
    }

    $rows += [pscustomobject]@{
      Pid = $parts[1]
      Name = $name
      Raw = $line
    }
  }

  return $rows
}

function Start-App {
  param(
    [string]$Pkg,
    [string]$Act
  )

  Invoke-Adb @("shell", "am", "force-stop", $Pkg) | Out-Null
  Start-Sleep -Milliseconds 500

  if ($Act) {
    Invoke-Adb @("shell", "am", "start", "-n", "$Pkg/$Act")
  } else {
    Invoke-Adb @("shell", "monkey", "-p", $Pkg, "-c", "android.intent.category.LAUNCHER", "1")
  }
}

function Test-LineMatch {
  param(
    [string]$Line,
    [hashtable]$PidNames,
    [string[]]$Patterns
  )

  if ($Line -notmatch "^\d\d-\d\d\s+\d\d:\d\d:\d\d\.\d+\s+(\d+)\s+") {
    return $false
  }

  $linePid = $Matches[1]
  if (-not $PidNames.ContainsKey($linePid)) {
    return $false
  }

  if ($Patterns -and $Patterns.Count -gt 0) {
    foreach ($pattern in $Patterns) {
      if ($Line -match $pattern) {
        return $true
      }
    }
    return $false
  }

  return $true
}

function Write-LogLine {
  param(
    [string]$Line,
    [System.IO.StreamWriter]$Writer
  )

  if ($Writer) {
    $Writer.WriteLine($Line)
    $Writer.Flush()
  }

  if ($Line -match "\s[EF]\s") {
    Write-Host $Line -ForegroundColor Red
  } elseif ($Line -match "\sW\s") {
    Write-Host $Line -ForegroundColor Yellow
  } else {
    Write-Host $Line
  }
}

if ($ApkPath) {
  $badging = Read-ApkBadging -Path $ApkPath
  if (-not $Package) {
    $Package = $badging.Package
  }
  if (-not $Activity) {
    $Activity = $badging.Activity
  }
}

if (-not $Package) {
  throw "Package is required. Pass -Package <packageName> or -ApkPath <apkFile>."
}

$script:Adb = Resolve-Adb
$script:Device = $Device
if (-not $script:Device) {
  $script:Device = Get-Device
}

if (-not $Output) {
  $logDir = Join-Path (Get-Location) "logs"
  New-Item -ItemType Directory -Force -Path $logDir | Out-Null
  $safePackage = $Package -replace "[^A-Za-z0-9_.-]", "_"
  $Output = Join-Path $logDir ("{0}_{1}_live.log" -f $safePackage, (Get-Date -Format "yyyyMMdd_HHmmss"))
} else {
  $parent = Split-Path -Parent $Output
  if ($parent) {
    New-Item -ItemType Directory -Force -Path $parent | Out-Null
  }
}

if ($Clear) {
  Invoke-Adb @("logcat", "-c") | Out-Null
}

if ($Start) {
  Start-App -Pkg $Package -Act $Activity | Out-Host
}

$writer = [System.IO.StreamWriter]::new($Output, $true, [System.Text.UTF8Encoding]::new($false))
$pidNames = @{}
$lastPidText = ""
$lastPoll = [DateTime]::MinValue

Write-Host "Device: $script:Device"
Write-Host "Package: $Package"
if ($Activity) {
  Write-Host "Activity: $Activity"
}
Write-Host "Writing: $Output"
if ($DurationSeconds -gt 0) {
  Write-Host "Watching live logcat for $DurationSeconds seconds."
} else {
  Write-Host "Watching live logcat. Press Ctrl+C to stop."
}

$endAt = $null
if ($DurationSeconds -gt 0) {
  $endAt = (Get-Date).AddSeconds($DurationSeconds)
}

$seen = [System.Collections.Generic.HashSet[string]]::new()
$seenQueue = [System.Collections.Generic.Queue[string]]::new()
$seenLimit = [Math]::Max($TailLines * 4, 20000)
$firstDump = $true

try {
  while ($true) {
    if ($endAt -and (Get-Date) -ge $endAt) {
      break
    }

    $now = Get-Date
    $rows = @(Get-ProcessRows -Pkg $Package)
    $next = @{}
    foreach ($row in $rows) {
      $next[$row.Pid] = $row.Name
    }

    $pidText = ($rows | Sort-Object Pid | ForEach-Object { "$($_.Pid):$($_.Name)" }) -join ", "
    if ($pidText -ne $lastPidText) {
      $status = if ($pidText) { $pidText } else { "not running" }
      $statusLine = "{0} process pids => {1}" -f (Get-Date -Format "MM-dd HH:mm:ss.fff"), $status
      $writer.WriteLine($statusLine)
      $writer.Flush()
      Write-Host $statusLine -ForegroundColor Cyan
      $lastPidText = $pidText
    }

    $suppressDumpOutput = $firstDump -and -not $IncludeExisting -and -not $Clear -and -not $Start
    $logArgs = @("logcat", "-d", "-v", "threadtime", "-t", [string]$TailLines)

    $lines = Invoke-Adb $logArgs 2>$null
    foreach ($line in $lines) {
      if (-not (Test-LineMatch -Line $line -PidNames $next -Patterns $Match)) {
        continue
      }

      if (-not $seen.Add($line)) {
        continue
      }

      $seenQueue.Enqueue($line)
      while ($seenQueue.Count -gt $seenLimit) {
        [void]$seen.Remove($seenQueue.Dequeue())
      }

      if (-not $suppressDumpOutput) {
        Write-LogLine -Line $line -Writer $writer
      }
    }
    $firstDump = $false

    $sleepMs = [Math]::Max(100, $PollSeconds * 1000)
    Start-Sleep -Milliseconds $sleepMs
  }
} finally {
  $writer.Dispose()
}
