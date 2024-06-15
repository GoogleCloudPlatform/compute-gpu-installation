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


K80_DRIVER_VERSION = "470.239.06"
K80_DEVICE_CODE = "10de:102d"
K80_DRIVER_URL = f"https://us.download.nvidia.com/tesla/{K80_DRIVER_VERSION}/NVIDIA-Linux-x86_64-{K80_DRIVER_VERSION}.run"
K80_DRIVER_SHA256_SUM = (
    "7d74caac140a0432d79ebe8e4330dc796f39ba7dd40b3fcd61df760181bf9ccc"
)

LATEST_DRIVER_VERSION = "550.90.07"
LATEST_DRIVER_URL = f"https://us.download.nvidia.com/tesla/{LATEST_DRIVER_VERSION}/NVIDIA-Linux-x86_64-{LATEST_DRIVER_VERSION}.run"
LATEST_DRIVER_SHA256_SUM = (
    "51acf579d5a9884f573a1d3f522e7fafa5e7841e22a9cec0b4bbeae31b0b9733"
)

CUDA_TOOLKIT_URL = "https://developer.download.nvidia.com/compute/cuda/12.5.0/local_installers/cuda_12.5.0_555.42.02_linux.run"
CUDA_TOOLKIT_SHA256_SUM = (
    "90fcc7df48226434065ff12a4372136b40b9a4cbf0c8602bb763b745f22b7a99"
)

CUDA_SAMPLES_TARGZ = (
    "https://github.com/NVIDIA/cuda-samples/archive/refs/tags/v12.4.1.tar.gz"
)
CUDA_SAMPLES_SHA256_SUM = (
    "01bb311cc8f802a0d243700e4abe6a2d402132c9d97ecf2c64f3fbb1006c304c"
)

CUDA_PROFILE_FILENAME = pathlib.Path("/etc/profile.d/google_cuda_install.sh")
CUDA_BIN_FOLDER = "/usr/local/cuda-12.5/bin"
CUDA_LIB_FOLDER = "/usr/local/cuda-12.5/lib64"

NVIDIA_PERSISTANCED_INSTALLER = (
    "/usr/share/doc/NVIDIA_GLX-1.0/samples/nvidia-persistenced-init.tar.bz2"
)
