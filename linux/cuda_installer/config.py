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

INSTALLER_DIR = pathlib.Path("/opt/google/cuda-installer/")
try:
    INSTALLER_DIR.mkdir(parents=True, exist_ok=True)
except PermissionError:
    pass

LATEST_DRIVER_VERSION = "570.124.06"
LATEST_DRIVER_URL = f"https://storage.googleapis.com/compute-gpu-installation-us/drivers/NVIDIA-Linux-x86_64-{LATEST_DRIVER_VERSION}.run"
LATEST_DRIVER_GS_URI = f"gs://compute-gpu-installation-us/drivers/NVIDIA-Linux-x86_64-{LATEST_DRIVER_VERSION}.run"
LATEST_DRIVER_SHA256_SUM = (
    "1818c90657d17e510de9fa032385ff7e99063e848e901cb4636ee71c8b339313"
)

CUDA_TOOLKIT_VERSION = "12.8.1"
CUDA_TOOLKIT_VERSION_SHORT = "12.8"
CUDA_TOOLKIT_URL = f"https://storage.googleapis.com/compute-gpu-installation-us/cuda_toolkits/cuda_{CUDA_TOOLKIT_VERSION}_{LATEST_DRIVER_VERSION}_linux.run"
CUDA_TOOLKIT_GS_URI = f"gs://compute-gpu-installation-us/cuda_toolkits/cuda_{CUDA_TOOLKIT_VERSION}_{LATEST_DRIVER_VERSION}_linux.run"
CUDA_TOOLKIT_SHA256_SUM = (
    "228f6bcaf5b7618d032939f431914fc92d0e5ed39ebe37098a24502f26a19797"
)

CUDA_SAMPLES_VERSION = "12.8"
CUDA_SAMPLES_URL = (
    f"https://storage.googleapis.com/compute-gpu-installation-us/cuda_samples/v{CUDA_SAMPLES_VERSION}.tar.gz"
)
CUDA_SAMPLES_SHA256_SUM = (
    "fe82484f9a87334075498f4e023a304cc70f240a285c11678f720f0a1e54a89d"
)
CUDA_SAMPLES_GS_URI = f"gs://compute-gpu-installation-us/cuda_samples/v{CUDA_SAMPLES_VERSION}.tar.gz"

CUDA_PROFILE_FILENAME = pathlib.Path("/etc/profile.d/google_cuda_install.sh")
CUDA_BIN_FOLDER = f"/usr/local/cuda-{CUDA_TOOLKIT_VERSION_SHORT}/bin"
CUDA_LIB_FOLDER = f"/usr/local/cuda-{CUDA_TOOLKIT_VERSION_SHORT}/lib64"

NVIDIA_PERSISTANCED_INSTALLER = (
    "/usr/share/doc/NVIDIA_GLX-1.0/samples/nvidia-persistenced-init.tar.bz2"
)
