import abc
import os
import pathlib
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
from contextlib import contextmanager
from datetime import datetime
from enum import Enum, auto
from typing import Optional, Union

from config import K80_DRIVER_URL, CUDA_TOOLKIT_URL, CUDA_TOOLKIT_SHA256_SUM, K80_DRIVER_SHA256_SUM, \
    K80_DEVICE_CODE, CUDA_PROFILE_FILENAME, CUDA_BIN_FOLDER, CUDA_LIB_FOLDER, NVIDIA_PERSISTANCED_INSTALLER, \
    CUDA_SAMPLES_TARGZ, CUDA_SAMPLES_SHA256_SUM
from decorators import checkpoint_decorator
from logger import logger


class RebootRequired(RuntimeError):
    pass


class System(Enum):
    CentOS = auto()
    Debian = auto()
    Fedora = auto()
    RHEL = auto()
    Rocky = auto()
    SUSE = auto()
    Ubuntu = auto()


@contextmanager
def chdir(path: Union[pathlib.Path, str]):
    prev = os.getcwd()
    try:
        os.chdir(path)
        yield
    finally:
        os.chdir(prev)


class LinuxInstaller(metaclass=abc.ABCMeta):
    def __init__(self):
        self.kernel_version = self.run('uname -r', silent=True).stdout
        self.device_code = self.detect_gpu_device()
        self._file_download_verified = set()

    @abc.abstractmethod
    def _install_prerequisites(self):
        """
        Update kernel to the newest version and install all required packages for the NVIDIA drivers to be installed.
        """
        pass

    @abc.abstractmethod
    def lock_kernel_updates(self):
        """
        Make sure that drivers aren't broken by an automatic kernel update.
        """
        pass

    @abc.abstractmethod
    def unlock_kernel_updates(self):
        """
        Allows the kernel related packages to be upgraded.
        """
        pass

    def install_driver(self):
        if self.verify_driver():
            logger.info("GPU driver already installed.")
            return

        if self.device_code == K80_DEVICE_CODE:
            installer_path = self.download_k80_driver_installer()
        else:
            installer_path = self.download_cuda_toolkit_installer()

        logger.info("Installing prerequisite packages and updating kernel...")
        try:
            self._install_prerequisites()
        except RebootRequired:
            self.reboot()

        if self.device_code == K80_DEVICE_CODE:
            logger.info("Installing GPU drivers for K80...")
            self.run(f"sh {installer_path} -s", check=True)
        else:
            logger.info("Installing GPU drivers for your device...")
            self.run(f"sh {installer_path} --silent --driver", check=True)

        if self.verify_driver():
            self.lock_kernel_updates()
            logger.info("GPU driver installation completed!")
        else:
            logger.error("Something went wrong with driver installation. The installation failed :(")

    def uninstall_driver(self):
        if not self.verify_driver():
            logger.info("GPU driver not found.")
            return
        with tempfile.TemporaryDirectory() as temp_dir:
            if self.device_code == K80_DEVICE_CODE:
                installer_path = self.download_k80_driver_installer()
            else:
                installer_path = self.download_cuda_toolkit_installer()
                logger.info("Extracting NVIDIA driver installer, to complete uninstallation...")
                self.run(f"sh {installer_path} --extract={temp_dir}", check=True)
                installer_path = pathlib.Path(f"{temp_dir}/NVIDIA-Linux-x86_64-550.54.15.run")

            logger.info("Starting uninstallation...")
            self.run(f"sh {installer_path} -s --uninstall", check=True)
            logger.info("Uninstallation completed!")
        self.unlock_kernel_updates()

    def verify_driver(self, verbose: bool = False) -> bool:
        """
        Checks if the driver is already installed by calling the `nvidia-smi` binary.
        If it's available, that means the driver is already installed.
        """
        process = self.run("which nvidia-smi", check=False, silent=True)
        if process.returncode != 0:
            if verbose:
                print("Couldn't find nvidia-smi, the driver is not installed.")
            return False
        process2 = self.run("nvidia-smi -L", check=False, silent=True)
        success = process2.returncode == 0 and "UUID" in process2.stdout
        if verbose:
            print(f"nvidia-smi -L output: {process2.stdout} {process2.stderr}")
        return success

    @checkpoint_decorator("cuda_installation", "CUDA toolkit already marked as installed.")
    def install_cuda(self):
        if self.device_code == K80_DEVICE_CODE:
            logger.info("CUDA installation is not supported for K80 GPUs.")
            return
        if not self.verify_driver():
            logger.info("CUDA installation requires GPU driver to be installed first. "
                        "Attempting to install GPU driver now.")
            self.install_driver()

        installer_path = self.download_cuda_toolkit_installer()

        logger.info("Installing CUDA toolkit...")
        self.run(f"sh {installer_path} --silent --toolkit", check=True)
        logger.info("CUDA toolkit installation completed!")
        logger.info("Executing post-installation actions...")
        self.cuda_postinstallation_actions()
        logger.info("CUDA post-installation actions completed!")
        raise RebootRequired

    def cuda_postinstallation_actions(self):
        """
        Perform required and suggested post-installation actions:
        * set environment variables
        * make persistent changes to environment variables
        * configure nvidia-persistanced to auto-start (if exists)
        """
        os.environ["PATH"] = f"{CUDA_BIN_FOLDER}:{os.environ['PATH']}"
        if "LD_LIBRARY_PATH" in os.environ:
            os.environ["LD_LIBRARY_PATH"] = f"{CUDA_LIB_FOLDER}:{os.environ['LD_LIBRARY_PATH']}"
        else:
            os.environ["LD_LIBRARY_PATH"] = CUDA_LIB_FOLDER

        with CUDA_PROFILE_FILENAME.open("w") as profile:
            profile.write("# Configuring CUDA toolkit. File created by Google CUDA installation manager.\n")
            profile.write("export PATH=" + CUDA_BIN_FOLDER + "${PATH:+:${PATH}}\n")
            profile.write("export LD_LIBRARY_PATH=" + CUDA_LIB_FOLDER + "${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}\n")

        self.configure_persistanced_service()

    def configure_persistanced_service(self):
        if not pathlib.Path('/usr/bin/nvidia-persistenced').exists():
            return

        if not pathlib.Path(NVIDIA_PERSISTANCED_INSTALLER).exists():
            return

        with tempfile.TemporaryDirectory() as temp_dir:
            shutil.copy(NVIDIA_PERSISTANCED_INSTALLER, temp_dir + "/installer.tar.bz2")
            with chdir(temp_dir):
                self.run("tar -xf installer.tar.bz2", silent=True)
                logger.info("Executing nvidia-persistenced installer...")
                self.run("sh nvidia-persistenced-init/install.sh", check=True)

    def verify_cuda(self) -> bool:
        """
        Make sure that CUDA is properly installed by compiling and executing CUDA code samples.
        """
        logger.info("Verifying CUDA installation...")
        with tempfile.TemporaryDirectory() as temp_dir:
            with chdir(temp_dir):
                logger.info(f"Using {temp_dir} to download, build and execute code samples.")
                samples_tar = self.download_file(CUDA_SAMPLES_TARGZ, CUDA_SAMPLES_SHA256_SUM)


        return True

    @staticmethod
    def run(command: str, check=True, input=None, cwd=None, silent=False, environment=None,
            retries=0) -> subprocess.CompletedProcess:
        """
        Runs a provided command, streaming its output to the log files.

        :param command: A command to be executed, as a single string.
        :param check: If true, will throw exception on failure (exit code != 0)
        :param input: Input for the executed command.
        :param cwd: Directory in which to execute the command.
        :param silent: If set to True, the output of command won't be logged or printed.
        :param environment: A set of environment variable for the process to use. If None, the current env is inherited.
        :param retries: How many times should the command be repeated if it exits with non-zero code.

        :return: CompletedProcess instance - the result of the command execution.
        """
        if not silent:
            logger.info(f"Executing: {command}")

        try_count = 0
        stdout = []
        stderr = []
        proc = None

        while try_count <= retries:
            stdout.clear()
            stderr.clear()
            proc = subprocess.Popen(shlex.split(command),
                                    stderr=subprocess.PIPE,
                                    stdout=subprocess.PIPE,
                                    stdin=subprocess.PIPE if input else None,
                                    cwd=cwd,
                                    env=environment)
            os.set_blocking(proc.stdout.fileno(), False)
            os.set_blocking(proc.stderr.fileno(), False)
            if input is not None:
                proc.stdin.write(input.encode())
                proc.stdin.close()

            def capture_comms():
                for line in proc.stdout.readlines():
                    if not silent:
                        logger.info(line.decode().strip())
                    stdout.append(line.decode().strip())
                for line in proc.stderr.readlines():
                    if not silent:
                        logger.warning(line.decode().strip())
                    stdout.append(line.decode().strip())

            while proc.poll() is None:
                # While the process is running, we capture the output
                capture_comms()
                try:
                    proc.wait(0.1)
                except subprocess.TimeoutExpired:
                    continue
            # When the process is finished, we need to capture any output left in buffers
            capture_comms()

            if proc.returncode == 0:
                break
            else:
                try_count += 1
                continue

        if check and proc.returncode:
            raise subprocess.SubprocessError("Command exited with non-zero code")

        return subprocess.CompletedProcess(command, proc.returncode, stdout="\n".join(stdout), stderr="\n".join(stderr))

    @classmethod
    def check_gpu_present(cls) -> bool:
        """
        Checks in `lspci` if there's an NVIDIA device present in the system.
        """
        lspci = cls.run("lspci")
        return 'nvidia' in lspci.stdout.lower()

    @classmethod
    def check_driver_installed(cls) -> bool:
        """
        Checks if the driver is already installed by calling the `nvidia-smi` binary.
        If it's available, that means the driver is already installed.
        """
        process = cls.run("which nvidia-smi", check=False)
        if process.returncode != 0:
            return False
        process2 = cls.run("nvidia-smi", check=False)
        return process2.returncode == 0

    @staticmethod
    def check_python_version():
        """
        Makes sure that the script is run with Python 3.6 or newer.
        """
        if sys.version_info.major == 3 and sys.version_info.minor >= 6:
            return
        version = "{}.{}".format(sys.version_info.major, sys.version_info.minor)
        raise RuntimeError("Unsupported Python version {}. "
                           "Supported versions: 3.6 - 3.12".format(version))

    @classmethod
    def reboot(cls):
        """
        Reboots the system.
        """
        logger.info("The system needs to be rebooted to complete the installation process. "
                    "The process will be continued after the reboot.")
        logger.info("Rebooting now.")
        cls.run("reboot")
        sys.exit(0)

    @classmethod
    def detect_gpu_device(cls) -> Optional[str]:
        """
        Check if there is an NVIDIA GPU device attached and return its device code.
        """
        lspci = cls.run('lspci -n', silent=True)
        output = lspci.stdout
        dev_re = re.compile(r"10de:[\w\d]{4}")
        for line in output.splitlines():
            dev_code = dev_re.findall(line)
            if dev_code:
                return dev_code[0]
        else:
            return None

    def download_cuda_toolkit_installer(self) -> pathlib.Path:
        logger.info("Downloading CUDA installation kit...")
        return self.download_file(CUDA_TOOLKIT_URL, CUDA_TOOLKIT_SHA256_SUM)

    def download_k80_driver_installer(self) -> pathlib.Path:
        logger.info("K80 GPU detected, downloading only the driver installer...")
        return self.download_file(K80_DRIVER_URL, K80_DRIVER_SHA256_SUM)

    def download_file(self, url: str, sha256sum: str) -> pathlib.Path:
        filename = urllib.parse.urlparse(url).path.split('/')[-1]
        file_path = pathlib.Path(filename)

        if file_path.exists() and url in self._file_download_verified:
            return file_path

        if not file_path.exists():
            self.run(f"curl -fSsl -O {url}")

        checksum = self.run(f"sha256sum {file_path}").stdout.strip().split()[0]
        if checksum != sha256sum:
            raise RuntimeError(f"The installer file checksum does not match. Won't continue installation."
                               f"Try deleting {file_path.absolute()} and trying again.")
        self._file_download_verified.add(url)
        return file_path


def _detect_linux_distro() -> (System, str):
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


def get_installer() -> LinuxInstaller:
    system, version = _detect_linux_distro()

    from os_installers.debian import DebianInstaller
    from os_installers.ubuntu import UbuntuInstaller
    from os_installers.rhel import RHELInstaller
    from os_installers.rocky import RockyInstaller

    if system == System.Debian:
        return DebianInstaller()
    elif system == System.Ubuntu:
        return UbuntuInstaller()
    elif system == System.RHEL:
        return RHELInstaller()
    elif system == System.Rocky:
        return RockyInstaller()
    else:
        raise NotImplementedError("Sorry, don't know how to install for this system.")
