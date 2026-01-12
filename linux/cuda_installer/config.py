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
    VERSION = "v1.8.0"

# Hashes in this map are SHA256
VERSION_MAP = {
    "prod": {
        "driver": {
            "version": "580.105.08",
            "hash": "d9c6e8188672f3eb74dd04cfa69dd58479fa1d0162c8c28c8d17625763293475",
        },
        "rtx-driver": {
            "version": "580.105.08-grid",
            "hash": "6372d1058fc1434a7f42b9bde02dbd266ec45f1c3253682b860c82427d6c33db",
        },
        "cuda": {
            "major": "13",
            "minor": "0",
            "patch": "2",
            "driver": "580.95.05",
            "hash": "81a5d0d0870ba2022efb0a531dcc60adbdc2bbff7b3ef19d6fd6d8105406c775",
            "samples": "13.0",
            "samples_hash": "63cc9d5d8280c87df3c1f4e2276234a0f42cc497c52b40dd5bdda2836607db79",
        },
    },
    "nfb": {
        "driver": {
            "version": "590.48.01",
            "hash": "b9e2f80693781431cc87f4cd29109e133dcecb50a50d6b68d4b3bf2d696bd689",
        },
        "cuda": {
            "major": "13",
            "minor": "1",
            "patch": "0",
            "driver": "590.44.01",
            "hash": "6b4fdf2694b3d7afbc526f26412b4cf4f050b202324455053307310f53b323a7",
            "samples": "13.1",
            "samples_hash": "03d7748a773fcd2350c2de88f2d167252c78ea90a52e229e7eb2a6922e3ba350",
        },
    },
    "lts": {
        "driver": {
            "version": "580.105.08",
            "hash": "d9c6e8188672f3eb74dd04cfa69dd58479fa1d0162c8c28c8d17625763293475",
        },
        "cuda": {
            "major": "13",
            "minor": "0",
            "patch": "2",
            "driver": "580.95.05",
            "hash": "81a5d0d0870ba2022efb0a531dcc60adbdc2bbff7b3ef19d6fd6d8105406c775",
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
        "13": "dd28f1f6ba0038180d6b23f846cefca1e3de4c9327751665241370bacea452a1"
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

# Mapping the certificate files to their SHA1 hashes.
# See more: https://docs.cloud.google.com/compute/shielded-vm/docs/creating-shielded-images#default_certificates
SECURE_BOOT_CERTS = {
    'KEK': [
        ('MicCorKEKCA2011_2011-06-24.crt', '31590bfd89c9d74ed087dfac66334b3931254b30'),
        ('microsoft_corporation_kek_2k_ca_2023.crt', '459ab6fb5e284d272d5e3e6abc8ed663829d632b')
    ],
    'DB': [
        ('MicWinProPCA2011_2011-10-19.crt', '580a6f4cc4e4b669b9ebdc1b2b3e087b80d0678d'),
        ('MicCorUEFCA2011_2011-06-27.crt', '46def63b5ce61cf8ba0de2e6639c1019d0ed14f3'),
        ('microsoft_uefi_ca_2023.crt', 'b5eeb4a6706048073f0ed296e7f580a790b59eaa'),
        ('windows_uefi_ca_2023.crt', '45a0fa32604773c82433c3b7d59e7466b3ac0c67')
    ]
}

SECURE_BOOT_CERTS_URL_TEMPLATE = "https://storage.googleapis.com/compute-gpu-installation-{MULTIREGION}/certificates/{FILENAME}"
