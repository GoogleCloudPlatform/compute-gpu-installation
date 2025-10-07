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
from typing import Optional

from config import VERSION_MAP
from decorators import checkpoint_decorator
from logger import logger
from os_installers import RebootRequired, System
from os_installers.dnf_system import DNFSystemInstaller


class RHELInstaller(DNFSystemInstaller):

    def __init__(self):
        if os.getuid() == 0:
            self.run("dnf install -y pciutils")
        DNFSystemInstaller.__init__(self)

    @checkpoint_decorator("prerequisites", "System preparations already done.")
    def _install_prerequisites(self):
        system, version = self._detect_linux_distro()
        version = version.split(".")[0]
        if system == System.RHEL:
            self.run(
                f"dnf install -y https://dl.fedoraproject.org/pub/epel/epel-release-latest-{version}.noarch.rpm"
            )
        else:
            self.run("dnf install -y epel-release")
        self.run(
            "dnf --refresh install -y kernel kernel-devel kernel-headers gcc gcc-c++ make bzip2 cmake dkms"
        )
        raise RebootRequired

    def _repo_install_driver(
        self,
        secure_boot_public_key: Optional[pathlib.Path] = None,
        secure_boot_private_key: Optional[pathlib.Path] = None,
        branch: str = "prod",
    ):

        self._add_nvidia_repo()

        if secure_boot_public_key and secure_boot_private_key:
            self.place_custom_dkms_signing_keys(
                secure_boot_public_key, secure_boot_private_key
            )

        try:
            logger.info("Installing GPU driver...")
            driver_version = VERSION_MAP[branch]["driver"]["version"].split(".")[0]
            self.run(f"dnf -y module enable nvidia-driver:{driver_version}-dkms")
            self.run(f"dnf -y module install nvidia-driver:{driver_version}-dkms")
        finally:
            if secure_boot_public_key and secure_boot_private_key:
                self.remove_custom_dkms_signing_keys()

    def _repo_uninstall_driver(self):
        self.run("dnf -y module remove nvidia-driver")
