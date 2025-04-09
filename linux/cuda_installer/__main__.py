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
import pathlib
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
    subparsers = parser.add_subparsers(
        dest="command", help="Install GPU driver or CUDA Toolkit."
    )

    # Subparser for install_driver
    install_driver_parser = subparsers.add_parser(
        "install_driver", help="Install GPU driver."
    )
    install_driver_parser.add_argument(
        "--secure-boot-pub-key",
        help="Path to the secure boot public key file.",
        required=False,
        type=pathlib.Path
    )
    install_driver_parser.add_argument(
        "--secure-boot-priv-key",
        help="Path to the secure boot private key file.",
        required=False,
        type=pathlib.Path
    )
    install_driver_parser.add_argument(
        "--ignore-no-gpu",
        action="store_true",
        help="Ignore the absence of a GPU.",
        required=False
    )

    # Subparser for verify_driver
    verify_driver_parser = subparsers.add_parser(
        "verify_driver", help="Verify GPU driver installation."
    )

    # Subparser for uninstall_driver
    uninstall_driver_parser = subparsers.add_parser(
        "uninstall_driver", help="Uninstall GPU driver."
    )

    # Subparser for install_cuda
    install_cuda_parser = subparsers.add_parser(
        "install_cuda", help="Install CUDA Toolkit."
    )
    install_cuda_parser.add_argument(
        "--ignore-no-gpu",
        action="store_true",
        help="Ignore the absence of a GPU.",
        required=False
    )

    # Subparser for verify_cuda
    verify_cuda_parser = subparsers.add_parser(
        "verify_cuda", help="Verify CUDA Toolkit installation."
    )

    return parser.parse_args()

def assert_root():
    if os.geteuid() != 0:
        print("This script needs to be run with root privileges!")
        sys.exit(1)

if __name__ == "__main__":
    args = parse_args()
    secure_boot_public_key = args.secure_boot_pub_key.absolute() if 'secure_boot_pub_key' in args else None
    secure_boot_private_key = args.secure_boot_priv_key.absolute() if 'secure_boot_priv_key' in args else None
    logger.info(f"Switching to working directory: {config.INSTALLER_DIR}")
    os.chdir(config.INSTALLER_DIR)
    installer = get_installer()

    if args.command == "install_driver":
        assert_root()
        installer.install_driver(
            secure_boot_public_key=secure_boot_public_key,
            secure_boot_private_key=secure_boot_private_key,
            ignore_no_gpu=args.ignore_no_gpu,
        )
    elif args.command == "verify_driver":
        if installer.verify_driver(verbose=True):
            sys.exit(0)
        else:
            sys.exit(1)
    elif args.command == "uninstall_driver":
        assert_root()
        installer.uninstall_driver()
    elif args.command == "install_cuda":
        assert_root()
        installer.install_cuda(ignore_no_gpu=args.ignore_no_gpu,)
    elif args.command == "verify_cuda":
        if installer.verify_cuda():
            sys.exit(0)
        else:
            sys.exit(1)
