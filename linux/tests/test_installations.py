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
import random
import uuid
import zipapp
from pathlib import Path
from multiprocessing import BoundedSemaphore
from typing import Tuple

import google.api_core.exceptions
import google.auth
import pytest
from google.cloud import iam_admin_v1
from google.cloud import compute_v1
from google.cloud import storage
from google.cloud.storage.constants import STANDARD_STORAGE_CLASS

PROJECT = google.auth.default()[1]

INSTALLATION_TIMEOUT = 30 * 60  # 30 minutes

GS_BUCKET_NAME = f"{PROJECT}-cuda-installer-tests"

# Cloud project and family
OPERATING_SYSTEMS = (
    ("debian-cloud", "debian-11"),
    ("debian-cloud", "debian-12"),
    ("rhel-cloud", "rhel-8"),
    ("rhel-cloud", "rhel-9"),
    ("rocky-linux-cloud", "rocky-linux-8"),
    ("rocky-linux-cloud", "rocky-linux-9"),
    ("ubuntu-os-cloud", "ubuntu-2004-lts"),
    ("ubuntu-os-cloud", "ubuntu-2204-lts"),
    ("ubuntu-os-cloud", "ubuntu-2404-lts-amd64"),
)

GPUS = {
    # "L4": "nvidia-l4",
    # "A100": "nvidia-tesla-a100",
    # "P4": "nvidia-tesla-p4",
    "T4": "nvidia-tesla-t4",
    # "P100": "nvidia-tesla-p100",
    # "V100": "nvidia-tesla-v100",
}

GPU_QUOTA_SEMAPHORES = {
    "L4": BoundedSemaphore(8),
    "A100": BoundedSemaphore(8),
    "P4": BoundedSemaphore(1),
    "T4": BoundedSemaphore(8),
    "P100": BoundedSemaphore(1),
    "V100": BoundedSemaphore(8),
}

ZONES = {
    "L4": ("us-central1-a",),
    "A100": ("us-central1-f",),
    "P4": ("us-central1-a",),
    "T4": (
        "us-central1-b",
        "europe-west2-a",
        "us-west1-b",
        "northamerica-northeast1-c",
        "europe-west3-b",
    ),
    "P100": ("us-central1-c",),
    "V100": ("us-central1-a",),
}

MACHINE_TYPES = {
    "L4": "g2-standard-4",
    "A100": "a2-highgpu-1g",
    "P4": "n1-standard-8",
    "T4": "n1-standard-8",
    "P100": "n1-standard-8",
    "V100": "n1-standard-8",
}


@pytest.fixture(scope="session")
def service_account():
    iam_admin_client = iam_admin_v1.IAMClient()

    sa_full_name = f"cuda-tester@{PROJECT}.iam.gserviceaccount.com"
    if sa_full_name in (
        sa.email
        for sa in iam_admin_client.list_service_accounts(name=f"projects/{PROJECT}")
    ):
        yield sa_full_name
        return

    request = iam_admin_v1.CreateServiceAccountRequest()

    request.account_id = "cuda-tester"
    request.name = f"projects/{PROJECT}"

    service_account = iam_admin_v1.ServiceAccount()
    service_account.display_name = "Cuda Installer testing account"
    request.service_account = service_account

    account = iam_admin_client.create_service_account(request)

    yield account.email


@pytest.fixture(scope="session")
def gs_bucket():
    storage_client = storage.Client()

    if GS_BUCKET_NAME in (b.name for b in storage_client.list_buckets()):
        bucket = storage_client.get_bucket(GS_BUCKET_NAME)
        yield bucket
        return

    # Need to create the bucket
    bucket = storage_client.bucket(GS_BUCKET_NAME)
    bucket.storage_class = STANDARD_STORAGE_CLASS
    yield storage_client.create_bucket(bucket, location="us-central1")


@pytest.fixture(scope="session")
def zipapp_gs_url(gs_bucket: storage.Bucket, service_account: str):
    """
    Package the cuda_installer to a zipapp file and upload to a GS bucket.
    """
    file_name = f"cuda-installer-{uuid.uuid4().hex[:8]}.pyz"
    with tempfile.NamedTemporaryFile(mode="wb+", suffix=".pyz") as pyz_file:
        zipapp.create_archive("cuda_installer", pyz_file.file)
        pyz_file.seek(0)
        blob = gs_bucket.blob(file_name)
        blob.upload_from_filename(pyz_file.name, if_generation_match=0)
        blob.acl.reload()
        blob.acl.user(service_account).grant_read()
        blob.acl.save()
        yield f"gs://{gs_bucket.name}/{blob.name}"


@pytest.fixture(scope="module")
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
        timeout=60,
    )
    print(f"Created ssh key: {tmp_file.name}")
    yield tmp_file.name
    os.unlink(tmp_file.name + ".pub")


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
    with open(ssh_key + ".pub") as key_file:
        pub_key = key_file.read()
    user = pub_key.rsplit(" ", 1)[1].split("@")[0]
    return f"{user}:{pub_key}"


@pytest.mark.parametrize("opsys,gpu", itertools.product(OPERATING_SYSTEMS, GPUS))
def test_install_driver_for_system(
    zipapp_gs_url: str,
    service_account: str,
    ssh_key: str,
    opsys: Tuple[str, str],
    gpu: str,
):
    """
    Run the installation test for given operating system and GPU card.
    """
    zone = random.choice(ZONES[gpu])

    op_sys_image = get_image_from_family(*opsys)
    disks = [_get_boot_disk(op_sys_image.self_link, zone)]

    network_interface = compute_v1.NetworkInterface()
    network_interface.name = "global/networks/default"
    access = compute_v1.AccessConfig()
    access.type_ = compute_v1.AccessConfig.Type.ONE_TO_ONE_NAT.name
    access.name = "External NAT"
    access.network_tier = access.NetworkTier.PREMIUM.name
    network_interface.access_configs = [access]

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
    compute_sa = compute_v1.ServiceAccount()
    compute_sa.email = service_account
    compute_sa.scopes = ["https://www.googleapis.com/auth/cloud-platform"]
    instance.service_accounts = [compute_sa]

    # Instance with GPU has to have LiveMigration disabled
    instance.scheduling = compute_v1.Scheduling()
    instance.scheduling.automatic_restart = False
    instance.scheduling.on_host_maintenance = (
        compute_v1.Scheduling.OnHostMaintenance.TERMINATE.name
    )
    instance.scheduling.preemptible = False

    # Set the startup script to install the drivers
    instance.metadata = compute_v1.Metadata()
    meta_item = compute_v1.Items()
    meta_item.key = "startup-script"
    with open(Path(__file__).parent / "startup_script.sh") as script:
        meta_item.value = script.read().format(GS_INSTALLER_PATH=zipapp_gs_url)
    ssh_item = compute_v1.Items()
    ssh_item.key = "ssh-keys"
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

    try:
        operation = instance_client.insert_unary(request)
        operation = operation_client.wait(
            project=PROJECT, zone=zone, operation=operation.name
        )

        if operation.error:
            print(
                f"Error during instance {instance_name} creation:",
                operation.error,
                file=sys.stderr,
            )
            raise RuntimeError(operation.error)

        if operation.warnings:
            msgs = []
            for warning in operation.warnings:
                if warning.code != "DISK_SIZE_LARGER_THAN_IMAGE_SIZE":
                    msgs.append(f" - {warning.code}: {warning.message}")
            if msgs:
                print(
                    f"Warnings during instance {instance_name} creation:\n",
                    file=sys.stderr,
                )
                for msg in msgs:
                    print(msg, file=sys.stderr)

        _test_body(zone, instance_name, gpu, ssh_key)
    finally:
        try:
            # print("This is where I'd delete the instance, but we keep it for debugging.")
            operation = instance_client.delete_unary(
                project=PROJECT, zone=zone, instance=instance_name
            )
            operation_client.wait(project=PROJECT, zone=zone, operation=operation.name)
        except google.api_core.exceptions.NotFound:
            # The instance was not properly created at all.
            pass


def _test_body(zone: str, instance_name: str, gpu: str, ssh_key: str):
    """
    Execute the proper checks to see if the instance got the GPU drivers properly installed.
    """
    start_time = time.time()
    output = ("", "")
    time.sleep(30)  # Let the instance start
    tries = 0
    while time.time() - start_time <= INSTALLATION_TIMEOUT:
        time.sleep(10)
        try:
            tries += 1
            process = subprocess.run(
                [
                    "gcloud",
                    "compute",
                    "ssh",
                    instance_name,
                    "--zone",
                    zone,
                    "--ssh-key-file",
                    ssh_key,
                    "--command",
                    "ls /opt/google/cuda-installer",
                ],
                stderr=subprocess.PIPE,
                stdout=subprocess.PIPE,
                text=True,
                timeout=10,
            )
        except subprocess.TimeoutExpired as err:
            continue
        else:
            output = process.stdout, process.stderr
            print("Output:", output)
            if "cuda_installation" in process.stdout:
                # Give it some time to reboot, as in some cases it can take a while.
                time.sleep(60)
                # Installation appears to be completed successfully
                process = subprocess.run(
                    [
                        "gcloud",
                        "compute",
                        "ssh",
                        instance_name,
                        "--zone",
                        zone,
                        "--ssh-key-file",
                        ssh_key,
                        "--command",
                        "python3 /opt/google/cuda-installer/cuda_installer.pyz verify_cuda",
                    ],
                    stderr=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    text=True,
                    timeout=600,
                )
                print("process.stdout: ", process.stdout)
                if "CMake 3.20 or higher is required." in process.stdout:
                    pytest.skip("CMake 3.20 or higher is required. Skipping the sample verification (nvidia-smi worked).")
                    break
                if "Cuda Toolkit verification completed!" in process.stdout:
                    # Now we're sure that the installation worked.
                    break
                pytest.fail(f"Cuda verification failed for {instance_name}!")
    else:
        print(f"Tried to run SSH connection {tries} times.")
        print(f"Standard output from {instance_name}:\n" + output[0])
        print(f"Error output from {instance_name}:\n" + output[1])
        pytest.fail(f"Timeout during driver installation for instance {instance_name}.")

    # Check if nvidia-smi lists the GPU as expected
    process = subprocess.run(
        [
            "gcloud",
            "compute",
            "ssh",
            instance_name,
            "--zone",
            zone,
            "--ssh-key-file",
            ssh_key,
            "--command",
            "nvidia-smi -L",
        ],
        stderr=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        timeout=60,
    )
    assert gpu.lower() in process.stdout.lower()
