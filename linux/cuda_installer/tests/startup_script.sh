#!/bin/bash
if test -f /opt/google/cuda-installer
then
  exit
fi

mkdir -p /opt/google/cuda-installer
cd /opt/google/cuda-installer/ || exit

gsutil cp {GS_INSTALLER_PATH} cuda_installer.pyz
python3 cuda_installer.pyz install_cuda --installation-mode {MODE} --installation-branch {BRANCH}