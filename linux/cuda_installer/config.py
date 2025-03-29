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

LATEST_DRIVER_VERSION = "560.35.03"
LATEST_DRIVER_URL = f"https://us.download.nvidia.com/tesla/{LATEST_DRIVER_VERSION}/NVIDIA-Linux-x86_64-{LATEST_DRIVER_VERSION}.run"
LATEST_DRIVER_SHA256_SUM = (
    "f2932c92fadd43c5b2341be453fc4f73f0ad7185c26bb7a43fbde81ae29f1fe3"
)

CUDA_TOOLKIT_URL = "https://developer.download.nvidia.com/compute/cuda/12.6.3/local_installers/cuda_12.6.3_560.35.05_linux.run"
CUDA_TOOLKIT_SHA256_SUM = (
    "81d60e48044796d7883aa8a049afe6501b843f2c45639b3703b2378de30d55d3"
)

CUDA_SAMPLES_TARGZ = (
    "https://github.com/NVIDIA/cuda-samples/archive/refs/tags/v12.4.1.tar.gz"
)
CUDA_SAMPLES_SHA256_SUM = (
    "01bb311cc8f802a0d243700e4abe6a2d402132c9d97ecf2c64f3fbb1006c304c"
)

CUDA_PROFILE_FILENAME = pathlib.Path("/etc/profile.d/google_cuda_install.sh")
CUDA_BIN_FOLDER = "/usr/local/cuda-12.6/bin"
CUDA_LIB_FOLDER = "/usr/local/cuda-12.6/lib64"

NVIDIA_PERSISTANCED_INSTALLER = (
    "/usr/share/doc/NVIDIA_GLX-1.0/samples/nvidia-persistenced-init.tar.bz2"
)
