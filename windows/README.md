## Installer Script for NVIDIA GPU Drivers

This script installs the latest supported NVIDIA GPU drivers for Google Cloud
Windows VM on Compute Engine.

This script supports both the G2, A2, and N1 series. On N1 and A2 VMs, it also
installs the CUDA toolkit.

## Usage Instructions

To use this script you must run it as an Administrator:

Start-Process powershell -Verb RunAs -ArgumentList "-file
path_to\install_gpu_driver.ps1"

You should replace path_to with the directory where the file is.

Alternatively you can copy and paste the script to Powershell as long as it is
runnning as an administrator
