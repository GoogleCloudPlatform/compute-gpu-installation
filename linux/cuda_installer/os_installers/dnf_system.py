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
import configparser
import shutil

from logger import logger
from os_installers import LinuxInstaller


class DNFSystemInstaller(LinuxInstaller, metaclass=abc.ABCMeta):
    """
    An abstract class providing implementation of DNF kernel locking methods.
    """

    def lock_kernel_updates(self):
        """Make sure no kernel updates are installed."""
        logger.info("Attempting to update /etc/dnf/dnf.conf to block kernel updates.")

        conf_parser = configparser.ConfigParser()
        conf_parser.read("/etc/dnf/dnf.conf")
        if "exclude" in conf_parser["main"]:
            value = conf_parser["main"]["exclude"]
            if "kernel*" in value:
                logger.info("Kernel updates are already blocked in /etc/dnf/dnf.conf")
                return
            value = [s.strip() for s in value.split(",")]
            value.append("kernel*")
        else:
            value = ["kernel*"]
        conf_parser["main"]["exclude"] = ", ".join(value)

        shutil.copyfile("/etc/dnf/dnf.conf", "/etc/dnf/dnf.conf_backup")
        try:
            with open("/etc/dnf/dnf.conf", mode="w") as dnf_conf_file:
                conf_parser.write(dnf_conf_file)
        except Exception as e:
            logger.error(
                "Failed to update /etc/dnf/dnf.conf due to {}. Restoring config file from backup.".format(
                    e
                )
            )
            shutil.copyfile("/etc/dnf/dnf.conf_backup", "/etc/dnf/dnf.conf")
            raise e
        else:
            logger.info(
                "Kernel updates blocked by `exclude` entry in /etc/dnf/dnf.conf"
            )

    def unlock_kernel_updates(self):
        """Remove `kernel*` from exclusion list in /etc/dnf/dnf.conf"""
        logger.info("Attempting to update /etc/dnf/dnf.conf to unblock kernel updates.")

        conf_parser = configparser.ConfigParser()
        conf_parser.read("/etc/dnf/dnf.conf")
        if "exclude" not in conf_parser["main"]:
            logger.info("Kernel updates are not blocked in /etc/dnf/dnf.conf")
            return

        value = conf_parser["main"]["exclude"]
        value = [s.strip() for s in value.split(",")]
        if "kernel*" not in value:
            logger.info("Kernel updates are not blocked in /etc/dnf/dnf.conf")
            return
        value.remove("kernel*")
        conf_parser["main"]["exclude"] = ", ".join(value)

        shutil.copyfile("/etc/dnf/dnf.conf", "/etc/dnf/dnf.conf_backup")

        try:
            with open("/etc/dnf/dnf.conf", mode="w") as dnf_conf_file:
                conf_parser.write(dnf_conf_file)
        except Exception as e:
            logger.error(
                "Failed to update /etc/dnf/dnf.conf due to {}. Restoring config file from backup.".format(
                    e
                )
            )
            shutil.copyfile("/etc/dnf/dnf.conf_backup", "/etc/dnf/dnf.conf")
            raise e
        else:
            logger.info("Kernel updates unblocked in /etc/dnf/dnf.conf")
