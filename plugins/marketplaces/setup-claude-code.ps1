# Claude Code Configuration Script for API Router (Windows)
# This script configures Claude Code to use your API Router instance
# Run with: powershell -ExecutionPolicy Bypass -File setup-claude-code.ps1 -BaseUrl https://your-domain.tld -ApiKey YOUR_KEY
# Or via one-liner: & { $url='https://your-domain.tld'; $key='YOUR_KEY'; iwr -useb $url/setup-claude-code.ps1 | iex }

param(
    [string]$BaseUrl,
    [string]$ApiKey,
    [switch]$Test,
    [switch]$Show,
    [switch]$Help
)

# Check for pre-set variables from one-liner command (use different names to avoid conflict)
if (-not $BaseUrl -and (Test-Path Variable:url)) { $BaseUrl = $url }
if (-not $ApiKey -and (Test-Path Variable:key)) { $ApiKey = $key }

# Configuration
$DefaultBaseUrl = "http://localhost:8080"
$ClaudeConfigDir = "$env:USERPROFILE\.claude"
$ClaudeSettingsFile = "$ClaudeConfigDir\settings.json"
$ClaudeCodePatchedVersion = "2.1.84"
$ClaudeCodePatchedBuild = "7"
$ClaudeCodePatchedPackageVersion = "$ClaudeCodePatchedVersion-yescode.$ClaudeCodePatchedBuild"
$ClaudeCodePatchedPackageName = "yescode-$ClaudeCodePatchedVersion.tgz"

# Color functions for output
function Write-Info {
    param([string]$Message)
    Write-Host "[INFO]" -ForegroundColor Blue -NoNewline
    Write-Host " $Message"
}

function Write-Success {
    param([string]$Message)
    Write-Host "[SUCCESS]" -ForegroundColor Green -NoNewline
    Write-Host " $Message"
}

function Write-Warning {
    param([string]$Message)
    Write-Host "[WARNING]" -ForegroundColor Yellow -NoNewline
    Write-Host " $Message"
}

function Write-Error {
    param([string]$Message)
    Write-Host "[ERROR]" -ForegroundColor Red -NoNewline
    Write-Host " $Message"
}

# Function to show help
function Show-Help {
    Write-Host @"
Claude Code Configuration Script for API Router (Windows)

Usage: powershell -ExecutionPolicy Bypass -File setup-claude-code.ps1 [OPTIONS]

Options:
  -BaseUrl <URL> Set the API Router base URL (default: $DefaultBaseUrl)
  -ApiKey <KEY>  Set the API key
  -Test          Test API connection only (requires -BaseUrl and -ApiKey)
  -Show          Show current settings and exit
  -Help          Show this help message

Examples:
  .\setup-claude-code.ps1 -BaseUrl https://your-domain.tld -ApiKey your-api-key-here
  .\setup-claude-code.ps1 -Test -BaseUrl https://your-domain.tld -ApiKey your-api-key-here
  .\setup-claude-code.ps1 -Show

Interactive mode (no arguments):
  .\setup-claude-code.ps1

PowerShell Execution Policy:
  If you get an execution policy error, run:
  powershell -ExecutionPolicy Bypass -File setup-claude-code.ps1
"@
    exit 0
}

# Function to backup existing settings
function Backup-Settings {
    if (Test-Path $ClaudeSettingsFile) {
        $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
        $backupFile = "$ClaudeSettingsFile.backup.$timestamp"
        Copy-Item -Path $ClaudeSettingsFile -Destination $backupFile
        Write-Info "Backed up existing settings to: $backupFile"
    }
}

# Function to create settings directory
function New-SettingsDirectory {
    if (-not (Test-Path $ClaudeConfigDir)) {
        New-Item -ItemType Directory -Path $ClaudeConfigDir -Force | Out-Null
        Write-Info "Created Claude configuration directory: $ClaudeConfigDir"
    }
}

# Function to validate API key format
function Test-ApiKey {
    param([string]$ApiKey)

    if ($ApiKey -match '^[A-Za-z0-9_-]+$') {
        return $true
    } else {
        Write-Error "Invalid API key format. API key should contain only alphanumeric characters, hyphens, and underscores."
        return $false
    }
}

# Function to test API connection
function Test-ApiConnection {
    param(
        [string]$BaseUrl,
        [string]$ApiKey
    )

    Write-Info "Testing API connection..."

    try {
        $headers = @{
            "Content-Type" = "application/json"
            "X-API-Key" = $ApiKey
        }

        # Use team balance for team URLs; otherwise user balance with legacy fallback.
        $isTeam = $BaseUrl.EndsWith("/team")
        if ($isTeam) {
            $uri = "$BaseUrl/api/v1/team/stats/spending"
            $balanceField = "daily_remaining"
            $balanceLabel = "Daily remaining"
        } else {
            $uri = "$BaseUrl/api/v1/user/balance"
            $balanceField = "balance"
            $balanceLabel = "Current balance"
        }

        $response = Invoke-RestMethod -Uri $uri -Method Get -Headers $headers -ErrorAction Stop

        if ($response.$balanceField) {
            Write-Success "API connection successful! ${balanceLabel}: `$$($response.$balanceField)"
            return $true
        } else {
            Write-Error "API test failed: Invalid response"
            return $false
        }
    }
    catch {
        if ($_.Exception.Response -and $_.Exception.Response.StatusCode -eq 401) {
            Write-Error "API key authentication failed. Please check your API key."
        } elseif ($_.Exception.Message -like "*Unable to connect*" -or $_.Exception.Message -like "*could not be resolved*") {
            Write-Error "Cannot connect to API server. Please check the URL and your internet connection."
        } else {
            Write-Error "API test failed: $($_.Exception.Message)"
        }
        return $false
    }
}

# Function to create or update Claude Code settings
function New-Settings {
    param(
        [string]$BaseUrl,
        [string]$ApiKey
    )

    $settings = $null

    # Check if settings file exists and try to load it
    if (Test-Path $ClaudeSettingsFile) {
        try {
            $existingContent = Get-Content $ClaudeSettingsFile -Raw -ErrorAction Stop
            $settings = $existingContent | ConvertFrom-Json -ErrorAction Stop
            Write-Info "Updating existing settings file (preserving other settings)..."

            # Ensure env object exists
            if (-not $settings.env) {
                $settings | Add-Member -NotePropertyName "env" -NotePropertyValue @{} -Force
            }

            # Update only the API URL and token (convert to hashtable for modification)
            $envHash = @{}
            $settings.env.PSObject.Properties | ForEach-Object {
                $envHash[$_.Name] = $_.Value
            }
            $envHash["ANTHROPIC_BASE_URL"] = $BaseUrl
            $envHash["ANTHROPIC_AUTH_TOKEN"] = $ApiKey

            # Convert back to PSObject
            $settings.env = [PSCustomObject]$envHash
        }
        catch {
            Write-Warning "Existing settings file is invalid JSON, creating new one..."
            $settings = $null
        }
    }

    # If no valid existing settings, create new with defaults
    if (-not $settings) {
        Write-Info "Creating new settings file with defaults..."
        $settings = @{
            env = @{
                ANTHROPIC_BASE_URL = $BaseUrl
                ANTHROPIC_AUTH_TOKEN = $ApiKey
                CLAUDE_CODE_MAX_OUTPUT_TOKENS = 20000
                DISABLE_TELEMETRY = 1
                DISABLE_ERROR_REPORTING = 1
                CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC = 1
                CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR = 1
                MAX_THINKING_TOKENS = 12000
            }
            model = "sonnet"
        }
    }

    try {
        $json = $settings | ConvertTo-Json -Depth 10
        Set-Content -Path $ClaudeSettingsFile -Value $json -Encoding UTF8
        Write-Success "Claude Code settings written to: $ClaudeSettingsFile"
        return $true
    }
    catch {
        Write-Error "Failed to create settings file: $($_.Exception.Message)"
        return $false
    }
}

# Function to display current settings
function Show-Settings {
    if (Test-Path $ClaudeSettingsFile) {
        Write-Info "Current Claude Code settings:"
        Write-Host "----------------------------------------"
        $settings = Get-Content $ClaudeSettingsFile -Raw | ConvertFrom-Json
        $settings | ConvertTo-Json -Depth 10
        Write-Host "----------------------------------------"
    } else {
        Write-Info "No existing Claude Code settings found."
    }

    Write-Host ""
    Write-Info "Current environment variables:"
    Write-Host "----------------------------------------"
    $baseUrl = [Environment]::GetEnvironmentVariable("ANTHROPIC_BASE_URL", [EnvironmentVariableTarget]::User)
    $authToken = [Environment]::GetEnvironmentVariable("ANTHROPIC_AUTH_TOKEN", [EnvironmentVariableTarget]::User)

    if ($baseUrl) {
        Write-Info "ANTHROPIC_BASE_URL: $baseUrl"
    } else {
        Write-Info "ANTHROPIC_BASE_URL: (not set)"
    }

    if ($authToken) {
        $maskedToken = if ($authToken.Length -gt 12) {
            "$($authToken.Substring(0, 8))...$($authToken.Substring($authToken.Length - 4))"
        } else {
            "$($authToken.Substring(0, [Math]::Min(4, $authToken.Length)))..."
        }
        Write-Info "ANTHROPIC_AUTH_TOKEN: $maskedToken"
    } else {
        Write-Info "ANTHROPIC_AUTH_TOKEN: (not set)"
    }
    Write-Host "----------------------------------------"
}

function Get-PatchedClaudeCodePackageUrl {
    param([string]$BaseUrl)
    return "$($BaseUrl.TrimEnd('/'))/downloads/yescode/$ClaudeCodePatchedVersion/$ClaudeCodePatchedPackageName?v=$ClaudeCodePatchedPackageVersion"
}

# Main function
function Main {
    Write-Info "Claude Code Configuration Script for API Router"
    Write-Host "======================================================="
    Write-Host ""

    # Handle command line arguments
    if ($Help) {
        Show-Help
    }

    if ($Show) {
        Show-Settings
        exit 0
    }

    # Interactive mode if no URL or Key provided
    if (-not $BaseUrl -and -not $ApiKey) {
        Write-Info "Interactive setup mode"
        Write-Host ""

        # Get base URL
        $inputUrl = Read-Host "Enter API Router URL [$DefaultBaseUrl]"
        if ([string]::IsNullOrWhiteSpace($inputUrl)) {
            $BaseUrl = $DefaultBaseUrl
        } else {
            $BaseUrl = $inputUrl
        }

        # Get API key
        while ([string]::IsNullOrWhiteSpace($ApiKey)) {
            $ApiKey = Read-Host "Enter your API key"
            if ([string]::IsNullOrWhiteSpace($ApiKey)) {
                Write-Warning "API key is required"
            } elseif (-not (Test-ApiKey $ApiKey)) {
                $ApiKey = ""
            }
        }
    }

    # Validate inputs
    if ([string]::IsNullOrWhiteSpace($BaseUrl) -or [string]::IsNullOrWhiteSpace($ApiKey)) {
        Write-Error "Both URL and API key are required"
        Write-Info "Use -Help for usage information"
        exit 1
    }

    # Validate API key
    if (-not (Test-ApiKey $ApiKey)) {
        exit 1
    }

    # Remove trailing slash from URL
    $BaseUrl = $BaseUrl.TrimEnd('/')

    Write-Info "Configuration:"
    Write-Info "  Base URL: $BaseUrl"
    $maskedKey = if ($ApiKey.Length -gt 12) {
        "$($ApiKey.Substring(0, 8))...$($ApiKey.Substring($ApiKey.Length - 4))"
    } else {
        "$($ApiKey.Substring(0, [Math]::Min(4, $ApiKey.Length)))..."
    }
    Write-Info "  API Key: $maskedKey"
    Write-Host ""

    # Test API connection
    $connectionSuccess = Test-ApiConnection -BaseUrl $BaseUrl -ApiKey $ApiKey

    if (-not $connectionSuccess) {
        if ($Test) {
            exit 1
        }

        $continue = Read-Host "API test failed. Continue anyway? (y/N)"
        if ($continue -notmatch '^[Yy]$') {
            Write-Info "Setup cancelled"
            exit 1
        }
    }

    # Exit if test only
    if ($Test) {
        Write-Success "API test completed successfully"
        exit 0
    }

    # Create settings directory
    New-SettingsDirectory

    # Backup existing settings
    Backup-Settings

    # Create new settings
    if (New-Settings -BaseUrl $BaseUrl -ApiKey $ApiKey) {
        Write-Host ""

        # Also set environment variables for Windows
        Write-Info "Setting environment variables..."
        try {
            # Set user environment variables (persistent across sessions)
            [Environment]::SetEnvironmentVariable("ANTHROPIC_BASE_URL", $BaseUrl, [EnvironmentVariableTarget]::User)
            [Environment]::SetEnvironmentVariable("ANTHROPIC_AUTH_TOKEN", $ApiKey, [EnvironmentVariableTarget]::User)

            # Also set for current session
            $env:ANTHROPIC_BASE_URL = $BaseUrl
            $env:ANTHROPIC_AUTH_TOKEN = $ApiKey

            Write-Success "Environment variables set successfully"
        }
        catch {
            Write-Warning "Failed to set environment variables: $($_.Exception.Message)"
            Write-Info "You may need to set them manually:"
            Write-Info "  ANTHROPIC_BASE_URL=$BaseUrl"
            Write-Info "  ANTHROPIC_AUTH_TOKEN=$ApiKey"
        }

        Write-Host ""
        Write-Success "Claude Code has been configured successfully!"
        Write-Info "You can now use Claude Code with your API router."
        Write-Info ""
        Write-Info "To verify the setup, run:"
        Write-Info "  yescode --version"
        Write-Info ""
        Write-Info "Configuration file location: $ClaudeSettingsFile"
        Write-Info "Environment variables have been set for ANTHROPIC_BASE_URL and ANTHROPIC_AUTH_TOKEN"

        $packageUrl = Get-PatchedClaudeCodePackageUrl -BaseUrl $BaseUrl
        Write-Host ""
        Write-Info "Prepatched Claude Code package:"
        Write-Info "  $packageUrl"
        Write-Info ""
        Write-Info "Install or upgrade Claude Code directly from YesCode with:"
        Write-Info "  npm install -g `"$packageUrl`""

        if (Test-Path $ClaudeSettingsFile) {
            Write-Host ""
            Write-Info "Current settings:"
            $settings = Get-Content $ClaudeSettingsFile -Raw | ConvertFrom-Json
            $settings | ConvertTo-Json -Depth 10
        }
    } else {
        Write-Error "Failed to create Claude Code settings"
        exit 1
    }
}

# Run main function
Main
