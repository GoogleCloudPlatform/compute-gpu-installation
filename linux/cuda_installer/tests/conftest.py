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

import tempfile
import uuid
import zipapp
from multiprocessing import BoundedSemaphore

import google.auth
import pytest
from google.cloud import storage, compute
from google.cloud.storage.constants import STANDARD_STORAGE_CLASS

PROJECT = google.auth.default()[1]
INSTALLATION_TIMEOUT = 30 * 60  # 30 minutes
GS_BUCKET_NAME = f"{PROJECT}-cuda-installer-tests"
VPC_NETWORK = "cuda-installer-test-network"


OPERATING_SYSTEMS = (
    ("debian-cloud", "debian-12"),
    ("rhel-cloud", "rhel-8"),
    ("rhel-cloud", "rhel-9"),
    ("rocky-linux-cloud", "rocky-linux-8"),
    ("rocky-linux-cloud", "rocky-linux-9"),
    ("ubuntu-os-cloud", "ubuntu-2204-lts"),
    ("ubuntu-os-cloud", "ubuntu-2404-lts-amd64"),
)

BRANCHES = ("prod", "nfb", "lts")
MODES = ("binary", "repo")

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
        "asia-southeast1-a",
        "asia-southeast1-b",
        "asia-southeast1-c",
        "europe-west1-b",
        "europe-west1-c",
        "europe-west1-d",
        "europe-west2-a",
        "europe-west2-b",
        "europe-west3-b",
        "europe-west4-c",
        "us-central1-a",
        "us-central1-b",
        "us-central1-c",
        "us-east1-d",
        "us-east4-b",
        "us-west1-b",
        "northamerica-northeast1-c",
    ),
    "P100": ("us-central1-c",),
    "V100": ("us-central1-a",),
}
MACHINE_TYPES = {
    "L4": "g2-standard-4",
    "A100": "a2-highgpu-1g",
    "P4": "n1-standard-8",
    "T4": "n1-standard-16",
    "P100": "n1-standard-8",
    "V100": "n1-standard-8",
}


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
def zipapp_file_path():
    """
    Package the cuda_installer to a zipapp file.
    """
    with tempfile.NamedTemporaryFile(mode="wb+", suffix=".pyz") as pyz_file:
        zipapp.create_archive("../cuda_installer", pyz_file.file)
        pyz_file.seek(0)
        yield pyz_file.name


@pytest.fixture(scope="session")
def zipapp_gs_url(
    gs_bucket: storage.Bucket, service_account: str, zipapp_file_path: str
):
    """
    Package the cuda_installer to a zipapp file and upload to a GS bucket.
    """
    file_name = f"cuda-installer-{uuid.uuid4().hex[:8]}.pyz"
    blob = gs_bucket.blob(file_name)
    blob.upload_from_filename(zipapp_file_path, if_generation_match=0)
    blob.acl.reload()
    blob.acl.user(service_account).grant_read()
    blob.acl.save()
    yield f"gs://{gs_bucket.name}/{blob.name}"

@pytest.fixture(scope="session")
def vpc_network():
    """
    Returns a VPC network dedicated to testing the image builder. Makes a new VPC network if it doesn't exist.
    """
    client = compute.NetworksClient()
    for network in client.list(project=PROJECT):
        if network.name == VPC_NETWORK:
            break
    else:
        new_network = compute.Network()
        new_network.name = VPC_NETWORK
        new_network.auto_create_subnetworks = True
        client.insert(project=PROJECT, network_resource=new_network).result()
        network = new_network

        firewall_rule = compute.Firewall()
        firewall_rule.name = "allow-ssh"
        firewall_rule.direction = "INGRESS"

        allowed_ports = compute.Allowed()
        allowed_ports.I_p_protocol = "tcp"
        allowed_ports.ports = ["22"]

        firewall_rule.allowed = [allowed_ports]
        firewall_rule.source_ranges = ["0.0.0.0/0"]
        firewall_rule.network = f"global/networks/{network.name}"
        firewall_rule.description = "Allowing SSH traffic on port 22 from Internet."

        firewall_client = compute.FirewallsClient()
        operation = firewall_client.insert(
            project=PROJECT, firewall_resource=firewall_rule
        )
        operation.result()

    return network.name