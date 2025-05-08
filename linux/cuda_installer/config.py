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
import urllib.request
import urllib.error

INSTALLER_DIR = pathlib.Path("/opt/google/cuda-installer/")
try:
    INSTALLER_DIR.mkdir(parents=True, exist_ok=True)
except PermissionError:
    pass


# Check what multi-region should be used to download stuff
_region_to_multi_map = {
    "africa": "eu",
    "asia": "asia",
    "australia": "asia",
    "europe": "eu",
    "me": "eu",
    "northamerica": "us",
    "southamerica": "us",
    "us": "us",
}


def region_or_zone_to_multiregion(region: str) -> str:
    """Translated a region name like `europe-central2` to multi-region name like `eu`."""
    region = region.split("-")[0]
    return _region_to_multi_map.get(region, "us")


try:
    req = urllib.request.Request(
        "http://metadata.google.internal/computeMetadata/v1/instance/zone",
        headers={"Metadata-Flavor": "Google"},
    )
    response = urllib.request.urlopen(req).read().decode()
    zone = response.split("/")[-1]
    MULTIREGION = region_or_zone_to_multiregion(zone)
except urllib.error.URLError:
    MULTIREGION = "us"


LATEST_DRIVER_VERSION = "570.124.06"
LATEST_DRIVER_URL = f"https://storage.googleapis.com/compute-gpu-installation-{MULTIREGION}/drivers/NVIDIA-Linux-x86_64-{LATEST_DRIVER_VERSION}.run"
LATEST_DRIVER_GS_URI = f"gs://compute-gpu-installation-{MULTIREGION}/drivers/NVIDIA-Linux-x86_64-{LATEST_DRIVER_VERSION}.run"
LATEST_DRIVER_SHA256_SUM = (
    "1818c90657d17e510de9fa032385ff7e99063e848e901cb4636ee71c8b339313"
)

CUDA_TOOLKIT_VERSION = "12.8.1"
CUDA_TOOLKIT_VERSION_SHORT = "12.8"
CUDA_TOOLKIT_URL = f"https://storage.googleapis.com/compute-gpu-installation-{MULTIREGION}/cuda_toolkits/cuda_{CUDA_TOOLKIT_VERSION}_{LATEST_DRIVER_VERSION}_linux.run"
CUDA_TOOLKIT_GS_URI = f"gs://compute-gpu-installation-{MULTIREGION}/cuda_toolkits/cuda_{CUDA_TOOLKIT_VERSION}_{LATEST_DRIVER_VERSION}_linux.run"
CUDA_TOOLKIT_SHA256_SUM = (
    "228f6bcaf5b7618d032939f431914fc92d0e5ed39ebe37098a24502f26a19797"
)

# Repo install settings

## RHEL and Rocky settings, needs to have .format(version=) applied for good URL
NVIDIA_RHEL_REPO_URL = "https://developer.download.nvidia.com/compute/cuda/repos/rhel{version}/x86_64/cuda-rhel{version}.repo"

## DEB repos, needs to have .format(system=, version=) applied for good URL
NVIDIA_DEB_REPO_KEYRING_URL = (
    "https://storage.googleapis.com/compute-gpu-installation-"
    + MULTIREGION
    + "/repos/{system}{version}/x86_64/cuda-keyring_1.1-1_all.deb"
)
NVIDIA_DEB_REPO_KEYRING_GS_URI = (
    "gs://compute-gpu-installation-"
    + MULTIREGION
    + "/repos/{system}{version}/x86_64/cuda-keyring_1.1-1_all.deb"
)
NVIDIA_KEYRING_SHA256_SUMS = {
    "ubuntu": {
        "2004": "cf5ca9853118b9fb2b78dd2708786e1eb5ab14e39d8738539281429428eb4efe",
        "2204": "d93190d50b98ad4699ff40f4f7af50f16a76dac3bb8da1eaaf366d47898ff8df",
        "2404": "d2a6b11c096396d868758b86dab1823b25e14d70333f1dfa74da5ddaf6a06dba",
    },
    "debian": {
        "11": "dfc6e5cdbfc9b4cd1ca8bf6b6eda5d8582ca50d51b7e64ba049b935d52325d58",
        "12": "e7f219eab6fe4819cdb5c15b98233dc3420302d9c00883219cd3d896857cf48d",
    },
}

CUDA_SAMPLES_VERSION = "12.8"

CUDA_SAMPLES_URL = f"https://storage.googleapis.com/compute-gpu-installation-{MULTIREGION}/cuda_samples/v{CUDA_SAMPLES_VERSION}.tar.gz"
CUDA_SAMPLES_GS_URI = f"gs://compute-gpu-installation-{MULTIREGION}/cuda_samples/v{CUDA_SAMPLES_VERSION}.tar.gz"
CUDA_SAMPLES_SHA256_SUM = (
    "fe82484f9a87334075498f4e023a304cc70f240a285c11678f720f0a1e54a89d"
)

CUDA_PROFILE_FILENAME = pathlib.Path("/etc/profile.d/google_cuda_install.sh")
CUDA_BIN_FOLDER = f"/usr/local/cuda-{CUDA_TOOLKIT_VERSION_SHORT}/bin"
CUDA_LIB_FOLDER = f"/usr/local/cuda-{CUDA_TOOLKIT_VERSION_SHORT}/lib64"

NVIDIA_PERSISTANCED_INSTALLER = (
    "/usr/share/doc/NVIDIA_GLX-1.0/samples/nvidia-persistenced-init.tar.bz2"
)
