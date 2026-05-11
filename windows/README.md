## Installer Script for NVIDIA GPU Drivers

This script installs the latest supported NVIDIA GPU drivers for Google Cloud
Windows VM on Compute Engine.

The script automatically detects the machine type it's running on. If it detects
a fractional VM (vGPU), such as `g4-standard-6`, `g4-standard-12`, or `g4-standard-24`, 
it will install the specific driver version required for those instances.

## Usage Instructions


To use this script you must run it as an Administrator:

Start-Process powershell -Verb RunAs -ArgumentList "-file
path_to\install_gpu_driver.ps1"

You should replace path_to with the directory where the file is.

Alternatively you can copy and paste the script to Powershell as long as it is
runnning as an administrator
