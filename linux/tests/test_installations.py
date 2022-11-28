# Copyright 2022 Google LLC
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
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from threading import BoundedSemaphore
from typing import Tuple

import google.api_core.exceptions
import google.auth
import pytest
from google.cloud import compute_v1

PROJECT = google.auth.default()[1]

INSTALLATION_TIMEOUT = 30*60  # 30 minutes

# Cloud project and family
OPERATING_SYSTEMS = (
    ("centos-cloud", "centos-7"),
    ("centos-cloud", "centos-stream-8"),
    ("debian-cloud", "debian-10"),
    ("debian-cloud", "debian-11"),
    ("rhel-cloud", "rhel-7"),
    ("rhel-cloud", "rhel-8"),
    ("rocky-linux-cloud", "rocky-linux-8"),
    ("ubuntu-os-cloud", "ubuntu-2004-lts"),
    ("ubuntu-os-cloud", "ubuntu-1804-lts"),
    ("ubuntu-os-cloud", "ubuntu-2204-lts"),
)

GPUS = {
    "A100": "nvidia-tesla-a100",
    "K80": "nvidia-tesla-k80",
    "P4": "nvidia-tesla-p4",
    "T4": "nvidia-tesla-t4",
    "P100": "nvidia-tesla-p100",
    "V100": "nvidia-tesla-v100",
}

GPU_QUOTA_SEMAPHORES = {
    "A100": BoundedSemaphore(16),
    "K80": BoundedSemaphore(16),
    "P4": BoundedSemaphore(1),
    "T4": BoundedSemaphore(4),
    "P100": BoundedSemaphore(1),
    "V100": BoundedSemaphore(8),
}

ZONES = {
    "A100": "us-central1-f",
    "K80": "us-central1-a",
    "P4": "us-central1-a",
    "T4": "us-central1-b",
    "P100": "us-central1-c",
    "V100": "us-central1-a",
}

MACHINE_TYPES = {
    "A100": "a2-highgpu-1g",
    "K80": "n1-standard-8",
    "P4": "n1-standard-8",
    "T4": "n1-standard-8",
    "P100": "n1-standard-8",
    "V100": "n1-standard-8",
}


@pytest.fixture(scope='module')
def ssh_key():
    """
    Generate an SSH key to be used while testing.
    """
    tmp_file = tempfile.NamedTemporaryFile()
    process = subprocess.run(
        ["ssh-keygen", "-b", "4096", "-f", tmp_file.name, "-N", ""],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        input="y",
        text=True,
        timeout=60
    )
    print(f"Created ssh key: {tmp_file.name}")
    yield tmp_file.name
    os.unlink(tmp_file.name + '.pub')


def get_image_from_family(project: str, family: str) -> compute_v1.Image:
    """
    Retrieve the newest image that is part of a given family in a project.
    Args:
        project: project ID or project number of the Cloud project you want to get image from.
        family: name of the image family you want to get image from.
    Returns:
        An Image object.
    """
    image_client = compute_v1.ImagesClient()
    # List of public operating system (OS) images: https://cloud.google.com/compute/docs/images/os-details
    newest_image = image_client.get_from_family(project=project, family=family)
    return newest_image


def _get_boot_disk(source_image_link: str, zone: str) -> compute_v1.AttachedDisk:
    """
    Prepare an AttachedDisk object to be used for instance creation.
    """
    boot_disk = compute_v1.AttachedDisk()
    initialize_params = compute_v1.AttachedDiskInitializeParams()
    initialize_params.source_image = source_image_link
    initialize_params.disk_size_gb = 100
    initialize_params.disk_type = f"zones/{zone}/diskTypes/pd-standard"
    boot_disk.initialize_params = initialize_params
    # Remember to set auto_delete to True if you want the disk to be deleted when you delete
    # your VM instance.
    boot_disk.auto_delete = True
    boot_disk.boot = True
    return boot_disk


def read_ssh_pubkey(ssh_key: str) -> str:
    """
    Read the public key of the generated ssh-key and returns it in a format acceptable for
    instance Metadata.
    """
    with open(ssh_key + '.pub') as key_file:
        pub_key = key_file.read()
    user = pub_key.rsplit(' ', 1)[1].split('@')[0]
    return f"{user}:{pub_key}"


@pytest.mark.parametrize("opsys,gpu", itertools.product(OPERATING_SYSTEMS, GPUS))
def test_install_driver_for_system(ssh_key: str, opsys: Tuple[str, str], gpu: str):
    """
    Run the installation test for given operating system and GPU card.
    """
    zone = ZONES[gpu]

    op_sys_image = get_image_from_family(*opsys)
    disks = [_get_boot_disk(op_sys_image.self_link, zone)]

    # We do not configure external IP to save on the billing,
    # but the project you try to run this tests in needs to
    # have a Cloud NAT configured, so the instances can
    # download the drivers.
    network_interface = compute_v1.NetworkInterface()
    network_interface.name = "global/networks/default"

    # GPUs
    accelerator = compute_v1.AcceleratorConfig()
    accelerator.accelerator_count = 1
    accelerator.accelerator_type = f"zones/{zone}/acceleratorTypes/{GPUS[gpu]}"

    instance = compute_v1.Instance()
    instance.machine_type = f"zones/{zone}/machineTypes/{MACHINE_TYPES[gpu]}"
    instance_name = f"gpu-test-{opsys[1]}-{gpu}-".lower() + uuid.uuid4().hex[:10]
    instance.name = instance_name
    instance.disks = disks
    instance.guest_accelerators = [accelerator]
    instance.network_interfaces = [network_interface]

    # Instance with GPU has to have LiveMigration disabled
    instance.scheduling = compute_v1.Scheduling()
    instance.scheduling.automatic_restart = False
    instance.scheduling.on_host_maintenance = compute_v1.Scheduling.OnHostMaintenance.TERMINATE.name
    instance.scheduling.preemptible = False

    # Set the startup script to install the drivers
    instance.metadata = compute_v1.Metadata()
    meta_item = compute_v1.Items()
    meta_item.key = 'startup-script'
    with open(Path(__file__).parent / '../startup_script.sh') as script:
        meta_item.value = script.read()
    ssh_item = compute_v1.Items()
    ssh_item.key = 'ssh-keys'
    ssh_item.value = read_ssh_pubkey(ssh_key)
    block_item = compute_v1.Items()
    block_item.key = "block-project-ssh-keys"
    block_item.value = "true"
    instance.metadata.items = [meta_item, ssh_item, block_item]

    # Prepare the request to insert an instance.
    request = compute_v1.InsertInstanceRequest()
    request.zone = zone
    request.project = PROJECT
    request.instance_resource = instance

    instance_client = compute_v1.InstancesClient()
    operation_client = compute_v1.ZoneOperationsClient()

    with GPU_QUOTA_SEMAPHORES[gpu]:
        # Making sure not to exceed the GPU quota while executing the tests
        # in multiple threads.
        try:
            operation = instance_client.insert_unary(request)
            operation = operation_client.wait(project=PROJECT, zone=zone, operation=operation.name)

            if operation.error:
                print(f"Error during instance {instance_name} creation:", operation.error, file=sys.stderr)
                raise RuntimeError(operation.error)

            if operation.warnings:
                msgs = []
                for warning in operation.warnings:
                    if warning.code != 'DISK_SIZE_LARGER_THAN_IMAGE_SIZE':
                        msgs.append(f" - {warning.code}: {warning.message}")
                if msgs:
                    print(f"Warnings during instance {instance_name} creation:\n", file=sys.stderr)
                    for msg in msgs:
                        print(msg, file=sys.stderr)

            _test_body(zone, instance_name, gpu, ssh_key)
        finally:
            try:
                # print("This is where I'd delete the instance, but we keep it for debugging.")
                operation = instance_client.delete_unary(project=PROJECT, zone=zone, instance=instance_name)
                operation_client.wait(project=PROJECT, zone=zone, operation=operation.name)
            except google.api_core.exceptions.NotFound:
                # The instance was not properly created at all.
                pass


def _test_body(zone: str, instance_name: str, gpu: str, ssh_key: str):
    """
    Execute the proper checks to see if the instance got the GPU drivers properly installed.
    """
    start_time = time.time()
    output = ('', '')
    time.sleep(30)  # Let the instance start
    tries = 0
    while time.time() - start_time <= INSTALLATION_TIMEOUT:
        time.sleep(10)
        try:
            tries += 1
            process = subprocess.run(
                ["gcloud", "compute", "ssh", instance_name, "--zone", zone,
                 "--ssh-key-file", ssh_key,
                 "--command", "ls /opt/google/gpu-installer"],
                stderr=subprocess.PIPE,
                stdout=subprocess.PIPE,
                text=True,
                timeout=10
            )
        except subprocess.TimeoutExpired as err:
            continue
        else:
            output = process.stdout, process.stderr
            if 'success' in process.stdout:
                # Installation appears to be completed successfully
                break
    else:
        print(f"Tried to run SSH connection {tries} times.")
        print(f"Standard output from {instance_name}:\n" + output[0])
        print(f"Error output from {instance_name}:\n" + output[1])
        pytest.fail(f"Timeout during driver installation for instance {instance_name}.")

    # Check if nvidia-smi lists the GPU as expected
    process = subprocess.run(
        ["gcloud", "compute", "ssh", instance_name, "--zone", zone,
         "--ssh-key-file", ssh_key,
         "--command", "nvidia-smi -L"],
        stderr=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        timeout=60
    )
    assert gpu.lower() in process.stdout.lower()
