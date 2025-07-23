# Copyright 2024 Google LLC
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
from enum import Enum, auto
from typing import Optional, Union

import config
from config import (
    CUDA_TOOLKIT_URL,
    CUDA_TOOLKIT_GS_URI,
    DRIVER_URL,
    DRIVER_GS_URI,
    CUDA_PROFILE_FILENAME,
    CUDA_BIN_FOLDER,
    CUDA_LIB_FOLDER,
    NVIDIA_PERSISTANCED_INSTALLER,
    CUDA_SAMPLES_URL,
    CUDA_SAMPLES_GS_URI,
    INSTALLER_DIR,
)
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
    """
    Switch the current working directory for a while. Restore the previous one on context exit.
    """
    prev = os.getcwd()
    try:
        os.chdir(path)
        yield
    finally:
        os.chdir(prev)


class LinuxInstaller(metaclass=abc.ABCMeta):
    """
    Handles the installation process for both driver and CUDA toolkit. Needs to have a couple of methods implemented
    in child classes, but contains most of the required logic.
    """

    BASHRC_PATH = pathlib.Path("/etc/bash.bashrc")

    DKMS_MOK_PUB = pathlib.Path("/var/lib/dkms/mok.pub")
    DKMS_MOK_KEY = pathlib.Path("/var/lib/dkms/mok.key")

    def __init__(self):
        self.kernel_version = self.run("uname -r", silent=True).stdout
        self.device_code = self.detect_gpu_device()
        self._file_download_verified = set()
        logger.info(f"Switching to working directory: {config.INSTALLER_DIR}")
        try:
            os.chdir(config.INSTALLER_DIR)
        except FileNotFoundError:
            logger.warning(f"Couldn't switch working directory to {config.INSTALLER_DIR}. Running in {os.getcwd()}.")

    @abc.abstractmethod
    def _add_nvidia_repo(self):
        """
        Add the Nvidia repository to the system. Do nothing if already present.
        """
        pass

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

    def _backup_dkms_mok_keys(self):
        logger.info("Moving previous keys to a backup file...")
        try:
            shutil.copy(self.DKMS_MOK_PUB, str(self.DKMS_MOK_PUB) + "_goo_back")
            shutil.copy(self.DKMS_MOK_KEY, str(self.DKMS_MOK_KEY) + "_goo_back")
        except FileNotFoundError:
            logger.info("No previous keys to backup.")

    def _restore_dkms_mok_keys(self):
        logger.info("Restoring previous DKMS keys...")
        try:
            shutil.move(str(self.DKMS_MOK_PUB) + "_goo_back", self.DKMS_MOK_PUB)
            shutil.move(str(self.DKMS_MOK_KEY) + "_goo_back", self.DKMS_MOK_KEY)
        except FileNotFoundError:
            logger.info("No previous keys to restore.")

    def place_custom_dkms_signing_keys(
        self,
        secure_boot_public_key: Optional[pathlib.Path],
        secure_boot_private_key: Optional[pathlib.Path],
    ):
        logger.info("Placing secure boot keys in the system...")
        self._backup_dkms_mok_keys()
        shutil.copy(secure_boot_public_key, self.DKMS_MOK_PUB)
        shutil.copy(secure_boot_private_key, self.DKMS_MOK_KEY)
        logger.info(
            f"Secure boot keys placed in the system ({self.DKMS_MOK_KEY} and {self.DKMS_MOK_PUB})!"
        )

    def remove_custom_dkms_signing_keys(self):
        logger.info("Removing secure boot keys from the system...")
        self.run(f"shred -uz {self.DKMS_MOK_PUB}")
        self.run(f"shred -uz {self.DKMS_MOK_KEY}")
        self._restore_dkms_mok_keys()

    def install_driver(
        self,
        secure_boot_public_key: Optional[pathlib.Path] = None,
        secure_boot_private_key: Optional[pathlib.Path] = None,
        ignore_no_gpu: bool = False,
        installation_mode: str = "repo",
        branch: str = "prod",
    ):
        """
        Downloads the installation package and installs the driver. It also handles installation of
        drive prerequisites and will trigger a reboot on the first run when those prerequisites are installed.

        On the second run, it will proceed to download proper installer and install the driver. When it's done, `nvidia-smi`
        should be available in the system and the drivers are installed.

        It also triggers kernel packages lock in the system, so the driver is not broken by auto-updates.
        """
        if self.verify_driver():
            logger.info("GPU driver already installed.")
            return

        self.assert_correct_mode(installation_mode, branch)

        logger.info("Installing prerequisite packages and updating kernel...")
        try:
            self._install_prerequisites()
        except RebootRequired:
            self.reboot()

        if installation_mode == "binary":
            self._binary_install_driver(
                secure_boot_public_key, secure_boot_private_key, ignore_no_gpu, branch
            )
        else:
            self._add_nvidia_repo()
            self._repo_install_driver(secure_boot_public_key, secure_boot_private_key, branch)

    def _binary_install_driver(
        self,
        secure_boot_public_key: Optional[pathlib.Path] = None,
        secure_boot_private_key: Optional[pathlib.Path] = None,
        ignore_no_gpu: bool = False,
        branch: str = "prod",
    ):
        installer_path = self.download_driver_installer(branch)

        logger.info("Installing GPU drivers for your device...")
        if (
            secure_boot_public_key
            and secure_boot_private_key
            and secure_boot_private_key.is_file()
            and secure_boot_public_key.is_file()
        ):
            logger.info(
                f"Using secure boot keys from {secure_boot_public_key.absolute()} and {secure_boot_private_key.absolute()}"
            )
            self.run(
                f"sh {installer_path} -s --module-signing-secret-key={secure_boot_private_key.absolute()} --module-signing-public-key={secure_boot_public_key.absolute()}",
                check=True,
            )
        else:
            self.run(f"sh {installer_path} -s", check=True)

        if self.verify_driver() or ignore_no_gpu:
            self.lock_kernel_updates()
            logger.info("GPU driver installation completed!")
        else:
            logger.error(
                "Something went wrong with driver installation. The installation failed :("
            )

    @abc.abstractmethod
    def _repo_install_driver(
        self,
        secure_boot_public_key: Optional[pathlib.Path] = None,
        secure_boot_private_key: Optional[pathlib.Path] = None,
        branch: str = "prod",
    ):
        raise NotImplementedError

    @abc.abstractmethod
    def _repo_uninstall_driver(self):
        raise NotImplementedError

    def uninstall_driver(self):
        """
        Uses the Nvidia installers to execute driver uninstallation. It will also unlock the kernel updates in the
        system.
        """
        if not self.verify_driver():
            logger.info("GPU driver not found.")
            return

        mode, branch = self.get_installation_mode()

        if mode == 'repo':
            self._repo_uninstall_driver()
            return

        installer_path = self.download_driver_installer(branch)

        logger.info("Starting uninstallation...")
        self.run(f"sh {installer_path} -s --uninstall", check=True)
        logger.info("Uninstallation completed!")
        self.unlock_kernel_updates()

    def verify_driver(self, verbose: bool = False) -> bool:
        """
        Checks if the driver is already installed by calling the `nvidia-smi` binary.
        If it's available and doesn't produce errors, that means the driver is already installed.
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

    @checkpoint_decorator(
        "cuda_installation", "CUDA toolkit already marked as installed."
    )
    def _install_cuda(
        self, ignore_no_gpu: bool = False, installation_mode: str = "repo", branch: str = "prod",
    ):
        """
        This is the method to install the CUDA Toolkit. It will install the toolkit and execute post-installation
        configuration in the operating system, to make it available for all users.
        """
        self.assert_correct_mode(installation_mode, branch)

        if not (self.verify_driver() or ignore_no_gpu):
            logger.info(
                "CUDA installation requires GPU driver to be installed first. "
                "Attempting to install GPU driver now."
            )
            self.install_driver(installation_mode=installation_mode, branch=branch)

        if installation_mode == "binary":
            self._install_cuda_binary(branch)
        else:
            self._add_nvidia_repo()
            self._install_cuda_repo(branch)

        logger.info("Executing post-installation actions...")
        self.cuda_postinstallation_actions(branch)
        logger.info("CUDA post-installation actions completed!")
        raise RebootRequired

    def _install_cuda_binary(self, branch: str):
        logger.info("Downloading CUDA Toolkit package...")
        installer_path = self.download_cuda_toolkit_installer(branch)

        logger.info("Installing CUDA toolkit...")
        self.run(f"sh {installer_path} --silent --toolkit", check=True)
        logger.info("CUDA toolkit installation completed!")

    @abc.abstractmethod
    def _install_cuda_repo(self, branch: str):
        pass

    def install_cuda(
        self, ignore_no_gpu: bool = False, installation_mode: str = "repo", branch: str = "prod"
    ):
        try:
            self._install_cuda(ignore_no_gpu, installation_mode, branch)
        except RebootRequired:
            self.reboot()

    def cuda_postinstallation_actions(self, branch: str):
        """
        Perform required and suggested post-installation actions:
        * set environment variables
        * make persistent changes to environment variables
        * configure nvidia-persistanced to auto-start (if exists)

        More info: https://docs.nvidia.com/cuda/cuda-installation-guide-linux/index.html#post-installation-actions
        """
        cuda_major = config.VERSION_MAP[branch]["cuda"]["major"]
        cuda_minor = config.VERSION_MAP[branch]["cuda"]["minor"]
        cuda_patch = config.VERSION_MAP[branch]["cuda"]["patch"]

        cuda_bin_folder = CUDA_BIN_FOLDER.format(CUDA_MAJOR=cuda_major, CUDA_MINOR=cuda_minor)
        cuda_lib_folder = CUDA_LIB_FOLDER.format(CUDA_MAJOR=cuda_major, CUDA_MINOR=cuda_minor)

        os.environ["PATH"] = f"{cuda_bin_folder}:{os.environ['PATH']}"
        if "LD_LIBRARY_PATH" in os.environ:
            os.environ["LD_LIBRARY_PATH"] = (
                f"{cuda_lib_folder}:{os.environ['LD_LIBRARY_PATH']}"
            )
        else:
            os.environ["LD_LIBRARY_PATH"] = cuda_lib_folder

        with CUDA_PROFILE_FILENAME.open("w") as profile:
            logger.info(f"Creating {CUDA_PROFILE_FILENAME} file...")
            profile.write(
                "# Configuring CUDA toolkit. File created by Google CUDA installation manager.\n"
            )
            profile.write("export PATH=" + cuda_bin_folder + "${PATH:+:${PATH}}\n")
            profile.write(
                "export LD_LIBRARY_PATH="
                + cuda_lib_folder
                + "${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}\n"
            )

        with open(self.BASHRC_PATH, mode="r+") as global_bashrc:
            logger.info(
                f"Updating {self.BASHRC_PATH} to source {CUDA_PROFILE_FILENAME}..."
            )
            content = global_bashrc.read()
            global_bashrc.seek(0)
            global_bashrc.write("\n# Enabling NVIDIA CUDA Toolkit\n")
            global_bashrc.write(f"source {CUDA_PROFILE_FILENAME}\n")
            global_bashrc.write(content)

        self.configure_persistanced_service()

    def configure_persistanced_service(self):
        """
        Configures the nvidia-persistenced daemon to auto-start. It creates a service to be controlled using
        `systemctl`.
        """
        if not pathlib.Path("/usr/bin/nvidia-persistenced").exists():
            return

        if not pathlib.Path(NVIDIA_PERSISTANCED_INSTALLER).exists():
            return

        with tempfile.TemporaryDirectory() as temp_dir:
            shutil.copy(NVIDIA_PERSISTANCED_INSTALLER, temp_dir + "/installer.tar.bz2")
            with chdir(temp_dir):
                self.run("tar -xf installer.tar.bz2", silent=True)
                logger.info("Executing nvidia-persistenced installer...")
                self.run(
                    "sh nvidia-persistenced-init/install.sh",
                    check=self.check_gpu_present(),
                )

    def verify_cuda(self) -> bool:
        """
        Make sure that CUDA Toolkit is properly installed by compiling and executing CUDA code samples.
        """
        branch = self.get_installation_mode()[1]
        cuda_samples_version = config.VERSION_MAP[branch]["cuda"]["samples"]
        cuda_samples_url = CUDA_SAMPLES_URL.format(MULTIREGION=config.MULTIREGION, CUDA_SAMPLES_VERSION=cuda_samples_version)
        cuda_samples_gs_uri = CUDA_SAMPLES_GS_URI.format(MULTIREGION=config.MULTIREGION, CUDA_SAMPLES_VERSION=cuda_samples_version)
        cuda_samples_hash = config.VERSION_MAP[branch]["cuda"]["samples_hash"]

        logger.info("Verifying CUDA installation...")
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir = pathlib.Path(temp_dir)
            with chdir(temp_dir):
                logger.info(
                    f"Using {temp_dir} to download, build and execute code samples."
                )
                samples_tar = self.download_file(
                    cuda_samples_url, cuda_samples_hash, cuda_samples_gs_uri
                )
                self.run(f"tar -xf {samples_tar.name}")
                with chdir(temp_dir / f"cuda-samples-{cuda_samples_version}"):
                    self.run("cmake .", check=False)
                with chdir(
                    temp_dir
                    / f"cuda-samples-{cuda_samples_version}/Samples/1_Utilities/deviceQuery"
                ):
                    self.run("make", check=True)
                    dev_query = self.run("./deviceQuery", check=True)
                    if "Result = PASS" not in dev_query.stdout:
                        logger.error(
                            "Cuda Toolkit verification failed. DeviceQuery sample failed."
                        )
                        return False
                with chdir(
                    temp_dir
                    / f"cuda-samples-{cuda_samples_version}/Samples/1_Utilities/bandwidthTest"
                ):
                    self.run("make", check=True)
                    bandwidth = self.run("./bandwidthTest", check=True)
                    if "Result = PASS" not in bandwidth.stdout:
                        logger.error(
                            "Cuda Toolkit verification failed. BandwidthTest sample failed."
                        )
                        return False
        logger.info("Cuda Toolkit verification completed!")
        return True

    @staticmethod
    def run(
        command: str,
        check=True,
        input=None,
        cwd=None,
        silent=False,
        environment=None,
        retries=0,
    ) -> subprocess.CompletedProcess:
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
            proc = subprocess.Popen(
                shlex.split(command),
                stderr=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stdin=subprocess.PIPE if input else None,
                cwd=cwd,
                env=environment,
            )
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
                    stderr.append(line.decode().strip())

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
            logger.error("Command exited with non-zero code.")
            logger.error("Stdout:\n" + "\n".join(stdout))
            logger.error("Stderr:\n" + "\n".join(stderr))
            logger.error("--------------------------------")
            if check:
                raise subprocess.SubprocessError("Command exited with non-zero code")

        return subprocess.CompletedProcess(
            command, proc.returncode, stdout="\n".join(stdout), stderr="\n".join(stderr)
        )

    @classmethod
    def check_gpu_present(cls) -> bool:
        """
        Checks in `lspci` if there's an NVIDIA device present in the system.
        """
        lspci = cls.run("lspci")
        return "nvidia" in lspci.stdout.lower()

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
        raise RuntimeError(
            "Unsupported Python version {}. "
            "Supported versions: 3.6 - 3.12".format(version)
        )

    @classmethod
    def reboot(cls):
        """
        Reboots the system.
        """
        logger.info(
            "The system needs to be rebooted to complete the installation process. "
            "The process will be continued after the reboot."
        )
        logger.info("Rebooting now.")
        cls.run("reboot now")
        sys.exit(0)

    @classmethod
    def detect_gpu_device(cls) -> Optional[str]:
        """
        Check if there is an NVIDIA GPU device attached and return its device code.
        """
        lspci = cls.run("lspci -n", silent=True)
        output = lspci.stdout
        dev_re = re.compile(r"10de:[\w\d]{4}")
        for line in output.splitlines():
            dev_code = dev_re.findall(line)
            if dev_code:
                return dev_code[0]
        else:
            return None

    def download_cuda_toolkit_installer(self, branch: str) -> pathlib.Path:

        cuda_major = config.VERSION_MAP[branch]["cuda"]["major"]
        cuda_minor = config.VERSION_MAP[branch]["cuda"]["minor"]
        cuda_patch = config.VERSION_MAP[branch]["cuda"]["patch"]
        driver_version = config.VERSION_MAP[branch]["cuda"]["driver"]
        logger.info(f"Downloading CUDA installation kit for {branch} branch ({cuda_major}.{cuda_minor}.{cuda_patch})...")

        return self.download_file(
            CUDA_TOOLKIT_URL.format(MULTIREGION=config.MULTIREGION, CUDA_MAJOR=cuda_major, CUDA_MINOR=cuda_minor,
                                    CUDA_PATCH=cuda_patch, CUDA_DRIVER_VERSION=driver_version),
            config.VERSION_MAP[branch]["cuda"]["hash"],
            CUDA_TOOLKIT_GS_URI.format(MULTIREGION=config.MULTIREGION, CUDA_MAJOR=cuda_major, CUDA_MINOR=cuda_minor,
                                       CUDA_PATCH=cuda_patch, CUDA_DRIVER_VERSION=driver_version)
        )

    def download_driver_installer(self, branch: str) -> pathlib.Path:
        driver_version = config.VERSION_MAP[branch]["driver"]["version"]
        logger.info(f"Downloading driver for {branch} branch ({driver_version})...")

        return self.download_file(
            DRIVER_URL.format(MULTIREGION=config.MULTIREGION, DRIVER_VERSION=driver_version),
            config.VERSION_MAP[branch]["driver"]["hash"],
            DRIVER_GS_URI.format(MULTIREGION=config.MULTIREGION, DRIVER_VERSION=driver_version)
        )

    def download_file(
        self, url: str, sha256sum: str, gs_uri: str = None
    ) -> pathlib.Path:
        """
        Uses `curl` to download a file pointed by url. It will also execute `sha256sum` on the downloaded file
        to verify if it's matching with the expected hash.

        If provided uses `gs_uri` together with `gsutil` to download the file.

        It also keeps track of files already downloaded and checked, so that it doesn't waste time with repeating the
        download or check.
        """
        filename = urllib.parse.urlparse(url).path.split("/")[-1]
        file_path = pathlib.Path(filename)

        if file_path.exists() and url in self._file_download_verified:
            return file_path

        gsutil_available = (
            self.run("which gsutil", check=False, silent=True).returncode == 0
        )

        if not file_path.exists():
            if gsutil_available and gs_uri:
                self.run(f"gsutil cp {gs_uri} .", silent=True, check=True)
            else:
                self.run(f"curl -fSsL -O {url}", check=True)

        checksum = self.run(f"sha256sum {file_path}").stdout.strip().split()[0]
        if checksum != sha256sum:
            raise RuntimeError(
                f"The installer file checksum does not match. Won't continue installation."
                f"Try deleting {file_path.absolute()} and trying again."
            )
        self._file_download_verified.add(url)
        return file_path

    @staticmethod
    def _detect_linux_distro() -> (System, str):
        """
        Checks the /etc/os-release file to figure out what distribution of OS
        we're running.
        """
        with open("/etc/os-release") as os_release:
            lines = [
                line.strip() for line in os_release.readlines() if line.strip() != ""
            ]
            info = {
                k: v.strip("'\"")
                for k, v in (line.split("=", maxsplit=1) for line in lines)
            }

        name = info["NAME"]

        if name.startswith("Debian"):
            system = System.Debian
            version = info["VERSION"].split()[0]  # 11 (rodete) -> 11
        elif name.startswith("CentOS"):
            system = System.CentOS
            version = info["VERSION_ID"]  # 8
        elif name.startswith("Rocky"):
            system = System.Rocky
            version = info["VERSION_ID"]  # 8.4
        elif name.startswith("Ubuntu"):
            system = System.Ubuntu
            version = info["VERSION_ID"]  # 20.04
        elif name.startswith("SLES"):
            system = System.SUSE
            version = info["VERSION_ID"]  # 15.3
        elif name.startswith("Red Hat"):
            system = System.RHEL
            version = info["VERSION_ID"]  # 8.4
        elif name.startswith("Fedora"):
            system = System.Fedora
            version = info["VERSION_ID"]  # 34
        else:
            raise RuntimeError("Unrecognized operating system.")
        return system, version

    @classmethod
    def get_installer(cls) -> "LinuxInstaller":
        """
        Retrieve an Installer instance appropriate for the hosting operating system.
        """
        system, version = cls._detect_linux_distro()

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
            raise NotImplementedError(
                "Sorry, don't know how to install for this system."
            )

    @staticmethod
    def assert_correct_mode(mode: str, branch: str):
        """
        Check if the previously used installation method is the same as the current one. If it's not, abort the process
        and display a message about the problem.
        """
        mode_file = INSTALLER_DIR / "mode"
        mode_text = f"{mode} {branch}"

        assert mode in ("binary", "repo")
        assert branch in ("prod", "nfb", "lts")

        if mode == "repo" and branch == "lts":
            raise RuntimeError("The LTS driver branch is supported only in binary installation mode. "
                               "Please use --installation-mode=binary and --installation-branch=lts to install "
                               "LTS driver branch.")

        if not mode_file.exists():
            # First run, no mode file exists, we make it and set the mode
            mode_file.write_text(mode_text)
            return

        # There was a previous mode, need to make sure that we're in the same mode.
        prev_mode = mode_file.read_text().strip()
        if prev_mode == mode_text:
            return

        logger.error(
            f"Previous installations using '{prev_mode}' detected, that's different than requested '{mode_text}' mode. "
            f"You can't switch installation modes, try again in '{prev_mode}' mode or with a clean system."
        )
        assert f"You have to use {prev_mode} in this system."

    @staticmethod
    def get_installation_mode() -> (str, str):
        """
        Checks what method was used to install the driver and CUDA Toolkit in this system.

        Returns a tuple of mode and branch. For example ('repo', 'prod').
        """
        mode_file = INSTALLER_DIR / "mode"

        if not mode_file.exists():
            raise RuntimeError("No installation data found.")

        return mode_file.read_text().split(" ")
