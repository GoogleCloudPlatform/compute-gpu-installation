<#
.SYNOPSIS
    Automated NVIDIA Driver Installer for Windows Server 2019+
    
.DESCRIPTION
    1. Determines GCP Multi-region based on instance metadata.
    2. Checks for NVIDIA GPU presence using PCI Vendor ID (10DE).
    3. Checks if nvidia-smi is already installed.
    4. Downloads the region-specific driver installer.
    5. Silently installs the driver.
    6. Cleans up installer artifacts.

.NOTES
    Run this script as Administrator.
#>

$ErrorActionPreference = "Stop"

# --- Constants & Config ---
$DriverVersionFilename = "581.15_grid_win10_win11_server2022_dch_64bit_international.exe"
$TempDir = [System.IO.Path]::GetTempPath()
$InstallerName = "nvidia_driver_installer.exe"
$InstallerPath = Join-Path -Path $TempDir -ChildPath $InstallerName

# --- Functions for Region Detection ---
function Get-GcpMultiRegion {
    # Map region prefixes to multi-regions
    $RegionMap = @{
        "africa"       = "eu"
        "asia"         = "asia"
        "australia"    = "asia"
        "europe"       = "eu"
        "me"           = "eu"
        "northamerica" = "us"
        "southamerica" = "us"
        "us"           = "us"
    }

    Write-Host "Detecting GCP Region..." -ForegroundColor Cyan

    try {
        # Query Google Metadata server for the zone
        # Timeout included to prevent hanging if not on GCP or metadata is unreachable
        $ZoneUrl = "http://metadata.google.internal/computeMetadata/v1/instance/zone"
        $Response = Invoke-RestMethod -Uri $ZoneUrl -Headers @{"Metadata-Flavor" = "Google"} -TimeoutSec 5 -ErrorAction Stop

        # Response format is usually: projects/PROJECT_ID/zones/REGION-ZONE (e.g., projects/123/zones/us-central1-a)
        $ZoneName = $Response.Split('/')[-1]

        # Get the region prefix (e.g., 'us' from 'us-central1-a')
        $RegionPrefix = $ZoneName.Split('-')[0]

        if ($RegionMap.ContainsKey($RegionPrefix)) {
            $MultiRegion = $RegionMap[$RegionPrefix]
            Write-Host "Region detected: $RegionPrefix -> Multi-region: $MultiRegion" -ForegroundColor Green
            return $MultiRegion
        }
    }
    catch {
        Write-Warning "Could not detect GCP region via metadata server. Defaulting to 'us'."
    }

    return "us"
}

# --- Functions for GPU Detection ---
function Get-Mgmt-Command {
    $Command = 'Get-CimInstance'
    if (Get-Command Get-WmiObject -ErrorAction SilentlyContinue) {
        $Command = 'Get-WmiObject'
    }
    return $Command
}

function Find-GPU {
    $MgmtCommand = Get-Mgmt-Command
    try {
        # Query specifically for NVIDIA (VEN_10DE) in Display or 3D Controller classes
        $Command = "(${MgmtCommand} -query ""select DeviceID from Win32_PNPEntity Where (deviceid Like '%PCI\\VEN_10DE%') and (PNPClass = 'Display' or Name = '3D Video Controller')"" | Select-Object DeviceID -ExpandProperty DeviceID).substring(13,8)"
        $dev_id = Invoke-Expression -Command $Command
        return $dev_id
    }
    catch {
        Write-Warning "There doesn't seem to be a GPU unit connected to your system."
        return ""
    }
}

# --- Step 0: Determine Download URL ---
$MultiRegion = Get-GcpMultiRegion
$DriverUrl = "https://storage.googleapis.com/compute-gpu-installation-$MultiRegion/windows/$DriverVersionFilename"

# --- Step 1: Check for GPU Presence ---
Write-Host "Step 1: Checking for NVIDIA GPU (PCI ID Check)..." -ForegroundColor Cyan

$gpuId = Find-GPU

if ([string]::IsNullOrWhiteSpace($gpuId)) {
    Write-Warning "No NVIDIA GPU (VEN_10DE) detected via PnP Entity check. Exiting."
    Exit
} else {
    Write-Host "GPU Detected with Device ID substring: $gpuId" -ForegroundColor Green
}

# --- Step 2: Check for nvidia-smi ---
Write-Host "Step 2: Checking for existing installation (nvidia-smi)..." -ForegroundColor Cyan

$smiCommand = Get-Command "nvidia-smi" -ErrorAction SilentlyContinue
$smiPathDefault = "C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe"
$smiPathSystem = "C:\Windows\System32\nvidia-smi.exe"

if ($smiCommand -or (Test-Path $smiPathDefault) -or (Test-Path $smiPathSystem)) {
    Write-Warning "nvidia-smi is already present. Driver appears to be installed. Exiting."
    Exit
} else {
    Write-Host "nvidia-smi not found. Proceeding with installation." -ForegroundColor Green
}

# --- Step 3: Download Installer ---
Write-Host "Step 3: Downloading driver..." -ForegroundColor Cyan
Write-Host "Source: $DriverUrl" -ForegroundColor Gray

# Ensure TLS 1.2 is enabled for the download
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

try {
    # CRITICAL PERFORMANCE FIX:
    # The Invoke-WebRequest progress bar significantly slows down downloads in Windows PowerShell 5.1.
    # We disable it temporarily to speed up the transfer.
    $OriginalProgressPreference = $ProgressPreference
    $ProgressPreference = 'SilentlyContinue'

    Invoke-WebRequest -Uri $DriverUrl -OutFile $InstallerPath -UseBasicParsing

    # Restore preference
    $ProgressPreference = $OriginalProgressPreference

    Write-Host "Download complete. Saved to: $InstallerPath" -ForegroundColor Green
}
catch {
    Write-Error "Failed to download the installer. Error: $_"
    Exit
}

# --- Step 4 & 5: Execute and Wait ---
Write-Host "Step 4: Executing installer..." -ForegroundColor Cyan
Write-Host "Flags used: /s /n (Silent, No Reboot)" -ForegroundColor Gray

try {
    # Start the process with /s (silent) and /n (no reboot)
    $process = Start-Process -FilePath $InstallerPath -ArgumentList "/s", "/n" -PassThru -Wait -Verb RunAs
    
    if ($process.ExitCode -eq 0) {
        Write-Host "Installation finished successfully." -ForegroundColor Green
    } else {
        Write-Warning "Installation finished with Exit Code: $($process.ExitCode). This might indicate a reboot is required or a non-fatal warning."
    }
}
catch {
    Write-Error "Failed to execute installer. Error: $_"
    Exit
}

# --- Cleanup ---
Write-Host "Cleaning up temporary files..." -ForegroundColor Cyan
if (Test-Path $InstallerPath) {
    Remove-Item -Path $InstallerPath -Force
}

Write-Host "Done." -ForegroundColor Green