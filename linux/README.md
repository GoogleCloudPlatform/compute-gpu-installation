# Installation for Linux

The recommended way to install NVIDIA GPU drivers and CUDA Toolkit for Google Cloud Compute Engine 
instances is through the cuda_installer tool. Look for the newest version in the
[releases](https://github.com/GoogleCloudPlatform/compute-gpu-installation/releases)
section of this repository.

The `install_gpu_driver.py` script is still available to not break existing setups,
but is considered deprecated and should not be used anymore.

## OS Support

The tool supports the following operating systems (x86_64/amd64 architecture):

* Debian: version 12
* RHEL: versions 8 and 9
* Rocky: version 8 and 9
* Ubuntu: version 22 and 24

Some installation methods and branches are unavailable on some of the operating systems.

|              | Binary | Repository |
|--------------|--------|------------|
| Debian 12    | ✓      | Only NFB   |
| RHEL 8       | ✓      | No LTS     |
| RHEL 9       | ✓      | No LTS     |
| Rocky 8      | ✓      | No LTS     |
| Rocky 9      | ✓      | No LTS     |
| Ubuntu 22.04 | ✓      | No LTS     |
| Ubuntu 24.04 | ✓      | No LTS     |

✓ - Production, New Feature and LTS branch supported
NFB = New feature branch

Note: Just because an operating system is not listed as supported by this tool,  
it doesn't mean that it's impossible to install NVIDIA drivers on it. You should check and
try instructions on [NVIDIAs website](https://docs.nvidia.com/cuda/cuda-installation-guide-linux/index.html) to discover other ways of installing drivers.

## Requirements

The system on which you want to run the script needs to meet the following
requirements:

*   Python interpreter in version 3.8 or newer installed.
*   Access to Google Cloud Storage (the script needs to download the driver and CUDA toolkit).

## Driver branches

NVIDIA releases their GPU drivers in [three branches](https://docs.nvidia.com/datacenter/tesla/drivers/#driver-lifecycle). To quote from their documentation:

* **Long-Term Support** - branch releases will receive bug updates and critical security updates, 
  on a reasonable effort basis, through minor releases during the 3 years that they are supported.
* **Production** - branch is qualified for use in production for enterprise/data center GPUs. Bug 
  fixes and security updates are provided for up to 1 year.
* **New feature (NFB)** - branch is targeted towards early adopters who want to evaluate new features 
  (for example, new CUDA APIs). New driver branch is released approximately every quarter.

The `cuda_installer.pyz` tool allows you to pick the driver branch you want to install. Only 
production and new feature branches are currently supported. To specify the branch you want to
install use the `--installation-branch <prod|nfb|lts>` flag. If the flag is omitted, production
branch is used by default.

## Driver versions

This table shows the versions of drivers installed by different versions of the tool. The repository
installation method will always match the major version of the drivers and CUDA Toolkit installed by
the binary version.

| release | new feature branch       | prod branch               | long term support branch   | RTX (Virtual Workstation) |
|---------|--------------------------|---------------------------|----------------------------|---------------------------|
| v1.7.0  | 575.57.08 (cuda: 12.9.1) | 580.82.07 (cuda: 13.0.1)  | 580.82.07 (cuda: 13.0.1)   | 580.82.07 (cuda: 13.0.1)  |
| v1.6.0  | 575.57.08 (cuda: 12.9.1) | 570.172.08 (cuda: 12.8.1) | 535.261.03 (cuda: 12.2.2)  | n/a                       |
| v1.5.0  | 575.57.08 (cuda: 12.9.1) | 570.158.01 (cuda: 12.8.1) | n/a                        | n/a                       |


## Running the tool

The `cuda_installer.pyz` script needs to be executed with root privileges when installing 
drivers or CUDA Toolkit (for example `sudo python3 cuda_installer.pyz`).

### Installing the driver

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

The installation tool logs its outputs to `/opt/google/cuda-installer/` folder when run as root.
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

## Preparing OS Images with Pre-installed Drivers/CUDA

The `cuda_installer` tool includes a command to build new Google Compute Engine OS images 
with NVIDIA drivers and (optionally) the CUDA Toolkit pre-installed. This is useful for 
creating standardized environments or speeding up VM startup times.

The command uses a temporary VM within your specified Google Cloud project and zone to 
perform the installation steps on a fresh disk, which is then saved as a new custom image.

### Basic Usage

To build an image, you need to provide your Google Cloud project ID, a zone for the 
temporary build VM, and a name for the final image.

By default, this uses the `ubuntu-24` base image and installs both the driver and CUDA toolkit 
using the 'repo' installation mode. You can customize the base OS using the `--base-image` 
argument (e.g., `--base-image debian-12`, `--base-image rhel-9`).

```bash
python3 cuda_installer.pyz build_image --project $PROJECT --vm-zone $ZONE --base-image ubuntu-24 name_of_the_image
```

### Secure Boot Support

If you intend to use the resulting image on VMs with Secure Boot enabled, the NVIDIA kernel modules 
need to be signed during the image build process.

**Option 1: Provide Existing Keys**

If you already have a public/private key pair (MOK - Machine Owner Key) you want to use 
for signing, provide the paths to the keys:

```bash
python3 cuda_installer.pyz build_image \
    --project $PROJECT --vm-zone $ZONE \
    --secure-boot-pub-key /path/to/public.der \
    --secure-boot-priv-key /path/to/private.key \
    --base-image ubuntu-24 name_of_the_image
```


**Option 2: Generate and Save Keys**

If you don't provide keys, the tool will generate a new pair specifically for this image 
build. By default, these keys are destroyed after the build. If you want to save these 
generated keys, use the `--save-keys-path` argument:

```bash
python3 cuda_installer.pyz build_image \
    --project $PROJECT --vm-zone $ZONE \
    --save-keys-path /path/to/save/keys \
    --base-image ubuntu-24 name_of_the_image
```
This will save `mok.der` and `mok.key` to the specified directory.

### Other Options

*   `--base-image <OS>`: Specify the base OS image. Supported options include `debian-12`, `rhel-8`, `rhel-9`, 
        `rocky-8`, `rocky-9`, `ubuntu-22`, `ubuntu-24`. Defaults to `ubuntu-24`.
*   `--driver-only`: Use this flag if you only want to install the NVIDIA driver and skip the CUDA Toolkit installation.
*   `--installation-mode <MODE>`: Choose between `repo` (default) or `binary` installation methods.
*   `--installation-branch <BRANCH>`: Choose between `prod` (production branch) and `nfb` (new feature branch). Default: `prod`.
*   `--vm-type <TYPE>`: Specify the machine type for the temporary build VM (default: `e2-standard-8`).
*   `--vm-disk-type <TYPE>`: Set the disk type for the build VM (e.g., `ssd`, `balanced`, `standard`). Default: `balanced`.
*   `--vm-disk-size <SIZE_GB>`: Set the disk size in GB for the build VM (default: 100).
*   `--family <FAMILY_NAME>`: Assign the created image to an image family.
*   `--image-region <REGION>`: Specify the region or multi-region (e.g., `us`, `eu`) to store the final image. 
        Defaults to the multi-region containing `--vm-zone`.
*   `--skip-cleanup`: Prevents the deletion of the temporary build VM and its disk after image creation (useful for debugging).
*   `--interactive`: The image preparation process will be paused before shutting down the build VM, and an SSH session 
        will be opened. This way you can customize your future image, install additional packages, etc.
*   `--custom-script <PATH_TO_CUSTOM_SCRIPT.sh>`: Provide a path to bash script that will be executed on the build VM 
        before it's turned off. This way you can install additional packages and execute additional configuration steps.
*   `--network`: The name of the VPC network to which the build VM is connected to. (default: `default`)
*   `--subnet`: The name of the subnet to be used for the build VM. If not provided, the name of the network is used. 
        Required for custom mode VPC networks.
