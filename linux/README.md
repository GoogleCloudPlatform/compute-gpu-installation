# Installation for Linux

The recommended way to install NVIDIA GPU drivers and CUDA Toolkit for Google Cloud Compute Engine 
instances is through the cuda_installer tool. Look for the newest version in the
[releases](https://github.com/GoogleCloudPlatform/compute-gpu-installation/releases)
section of this repository.

The `install_gpu_driver.py` script is still available to not break existing setups,
but is considered deprecated and should not be used anymore.

The tool supports following operating systems (x86_64/amd64 architecture):

* Debian: versions 10, 11 and 12
* RHEL: versions 8 and 9
* Rocky: version 8 and 9
* Ubuntu: version 20, 22 and 24

Note: Just because an operating system is not listed as supported by this tool,  
it doesn't mean that it's impossible to install NVIDIA drivers on it. You should check and
try instructions on [NVIDIAs website](https://docs.nvidia.com/cuda/cuda-installation-guide-linux/index.html) to discover other ways of installing drivers.

## Requirements

The system on which you want to run the script needs to meet the following
requirements:

*   Python interpreter in version 3.6 or newer installed.
*   Access to Internet (the script needs to download the driver and CUDA tookit).
*   At least one GPU unit attached.

## Running the tool

The `cuda_installer.pyz` script needs to be executed with root privileges
(for example `sudo python3 cuda_installer.pyz`).

Note: During the installation the script will trigger system reboots. After a
reboot, the script needs to be started again to continue the installation process.

After successfully installation, the tool will restart your system once more to make 
sure everything is initialized properly and working system wide.

## Script output

The installation tool logs its outputs to `/opt/google/cuda-installer/` folder.
If you are facing any problems with the installation, this should be the first
place to check for any errors. When asking for support, you will be asked to
provide the log files from this folder.
