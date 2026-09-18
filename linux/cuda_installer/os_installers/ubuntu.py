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
import sys
from typing import Optional, Tuple

from config import (
    NVIDIA_DEB_REPO_KEYRING_URL,
    NVIDIA_KEYRING_SHA256_SUMS,
    NVIDIA_DEB_REPO_KEYRING_GS_URI,
    VERSION_MAP,
)
from decorators import checkpoint_decorator
from logger import logger
from os_installers import LinuxInstaller, RebootRequired, System


class UbuntuInstaller(LinuxInstaller):

    DKMS_MOK_PUB = pathlib.Path("/var/lib/shim-signed/mok/MOK.der")
    DKMS_MOK_KEY = pathlib.Path("/var/lib/shim-signed/mok/MOK.priv")

    def _get_kernel_meta_packages(self) -> Tuple[str, str]:
        """
        Derives the Ubuntu kernel image and headers meta-packages from the running
        kernel flavor (e.g. '6.8.0-1065-gcp' -> 'linux-image-gcp', 'linux-headers-gcp').
        """
        flavor = (
            self.kernel_version.rsplit("-", 1)[-1]
            if "-" in self.kernel_version
            else "gcp"
        )
        return f"linux-image-{flavor}", f"linux-headers-{flavor}"

    def _get_driver_package(self) -> str:
        """
        Returns the appropriate Ubuntu repository driver package for the detected OS version.
        """
        system, version = self._detect_linux_distro()
        assert system == System.Ubuntu
        if version not in ("22.04", "24.04", "26.04"):
            raise RuntimeError(
                f"The 'repo' mode is not available for Ubuntu {version}."
            )
        if version in ("24.04", "26.04"):
            return "nvidia-driver-open"
        return "nvidia-open"

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
        self.run("apt-get update")

    @checkpoint_decorator("prerequisites", "System preparations already done.")
    def _install_prerequisites(self):
        """
        Installs packages required for the proper driver installation on Ubuntu.
        """
        self.run("apt-get update")

        image_meta_pkg, headers_meta_pkg = self._get_kernel_meta_packages()
        pkgs = [
            image_meta_pkg,
            headers_meta_pkg,
            'libc-dev',
            'gcc',
            'make',
            'dkms',
            'pciutils',
            'software-properties-common',
            'cmake',
            'git',
            'g++',
        ]

        self.run(
            f"apt-get install -y {' '.join(pkgs)}"
        )
        raise RebootRequired

    def lock_kernel_updates(self):
        """
        Marks kernel related packages, so they don't get auto-updated. This would cause the driver to stop working.
        """
        logger.info("Locking kernel updates...")
        image_meta_pkg, headers_meta_pkg = self._get_kernel_meta_packages()
        self.run(
            f"apt-mark hold "
            f"{image_meta_pkg} "
            f"{headers_meta_pkg} "
            f"linux-image-{self.kernel_version} "
            f"linux-headers-{self.kernel_version}"
        )
        self._install_kernel_postinst_header_check()
        logger.warning(
            f"WARNING: Kernel meta-packages ({image_meta_pkg}, {headers_meta_pkg}) have been placed on hold (apt-mark hold) "
            f"because binary installation mode is active. If you update the kernel manually or via third-party patch "
            f"management tools (such as BigFix, OS Config, or Ansible) that install explicit linux-image-<version> packages, "
            f"you MUST also install the matching linux-headers-<version> package before rebooting so DKMS can build the "
            f"NVIDIA driver module for the new kernel."
        )

    def unlock_kernel_updates(self):
        """
        Allows the kernel related packages to be upgraded.
        """
        logger.info("Unlocking kernel updates...")
        image_meta_pkg, headers_meta_pkg = self._get_kernel_meta_packages()
        self.run(
            f"apt-mark unhold "
            f"{image_meta_pkg} "
            f"{headers_meta_pkg} "
            f"linux-image-{self.kernel_version} "
            f"linux-headers-{self.kernel_version}"
        )
        self._remove_kernel_postinst_header_check()

    def _repo_install_driver(
        self,
        secure_boot_public_key: Optional[pathlib.Path] = None,
        secure_boot_private_key: Optional[pathlib.Path] = None,
        branch: str = "prod",
    ):
        driver_pkg = self._get_driver_package()
        if secure_boot_public_key and secure_boot_private_key:
            if secure_boot_public_key.exists() and secure_boot_private_key.exists():
                self.place_custom_dkms_signing_keys(
                    secure_boot_public_key=secure_boot_public_key,
                    secure_boot_private_key=secure_boot_private_key,
                )

        try:
            logger.info("Installing GPU driver...")
            self.run(f"apt-get install -yq {driver_pkg}")
            self.run(f"apt-mark hold {driver_pkg}")
        finally:
            if secure_boot_public_key and secure_boot_private_key:
                self.remove_custom_dkms_signing_keys()

    def _repo_uninstall_driver(self):
        driver_pkg = self._get_driver_package()
        self.run(f"apt-mark unhold {driver_pkg}", check=False)
        self.run(f"apt-get remove -y {driver_pkg}")

    def _install_cuda_repo(self, branch: str):
        """
        Install CUDA Toolkit using APT.
        """
        self._add_nvidia_repo()
        system, version = self._detect_linux_distro()
        if int(version.split('.')[0]) >= 26:
            self.run(f"apt-get install -yq nvidia-cuda-toolkit")
        else:
            self.run(f"apt-get install -yq cuda-toolkit")

    def verify_cuda(self) -> bool:
        system, version = self._detect_linux_distro()
        version_number = int(version.rsplit('.')[0])
        return super().verify_cuda()

    def _install_cuda_binary(self, branch: str):
        system, version = self._detect_linux_distro()
        assert system == System.Ubuntu
        version_number = int(version.rsplit('.')[0])
        major = int(VERSION_MAP[branch]["cuda"]["major"])
        minor = int(VERSION_MAP[branch]["cuda"]["minor"])
        # if version_number < 26 and major <= 13 and minor < 3:
        #     logger.error(f"Sorry, the selected version of CUDA Toolkit is incompatible with Ubuntu {version_number}.")
        #     sys.exit(1)
        super()._install_cuda_binary(branch)
