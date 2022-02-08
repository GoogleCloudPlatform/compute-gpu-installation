# Installation for Linux.

In the `install_gpu_driver.py` you can find a script that automates installation
of newer GPU drivers for NVIDIA GPU drivers available for Google Compute Engine
instances.

The script support the following operating systems:

* CentOS: versions 7
* CentOS Stream: version 8
* Debian: versions 10 and 11
* RHEL: versions 7 and 8
* Rocky: version 8
* Ubuntu: version 18, 20 and 21

Note: Just because an operating system is not supported by this script, doesn't
mean that it's impossible to install NVIDIA drivers on it. You should check and
try instructions on
[NVIDIAs website](https://docs.nvidia.com/cuda/cuda-installation-guide-linux/index.html)
to discover other ways of installing drivers.

## Requirements

The system on which you want to run the script needs to meet the following
requirements:

*   Python interpreter in version 3.6 installed (by default available in all
    supported OSes except CentOS 7 and RHEL 7).
*   Access to Internet (the script needs to download the driver).
*   (optional) At least one GPU unit attached.

## Running the script

The `install_gpu_driver.py` script needs to be executed with root privileges
(for example `sudo python3 install_gpu_driver.py`).

Note: On some systems the script might trigger system reboot, it
needs to be restarted after the reboot is done.

After the installation, you should restart your system to make sure everything
is initialized properly and working.

## Script output

The installation script logs its outputs to `/opt/google/gpu-installer/` folder.
If you are facing any problems with the installation, this should be the first
place to check for any errors. When asking for support, you will be asked to
provide the log files from this folder.
