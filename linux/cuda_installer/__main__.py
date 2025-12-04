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
from urllib.request import Request, urlopen
from urllib.error import URLError

import image_builder
from config import VERSION

# Need to import all the subpackages here, or the program fails for Python 3.6
from os_installers import LinuxInstaller, debian, ubuntu, rhel, rocky

# Mentioning the packages from import above, so automatic import cleanups don't remove them
del debian
del ubuntu
del rhel
del rocky


def parse_args():
    parser = argparse.ArgumentParser(
        description="Manage GPU drivers and CUDA toolkit installation.",
        prog="Cuda Installer",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    subparsers = parser.add_subparsers(
        dest="command", help="Install GPU driver or CUDA Toolkit."
    )

    # Subparser for install_driver -------------------------------------------------------------------------------------
    install_driver_parser = subparsers.add_parser(
        "install_driver", help="Install GPU driver."
    )
    install_driver_parser.add_argument(
        "--secure-boot-pub-key",
        help="Path to the secure boot public key file.",
        required=False,
        type=pathlib.Path,
    )
    install_driver_parser.add_argument(
        "--secure-boot-priv-key",
        help="Path to the secure boot private key file.",
        required=False,
        type=pathlib.Path,
    )
    install_driver_parser.add_argument(
        "--ignore-no-gpu",
        action="store_true",
        help="Ignore the absence of a GPU.",
        required=False,
    )

    install_driver_parser.add_argument(
        "--installation-mode",
        help="Pick the installation mode. Either 'repo' or 'binary'. Repo mode will add NVIDIA repository to your sources list and install packages from repository. Binary will download binary installer files and use them to install. Default mode is 'repo'.",
        required=False,
        default="repo",
        choices=["repo", "binary"],
    )

    install_driver_parser.add_argument(
        "--installation-branch",
        help="Select driver branch to install from. Available branches: nfb, prod and lts. Those will install drivers in versions 575, 570 and 535 respectively. Default: prod",
        required=False,
        default="prod",
        choices=["prod", "nfb", "lts"],
    )

    # Subparser for build_image ----------------------------------------------------------------------------------------
    image_builder = subparsers.add_parser(
        "build_image",
        help="Prepares a new disk image with drivers and/or CUDA Toolkit installed.",
    )

    image_builder.add_argument(
        "--installation-mode",
        help="Pick the installation mode. Either 'repo' or 'binary'. Repo mode will add NVIDIA repository to your sources list and install packages from repository. Binary will download binary installer files and use them to install. Default mode is 'repo'.",
        required=False,
        default="repo",
        choices=["repo", "binary"],
    )

    image_builder.add_argument(
        "--installation-branch",
        help="Select driver  branch to install from. Available branches: nfb, prod and lts. Those will install drivers in versions 575, 570 and 535 respectively with compatible CUDA Toolkit versions (12.9, 12.8 and 12.2). Default: prod.",
        required=False,
        default="prod",
        choices=["prod", "nfb", "lts"],
    )

    image_builder.add_argument(
        "--save-keys-path",
        help="Saves the keys used to sign the installed drivers in the given location. If not provided, the keys are destroyed at the end of the process.",
        required=False,
        type=pathlib.Path,
    )

    image_builder.add_argument(
        "--driver-only",
        help="Limits the process to only install GPU driver, without installing CUDA Toolkit.",
        action="store_true",
    )

    image_builder.add_argument(
        "--project",
        help="Project in which the image building process will happen and in which the Image will be created.",
        required=True,
        type=str,
    )

    image_builder.add_argument(
        "--vm-zone",
        help="Zone in which the image building process will happen (a small VM needs to be created to prepare the image)",
        required=True,
        type=str,
    )

    image_builder.add_argument(
        "--vm-type",
        help="Machine type that will be used to prepare the disk image. Default: e2-standard-8",
        required=False,
        default="e2-standard-8",
    )

    image_builder.add_argument(
        "--vm-disk-type",
        help="Type of the disk used for the image preparation. Available types: ssd, balanced and standard. Default: balanced",
        required=False,
        default="balanced",
    )

    image_builder.add_argument(
        "--vm-disk-size",
        help="Size of the disk used for the image preparation in Gb. Default: 100",
        required=False,
        default=100,
        type=int,
    )

    image_builder.add_argument(
        "--family",
        help="Save the created image as part of a given image family.",
        required=False,
        action="store",
    )

    image_builder.add_argument(
        "--image-region",
        help="Location to save the disk image in. This can be a region or multi-region (us, eu or asia) name. If not provided, it will be the multiregion inferred from the --vm-zone option.",
        required=False,
        type=str,
    )

    image_builder.add_argument(
        "--secure-boot-pub-key",
        help="Path to the secure boot public key file.",
        required=False,
        type=pathlib.Path,
    )

    image_builder.add_argument(
        "--secure-boot-priv-key",
        help="Path to the secure boot private key file.",
        required=False,
        type=pathlib.Path,
    )

    image_builder.add_argument(
        "--base-image",
        help="Base image to build upon. Available options: debian-12, rhel-8, rhel-9, rocky-8, rocky-9, ubuntu-22 and ubuntu-24. Default: ubuntu-24",
        default="ubuntu-24",
    )

    image_builder.add_argument(
        "--skip-cleanup",
        help="After the image is created, the build VM and it's disk will not be deleted.",
        action="store_true",
    )

    image_builder.add_argument(
        "--interactive",
        help="The image preparation process will be paused before shutting down the build VM, and SSH session will be opened. This way you can customize your future image, install additional packages etc.",
        action="store_true",
    )

    image_builder.add_argument(
        "--custom-script",
        help="Provide a bash script that will be executed on the build VM before it's turned off. This way you can install additional packages and execute additional configuration steps.",
        action="store",
        type=pathlib.Path,
    )

    image_builder.add_argument(
        "--network",
        help="Provide a VPC network identifier to be used for the build VM. Default network is used if not specified.",
        required=False,
        default="default",
    )

    image_builder.add_argument(
        "--subnet",
        help="Provide a VPC subnet identifier to be used for the build VM. If not provided, the name of the network will be used. Required for custom mode VPC networks.",
        required=False,
    )

    image_builder.add_argument(
        "image_name", help="Name of the image to be created.", type=str
    )

    # Subparser for verify_driver --------------------------------------------------------------------------------------
    verify_driver_parser = subparsers.add_parser(
        "verify_driver", help="Verify GPU driver installation."
    )

    # Subparser for uninstall_driver -----------------------------------------------------------------------------------
    uninstall_driver_parser = subparsers.add_parser(
        "uninstall_driver", help="Uninstall GPU driver."
    )

    # Subparser for install_cuda ---------------------------------------------------------------------------------------
    install_cuda_parser = subparsers.add_parser(
        "install_cuda", help="Install CUDA Toolkit."
    )
    install_cuda_parser.add_argument(
        "--ignore-no-gpu",
        action="store_true",
        help="Ignore the absence of a GPU.",
        required=False,
    )
    install_cuda_parser.add_argument(
        "--installation-mode",
        help="Pick the installation mode. Either 'repo' or 'binary'. Repo mode will add NVIDIA repository to your sources list and install packages from repository. Binary will download binary installer files and use them to install. Default mode is 'repo'. You have to use the same mode you used when installing the driver.",
        required=False,
        default="repo",
        choices=["repo", "binary"],
    )

    install_cuda_parser.add_argument(
        "--installation-branch",
        help="Select driver branch to install from. Available branches: nfb, prod and lts. Those will install drivers in versions 575, 570 and 535 respectively with compatible CUDA Toolkit versions (12.9, 12.8 and 12.2). This value must match the value used for driver installation, if driver was installed separately. Default: prod.",
        required=False,
        default="prod",
        choices=["prod", "nfb", "lts"],
    )

    # Subparser for verify_cuda ----------------------------------------------------------------------------------------
    verify_cuda_parser = subparsers.add_parser(
        "verify_cuda", help="Verify CUDA Toolkit installation."
    )

    return parser.parse_args()


def assert_root():
    if os.geteuid() != 0:
        print("This script needs to be run with root privileges!")
        sys.exit(1)


def detect_virtual_workstation():
    request = Request(
        "http://metadata.google.internal/computeMetadata/v1/instance/",
        headers={"Metadata-Flavor": "Google"},
    )
    try:
        response = urlopen(request).read().decode()
    except URLError:
        return False
    return "nvidia-grid-license" in response


if __name__ == "__main__":
    args = parse_args()
    secure_boot_public_key = (
        args.secure_boot_pub_key.absolute()
        if getattr(args, "secure_boot_pub_key", False)
        else None
    )
    secure_boot_private_key = (
        args.secure_boot_priv_key.absolute()
        if getattr(args, "secure_boot_priv_key", False)
        else None
    )

    rtx_vw_enabled = detect_virtual_workstation()

    if args.command == "install_driver":
        assert_root()
        installer = LinuxInstaller.get_installer()
        installer.install_driver(
            secure_boot_public_key=secure_boot_public_key,
            secure_boot_private_key=secure_boot_private_key,
            ignore_no_gpu=args.ignore_no_gpu,
            installation_mode=args.installation_mode,
            branch=args.installation_branch,
            rtx_vw_enabled=rtx_vw_enabled,
        )
    elif args.command == "verify_driver":
        installer = LinuxInstaller.get_installer()
        if installer.verify_driver(verbose=True):
            sys.exit(0)
        else:
            sys.exit(1)
    elif args.command == "uninstall_driver":
        assert_root()
        installer = LinuxInstaller.get_installer()
        installer.uninstall_driver()
    elif args.command == "install_cuda":
        assert_root()
        installer = LinuxInstaller.get_installer()
        installer.install_cuda(
            ignore_no_gpu=args.ignore_no_gpu,
            installation_mode=args.installation_mode,
            branch=args.installation_branch,
            rtx_vw_enabled=rtx_vw_enabled,
        )
    elif args.command == "verify_cuda":
        installer = LinuxInstaller.get_installer()
        if installer.verify_cuda():
            sys.exit(0)
        else:
            sys.exit(1)
    elif args.command == "build_image":
        image_builder.Builder(args).build()
