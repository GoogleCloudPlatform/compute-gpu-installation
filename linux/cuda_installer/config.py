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
import urllib.request
import urllib.error

INSTALLER_DIR = pathlib.Path("/opt/google/cuda-installer/")
try:
    INSTALLER_DIR.mkdir(parents=True, exist_ok=True)
except PermissionError:
    pass

if os.getenv("CUDA_INSTALLER_DEBUG", False) == "True":
    VERSION = "debug"
else:
    VERSION = "v1.7.0"

VERSION_MAP = {
    "prod": {
        "driver": {
            "version": "580.82.07",
            "hash": "061e48e11fe552232095811d0b1cea9b718ba2540d605074ff227fce0628798c",
        },
        "rtx-driver": {
            "version": "580.82.07-grid",
            "hash": "387dc4927ffeba00ecc8c2a561c3f2cfb1c486d2e63105ce1bf52572483a63dc",
        },
        "cuda": {
            "major": "13",
            "minor": "0",
            "patch": "1",
            "driver": "580.82.07",
            "hash": "4c7ac59d1f41d67be27d140a4622801738ad71088570a0facfd6ec878a4c4100",
            "samples": "13.0",
            "samples_hash": "63cc9d5d8280c87df3c1f4e2276234a0f42cc497c52b40dd5bdda2836607db79",
        },
    },
    "nfb": {
        "driver": {
            "version": "575.57.08",
            "hash": "2aa701dac180a7b20a6e578cccd901ded8d44e57d60580f08f9d28dd1fffc6f2",
        },
        "cuda": {
            "major": "12",
            "minor": "9",
            "patch": "1",
            "driver": "575.57.08",
            "hash": "0f6d806ddd87230d2adbe8a6006a9d20144fdbda9de2d6acc677daa5d036417a",
            "samples": "12.9",
            "samples_hash": "2e67e1f6bdb15bf11b21e07e988e2f9f60fb054eff51ef01cebdd47229788015",
        },
    },
    "lts": {
        "driver": {
            "version": "580.82.07",
            "hash": "061e48e11fe552232095811d0b1cea9b718ba2540d605074ff227fce0628798c",
        },
        "cuda": {
            "major": "13",
            "minor": "0",
            "patch": "1",
            "driver": "580.82.07",
            "hash": "4c7ac59d1f41d67be27d140a4622801738ad71088570a0facfd6ec878a4c4100",
            "samples": "13.0",
            "samples_hash": "63cc9d5d8280c87df3c1f4e2276234a0f42cc497c52b40dd5bdda2836607db79",
        },
    },
}

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


DRIVER_URL = "https://storage.googleapis.com/compute-gpu-installation-{MULTIREGION}/drivers/NVIDIA-Linux-x86_64-{DRIVER_VERSION}.run"
DRIVER_GS_URI = "gs://compute-gpu-installation-{MULTIREGION}/drivers/NVIDIA-Linux-x86_64-{DRIVER_VERSION}.run"

CUDA_TOOLKIT_URL = "https://storage.googleapis.com/compute-gpu-installation-{MULTIREGION}/cuda_toolkits/cuda_{CUDA_MAJOR}.{CUDA_MINOR}.{CUDA_PATCH}_{CUDA_DRIVER_VERSION}_linux.run"
CUDA_TOOLKIT_GS_URI = "gs://compute-gpu-installation-{MULTIREGION}/cuda_toolkits/cuda_{CUDA_MAJOR}.{CUDA_MINOR}.{CUDA_PATCH}_{CUDA_DRIVER_VERSION}_linux.run"

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
        "12": "e7f219eab6fe4819cdb5c15b98233dc3420302d9c00883219cd3d896857cf48d",
        # "13": "e7f219eab6fe4819cdb5c15b98233dc3420302d9c00883219cd3d896857cf48d"
    },
}

# Hosted on GitHub: https://github.com/NVIDIA/cuda-samples
CUDA_SAMPLES_URL = "https://storage.googleapis.com/compute-gpu-installation-{MULTIREGION}/cuda_samples/v{CUDA_SAMPLES_VERSION}.tar.gz"
CUDA_SAMPLES_GS_URI = "gs://compute-gpu-installation-{MULTIREGION}/cuda_samples/v{CUDA_SAMPLES_VERSION}.tar.gz"

CUDA_PROFILE_FILENAME = pathlib.Path("/etc/profile.d/google_cuda_install.sh")
CUDA_BIN_FOLDER = "/usr/local/cuda-{CUDA_MAJOR}.{CUDA_MINOR}/bin"
CUDA_LIB_FOLDER = "/usr/local/cuda-{CUDA_MAJOR}.{CUDA_MINOR}/lib64"

NVIDIA_PERSISTANCED_INSTALLER = (
    "/usr/share/doc/NVIDIA_GLX-1.0/samples/nvidia-persistenced-init.tar.bz2"
)
