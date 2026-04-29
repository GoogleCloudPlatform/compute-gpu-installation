#!/usr/bin/env python3
# Copyright 2026 Google LLC
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
Queries the NVIDIA Linux driver archive and other sources to find
new releases of GPU drivers and uploads them to a GCS bucket.
"""
import argparse
import hashlib
import multiprocessing
import os
import pathlib
import re
import subprocess
import tempfile
import urllib.request
from urllib.error import HTTPError

NVIDIA_DRIVER_ARCHIVE = "https://download.nvidia.com/XFree86/Linux-x86_64/"
NVIDIA_DRIVER_FILE_TEMPLATE = "https://download.nvidia.com/XFree86/Linux-x86_64/{version}/NVIDIA-Linux-x86_64-{version}.run"
NVIDIA_DRIVER_SUM_TEMPLATE = "https://download.nvidia.com/XFree86/Linux-x86_64/{version}/NVIDIA-Linux-x86_64-{version}.run.sha256sum"
RTX_NVIDIA_DRIVER_FILE_TEMPLATE = (
    "gs://nvidia-drivers-us-public/GRID/vGPU*/NVIDIA-Linux-x86_64-{version}.run"
)
RTX_NVIDIA_DRIVER_SUM_TEMPLATE = (
    "gs://nvidia-drivers-us-public/GRID/vGPU*/NVIDIA-Linux-x86_64-{version}.run.sha256"
)
VGPU_NVIDIA_DRIVER_FILE_TEMPLATE = (
    "gs://gce-nvidia-vgpu-drivers/G4_VGPU/NVIDIA-Linux-x86_64-{version}.run"
)
DRIVER_BUCKET_PATH = "gs://compute-gpu-installation-eu/drivers/"
SYNC_BUCKETS = [
    "gs://compute-gpu-installation-us/drivers/",
    "gs://compute-gpu-installation-asia/drivers/",
]
RTX_DRIVERS_SOURCE = "gs://nvidia-drivers-us-public/GRID/vGPU*/"
VGPU_DRIVERS_SOURCE = "gs://gce-nvidia-vgpu-drivers/G4_VGPU/"

DRIVER_FILENAME_TEMPLATE = "NVIDIA-Linux-x86_64-{version}.run"

DRIVER_FILE_RE = re.compile(
    r"NVIDIA-Linux-x86_64-(\d{3}\.\d{2,3}(?:\.\d{2,3})?(?:-grid(?:-gcp)?)?).run"
)
RTX_DRIVER_FILE_RE = re.compile(
    r"NVIDIA-Linux-x86_64-(\d{3}\.\d{2,3}(?:\.\d{2,3})?-grid).run"
)
VGPU_DRIVER_FILE_RE = re.compile(
    r"NVIDIA-Linux-x86_64-(\d{3}\.\d{2,3}(?:\.\d{2,3})?-grid-gcp).run"
)


def get_available_base_driver_versions() -> set[str]:
    """
    Checks the NVIDIA_DRIVER_ARCHIVE and finds all driver versions > 500.
    """
    print("Getting list of available drivers from NVIDIA website...")
    with urllib.request.urlopen(NVIDIA_DRIVER_ARCHIVE) as response:
        html = response.read().decode("utf-8")

    # The driver versions are in the format of "535.104.05/"
    # We can use a regex to find all such occurrences
    versions = re.findall(r"href=\'(\d{3}\.\d{2,3}(?:\.\d{2,3})?)/", html)

    # Filter for versions > 500
    return {v for v in versions if int(v.split(".")[0]) >= 500}


def get_available_rtx_and_vgpu_driver_versions() -> set[str]:
    """
    Checks the NVIDIA owned GCS bucket for new RTX drivers for GCP.
    """
    print("Getting list of available RTX drivers in Nvidia's bucket...")
    rtx_ls = subprocess.run(
        ["gcloud", "storage", "ls", "-r", RTX_DRIVERS_SOURCE],
        capture_output=True,
        check=True,
        text=True,
    )
    versions = set(RTX_DRIVER_FILE_RE.findall(rtx_ls.stdout))
    print("Getting list of available vGPU drivers...")
    vgpu_ls = subprocess.run(
        ["gcloud", "storage", "ls", "-r", VGPU_DRIVERS_SOURCE],
        capture_output=True,
        check=True,
        text=True,
    )
    versions.update(VGPU_DRIVER_FILE_RE.findall(vgpu_ls.stdout))
    return {v for v in versions if int(v.split(".")[0]) >= 500}


def get_stored_driver_versions() -> set[str]:
    """
    Checks the list of drivers stored in the GCS Bucket.
    """
    gs_ls = subprocess.run(
        ["gcloud", "storage", "ls", DRIVER_BUCKET_PATH],
        capture_output=True,
        check=True,
        text=True,
    )
    versions = DRIVER_FILE_RE.findall(gs_ls.stdout)
    return set(versions)


def find_new_versions() -> set[str]:
    """
    Checks the driver versions available on NVIDIA servers and the ones already
    present in the GCS bucket. Returns the list of drivers that are not present
    in the GCS bucket.
    """
    new_versions = get_available_base_driver_versions()
    new_versions.update(get_available_rtx_and_vgpu_driver_versions())
    stored_versions = get_stored_driver_versions()
    return new_versions - stored_versions


def download_basic_version(
    version: str, destination: pathlib.Path
) -> tuple[pathlib.Path, str]:
    """
    Download the driver from NVIDIA and verify it's sha256sum.
    """
    file_url = NVIDIA_DRIVER_FILE_TEMPLATE.format(version=version)
    file_name = file_url.rsplit("/", 1)[-1]
    sum_url = NVIDIA_DRIVER_SUM_TEMPLATE.format(version=version)

    file_path, _ = urllib.request.urlretrieve(file_url, destination / file_name)

    nvidia_sum_value = urllib.request.urlopen(sum_url).read().decode().split(" ")[0]

    my_sum_value = subprocess.run(
        ["sha256sum", file_path], capture_output=True, check=True, text=True
    ).stdout.split(" ")[0]
    assert nvidia_sum_value == my_sum_value

    return pathlib.Path(file_path), my_sum_value


def download_rtx_or_vgpu_version(
    version: str, destination: pathlib.Path
) -> tuple[pathlib.Path, str]:
    """
    Download the RTX driver from NVIDIA's bucket and verify it's sha256sum.
    """
    assert version.endswith("-grid") or version.endswith("-grid-gcp")
    if version.endswith("-grid"):
        file_template = RTX_NVIDIA_DRIVER_FILE_TEMPLATE
        sum_template = RTX_NVIDIA_DRIVER_SUM_TEMPLATE
    else:
        file_template = VGPU_NVIDIA_DRIVER_FILE_TEMPLATE
        # There are no checksums provided for vGPU drivers
        sum_template = None

    file_gs_url = file_template.format(version=version)
    file_name = file_gs_url.rsplit("/", 1)[-1]
    file_path = destination / file_name

    subprocess.run(
        ["gcloud", "storage", "cp", "--quiet", file_gs_url, destination], check=True
    )
    my_sum_value = subprocess.run(
        ["sha256sum", file_path], capture_output=True, check=True, text=True
    ).stdout.split(" ")[0]

    if sum_template:
        sum_gs_url = sum_template.format(version=version)
        nvidia_sum_value = subprocess.run(
            ["gcloud", "storage", "cat", sum_gs_url],
            check=True,
            text=True,
            capture_output=True,
        ).stdout.split(" ")[0]
        assert nvidia_sum_value == my_sum_value

    return pathlib.Path(file_path), my_sum_value


def download_and_upload_new_version(new_version: str) -> str:
    """
    Downloads the new version of drivers and stores it in the GCS bucket.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = pathlib.Path(tmpdir)
        if new_version.endswith("-grid"):
            file_path, checksum = download_rtx_or_vgpu_version(new_version, tmpdir)
        elif new_version.endswith("-grid-gcp"):
            file_path, checksum = download_rtx_or_vgpu_version(new_version, tmpdir)
        else:
            file_path, checksum = download_basic_version(new_version, tmpdir)
        file_name = pathlib.Path(file_path).name
        subprocess.run(
            [
                "gcloud",
                "storage",
                "cp",
                "--quiet",
                str(file_path),
                DRIVER_BUCKET_PATH + file_name,
            ],
            check=True,
        )
        return checksum


def generate_versions_file():
    """
    Generates a versions.txt file with all available driver versions in the GCS bucket.
    """
    stored_versions = sorted(list(get_stored_driver_versions()))
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as tmpfile:
        tmpfile.write("\n".join(stored_versions))
        tmpfile.flush()
        subprocess.run(
            [
                "gcloud",
                "storage",
                "cp",
                tmpfile.name,
                DRIVER_BUCKET_PATH + "versions.txt",
            ],
            check=True,
        )
    print("versions.txt generated and uploaded.")


def update_version_list(new_hashes: dict):
    """
    Updates the list of versions in cuda_installer/drivers_list.py.
    """
    from cuda_installer.drivers_list import DRIVER_CHECKSUMS

    assert len(set(DRIVER_CHECKSUMS.keys()).intersection(new_hashes.keys())) == 0

    DRIVER_CHECKSUMS.update(new_hashes)
    write_drivers_list_file(DRIVER_CHECKSUMS)


def write_drivers_list_file(driver_checksums: dict):
    with open("cuda_installer/drivers_list.py", "w") as drivers_list_file:
        drivers_list_file.write("DRIVER_CHECKSUMS = {\n")
        for version, checksum in sorted(driver_checksums.items()):
            drivers_list_file.write(f"  '{version}': '{checksum}',\n")
        drivers_list_file.write("}\n")
        drivers_list_file.flush()


def calculate_stored_version_hash(version: str, workdir: pathlib.Path) -> (str, str):
    """
    Downloads a driver file and calculates its sha256sum.
    """
    file_name = DRIVER_FILENAME_TEMPLATE.format(version=version)
    gs_path = DRIVER_BUCKET_PATH + file_name
    subprocess.run(
        ["gcloud", "storage", "cp", "--quiet", gs_path, workdir / file_name], check=True
    )
    with open(workdir / file_name, mode="rb") as driver_file:
        sha256sum = hashlib.file_digest(driver_file, "sha256")
    os.unlink(workdir / file_name)
    print("Version:", version, "sha256sum:", sha256sum.hexdigest())
    return version, sha256sum.hexdigest()


def fix_drivers_list_file():
    """
    Download every driver file and recalculate it's SHA 256 checksum.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        work_dir = pathlib.Path(tmpdir)
        print(f"Starting hash calculations in {work_dir}...")
        versions = get_stored_driver_versions()
        with multiprocessing.Pool(max(1, os.process_cpu_count() - 2)) as pool:
            hashes = pool.starmap(
                calculate_stored_version_hash,
                [(version, work_dir) for version in versions],
            )
        write_drivers_list_file({version: checksum for version, checksum in hashes})


def main():
    parser = argparse.ArgumentParser(
        description="Synchronize NVIDIA drivers with GCS bucket."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Sub-command for listing new versions
    subparsers.add_parser(
        "list", help="List new driver versions available from NVIDIA."
    )

    # Sub-command for uploading new versions
    subparsers.add_parser("upload", help="Upload new driver versions to GCS bucket.")

    # Sub-command for generating versions.txt
    subparsers.add_parser(
        "generate-versions-file", help="Generate versions.txt in the GCS bucket."
    )

    # Sub-command to regenerate the drivers_list.py
    subparsers.add_parser(
        "fix-drivers-list", help="Regenerate the cuda_installer/drivers_list.py file."
    )

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
        new_checksums = {}
        if not new_versions:
            print("No new driver versions to upload.")
            return
        print(f"Found {len(new_versions)} new versions to upload.")
        for version in sorted(list(new_versions)):
            print(f"Downloading and uploading version {version}...")
            try:
                new_checksums[version] = download_and_upload_new_version(version)
            except HTTPError as err:
                print(f"Encountered error for version {version}: ", err)
            except AssertionError:
                print(
                    f"Checksum validation for version {version} failed. Skipping that version."
                )
        print("All new versions have been uploaded.")
        print("Generating new versions.txt")
        generate_versions_file()
        print("Updating cuda_installer/drivers_list.py")
        update_version_list(new_checksums)
        print("Syncing multiregion buckets...")
        for bucket in SYNC_BUCKETS:
            print(f"Updating {bucket}...")
            subprocess.run(
                [
                    "gcloud",
                    "storage",
                    "rsync",
                    "-r",
                    "--quiet",
                    DRIVER_BUCKET_PATH,
                    bucket,
                ]
            )
        print("Done!")
    elif args.command == "generate-versions-file":
        generate_versions_file()
    elif args.command == "fix-drivers-list":
        fix_drivers_list_file()


if __name__ == "__main__":
    main()
