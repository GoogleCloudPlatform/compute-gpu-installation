#!/bin/bash
if test -f /opt/google/cuda-installer
then
  exit
fi

mkdir -p /opt/google/cuda-installer
cd /opt/google/cuda-installer/ || exit

curl -fSsL -O https://storage.googleapis.com/compute-gpu-installation-us/installer/v1.3.0/cuda_installer.pyz
python3 cuda_installer.pyz install_cuda