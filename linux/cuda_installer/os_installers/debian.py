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
import os
import pathlib
import re
from typing import Optional

from config import (
    NVIDIA_DEB_REPO_KEYRING_URL,
    NVIDIA_DEB_REPO_KEYRING_GS_URI,
    NVIDIA_KEYRING_SHA256_SUMS,
    VERSION_MAP,
)
from decorators import checkpoint_decorator
from logger import logger
from os_installers import LinuxInstaller, RebootRequired, System


class DebianInstaller(LinuxInstaller):
    KERNEL_IMAGE_PACKAGE = "linux-image-{version}"
    KERNEL_VERSION_FORMAT = "{major}.{minor}.{patch}-{micro}-cloud-amd64"
    KERNEL_HEADERS_PACKAGE = "linux-headers-{version}"
    KERNEL_PACKAGE_REGEX = r"linux-image-{major}.{minor}.([\d]+)-([\d]+)-cloud-amd64"

    def __init__(self):
        super().__init__()
        # To make sure we don't get stuck waiting for user input.
        os.environ["DEBIAN_FRONTEND"] = "noninteractive"

    @checkpoint_decorator("add_nvidia_repo", "NVIDIA repository already added.")
    def _add_nvidia_repo(self):
        """
        Add the Nvidia repository to the system. Do nothing if already present.
        """
        system, version = self._detect_linux_distro()
        assert system == System.Debian
        system = "debian"
        keyring = self.download_file(
            NVIDIA_DEB_REPO_KEYRING_URL.format(system=system, version=version),
            NVIDIA_KEYRING_SHA256_SUMS[system][version],
            NVIDIA_DEB_REPO_KEYRING_GS_URI.format(system=system, version=version),
        )
        self.run(f"dpkg -i {keyring.absolute()}")
        self.run("apt-get update")

    @checkpoint_decorator("prerequisites", "System preparations already done.")
    def _install_prerequisites(self):
        """
        Installs packages required for the proper driver installation on Debian.
        """
        self.run("apt-get update")

        major, minor, *_ = self.kernel_version.split(".")
        kernel_package_regex = re.compile(
            self.KERNEL_PACKAGE_REGEX.format(major=major, minor=minor)
        )

        # Find the newest version of kernel to update to, but staying with the same major version
        packages = self.run("apt-cache search linux-image").stdout
        patch, micro = max(kernel_package_regex.findall(packages))

        wanted_kernel_version = self.KERNEL_VERSION_FORMAT.format(
            major=major, minor=minor, patch=patch, micro=micro
        )
        wanted_kernel_package = self.KERNEL_IMAGE_PACKAGE.format(
            version=wanted_kernel_version
        )
        wanted_kernel_headers = self.KERNEL_HEADERS_PACKAGE.format(
            version=wanted_kernel_version
        )

        self.run(
            f"apt-get install -y make gcc {wanted_kernel_package} {wanted_kernel_headers} "
            f"software-properties-common pciutils gcc make dkms cmake"
        )
        raise RebootRequired

    def lock_kernel_updates(self):
        """
        Marks kernel related packages, so they don't get auto-updated. This would cause the driver to stop working.
        """
        logger.info("Locking kernel updates...")
        self.run(
            f"apt-mark hold "
            f"linux-image-{self.kernel_version} "
            f"linux-headers-{self.kernel_version} "
            f"linux-image-cloud-amd64 "
            f"linux-headers-cloud-amd64"
        )

    def unlock_kernel_updates(self):
        """
        Allows the kernel related packages to be upgraded.
        """
        logger.info("Unlocking kernel updates...")
        self.run(
            f"apt-mark unhold "
            f"linux-image-{self.kernel_version} "
            f"linux-headers-{self.kernel_version} "
            f"linux-image-cloud-amd64 "
            f"linux-headers-cloud-amd64"
        )

    def _repo_uninstall_driver(self):
        self.run("apt-get remove -y cuda-drivers")

    def _repo_install_driver(
        self,
        secure_boot_public_key: Optional[pathlib.Path] = None,
        secure_boot_private_key: Optional[pathlib.Path] = None,
        branch: str = "prod"
    ):
        system, version = self._detect_linux_distro()
        assert system == System.Debian

        if version == "11":
            raise RuntimeError("Debian 11 is no longer supported.")

        if branch == "prod":
            raise RuntimeError("The 'prod' branch is only available for binary installations on Debian. Please use "
                               "--installation-mode=binary to install using binary installer or "
                               "--installation-branch=nfb to install new feature branch driver.")

        if secure_boot_public_key and secure_boot_private_key:
            if secure_boot_public_key.exists() and secure_boot_private_key.exists():
                self.place_custom_dkms_signing_keys(
                    secure_boot_public_key=secure_boot_public_key,
                    secure_boot_private_key=secure_boot_private_key,
                )

        try:
            driver_version = VERSION_MAP[branch]["driver"]["version"].split(".")[0]
            logger.info("Installing GPU driver...")
            self.run(f"apt-get install -yq cuda-drivers-{driver_version}")
            self.run(f"apt-mark hold cuda-drivers-{driver_version}")
        finally:
            if secure_boot_public_key and secure_boot_private_key:
                self.remove_custom_dkms_signing_keys()

    def _install_cuda_repo(self, branch: str):
        """
        Install CUDA Toolkit using DNF.
        """
        system, version = self._detect_linux_distro()

        if version == "lts":
            raise RuntimeError("The 'lts' branch is not available in repo installation mode.")

        self._add_nvidia_repo()
        major = VERSION_MAP[branch]["cuda"]["major"]
        minor = VERSION_MAP[branch]["cuda"]["minor"]
        logger.info(f"Installing CUDA Toolkit version ({major}.{minor}))")
        self.run(f"apt-get install -yq cuda-toolkit-{major}-{minor}")
