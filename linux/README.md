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
*   Access to Google Cloud Storage (the script needs to download the driver and CUDA tookit).

## Running the tool

The `cuda_installer.pyz` script needs to be executed with root privileges
(for example `sudo python3 cuda_installer.pyz`).

### Installing driver

To install NVIDIA driver use `sudo python3 cuda_installer.pyz install_driver`. The script
will update your system, lock kernel updates and install the driver. **The process will most 
likely be interrupted by a reboot. In that case, call the same command again**, until the
script indicates that the installation is completed. You can verify that with
`python3 cuda_installer.pyz verify_driver` or by calling `nvidia-smi`.

If you want to install the driver on a system without GPU (to prepare a Disk Image for example)
you will have to add `--ignore-no-gpu` flag to that command above.

If you want the installed driver to be signed (needed for Secure Boot compatibility), use the
`--secure-boot-pub-key` and `--secure-boot-priv-key` to indicate the location of your public 
and private keys.

### Installing CUDA Toolkit

To install CUDA Toolkit use `sudo python3 cuda_installer.pyz install_cuda`. The script will
install the NVIDIA drivers, if they are not yet installed, and then install the CUDA Toolkit.
**The process will most likely be interrupted by a reboot. In that case, call the same command 
again**, until the script indicates that the installation is completed.

After successfully installation, the tool will restart your system once more to make 
sure everything is initialized properly and working system-wide.

To verify successful toolkit installation, you can run `python3 cuda_installer.pyz verify_cuda`.
The script will then download a package of CUDA samples, then compile and run two of them
to verify that everything is configured properly.

## Script output

The installation tool logs its outputs to `/opt/google/cuda-installer/` folder.
If you are facing any problems with the installation, this should be the first
place to check for any errors. When asking for support, you will be asked to
provide the log files from this folder.

## Automating the installation process

You can automate the installation of the driver and/or CUDA Toolkit by using a 
[startup script](https://cloud.google.com/compute/docs/instances/startup-scripts/linux)
for your Compute Engine instance. See [startup_script.sh](startup_script.sh) for an example
startup script. Please note that the installation process will still require a reboot or two
of your machine. You can assume that the process is finished by checking if 
`/opt/google/cuda-installer/cuda_installation` file exists in the filesystem.