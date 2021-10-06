#Requires -RunAsAdministrator

<#
 # Copyright 2021 Google Inc.
 #
 # Licensed under the Apache License, Version 2.0 (the "License");
 # you may not use this file except in compliance with the License.
 # You may obtain a copy of the License at
 #
 #     http://www.apache.org/licenses/LICENSE-2.0
 #
 # Unless required by applicable law or agreed to in writing, software
 # distributed under the License is distributed on an "AS IS" BASIS,
 # WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 # See the License for the specific language governing permissions and
 # limitations under the License.
#>

# Check if the GPU exists with Windows Management Instrumentation
function Find-GPU {
    try {
        (Get-WmiObject -query "select DeviceID from Win32_PNPEntity Where (deviceid Like '%PCI\\VEN_10DE%') and (PNPClass = 'Display' or Name = '3D Video Controller')"  | Select-Object DeviceID -ExpandProperty DeviceID).substring(13,8)
    }
    catch {
        Write-Output "There doesn't seem to be a GPU unit connected to your system. Do you want to continue?"
        Read-Host -Prompt 'Press any key to continue'
    }
}

# Check if the Driver is already installed
function Check-Driver {
    try {
        &'C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe'
        Write-Output 'Driver is already installed. Do you wish to continue?'
        Read-Host -Prompt 'Press any key to continue'
    }
    catch {
        Write-Output 'Driver is not installed, proceeding with installation'
        Read-Host -Prompt 'Press any key to continue'
    }
}

# Install the driver
function Install-Driver {

    # Set the correct url for download and uses the appropriate file name to install the driver
    $url = 'https://developer.download.nvidia.com/compute/cuda/11.4.0/network_installers/cuda_11.4.0_win10_network.exe';
    $file_dir = 'C:\NVIDIA-Driver\cuda_11.4.0_win10_network.exe';

    # Check if the GPU exists and if the driver is already installed
    Find-GPU
    Check-Driver

    # Create the folder for the driver download
    if (!(Test-Path -Path 'C:\NVIDIA-Driver')) {
        New-Item -Path 'C:\' -Name 'NVIDIA-Driver' -ItemType 'directory' | Out-Null
    }

    # Download the file to a specfied directory
    Invoke-WebRequest $url -OutFile $file_dir

    # Install the file with the specified path from earlier as well as the RunAs admin option
    Start-Process -FilePath $file_dir -ArgumentList '/s /n' -Wait
}

# Run the functions
Install-Driver
