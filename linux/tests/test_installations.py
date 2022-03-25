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
import sys

import pytest
import uuid
import google.auth
from google.cloud import compute_v1

PROJECT = google.auth.default()[1]

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
    ("ubuntu-os-cloud", "ubuntu-2110"),

)

GPUS = {
    "A100": "nvidia-tesla-a100",
    "K80": "nvidia-tesla-k80",
    "P4": "nvidia-tesla-p4",
    "T4": "nvidia-tesla-t4",
    "P100": "nvidia-tesla-p100",
    "V100": "nvidia-tesla-v100",
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


def get_boot_disk(source_image_link: str, zone: str) -> compute_v1.AttachedDisk:
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


def test_install_driver():
    opsys = OPERATING_SYSTEMS[0]
    gpu = 'V100'

    zone = ZONES[gpu]

    op_sys_image = get_image_from_family(*opsys)
    disks = [get_boot_disk(op_sys_image.self_link, zone)]

    # Use the network interface provided in the network_link argument.
    network_interface = compute_v1.NetworkInterface()
    network_interface.name = "global/networks/default"

    # GPUs
    accelerator = compute_v1.AcceleratorConfig()
    accelerator.accelerator_count = 1
    accelerator.accelerator_type = f"zones/{zone}/acceleratorTypes/{GPUS[gpu]}"

    instance = compute_v1.Instance()
    instance.machine_type = f"zones/{zone}/machineTypes/{MACHINE_TYPES[gpu]}"
    instance_name = f"gpu-test-{opsys[1]}-{gpu}-" + uuid.uuid4()[:10]
    instance.name = instance_name
    instance.disks = disks
    instance.accelerators = [accelerator]

    # Prepare the request to insert an instance.
    request = compute_v1.InsertInstanceRequest()
    request.zone = zone
    request.project = PROJECT
    request.instance_resource = instance

    instance_client = compute_v1.InstancesClient()
    operation = instance_client.insert_unary(request)
    operation_client = compute_v1.ZoneOperationsClient()
    operation = operation_client.wait(project=PROJECT, zone=zone, operation=operation.name)

    if operation.error:
        print(f"Error during instance {instance_name} creation:", operation.error, file=sys.stderr)
        raise RuntimeError(operation.error)

    if operation.warnings:
        print(f"Warnings during instance {instance_name} creation:\n", file=sys.stderr)
        for warning in operation.warnings:
            print(f" - {warning.code}: {warning.message}", file=sys.stderr)

