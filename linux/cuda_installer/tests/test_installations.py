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
from pathlib import Path
from typing import Tuple

import google.api_core.exceptions
import google.auth
import pytest
from google.cloud import iam_admin_v1
from google.cloud import compute_v1

from config import VERSION_MAP
from tests.conftest import (
    PROJECT,
    BRANCHES,
    INSTALLATION_TIMEOUT,
    OPERATING_SYSTEMS,
    MODES,
    GPUS,
    ZONES,
    MACHINE_TYPES,
    zipapp_gs_url,
)


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
    initialize_params.disk_size_gb = 200
    initialize_params.disk_type = f"zones/{zone}/diskTypes/pd-ssd"
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


class RetryInDifferentZone(RuntimeError):
    pass


@pytest.mark.parametrize(
    "opsys,gpu,mode,branch", itertools.product(OPERATING_SYSTEMS, GPUS, MODES, BRANCHES)
)
def test_install_driver_for_system(
    zipapp_gs_url: str,
    service_account: str,
    ssh_key: str,
    opsys: Tuple[str, str],
    gpu: str,
    mode: str,
    branch: str,
):
    for _ in range(5):
        zone = random.choice(ZONES[gpu])
        try:
            _test_setup(zipapp_gs_url, service_account, ssh_key, opsys, gpu, mode, branch, zone)
        except RetryInDifferentZone:
            continue
        else:
            break
    else:
        pytest.fail("Couldn't find a zone to start the instance in.")


def _test_setup(zipapp_gs_url: str,
    service_account: str,
    ssh_key: str,
    opsys: Tuple[str, str],
    gpu: str,
    mode: str,
    branch: str,
    zone: str):
    """
    Run the installation test for given operating system and GPU card.
    """

    if mode == "repo" and opsys[1] == "debian-12" and branch == "prod":
        pytest.skip("Repo mode for prod branch doesn't work on Debian 12.")

    if branch == 'lts' and mode == 'repo':
        pytest.skip("LTS branch doesn't work for repo mode.")

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
    instance_name = f"gpu-test-{opsys[1]}-{gpu}-{mode}-{branch}-".lower() + uuid.uuid4().hex[:10]
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
    instance.scheduling.max_run_duration = compute_v1.Duration(
        {"seconds": 3600}
    )  # 1 hour
    instance.scheduling.instance_termination_action = (
        compute_v1.Scheduling.InstanceTerminationAction.DELETE.name
    )

    # Set the startup script to install the drivers
    instance.metadata = compute_v1.Metadata()
    meta_item = compute_v1.Items()
    meta_item.key = "startup-script"
    with open(Path(__file__).parent / "startup_script.sh") as script:
        meta_item.value = script.read().format(
            GS_INSTALLER_PATH=zipapp_gs_url, MODE=mode, BRANCH=branch
        )
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
            if operation.error.errors[0].code == 'ZONE_RESOURCE_POOL_EXHAUSTED_WITH_DETAILS':
                # Need to retry in different zone.
                raise RetryInDifferentZone()
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

        _test_body(zone, instance_name, gpu, ssh_key, branch)
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


def _test_body(zone: str, instance_name: str, gpu: str, ssh_key: str, branch: str):
    """
    Execute the proper checks to see if the instance got the GPU drivers properly installed.
    """
    start_time = time.time()
    output = ("", "")
    time.sleep(30)  # Let the instance start
    tries = 0
    while time.time() - start_time <= INSTALLATION_TIMEOUT:
        time.sleep(30)
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
                timeout=20,
            )
        except subprocess.TimeoutExpired as err:
            continue
        else:
            output = process.stdout, process.stderr
            # print("Output:", output)
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
                if "CMake 3.20 or higher is required." in process.stdout:
                    pytest.skip(
                        "CMake 3.20 or higher is required. Skipping the sample verification (nvidia-smi worked)."
                    )
                    break
                if "unsupported GNU version! gcc versions later than 12 are not supported!" in process.stdout:
                    pytest.skip("The system has too new gcc version. Skipping the sample verification (nvidia-smi worked).")
                    break
                if "Cuda Toolkit verification completed!" in process.stdout:
                    # Now we're sure that the installation worked.
                    break
                pytest.fail(f"Cuda verification failed for {instance_name}! \n-------------------\n{process.stdout} \n------------------------\n {process.stderr}\n---------------------")
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
            "nvidia-smi",
        ],
        stderr=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        timeout=60,
    )
    # assert f"driver version: {VERSION_MAP[branch]['driver']['version'].split('.')[0]}" in process.stdout.lower()
    assert gpu.lower() in process.stdout.lower()
