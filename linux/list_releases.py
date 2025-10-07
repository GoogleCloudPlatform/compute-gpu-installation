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
"""
Queries the NVIDIA hosted releases information to print useful summary
of available drivers.
"""
import json
import urllib.request
import urllib.error
import sys
import pprint

from cuda_installer.config import VERSION_MAP

NVIDIA_RELEASES_JSON = "https://docs.nvidia.com/datacenter/tesla/drivers/releases.json"
BRANCHES = {
    "lts": "lts branch",
    "prod": "production branch",
    "nfb": "new feature branch",
}
ARCHITECTURE = "x86_64"


def get_release_info() -> dict[str, dict]:
    """
    Fetch the releases.json file and return as a dictionary.
    """
    try:
        with urllib.request.urlopen(NVIDIA_RELEASES_JSON, timeout=10) as response:
            data = response.read()
            return json.loads(data)
    except urllib.error.URLError as e:
        print("Couldn't retrieve releases.json file.")
        print(e)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print("Couldn't parse releases.json file.")
        print(e)
        sys.exit(2)


def find_newest_branch_version(release_info: dict[str, dict], branch: str) -> str:
    for version in sorted(release_info.keys(), reverse=True):
        if release_info[version]["type"] == branch:
            return version
    raise RuntimeError(f"No {branch} branch found.")


def parse_version_info(version_info: dict) -> dict:
    return {
        "version": version_info["release_version"],
        "runfile_url": version_info["runfile_url"][ARCHITECTURE],
        "release_date": version_info["release_date"],
    }


def compare_with_config(version_info: dict, branch: str) -> dict:
    if VERSION_MAP[branch]["driver"]["version"] != version_info[branch]["version"]:
        print(
            f"Update on {branch.upper()} branch: {VERSION_MAP[branch]['driver']['version']} -> {version_info[branch]['version']}: {version_info[branch]['runfile_url']}"
        )


if __name__ == "__main__":
    release_info = get_release_info()
    versions = {
        branch: find_newest_branch_version(release_info, full_name)
        for branch, full_name in BRANCHES.items()
    }

    version_info = {
        branch: parse_version_info(release_info[versions[branch]]["driver_info"][0])
        for branch in BRANCHES
    }
    for branch in BRANCHES:
        compare_with_config(version_info, branch)
