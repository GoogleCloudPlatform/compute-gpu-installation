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

import itertools
import os
import pathlib
import random
import subprocess
import time
import uuid

import pytest

os.environ["PYTHONPATH"] = f"{os.getenv('PYTHONPATH')}:{os.getcwd()}"

from tests.conftest import PROJECT, MODES, ZONES, zipapp_file_path
from image_builder import BASE_IMAGES_MAP

BUILD_ZONE = "europe-west4-c"


@pytest.mark.parametrize(
    "mode,base_os", itertools.product(MODES, BASE_IMAGES_MAP.keys())
)
def test_image_building(zipapp_file_path: str, mode: str, base_os: str):
    """
    Execute the cuda_installer.pyz image builder to prepare an image, them make a VM from it and see if it works.
    """
    test_id = uuid.uuid4().hex[:8]
    test_image_name = f"test-image{base_os}-{mode}-{test_id}"
    process = subprocess.run(
        [
            "python",
            zipapp_file_path,
            "build_image",
            "--project",
            PROJECT,
            "--vm-zone",
            BUILD_ZONE,
            "--vm-type",
            "c3d-standard-16",
            "--vm-disk-type",
            "ssd",
            "--vm-disk-size",
            "1024",
            "--installation-mode",
            mode,
            "--custom-script",
            str(pathlib.Path(__file__).parent.absolute() / "test_custom_script.sh"),
            "--base-image",
            base_os,
            test_image_name,
        ],
        text=True,
        stderr=subprocess.PIPE,
        stdout=subprocess.PIPE,
        check=False,
    )
    # This process will take some time.
    if process.returncode != 0:
        # Something went wrong.
        pytest.fail(
            f"Image building for {base_os} went wrong. Script output: \nStdout: {process.stdout}\nStderr: {process.stderr}"
        )

    # The image was build successfully, now we need to make a VM using it to check if it works.
    test_vm_name = f"test-image-vm-{base_os}-{mode}-{test_id}"
    test_zone = random.choice(ZONES["T4"])
    try:
        subprocess.run(
            f"gcloud compute instances create {test_vm_name} "
            f"--project={PROJECT} --zone={test_zone} --machine-type=n1-standard-4 "
            f"--accelerator=count=1,type=nvidia-tesla-t4 "
            f"--create-disk=auto-delete=yes,boot=yes,device-name={test_vm_name},image=projects/{PROJECT}/global/images/{test_image_name},mode=rw,size=1024,type=pd-balanced "
            f"--shielded-secure-boot --shielded-vtpm --shielded-integrity-monitoring "
            f"--maintenance-policy=TERMINATE",
            shell=True,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        # Wait for the machine to get ready.
        time.sleep(30)

        # Check if the machine has CUDA Toolkit properly installed
        nvidia_smi = subprocess.run(
            f"gcloud compute ssh --project={PROJECT} --zone={test_zone} {test_vm_name} --command 'nvidia-smi'",
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        assert f"Tesla T4" in nvidia_smi.stdout
        cuda_verify = subprocess.run(
            f"gcloud compute ssh --project={PROJECT} --zone={test_zone} {test_vm_name} --command 'python3 cuda_installer.pyz verify_cuda'",
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        assert "Cuda Toolkit verification completed!" in cuda_verify.stdout
        custom_script_verify = subprocess.run(
            f"gcloud compute ssh --project={PROJECT} --zone={test_zone} {test_vm_name} --command 'ls /opt/google/cuda-installer'",
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        assert "custom_script_executed_proof" in custom_script_verify.stdout
    finally:
        subprocess.run(
            f"gcloud compute instances delete {test_vm_name} --project={PROJECT} --zone={test_zone}",
            shell=True,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        subprocess.run(
            f"gcloud compute images delete {test_image_name} --project={PROJECT}",
            shell=True,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
