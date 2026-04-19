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

import os
import pathlib
import urllib.request
import urllib.error

INSTALLER_DIR = pathlib.Path("/opt/google/cuda-installer/")
try:
    INSTALLER_DIR.mkdir(parents=True, exist_ok=True)
except PermissionError:
    pass

if os.getenv("CUDA_INSTALLER_DEBUG", False) == "True":
    VERSION = "debug"
else:
    VERSION = "v1.8.1"

# Hashes in this map are SHA256
VERSION_MAP = {
    "prod": {
        "driver": {
            "version": "580.126.20",
            "hash": "a055dbeae72438f20335b41929a060148c82c69d2147c0d922660e8c5a265eb1",
        },
        "rtx-driver": {
            "version": "580.126.09-grid",
            "hash": "e12c87b74b68cfde53f342c4c66e06d0a8bb4b4c34ec9b78a499e67ffc47903d",
        },
        "cuda": {
            "major": "13",
            "minor": "0",
            "patch": "2",
            "driver": "580.95.05",
            "hash": "81a5d0d0870ba2022efb0a531dcc60adbdc2bbff7b3ef19d6fd6d8105406c775",
            "samples": "13.0",
            "samples_hash": "63cc9d5d8280c87df3c1f4e2276234a0f42cc497c52b40dd5bdda2836607db79",
        },
    },
    "nfb": {
        "driver": {
            "version": "590.48.01",
            "hash": "b9e2f80693781431cc87f4cd29109e133dcecb50a50d6b68d4b3bf2d696bd689",
        },
        "cuda": {
            "major": "13",
            "minor": "1",
            "patch": "1",
            "driver": "590.48.01",
            "hash": "24ff323723722781436804b392a48f691cb40de9808095d3e2192d0db6dfb8e4",
            "samples": "13.1",
            "samples_hash": "03d7748a773fcd2350c2de88f2d167252c78ea90a52e229e7eb2a6922e3ba350",
        },
    },
    "lts": {
        "driver": {
            "version": "580.126.20",
            "hash": "a055dbeae72438f20335b41929a060148c82c69d2147c0d922660e8c5a265eb1",
        },
        "cuda": {
            "major": "13",
            "minor": "0",
            "patch": "2",
            "driver": "580.95.05",
            "hash": "81a5d0d0870ba2022efb0a531dcc60adbdc2bbff7b3ef19d6fd6d8105406c775",
            "samples": "13.0",
            "samples_hash": "63cc9d5d8280c87df3c1f4e2276234a0f42cc497c52b40dd5bdda2836607db79",
        },
    },
}

for branch in VERSION_MAP.keys():
    VERSION_MAP[branch]["cuda"][
        "version"
    ] = f"{VERSION_MAP[branch]['cuda']['major']}.{VERSION_MAP[branch]['cuda']['minor']}.{VERSION_MAP[branch]['cuda']['patch']}"

# Check what multi-region should be used to download stuff
_region_to_multi_map = {
    "africa": "eu",
    "asia": "asia",
    "australia": "asia",
    "europe": "eu",
    "me": "eu",
    "northamerica": "us",
    "southamerica": "us",
    "us": "us",
}


def region_or_zone_to_multiregion(region: str) -> str:
    """Translated a region name like `europe-central2` to multi-region name like `eu`."""
    region = region.split("-")[0]
    return _region_to_multi_map.get(region, "us")


try:
    req = urllib.request.Request(
        "http://metadata.google.internal/computeMetadata/v1/instance/zone",
        headers={"Metadata-Flavor": "Google"},
    )
    response = urllib.request.urlopen(req).read().decode()
    zone = response.split("/")[-1]
    MULTIREGION = region_or_zone_to_multiregion(zone)
except urllib.error.URLError:
    MULTIREGION = "us"

VERSIONS_LIST = f"https://storage.googleapis.com/compute-gpu-installation-{MULTIREGION}/drivers/versions.txt"

DRIVER_URL = "https://storage.googleapis.com/compute-gpu-installation-{MULTIREGION}/drivers/NVIDIA-Linux-x86_64-{DRIVER_VERSION}.run"
DRIVER_GS_URI = "gs://compute-gpu-installation-{MULTIREGION}/drivers/NVIDIA-Linux-x86_64-{DRIVER_VERSION}.run"

CUDA_TOOLKIT_URL = "https://storage.googleapis.com/compute-gpu-installation-{MULTIREGION}/cuda_toolkits/cuda_{CUDA_MAJOR}.{CUDA_MINOR}.{CUDA_PATCH}_{CUDA_DRIVER_VERSION}_linux.run"
CUDA_TOOLKIT_GS_URI = "gs://compute-gpu-installation-{MULTIREGION}/cuda_toolkits/cuda_{CUDA_MAJOR}.{CUDA_MINOR}.{CUDA_PATCH}_{CUDA_DRIVER_VERSION}_linux.run"

# Repo install settings

## RHEL and Rocky settings, needs to have .format(version=) applied for good URL
NVIDIA_RHEL_REPO_URL = "https://developer.download.nvidia.com/compute/cuda/repos/rhel{version}/x86_64/cuda-rhel{version}.repo"

## DEB repos, needs to have .format(system=, version=) applied for good URL
NVIDIA_DEB_REPO_KEYRING_URL = (
    "https://storage.googleapis.com/compute-gpu-installation-"
    + MULTIREGION
    + "/repos/{system}{version}/x86_64/cuda-keyring_1.1-1_all.deb"
)
NVIDIA_DEB_REPO_KEYRING_GS_URI = (
    "gs://compute-gpu-installation-"
    + MULTIREGION
    + "/repos/{system}{version}/x86_64/cuda-keyring_1.1-1_all.deb"
)
NVIDIA_KEYRING_SHA256_SUMS = {
    "ubuntu": {
        "2004": "cf5ca9853118b9fb2b78dd2708786e1eb5ab14e39d8738539281429428eb4efe",
        "2204": "d93190d50b98ad4699ff40f4f7af50f16a76dac3bb8da1eaaf366d47898ff8df",
        "2404": "d2a6b11c096396d868758b86dab1823b25e14d70333f1dfa74da5ddaf6a06dba",
    },
    "debian": {
        "12": "e7f219eab6fe4819cdb5c15b98233dc3420302d9c00883219cd3d896857cf48d",
        "13": "dd28f1f6ba0038180d6b23f846cefca1e3de4c9327751665241370bacea452a1",
    },
}

# Hosted on GitHub: https://github.com/NVIDIA/cuda-samples
CUDA_SAMPLES_URL = "https://storage.googleapis.com/compute-gpu-installation-{MULTIREGION}/cuda_samples/v{CUDA_SAMPLES_VERSION}.tar.gz"
CUDA_SAMPLES_GS_URI = "gs://compute-gpu-installation-{MULTIREGION}/cuda_samples/v{CUDA_SAMPLES_VERSION}.tar.gz"

CUDA_PROFILE_FILENAME = pathlib.Path("/etc/profile.d/google_cuda_install.sh")
CUDA_BIN_FOLDER = "/usr/local/cuda-{CUDA_MAJOR}.{CUDA_MINOR}/bin"
CUDA_LIB_FOLDER = "/usr/local/cuda-{CUDA_MAJOR}.{CUDA_MINOR}/lib64"

NVIDIA_PERSISTANCED_INSTALLER = (
    "/usr/share/doc/NVIDIA_GLX-1.0/samples/nvidia-persistenced-init.tar.bz2"
)

# Mapping the certificate files to their SHA1 hashes.
# See more: https://docs.cloud.google.com/compute/shielded-vm/docs/creating-shielded-images#default_certificates
SECURE_BOOT_CERTS = {
    "KEK": [
        ("MicCorKEKCA2011_2011-06-24.crt", "31590bfd89c9d74ed087dfac66334b3931254b30"),
        (
            "microsoft_corporation_kek_2k_ca_2023.crt",
            "459ab6fb5e284d272d5e3e6abc8ed663829d632b",
        ),
    ],
    "DB": [
        ("MicWinProPCA2011_2011-10-19.crt", "580a6f4cc4e4b669b9ebdc1b2b3e087b80d0678d"),
        ("MicCorUEFCA2011_2011-06-27.crt", "46def63b5ce61cf8ba0de2e6639c1019d0ed14f3"),
        ("microsoft_uefi_ca_2023.crt", "b5eeb4a6706048073f0ed296e7f580a790b59eaa"),
        ("windows_uefi_ca_2023.crt", "45a0fa32604773c82433c3b7d59e7466b3ac0c67"),
    ],
}

SECURE_BOOT_CERTS_URL_TEMPLATE = "https://storage.googleapis.com/compute-gpu-installation-{MULTIREGION}/certificates/{FILENAME}"

DRIVER_CHECKSUMS = {
    "510.108.03": "410a515e78df29c2cba4ac0b497889ce0ff1b04cfc711ff889e2dfc80f0da0d8",
    "510.39.01": "2e3edc3afba5840a5eb91c9c222c98cb991c3efdd994cf2aaa93d45a5d1b991b",
    "510.47.03": "f2a421dae836318d3c0d96459ccb3af27e90e50c95b0faa4288af76279e5d690",
    "510.60.02": "a800dfc0549078fd8c6e8e6780efb8eee87872e6055c7f5f386a4768ce07e003",
    "510.68.02": "bd2c344ac92b2fc12b06043590a4fe8d4eb0ccb74d0c49352f004cf2d299f4c5",
    "510.73.05": "8087fa71bc73d2941dd55e1affc89b078c7bfc87461d996ac2edf269ae0857b2",
    "510.85.02": "372427e633f32cff6dd76020e8ed471ef825d38878bd9655308b6efea1051090",
    "515.105.01": "9dd2221f26c847c864dfe80cc8533f322c5f4dfaa2939cf54a934b8f7a2f6a0d",
    "515.43.04": "3e875a4d350e4b2316f2bb5db5a6c89122ec920cc0ca64327d3a0d970c4f3dc7",
    "515.48.07": "e28764cc5b13c32e76370513daeafc05c289b77ee0511552450f1a00e31ae1e3",
    "515.65.01": "0492ddc5b5e65aa00cbc762e8d6680205c8d08e103b7131087a15126aee495e9",
    "515.86.01": "141777e1ca2f11e97d8d33260213f1be327eb73922ae22f4ddab404bb2ef4664",
    "520.56.06": "51674b00bed6766ec43d41ca84d18d693906234f85519069b6a341f76c113c46",
    "525.105.17": "c635a21a282c9b53485f19ebb64a0f4b536a968b94d4d97629e0bc547a58142a",
    "525.116.03": "5c295b02ebec2e9a9ec0d79ba9292eb623b4b2fbba8a6ed619060929a30d0469",
    "525.116.04": "8610ec82447cff72cb5f18b3657ee9a634a5151662b8ad901eb81f4c4fb617fe",
    "525.125.06": "b5275689f4a833c37a507717ac8f0ee2f1f5cd2b7e236ffa70aad8dfb7455b9d",
    "525.147.05": "435183ea545c7e12e3044d7986da07758a3369befe7ee519eb3b063d4af3fef1",
    "525.60.11": "816ee6c2e0813ccc3d4a7958f71fc49a37c60efe1d51d6146c1ce72403983d5d",
    "525.60.13": "dce1c184f9f038be72237ccd29c66bb151077f6037f1c158c83d582bd2dba8ca",
    "525.78.01": "43da42d2bf69bc37ea9c7c0fa02f52db0dcc483c272f52edacad89a5cb495a93",
    "525.85.05": "ea63b4253403b224bb7313a8977a920dfe9d203d661dd5f6fc26585a70179140",
    "525.89.02": "0e412c88c5bd98f842a839a6f64614f20e4c0950ef7cffb12b158a71633593e9",
    "530.30.02": "47fddbbd7a22ba661923dbce6e7f51eec54df68050c406cc0490c3bfbede7963",
    "530.41.03": "ae27a16a968c85503f5d161dda343c1602612b025f4aee15f92e2ea0acb784b1",
    "535.104.05": "2f9d609d1da770beee757636635c46e7ed8253ade887b87c7a5482e33fcbedc9",
    "535.113.01": "28e304d8dfe81b7f5e9f60404bf38c62fca35578d97522e3c70a0e8f23167481",
    "535.129.03": "e6dca5626a2608c6bb2a046cfcb7c1af338b9e961a7dd90ac09bb8a126ff002e",
    "535.146.02": "49fd1cc9e445c98b293f7c66f36becfe12ccc1de960dfff3f1dc96ba3a9cbf70",
    "535.154.05": "7e95065caa6b82de926110f14827a61972eb12c200e863a29e9fb47866eaa898",
    "535.161.07": "edc527f1dcfa0212a3bf815ebf302d45ef9663834a41e11a851dd38da159a8cd",
    "535.171.04": "e8f1643b4bc95d8acd65a4470784a97dace4642f149236466120db2aa942437a",
    "535.183.01": "f6707afbdda9407e3cbc2e5128e60bcbcdbf02fae29958c72fafb5d405e8b883",
    "535.216.01": "5ddea1147810012e33967c3181341bcd6624bd3d654c63f845df833b4ece6af7",
    "535.230.02": "20cca9118083fcc8083158466e9cb2b616a7922206bcb7296b1fa5cc9af2e0fd",
    "535.247.01": "c250e686494cb0c1b5eeea58ba2003707510b2766df05b06ba20b11b3445466b",
    "535.261.03": "d74b61d11e9c9b9052f4042d6ec4437f13d1def30e964e232d47e5d659d11d68",
    "535.274.02": "3b4ef54f06991e6dfff7868dde797fad9a451fee68d5267df87ca2be8e7f293b",
    "535.288.01": "f20c32fd6ecd1f705c6df2797c0c084253ecf7ff48f2c347f82a39619882ece1",
    "535.43.02": "e0a4dd9389060e6046c879ed308cd6462bd4a44a739ab6bea7b441b132fc9983",
    "535.54.03": "454764f57ea1b9e19166a370f78be10e71f0626438fb197f726dc3caf05b4082",
    "535.86.05": "407df0ca36632ebd858fc62da5b8b124ffc3bcced5033817bac9c271a23af6db",
    "545.23.06": "4139d328019f72f2af2878a4d018007a65773eb46a46533707d8e365eba9082f",
    "545.29.02": "46770f95a4a386f0455023b359d5d21373c07d13c222b5805f224c74b3cab885",
    "545.29.06": "82bc55676add43416c146e70c624c8dc6af16cc04c7238680c56a30e0045b17b",
    "550.107.02": "f97c1ca4df306028d88c7aed631fa8061b55c57c4c234d853b575d8cce6c0168",
    "550.127.05": "d384f34f5d2a896bd7536d3deb6a6d973d8094a3ad485a1c2ee3bf5192086ae9",
    "550.144.03": "6a4838e2cdb26e4c0e07367ac0d3bcf799d56b5286f68fa201be3d3ddb88aac4",
    "550.163.01": "ef8149f5b34595460145e9fbf82d3c92ee46735b856067aa94887b975cab9a2e",
    "550.40.07": "298936c727b7eefed95bb87eb8d24cfeef1f35fecac864d98e2694d37749a4ad",
    "550.54.14": "8c497ff1cfc7c310fb875149bc30faa4fd26d2237b2cba6cd2e8b0780157cfe3",
    "550.90.07": "51acf579d5a9884f573a1d3f522e7fafa5e7841e22a9cec0b4bbeae31b0b9733",
    "555.42.02": "93b708dd90e52a9e264f8ea33242da22b736614c75961d708ff2784954875b29",
    "555.52.04": "9d53ae6dbef32ae95786ec7d02bb944d5050c1c70516e6065ab5356626a44402",
    "555.58.02": "c5cb6de133d194e27aaf94b9e21e56e8f4faff7672d91e0048d14fbbc4d21ca3",
    "560.28.03": "99aaedbf5f2f9e0601270d48154080698afeb9ceb92ad94700c74b31db5027e6",
    "560.31.02": "d1cc207a3a05b1e7e5d8cea3756642f8229ce7c0aa3970e34a2e2c6953cd298d",
    "560.35.03": "f2932c92fadd43c5b2341be453fc4f73f0ad7185c26bb7a43fbde81ae29f1fe3",
    "565.57.01": "6eebe94e585e385e8804f5a74152df414887bf819cc21bd95b72acd0fb182c7a",
    "570.124.04": "1b786a4b7122d7c4216c58ae4007688a4f778c196c148d919163815ee10d53c4",
    "570.124.06": "1818c90657d17e510de9fa032385ff7e99063e848e901cb4636ee71c8b339313",
    "570.133.07": "2d43e64c581be5ef554de9888b1aa90037ef6d45f54284d3d9dcedc08dc4dc26",
    "570.153.02": "148886e4f69576fa8fa67140e6e5dd6e51f90b2ec74a65f1a7a7334dfa5de1b6",
    "570.158.01": "47f4cc9ad07bf718d0dce8dbfc0045cd36aced699712c7e8417f85fb87d918eb",
    "570.172.08": "0256867e082caf93d7b25fa7c8e69b316062a9c6c72c6e228fad7b238c6fa17d",
    "570.195.03": "ab6f39c6bcdedb8b0fd8fb55ffa5480f0e90588e92ba5cadb0477bf11eb8b508",
    "570.211.01": "6d038c4fb83448ea4a3d25bdab1556514d5ac1da43377859e0586219a25ff72b",
    "570.86.16": "4563ea4bb654247f491005a57c72c676aacd95abe1691d71332cecf25261cbd5",
    "575.51.02": "5d9d0df084a6a000bca76f03ac61e4fd8375ac9b089c9d9d64d2fc3be4ee69ad",
    "575.51.03": "db563ec94e413e25a65bb92c36a06970c4b27659102d3ee806f1b06b8c19b6d9",
    "575.57.08": "2aa701dac180a7b20a6e578cccd901ded8d44e57d60580f08f9d28dd1fffc6f2",
    "575.64.03": "4bb7aa86004b2ed299c7d430a0622c5c90327ce3aca4f6e9a531d4c41d3a0ca0",
    "575.64.05": "85f2b50f912261c1917a0b2cf7e1f9743affd008fdc0f209f4d5563f774d502d",
    "580.105.08-grid": "6372d1058fc1434a7f42b9bde02dbd266ec45f1c3253682b860c82427d6c33db",
    "580.105.08": "d9c6e8188672f3eb74dd04cfa69dd58479fa1d0162c8c28c8d17625763293475",
    "580.119.02": "8020f5dfd3ee88aee7a38990d0c3d2afe54751e9a170ba9eadd7ea670138ecd7",
    "580.126.09-grid": "e12c87b74b68cfde53f342c4c66e06d0a8bb4b4c34ec9b78a499e67ffc47903d",
    "580.126.09": "4cac53e48f8adff661d47c8788ed24059a248c9fd8098ceafd088a498986ec26",
    "580.126.18": "a7781b2e1c2d65c6580914c76e79ed454d02945df84711c033070a092a9ab49d",
    "580.126.20": "a055dbeae72438f20335b41929a060148c82c69d2147c0d922660e8c5a265eb1",
    "580.65.06": "04b10867af585e765cfbfdcf39ed5f4bd112375bebab0172eaa187c6aa5024ff",
    "580.76.05": "219be636b60931b021b2e8c1e0eff887363c731f8a940caa87bcc054d05d97fd",
    "580.82.07-grid": "387dc4927ffeba00ecc8c2a561c3f2cfb1c486d2e63105ce1bf52572483a63dc",
    "580.82.07": "061e48e11fe552232095811d0b1cea9b718ba2540d605074ff227fce0628798c",
    "580.82.09": "3eecf832da2e15e0e09ac34c29d2c7a03803182f9045787a355cacbe5b5695b7",
    "580.95.05": "849ef0ef8e842b9806b2cde9f11c1303d54f1a9a769467e4e5d961b2fe1182a7",
    "590.44.01": "55b91568ac0495a6b3a237f19079f3fe737fe68964d777b3930fc442384a3e6b",
    "590.48.01": "b9e2f80693781431cc87f4cd29109e133dcecb50a50d6b68d4b3bf2d696bd689",
    "595.45.04": "cd496549246cba2a3b75291c6c14eec45f9d375d9dea310f1345a01af54e8f5e",
    "595.58.03": "8c0d4f967b7932c4ab5714272aee8103392b0a702c92afa555176d36205829f9",
}
