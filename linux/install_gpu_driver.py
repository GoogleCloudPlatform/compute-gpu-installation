# Copyright 2021 Google LLC
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
import argparse
import atexit
import os
import pathlib
import re
import shlex
import subprocess
import sys
from datetime import datetime
from enum import Enum, auto
from typing import Optional

DRIVER_URL = "https://us.download.nvidia.com/XFree86/Linux-x86_64/495.46/NVIDIA-Linux-x86_64-495.46.run"
K80_DRIVER_URL = "https://us.download.nvidia.com/tesla/470.103.01/NVIDIA-Linux-x86_64-470.103.01.run"

TESLA_K80_DEVICE_CODE = "10de:102d"


class System(Enum):
    CentOS = auto()
    Debian = auto()
    Fedora = auto()
    RHEL = auto()
    Rocky = auto()
    SUSE = auto()
    Ubuntu = auto()


# CentOS 7 and RHEL 7 may require Python3 to be installed before this script can be run.
# SLES and RHEL need a reboot after installation to load the driver.
SUPPORTED_SYSTEMS = {
    # CentOS 8 is dead: https://www.centos.org/centos-linux-eol/, but there's CentOS Stream 8
    System.CentOS: {"7", "8"},
    System.Debian: {"10", "11"},
    System.Fedora: set(),
    System.RHEL: {"7", "8"},
    System.Rocky: {"8"},
    System.SUSE: set(),
    System.Ubuntu: {"18", "20", "21", "22"}
}

INSTALLER_DIR = pathlib.Path('/opt/google/gpu-installer/')
DEPENDENCIES_INSTALLED_FLAG = INSTALLER_DIR / 'deps_installed.flag'
INSTALLER_DIR.mkdir(parents=True, exist_ok=True)


class Logger:
    STDOUT_LOG = INSTALLER_DIR / 'out.log'
    STDOUT_LOG_F = None
    STDERR_LOG = INSTALLER_DIR / 'err.log'
    STDERR_LOG_F = None

    @classmethod
    def close_logs(cls):
        if cls.STDOUT_LOG_F:
            cls.STDOUT_LOG_F.close()

        if cls.STDERR_LOG_F:
            cls.STDERR_LOG_F.close()

    @classmethod
    def setup_log_dir(cls):
        """
        Create the LOG_DIR path and STD(OUT|ERR)_LOG files.
        """
        cls.STDOUT_LOG.touch(exist_ok=True)
        cls.STDERR_LOG.touch(exist_ok=True)

        cls.STDOUT_LOG_F = open(cls.STDOUT_LOG, mode='a')
        cls.STDERR_LOG_F = open(cls.STDERR_LOG, mode='a')

        atexit.register(cls.close_logs)

    @classmethod
    def print_out(cls, msg: str, end=os.linesep, print_=True):
        if cls.STDOUT_LOG_F:
            cls.STDOUT_LOG_F.write(msg + end)
            cls.STDOUT_LOG_F.flush()
        if print_:
            print(msg, end=end, file=sys.stdout)

    @classmethod
    def print_err(cls, msg: str, end=os.linesep, print_=True):
        if cls.STDERR_LOG_F:
            cls.STDERR_LOG_F.write(msg + end)
            cls.STDERR_LOG_F.flush()
        if print_:
            print(msg, end=end, file=sys.stderr)


print_out = Logger.print_out
print_err = Logger.print_err


def run(command: str, check=True, input=None, cwd=None, silent=False, environment=None) -> subprocess.CompletedProcess:
    """
    Runs a provided command, streaming its output to the log files.

    :param command: A command to be executed, as a single string.
    :param check: If true, will throw exception on failure (exit code != 0)
    :param input: Input for the executed command.
    :param cwd: Directory in which to execute the command.
    :param silent: If set to True, the output of command won't be logged or printed.
    :param environment: A set of environment variable for the process to use. If None, the current env is inherited.

    :return: CompletedProcess instance - the result of the command execution.
    """
    if not silent:
        log_msg = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] " \
                  f"Executing: {command}" + os.linesep
        print_out(log_msg)
        print_err(log_msg, print_=False)

    proc = subprocess.run(shlex.split(command), check=check,
                          stderr=subprocess.PIPE, stdout=subprocess.PIPE,
                          input=input, cwd=cwd, env=environment)

    if not silent:
        print_err(proc.stderr.decode())
        print_out(proc.stdout.decode())

    return proc


def detect_gpu_device() -> Optional[str]:
    """
    Check if there is an NVIDIA GPU device attached and return its device code.
    """
    lspci = run('lspci -n')
    output = lspci.stdout.decode()
    dev_re = re.compile(r"10de:[\w\d]{4}")
    for line in output.splitlines():
        dev_code = dev_re.findall(line)
        if dev_code:
            return dev_code[0]
    else:
        return None


def check_python_version():
    """
    Makes sure that the script is run with Python 3.6 or newer.
    """
    if sys.version_info.major == 3 and sys.version_info.minor >= 6:
        return
    version = "{}.{}".format(sys.version_info.major, sys.version_info.minor)
    raise RuntimeError("Unsupported Python version {}. "
                       "Supported versions: 3.6 - 3.10".format(version))


def detect_linux_distro() -> (System, str):
    """
    Checks the /etc/os-release file to figure out what distribution of OS
    we're running.
    """
    with open('/etc/os-release') as os_release:
        lines = [line.strip() for line in os_release.readlines() if line.strip() != '']
        info = {k: v.strip("'\"") for k, v in (line.split('=', maxsplit=1) for line in lines)}

    name = info['NAME']

    if name.startswith("Debian"):
        system = System.Debian
        version = info['VERSION'].split()[0]  # 11 (rodete) -> 11
    elif name.startswith("CentOS"):
        system = System.CentOS
        version = info['VERSION_ID']  # 8
    elif name.startswith("Rocky"):
        system = System.Rocky
        version = info['VERSION_ID']  # 8.4
    elif name.startswith("Ubuntu"):
        system = System.Ubuntu
        version = info['VERSION_ID']  # 20.04
    elif name.startswith("SLES"):
        system = System.SUSE
        version = info['VERSION_ID']  # 15.3
    elif name.startswith("Red Hat"):
        system = System.RHEL
        version = info['VERSION_ID']  # 8.4
    elif name.startswith("Fedora"):
        system = System.Fedora
        version = info['VERSION_ID']  # 34
    else:
        raise RuntimeError("Unrecognized operating system.")
    return system, version


def check_linux_distro(system: System, version: str) -> bool:
    """
    Checks if given system version is supported by this script.
    Returns False if not, and prints information about the incompatibility.
    """
    if '.' in version:
        version = version.split('.')[0]

    if len(SUPPORTED_SYSTEMS[system]) == 0:
        print_out(f"The {system} distribution is not supported by this script.")
        print_out("You may check https://docs.nvidia.com/cuda/cuda-installation-guide-linux/index.html")
        print_out("to try installing the drivers manually.")
        return False
    elif version not in SUPPORTED_SYSTEMS[system]:
        print_out(f"The version {version} of {system} is not supported by this script.")
        print_out(f"Supported versions: {SUPPORTED_SYSTEMS[system]}")
        print_out("You may try installing the driver manually following instructions from: ")
        print_out("https://docs.nvidia.com/cuda/cuda-installation-guide-linux/index.html")
        return False

    return True


def check_driver_installed() -> bool:
    """
    Checks if the driver is already installed by calling the `nvidia-smi` binary.
    If it's available, that means the driver is already installed.
    """
    process = run("which nvidia-smi", check=False)
    return process.returncode == 0


def install_dependencies_centos_rhel_rocky(system: System, version: str) -> bool:
    """
    Installs required kernel-related packages and pciutils for CentOS and RHEL.
    """
    if version.startswith("8"):
        binary = "dnf"
    else:
        binary = "yum"
    run(f"{binary} clean all")
    general_update = run(f"{binary} update -y --skip-broken")
    if "kernel" in general_update.stdout.decode():
        return True  # Kernel update requires a reboot before continuing
    kernel_install = run(f"{binary} install -y kernel")
    kernel_version = run("uname -r").stdout.decode().strip()
    if "already installed" not in kernel_install.stdout.decode():
        return True  # Kernel update requires a reboot
    if system == System.Rocky:
        run("dnf config-manager --set-enabled powertools")
        run("dnf config-manager --add-repo https://developer.download.nvidia.com/compute/cuda/repos/rhel8/x86_64/cuda-rhel8.repo")
        run("dnf update -y --skip-broken")
        run("dnf install -y epel-release")
        run(f"dnf install -y kernel-devel-{kernel_version} kernel-headers-{kernel_version}")
    elif system == System.CentOS and version.startswith("8"):
        run("dnf config-manager --set-enabled powertools")
        run("dnf install -y epel-release epel-next-release")
    elif system == System.RHEL and version.startswith("8"):
        run("dnf config-manager --add-repo https://developer.download.nvidia.com/compute/cuda/repos/rhel8/x86_64/cuda-rhel8.repo")
        run("dnf update -y --skip-broken")
        run(f"dnf install -y kernel-devel-{kernel_version} kernel-headers-{kernel_version}")
        run("dnf install -y https://dl.fedoraproject.org/pub/epel/epel-release-latest-8.noarch.rpm")
    elif system in (System.RHEL, System.CentOS) and version.startswith("9"):
        run("dnf install -y https://dl.fedoraproject.org/pub/epel/next/9/Everything/x86_64/Packages/e/epel-next-release-9-1.el9.next.noarch.rpm")
        run("dnf install -y https://dl.fedoraproject.org/pub/epel/next/9/Everything/x86_64/Packages/e/epel-release-9-1.el9.next.noarch.rpm")

    run(f"{binary} install -y kernel-devel epel-release "
        f"kernel-headers pciutils gcc make dkms acpid "
        f"libglvnd-glx libglvnd-opengl libglvnd-devel pkgconfig")

    return False


def install_dependencies_sles(system: System, version: str) -> bool:
    # zypper install gcc make kernel-devel kernel-source
    # zypper install -t pattern devel_C_C++ devel_kernel
    # zypper install dkms
    return False
    # For now, there is not SLES script working.


def install_dependencies_debian_ubuntu(system: System, version: str) -> bool:
    """
    Installs kernel-related packages and pciutils for Debian and Ubuntu.
    """
    kernel_version = run("uname -r").stdout.decode().strip()
    run("apt update")
    run(f"apt install -y linux-headers-{kernel_version} "
        "software-properties-common pciutils gcc make dkms")
    return False


def reboot():
    """
    Reboots the system.
    """
    print_out("The system needs to be rebooted to complete the installation process. "
              "The process will be continued after the reboot.")
    print_out("Rebooting now.")
    run("reboot")
    sys.exit(0)



def install_dependencies(system: System, version: str):
    """
    Installs the driver dependencies to the system.
    This function may restart the system after installing some of the packages,
    in such situations the script should just be started again.
    """
    if DEPENDENCIES_INSTALLED_FLAG.is_file():
        return

    reboot_flag = False

    if system in (System.CentOS, System.RHEL, System.Rocky):
        reboot_flag = install_dependencies_centos_rhel_rocky(system, version)
    elif system in (System.Debian, System.Ubuntu):
        reboot_flag = install_dependencies_debian_ubuntu(system, version)
    elif system == System.SUSE:
        reboot_flag = install_dependencies_sles(system, version)
    else:
        raise RuntimeError("Unsupported operating system!")
    
    if reboot_flag:
        reboot()
    else:
        with DEPENDENCIES_INSTALLED_FLAG.open(mode='w') as flag:
            flag.write('1')

    if system == System.CentOS:
        # Both supported CentOS versions require reboot after this step
        reboot()


def install_driver_runfile(system: System, version: str):
    dkms = "--dkms"
    if system in (System.RHEL, System.Rocky) and version.startswith("8"):
        # There is a problem with DKMS installation on Rocky and RHEL 8
        # DKMS is disabled for those systems, you'll need to reinstall the drivers
        # with every kernel update.
        dkms = ""

    if detect_gpu_device() == TESLA_K80_DEVICE_CODE:
        run(f"curl -fSsl -O {K80_DRIVER_URL}")
        binary = "NVIDIA-Linux-x86_64-470.103.01.run"
    else:
        run(f"curl -fSsl -O {DRIVER_URL}")
        binary = "NVIDIA-Linux-x86_64-495.46.run"


    attempt = 0
    no_drm = ""

    while attempt < 3:
        install_run = run("sh {} -s {} {} --no-cc-version-check".format(binary, dkms, no_drm), check=False)

        if install_run.returncode == 0:
            return

        if "Failed to install the kernel module through DKMS" in install_run.stderr.decode():
            dkms = ""

        if "--no-drm" in install_run.stderr.decode():
            # Installer failed to install DRM KMS, so we try again with DRM disabled.
            no_drm = "--no-drm"

        attempt += 1


def post_install_steps():
    """
    Write the success message to log.
    """
    with open(INSTALLER_DIR / 'success', mode='w') as success_file:
        success_file.write("Installation was completed on {}".format(datetime.now()))


def parse_args():
    parser = argparse.ArgumentParser(description='Install or verify GPU drivers.')
    parser.add_argument("action", choices=['install', 'verify'], default="install", nargs="?")
    parser.add_argument("--force", help="Forces driver installation, even if there is no GPU detected.",
                        action='store_true')

    args = parser.parse_args()
    return args


def install(args: argparse.Namespace):
    # Prerequisites
    check_python_version()
    if os.geteuid() != 0:
        print("This script needs to be run with root privileges!")
        sys.exit(1)

    # Set up the log directory.
    Logger.setup_log_dir()

    if check_driver_installed() and not args.force:
        print('Already installed.')
        sys.exit(0)

    # Check what system we're running
    system, version = detect_linux_distro()
    # Install the drivers and CUDA Toolkit
    install_dependencies(system, version)
    if not detect_gpu_device() and not args.force:
        print("There doesn't seem to be a GPU unit connected to your system. "
              "Aborting drivers installation.")
        sys.exit(0)
    install_driver_runfile(system, version)
    post_install_steps()


def main():
    """
    Main function of the installation script.
    """
    args = parse_args()

    if args.action == 'verify':
        if not check_driver_installed():
            print("The driver is not installed.")
        else:
            print("The driver seems to be installed. Run `nvidia-smi` to check details.")
        return
    elif args.action == 'install':
        install(args)


if __name__ == '__main__':
    try:
        main()
    except Exception as err:
        print_err("Failed with exception: " + str(err))
        raise err
