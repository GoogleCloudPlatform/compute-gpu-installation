#!/usr/bin/env python3
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

import argparse
import os
import sys

import config
from logger import logger

# Need to import all the subpackages here, or the program fails for Python 3.6
from os_installers import get_installer, debian, ubuntu, rhel, rocky


# Mentioning the packages from import above, so automatic import cleanups don't remove them
del debian
del ubuntu
del rhel
del rocky


def parse_args():
    parser = argparse.ArgumentParser(
        description="Manage GPU drivers and CUDA toolkit installation."
    )
    parser.add_argument(
        "command",
        choices=[
            "install_driver",
            "install_cuda",
            "verify_driver",
            "verify_cuda",
            "uninstall_driver",
        ],
        help="Install GPU driver or CUDA Toolkit.",
    )

    return parser.parse_args()


if __name__ == "__main__":
    if os.geteuid() != 0:
        print("This script needs to be run with root privileges!")
        sys.exit(1)
    args = parse_args()
    logger.info(f"Switching to working directory: {config.INSTALLER_DIR}")
    os.chdir(config.INSTALLER_DIR)
    installer = get_installer()

    if args.command == "install_driver":
        installer.install_driver()
    elif args.command == "verify_driver":
        if installer.verify_driver(verbose=True):
            sys.exit(0)
        else:
            sys.exit(1)
    elif args.command == "uninstall_driver":
        installer.uninstall_driver()
    elif args.command == "install_cuda":
        installer.install_cuda()
    elif args.command == "verify_cuda":
        if installer.verify_cuda():
            sys.exit(0)
        else:
            sys.exit(1)
