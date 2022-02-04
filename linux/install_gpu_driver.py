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
import glob
import os
import pathlib
import re
import shlex
import subprocess
import sys
import tempfile
from datetime import datetime
from enum import Enum, auto

# K80 wspierane przez 470.103.01


DRIVER_DOWNLOAD_LINK = "https://us.download.nvidia.com/XFree86/Linux-x86_64/495.46/NVIDIA-Linux-x86_64-495.46.run"
BASE_URL = "https://us.download.nvidia.com/tesla"
VERSION = "495.46"
K80_VERSION = "470.103.01"
FINAL_URL = f"{BASE_URL}/{VERSION}/NVIDIA-Linux-x86_64-{VERSION}.run"
K80_FINAL_URL = f"{BASE_URL}/{K80_VERSION}/NVIDIA-Linux-x86_64-{K80_VERSION}.run"


class System(Enum):
    CentOS = auto()
    Debian = auto()
    Fedora = auto()
    RHEL = auto()
    Rocky = auto()
    SUSE = auto()
    Ubuntu = auto()


# CentOS 7 and RHEL 7 require Python3 to be installed before this script can be run.
# SLES and RHEL need a reboot after installation to load the driver.
SUPPORTED_SYSTEMS = {
    System.CentOS: {"7", "8"},
    System.Debian: {"10", "11"},
    System.Fedora: set(),
    System.RHEL: {"7", "8"},
    System.Rocky: set(),
    System.SUSE: {"15"},
    System.Ubuntu: {"18", "20"}
}


class Logger:
    LOG_DIR = '/opt/google/gpu-installer/'
    STDOUT_LOG = LOG_DIR + 'out.log'
    STDOUT_LOG_F = None
    STDERR_LOG = LOG_DIR + 'err.log'
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
        pathlib.Path(cls.LOG_DIR).mkdir(parents=True, exist_ok=True)
        pathlib.Path(cls.STDOUT_LOG).touch(exist_ok=True)
        pathlib.Path(cls.STDERR_LOG).touch(exist_ok=True)

        cls.STDOUT_LOG_F = open(cls.STDOUT_LOG, mode='a')
        cls.STDERR_LOG_F = open(cls.STDERR_LOG, mode='a')

        atexit.register(cls.close_logs)

    @classmethod
    def print_out(cls, msg: str, end=os.linesep, print_=True):
        if cls.STDOUT_LOG_F:
            cls.STDOUT_LOG_F.write(msg + end)
        if print_:
            print(msg, end=end, file=sys.stdout)

    @classmethod
    def print_err(cls, msg: str, end=os.linesep, print_=True):
        if cls.STDERR_LOG_F:
            cls.STDERR_LOG_F.write(msg + end)
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


def detect_gpu_device() -> bool:
    """
    Check if there is a GPU device attached.
    """
    lspci = run('lspci')
    return "controller: NVIDIA Corporation" in lspci.stdout.decode()


def check_python_version():
    """
    Makes sure that the script is run with Python 3.6 or newer.
    """
    if sys.version_info.major == 3 and sys.version_info.minor > 6:
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


def install_dependencies_centos_rhel(system: System, version: str):
    """
    Installs required kernel-related packages and pciutils for CentOS and RHEL.
    """
    kernel_version = run("uname -r").stdout.decode().strip()

    if version.startswith("8"):
        binary = "dnf"
    else:
        binary = "yum"
    run(f"{binary} clean all")
    kernel_install = run(f"{binary} install -y kernel")
    if "already installed" not in kernel_install.stdout.decode():
        run("reboot")  # Restart the system after installing the kernel modules
        sys.exit(0)
    run(f"{binary} install -y kernel-devel-{kernel_version} "
        f"kernel-headers-{kernel_version} pciutils gcc make")
    return


def install_dependencies_debian_ubuntu(system: System, version: str):
    """
    Installs kernel-related packages and pciutils for Debian and Ubuntu.
    """
    kernel_version = run("uname -r").stdout.decode().strip()
    run(f"apt install -y linux-headers-{kernel_version} "
        "software-properties-common pciutils gcc make")
    return


def install_dependencies(system: System, version: str):
    """
    Installs the driver dependencies to the system.
    This function may restart the system after installing some of the packages,
    in such situations the script should just be started again.
    """
    if system in (System.CentOS, System.RHEL):
        install_dependencies_centos_rhel(system, version)
        return
    elif system in (System.Debian, System.Ubuntu):
        install_dependencies_debian_ubuntu(system, version)
        return
    elif system == System.SUSE:
        return
    else:
        raise RuntimeError("Unsupported operating system!")


def install_driver(system: System, version: str):
    """
    Installs the GPU driver. The installation instructions are taken from
    https://developer.nvidia.com/cuda-downloads
    """
    if system == System.CentOS:
        install_driver_centos(version)
    elif system == System.RHEL:
        install_driver_rhel(version)
    elif system == System.SUSE:
        install_driver_suse()
    elif system == System.Ubuntu:
        install_driver_ubuntu(version)
    elif system == System.Debian:
        install_driver_debian()
    else:
        raise RuntimeError("Unsupported operating system.")


def install_driver_centos(version: str):
    if version.startswith("7"):
        run("yum install -y yum-utils epel-release")
        run("yum-config-manager --add-repo "
            "https://developer.download.nvidia.com/compute/cuda/repos/rhel7/x86_64/cuda-rhel7.repo")
        run("yum clean all")
        run("yum install -y nvidia-driver-latest-dkms cuda")
        run("yum install -y cuda-drivers")
        return
    else:
        run("dnf -y install epel-release")
        run("dnf config-manager --add-repo https://developer.download.nvidia.com/compute/cuda/repos/rhel8/x86_64/cuda-rhel8.repo")
        run("dnf clean all")
        run("dnf -y module install nvidia-driver:latest-dkms")
        run("dnf -y install cuda")
        return


def install_driver_debian():
    run(f"apt-key adv --fetch-keys "
        f"https://developer.download.nvidia.com/compute/cuda/repos/debian10/x86_64/7fa2af80.pub")
    run(f'add-apt-repository "deb '
        f'https://developer.download.nvidia.com/compute/cuda/repos/debian10/x86_64/ /"')
    run(f'add-apt-repository contrib')
    run("apt update")
    env = os.environ.copy()
    env['DEBIAN_FRONTEND'] = 'noninteractive'
    run("apt install -y cuda", environment=env)


def install_driver_ubuntu(version):
    version_nodot = "".join(version.split("."))
    run(f"curl -O https://developer.download.nvidia.com/compute/cuda/repos/ubuntu{version_nodot}/x86_64/cuda-ubuntu{version_nodot}.pin")
    run(f"mv cuda-ubuntu{version_nodot}.pin /etc/apt/preferences.d/cuda-repository-pin-600")
    run(f"apt-key adv --fetch-keys https://developer.download.nvidia.com/compute/cuda/repos/ubuntu{version_nodot}/x86_64/7fa2af80.pub")
    run(f'add-apt-repository "deb https://developer.download.nvidia.com/compute/cuda/repos/ubuntu{version_nodot}/x86_64/ /"')
    run("apt update")
    run("apt install -y cuda")


def install_driver_suse():
    run("zypper addrepo https://developer.download.nvidia.com/compute/cuda/repos/sles15/x86_64/cuda-sles15.repo")
    run("zypper --gpg-auto-import-keys refresh")
    run("zypper install -y cuda")


def install_driver_rhel(version):
    if version.startswith("7"):
        run("yum install -y yum-utils epel-release")
        run("yum-config-manager --add-repo https://developer.download.nvidia.com/compute/cuda/repos/rhel7/x86_64/cuda-rhel7.repo")
        run("yum clean all")
        run("yum -y install nvidia-driver-latest-dkms cuda")
        run("yum -y install cuda-drivers")
    else:
        run("dnf -y install https://dl.fedoraproject.org/pub/epel/epel-release-latest-8.noarch.rpm")
        run("dnf config-manager --add-repo https://developer.download.nvidia.com/compute/cuda/repos/rhel8/x86_64/cuda-rhel8.repo")
        run("dnf clean all")
        run("dnf -y module install nvidia-driver:latest-dkms")
        run("dnf -y install cuda")


def post_install_steps():
    """
    Execute post-installation steps as described on
    https://docs.nvidia.com/cuda/cuda-installation-guide-linux/index.html#post-installation-actions
    """
    # Update PATH and LD_LIBRARY_PATH env variables for everyone
    with open('/etc/profile.d/cuda.sh', mode='w') as env_conf:
        env_conf.write("# CUDA Toolkit settings" + os.linesep)
        env_conf.write("export PATH=/usr/local/cuda-11/bin:$PATH" + os.linesep)
        env_conf.write("export LD_LIBRARY_PATH=/usr/local/cuda-11/lib64:$LD_LIBRARY_PATH" + os.linesep)
    # Let's mark that the installation was successful.
    with open(Logger.LOG_DIR + 'success', mode='w') as success_file:
        success_file.write("Installation was completed on {}".format(datetime.now()))


def run_test(test_path: pathlib.PosixPath, test_bin: str) -> bool:
    print(f"Building {test_bin} test...")
    make = run("make", cwd=test_path, silent=True)
    if ">>> Waiving build. Minimum GCC version required is" in make.stdout.decode():
        # RHEL 7 and CentOS 7 have GCC in version 4.8, which is too low for some tests
        print(f"Skipping {test_bin} test, as it requires newer version of GCC: ")
        print(make.stdout.decode().splitlines()[0])
        return True
    print(f"Running the {test_bin} test...")
    dev_query = run(str((test_path / test_bin).absolute()), cwd=test_path, silent=True)
    out = dev_query.stdout.decode()
    print(out)
    print(dev_query.stderr.decode())
    if "Result = PASS" in out:
        print(f"{test_bin} test passed.")
        return True
    else:
        print(f"{test_bin} test failed!")
        return False


def verify_installation():
    """
    Compile sample programs provided by NVIDIA to check if the installation was successful.
    """
    try:
        sample_install_script = glob.glob("/usr/local/cuda-11/bin/cuda-install-samples*.sh")[0]
        cuda_version = re.findall(r"cuda-install-samples-(\d+\.\d+)\.sh", sample_install_script)[0]
    except IndexError:
        raise RuntimeError("Couldn't find the cuda-install-samples script to validate installation!")

    with tempfile.TemporaryDirectory() as tmp_dir:
        print(f"Setting up CUDA samples in {tmp_dir}...")
        run(f"{sample_install_script} {tmp_dir}", silent=True)
        sample_dir = pathlib.PosixPath(tmp_dir, f"NVIDIA_CUDA-{cuda_version}_Samples")

        dev_query_path = sample_dir / "1_Utilities" / "deviceQuery"
        bandwidth_test_path = sample_dir / "1_Utilities" / "bandwidthTest"
        passed = True
        passed &= run_test(dev_query_path, "deviceQuery")
        passed &= run_test(bandwidth_test_path, "bandwidthTest")

    sys.exit(0 if passed else 1)


def parse_args():
    parser = argparse.ArgumentParser(description='Install or verify GPU drivers.')
    parser.add_argument("action", choices=['install', 'verify'], default="install", nargs="?")
    parser.add_argument("--force", help="Forces driver installation, even if there is no GPU detected.",
                        action='store_true')

    args = parser.parse_args()
    return args


def main():
    """
    Main function of the installation script.
    """
    args = parse_args()

    if args.action == 'verify':
        verify_installation()
    elif args.action == 'install':
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
        install_driver(system, version)
        post_install_steps()


if __name__ == '__main__':
    try:
        main()
    except Exception as err:
        print_err("Failed with exception: " + str(err))
        raise err
