#!/usr/bin/env python3
import argparse
import sys
from logger import logger

# Need to import all the subpackages here, or the program fails for Python 3.6
from os_installers import get_installer, debian, ubuntu, rhel, rocky
import os
import config


def parse_args():
    parser = argparse.ArgumentParser(description='Manage GPU drivers and CUDA toolkit installation.')
    parser.add_argument("command", choices=[
        'install_driver', 'install_cuda', 'verify_driver', 'verify_cuda', 'uninstall_driver',
        'kernel_update'], help="Install GPU driver from NVIDIA package repository.")
    # subparsers = parser.add_subparsers(help="Select action you want to take.", required=True)

    # install_driver_parser = subparsers.add_parser('install_driver', help='Install GPU driver.')
    # install_cuda_parser = subparsers.add_parser('install_cuda', help='Install CUDA toolkit.')
    # verify_driver_parser = subparsers.add_parser('verify_driver', help='Verify GPU driver installation.')
    # verify_cuda_parser = subparsers.add_parser('verify_cuda', help='Verify CUDA toolkit installation.')
    # uninstall_driver_parser = subparsers.add_parser('uninstall_driver', help='Uninstall GPU driver.')
    # uninstall_cuda_parser = subparsers.add_parser('uninstall_cuda', help='Uninstall CUDA toolkit.')
    # update_kernel = subparsers.add_parser('update_kernel', help='Update system kernel if an update is available.')

    args = parser.parse_args()
    return args


if __name__ == '__main__':
    if os.geteuid() != 0:
        print("This script needs to be run with root privileges!")
        sys.exit(1)
    args = parse_args()
    logger.info(f"Switching to working directory: {config.INSTALLER_DIR}")
    os.chdir(config.INSTALLER_DIR)
    installer = get_installer()

    if args.command == 'install_driver':
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
