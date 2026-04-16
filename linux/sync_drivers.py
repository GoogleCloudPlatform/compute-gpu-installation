#!/usr/bin/env python3
# Copyright 2025 Google LLC
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
"""
Queries the NVIDIA Linux driver archive to find new releases of
GPU drivers.
"""
import argparse
import re
import urllib.request
import subprocess
import pathlib
import tempfile
from urllib.error import HTTPError

NVIDIA_DRIVER_ARCHIVE = "https://download.nvidia.com/XFree86/Linux-x86_64/"
NVIDIA_DRIVER_FILE_TEMPLATE = "https://download.nvidia.com/XFree86/Linux-x86_64/{version}/NVIDIA-Linux-x86_64-{version}.run"
NVIDIA_DRIVER_SUM_TEMPLATE = "https://download.nvidia.com/XFree86/Linux-x86_64/{version}/NVIDIA-Linux-x86_64-{version}.run.sha256sum"
DRIVER_BUCKET_PATH = "gs://compute-gpu-installation-eu/drivers/"
DRIVER_FILE_RE = re.compile(r"NVIDIA-Linux-x86_64-(\d{3}\.\d{2,3}\.\d{2,3}).run")

def get_available_driver_versions() -> set[str]:
    """
    Checks the NVIDIA_DRIVER_ARCHIVE and finds all driver versions > 500.
    """
    with urllib.request.urlopen(NVIDIA_DRIVER_ARCHIVE) as response:
        html = response.read().decode('utf-8')
    
    # The driver versions are in the format of "535.104.05/"
    # We can use a regex to find all such occurrences
    versions = re.findall(r'href=\'(\d{3}\.\d{2,3}\.\d{2,3})/', html)
    
    # Filter for versions > 500
    return {v for v in versions if int(v.split('.')[0]) >= 500}

def get_stored_driver_versions() -> set[str]:
    """
    Checks the list of drivers stored in the GCS Bucket.
    """
    gs_ls = subprocess.run(["gcloud", "storage", "ls", DRIVER_BUCKET_PATH], capture_output=True, check=True, text=True)
    versions = DRIVER_FILE_RE.findall(gs_ls.stdout)
    return set(versions)

def find_new_versions() -> set[str]:
    """
    Checks the driver versions available on NVIDIA servers and the ones already
    present in the GCS bucket. Returns the list of drivers that are not present
    in the GCS bucket.
    """
    nvidia_versions = get_available_driver_versions()
    stored_versions = get_stored_driver_versions()
    return nvidia_versions - stored_versions

def download_version(version: str, destination: pathlib.Path) -> pathlib.Path:
    """
    Download the driver from NVIDIA and verify it's sha256sum.
    """
    file_url = NVIDIA_DRIVER_FILE_TEMPLATE.format(version=version)
    file_name = file_url.rsplit('/', 1)[-1]
    sum_url = NVIDIA_DRIVER_SUM_TEMPLATE.format(version=version)

    file_path, message = urllib.request.urlretrieve(file_url, destination / file_name)
    try:
        nvidia_sum_value = urllib.request.urlopen(sum_url).read().decode().split(' ')[0]
    except HTTPError as err:
        if err.code != 404:
            raise err
    else:
        print(f"Couldn't find checksum file for version {version} - skipping checksum validation.")
        my_sum_value = subprocess.run(["sha256sum", file_path], capture_output=True, check=True, text=True).stdout.split(' ')[0]
        assert nvidia_sum_value == my_sum_value

    return pathlib.Path(file_path)

def download_and_upload_new_version(new_version: str) -> None:
    """
    Downloads the new version of drivers and stores it in the GCS bucket.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        file_path = download_version(new_version, pathlib.Path(tmpdir))
        file_name = pathlib.Path(file_path).name
        subprocess.run(["gcloud", "storage", "cp", str(file_path), DRIVER_BUCKET_PATH + file_name], check=True)

def generate_versions_file():
    """
    Generates a versions.txt file with all available driver versions in the GCS bucket.
    """
    stored_versions = sorted(list(get_stored_driver_versions()))
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix=".txt") as tmpfile:
        tmpfile.write('\n'.join(stored_versions))
        tmpfile.flush()
        subprocess.run(["gcloud", "storage", "cp", tmpfile.name, DRIVER_BUCKET_PATH + "versions.txt"], check=True)
    print("versions.txt generated and uploaded.")

def main():
    parser = argparse.ArgumentParser(description="Synchronize NVIDIA drivers with GCS bucket.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Sub-command for listing new versions
    subparsers.add_parser("list", help="List new driver versions available from NVIDIA.")

    # Sub-command for uploading new versions
    subparsers.add_parser("upload", help="Upload new driver versions to GCS bucket.")

    # Sub-command for generating versions.txt
    subparsers.add_parser("generate-versions-file", help="Generate versions.txt in the GCS bucket.")

    args = parser.parse_args()

    if args.command == "list":
        new_versions = find_new_versions()
        if new_versions:
            print("New driver versions available:")
            for version in sorted(list(new_versions)):
                print(version)
        else:
            print("No new driver versions found.")
    elif args.command == "upload":
        new_versions = find_new_versions()
        if not new_versions:
            print("No new driver versions to upload.")
            return
        print(f"Found {len(new_versions)} new versions to upload.")
        for version in sorted(list(new_versions)):
            print(f"Downloading and uploading version {version}...")
            download_and_upload_new_version(version)
        print("All new versions have been uploaded.")
        print("Generating new versions.txt")
        generate_versions_file()
    elif args.command == "generate-versions-file":
        generate_versions_file()

if __name__ == "__main__":
    main()
