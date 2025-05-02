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
import pathlib
from typing import Optional

from config import (
    NVIDIA_DEB_REPO_KEYRING_URL,
    NVIDIA_KEYRING_SHA256_SUMS,
    NVIDIA_DEB_REPO_KEYRING_GS_URI,
    CUDA_TOOLKIT_VERSION_SHORT,
)
from decorators import checkpoint_decorator
from logger import logger
from os_installers import LinuxInstaller, RebootRequired, System


class UbuntuInstaller(LinuxInstaller):

    DKMS_MOK_PUB = pathlib.Path("/var/lib/shim-signed/mok/MOK.der")
    DKMS_MOK_KEY = pathlib.Path("/var/lib/shim-signed/mok/MOK.priv")

    @checkpoint_decorator("add_nvidia_repo", "NVIDIA repository already added.")
    def _add_nvidia_repo(self):
        """
        Add the Nvidia repository to the system. Do nothing if already present.
        """
        system, version = self._detect_linux_distro()
        assert system == System.Ubuntu
        system = "ubuntu"
        version = version.replace(".", "")
        keyring = self.download_file(
            NVIDIA_DEB_REPO_KEYRING_URL.format(system=system, version=version),
            NVIDIA_KEYRING_SHA256_SUMS[system][version],
            NVIDIA_DEB_REPO_KEYRING_GS_URI.format(system=system, version=version),
        )
        self.run(f"dpkg -i {keyring.absolute()}")
        self.run("apt update")

    @checkpoint_decorator("prerequisites", "System preparations already done.")
    def _install_prerequisites(self):
        """
        Installs packages required for the proper driver installation on Debian.
        """
        self.run("apt-get update")

        self.run(
            "apt-get install -y linux-image-gcp linux-headers-gcp "
            "gcc make dkms pciutils software-properties-common cmake"
        )
        raise RebootRequired

    def lock_kernel_updates(self):
        """
        Marks kernel related packages, so they don't get auto-updated. This would cause the driver to stop working.
        """
        logger.info("Locking kernel updates...")
        self.run(
            f"apt-mark hold "
            f"linux-image-gcp "
            f"linux-headers-gcp "
            f"linux-image-{self.kernel_version} "
            f"linux-headers-{self.kernel_version}"
        )

    def unlock_kernel_updates(self):
        """
        Allows the kernel related packages to be upgraded.
        """
        logger.info("Unlocking kernel updates...")
        self.run(
            f"apt-mark unhold "
            f"linux-image-gcp "
            f"linux-headers-gcp "
            f"linux-image-{self.kernel_version} "
            f"linux-headers-{self.kernel_version}"
        )

    def _repo_install_driver(
        self,
        secure_boot_public_key: Optional[pathlib.Path] = None,
        secure_boot_private_key: Optional[pathlib.Path] = None,
    ):
        system, version = self._detect_linux_distro()
        assert system == System.Ubuntu
        if version not in ("20.04", "22.04", "24.04"):
            raise RuntimeError(
                f"The 'repo' mode is not available for Ubuntu {version}."
            )
        if secure_boot_public_key and secure_boot_private_key:
            if secure_boot_public_key.exists() and secure_boot_private_key.exists():
                self.place_custom_dkms_signing_keys(
                    secure_boot_public_key=secure_boot_public_key,
                    secure_boot_private_key=secure_boot_private_key,
                )

        try:
            logger.info("Installing GPU driver...")
            self.run("apt-get install -yq cuda-drivers")
        finally:
            if secure_boot_public_key and secure_boot_private_key:
                self.remove_custom_dkms_signing_keys()

    def _install_cuda_repo(self):
        """
        Install CUDA Toolkit using DNF.
        """
        self._add_nvidia_repo()
        major, minor = CUDA_TOOLKIT_VERSION_SHORT.split(".")
        self.run(f"apt-get install -yq cuda-toolkit-{major}-{minor}")
