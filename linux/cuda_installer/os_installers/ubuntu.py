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

from decorators import checkpoint_decorator
from logger import logger
from os_installers import LinuxInstaller, RebootRequired


class UbuntuInstaller(LinuxInstaller):

    @checkpoint_decorator("prerequisites", "System preparations already done.")
    def _install_prerequisites(self):
        """
        Installs packages required for the proper driver installation on Debian.
        """
        self.run("apt-get update")

        self.run(
            "apt-get install -y linux-image-gcp linux-headers-gcp "
            "gcc make dkms pciutils software-properties-common"
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
