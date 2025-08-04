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

import atexit
import pathlib
import subprocess
import sys
import tempfile
import time
import uuid
from argparse import Namespace
from typing import Iterable

from config import region_or_zone_to_multiregion, VERSION

BASE_IMAGES_MAP = {
    # Debian
    "debian-12": "image-family=debian-12,image-project=debian-cloud",
    # Red Hat
    "rhel-8": "image-family=rhel-8,image-project=rhel-cloud",
    "rhel-9": "image-family=rhel-9,image-project=rhel-cloud",
    # Rocky
    "rocky-8": "image-family=rocky-linux-8,image-project=rocky-linux-cloud",
    "rocky-9": "image-family=rocky-linux-9,image-project=rocky-linux-cloud",
    # Ubuntu
    "ubuntu-22": "image-family=ubuntu-2204-lts,image-project=ubuntu-os-cloud",
    "ubuntu-24": "image-family=ubuntu-2404-lts-amd64,image-project=ubuntu-os-cloud",
}


class Builder:
    def __init__(self, args: Namespace):
        self.build_uid = uuid.uuid4().hex[:8]
        self.build_instance_name = (
            f"image-builder-{args.base_image}-{args.installation_mode}-{self.build_uid}"
        )
        self.build_disk_name = f"image-builder-{args.base_image}-{args.installation_mode}-{self.build_uid}-disk"
        self.build_disk_size = args.vm_disk_size
        self.build_disk_type = {
            "ssd": "pd-ssd",
            "balanced": "pd-balanced",
            "standard": "pd-standard",
        }[args.vm_disk_type]
        self.build_zone = args.vm_zone
        self.multiregion = region_or_zone_to_multiregion(self.build_zone)
        self.build_machine_type = args.vm_type
        self.project = args.project
        self.base_os_image = BASE_IMAGES_MAP[args.base_image]
        self.image_name = args.image_name
        self.image_region = args.image_region or self.multiregion
        self.image_family = args.family
        self.installation_mode = args.installation_mode
        self.network = args.network
        self.subnet = args.subnet or self.network
        self.branch = args.installation_branch
        assert self.branch in ("nfb", "prod", "lts")
        self.skip_cleanup = args.skip_cleanup
        self.interactive = args.interactive

        self.custom_script = args.custom_script
        if self.custom_script:
            self.custom_script = pathlib.Path(self.custom_script)
            if not self.custom_script.is_file():
                raise RuntimeError(
                    f"The file {self.custom_script} does not exist or is not a file!"
                )

        assert self.installation_mode in ("repo", "binary")
        self.driver_only = args.driver_only
        self.tmp_dir = tempfile.TemporaryDirectory(delete=True)
        print("Using temp dir: ", self.tmp_dir)

        if self.base_os_image == 'debian-12' and self.installation_mode == 'repo' and self.branch == 'prod':
            print("Production branch is not supported in 'repo' mode for Debian 12.")
            sys.exit(1)

        self.pub_key, self.priv_key = self.get_signing_keys(args)

    @staticmethod
    def get_signing_keys(args: Namespace) -> (pathlib.Path, pathlib.Path):
        """
        Depending on the provided arguments, a new pair of keys is created and returned, or
        a pair of existing key paths is returned.
        """
        if args.secure_boot_pub_key and args.secure_boot_priv_key:
            pub_key = pathlib.Path(args.secure_boot_pub_key)
            priv_key = pathlib.Path(args.secure_boot_priv_key)
            if not pub_key.is_file():
                print(f"{pub_key} does not exist or is not a file!", file=sys.stderr)
                sys.exit(1)
            if not priv_key.is_file():
                print(f"{pub_key} does not exist or is not a file!", file=sys.stderr)
                sys.exit(1)
            return pub_key, priv_key

        if args.save_keys_path:
            keys_dir = pathlib.Path(args.save_keys_path)
            keys_dir.mkdir(parents=True, exist_ok=True)
            if not keys_dir.is_dir():
                print(
                    f"{keys_dir} does not exist or is not a directory!", file=sys.stderr
                )
                sys.exit(1)
        else:
            tmp_dir = tempfile.TemporaryDirectory(delete=True)
            keys_dir = pathlib.Path(tmp_dir.name)
            atexit.register(tmp_dir.cleanup)
            atexit.register(lambda: Builder.cleanup_keys(pub_key, priv_key))
        pub_key = keys_dir / "mok.der"
        priv_key = keys_dir / "mok.key"

        print("Generating new pair of keys to sign the drivers...")
        subprocess.run(
            [
                "openssl",
                "req",
                "-new",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-keyout",
                str(priv_key),
                "-out",
                str(pub_key),
                "-days",
                "36500",
                "-outform",
                "der",
                "-noenc",
                "-subj",
                "/CN=Graphics Drivers Secure Boot Signing",
            ],
            check=True,
        )
        print("Keys generated!")
        return pub_key, priv_key

    @staticmethod
    def cleanup_keys(pub_key: pathlib.Path, priv_key: pathlib.Path) -> None:
        """
        Removes the keys using shred tool.
        """
        print("Cleaning up keys...")
        subprocess.run(["shred", "-uz", str(pub_key)], check=True)
        subprocess.run(["shred", "-uz", str(priv_key)], check=True)
        return

    def start_vm(
        self, machine_type: str, instance_name: str, base_os_image: str, disk_name: str
    ):
        """
        Uses gcloud to create the build VM. Upon success, register a cleanup method to delete the VM.
        """
        print("Starting build VM...")
        subprocess.run(
            [
                "gcloud",
                "compute",
                "instances",
                "create",
                instance_name,
                "--zone",
                self.build_zone,
                "--machine-type",
                machine_type,
                "--project",
                self.project,
                "--max-run-duration",
                "1h",
                "--instance-termination-action",
                "DELETE",
                "--create-disk",
                f"auto-delete=yes,boot=yes,name={disk_name},{base_os_image},mode=rw,size={self.build_disk_size},type={self.build_disk_type}",
                "--no-shielded-secure-boot",
                "--network",
                self.network,
                "--subnet",
                self.subnet
            ],
            check=True,
        )
        if not self.skip_cleanup:
            atexit.register(lambda: self.delete_vm(instance_name))
        # Giving a moment for the VM to start up
        print(
            f"Build VM created ({instance_name}). Waiting 30 seconds to let it properly start..."
        )
        time.sleep(30)
        return

    def delete_vm(self, instance_name: str):
        """Uses gcloud to remove the build VM."""
        print("Deleting build VM...")
        subprocess.run(
            [
                "gcloud",
                "compute",
                "instances",
                "delete",
                "--project",
                self.project,
                "--zone",
                self.build_zone,
                "--quiet",
                instance_name,
            ],
            check=True,
        )
        return

    def shut_down_vm(self, instance_name: str):
        """Turns off a VM using gcloud."""
        print("Shutting down the build VM...")
        subprocess.run(
            [
                "gcloud",
                "compute",
                "instances",
                "stop",
                "--project",
                self.project,
                "--zone",
                self.build_zone,
                instance_name,
            ],
            check=True,
        )

    def download_certificates(self) -> Iterable[str]:
        """Locally downloads Microsoft certificates. Needed for Secure Boot to work."""
        try:
            subprocess.run(
                f"curl -L https://storage.googleapis.com/compute-gpu-installation-{self.multiregion}/certificates/MicCorUEFCA2011_2011-06-27.crt --output {self.tmp_dir.name}/MicCorUEFCA2011_2011-06-27.crt",
                shell=True,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            subprocess.run(
                f"curl -L https://storage.googleapis.com/compute-gpu-installation-{self.multiregion}/certificates/MicWinProPCA2011_2011-10-19.crt --output {self.tmp_dir.name}/MicWinProPCA2011_2011-10-19.crt",
                shell=True,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except subprocess.SubprocessError as err:
            print("Failed to download default certificates.")
            raise err
        return (
            f"{self.tmp_dir.name}/MicCorUEFCA2011_2011-06-27.crt",
            f"{self.tmp_dir.name}/MicWinProPCA2011_2011-10-19.crt",
        )

    def build_image(self, certs: Iterable[str]):
        """Creates the disk image based on the disk of the build VM."""
        print(f"Creating the disk image ({self.image_name})...")
        family_args = []
        if self.image_family:
            family_args = ["--family", self.image_family]
        subprocess.run(
            [
                "gcloud",
                "compute",
                "images",
                "create",
                self.image_name,
                "--source-disk",
                self.build_disk_name,
                "--source-disk-zone",
                self.build_zone,
                "--project",
                self.project,
                "--signature-database-file",
                ",".join(certs),
                "--storage-location",
                self.image_region,
                "--guest-os-features",
                "UEFI_COMPATIBLE",
                *family_args,
            ],
            check=True,
        )
        print(f"The {self.image_name} is ready!")

    def scp_keys(self, instance_name: str):
        """
        Uses gcloud compute scp to copy private and public key onto the build machine.
        """
        print("Copying signing keys to the build VM...")
        subprocess.run(
            [
                "gcloud",
                "compute",
                "scp",
                "--project",
                self.project,
                "--zone",
                self.build_zone,
                str(self.pub_key),
                f"{instance_name}:~/public.der",
            ],
            check=True,
        )
        subprocess.run(
            [
                "gcloud",
                "compute",
                "scp",
                "--project",
                self.project,
                "--zone",
                self.build_zone,
                str(self.priv_key),
                f"{instance_name}:~/private.key",
            ],
            check=True,
        )
        return

    def execute_command_over_ssh(self, instance_name: str, command: str) -> str:
        """
        Uses gcloud compute ssh to execute a command on the remote VM,
        """
        print("Executing remote command: ", command)
        while True:
            try:
                proc = subprocess.run(
                    [
                        "gcloud",
                        "compute",
                        "ssh",
                        "--project",
                        self.project,
                        f"--zone",
                        self.build_zone,
                        instance_name,
                        "--command",
                        command,
                    ],
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
                return proc.stdout
            except subprocess.CalledProcessError as err:
                output = str(err.stderr) + "\n" + str(err.stdout)
                if "Connection closed by" in output:
                    time.sleep(20)
                elif "Rebooting now." in output:
                    return output
                elif "Connection timed out" in output:
                    time.sleep(20)
                elif "Connection reset" in output:
                    time.sleep(20)
                elif "Connection refused" in output:
                    time.sleep(20)
                else:
                    print("\n------------------------\n")
                    print(
                        f"Remote SSH command: {err.args} failed with following output:\n{err.stdout}\n------------------------\n{err.stderr}\n------------------------\n"
                    )
                    raise err

    def start_interactive_ssh_session(self):
        """
        Starts an interactive SSH session with the build VM.
        """
        print(
            "An SSH session will not be opened with the build VM, so you can customize your future image."
        )
        print("The image building process will continue when you exit that session.")
        input("Press enter to continue...")
        subprocess.run(
            [
                "gcloud",
                "compute",
                "ssh",
                "--project",
                self.project,
                "--zone",
                self.build_zone,
                self.build_instance_name,
            ],
            text=True,
        )
        print("SSH session terminated. Continuing with the image building process...")

    def execute_custom_script(self):
        """
        Uploads the custom script to the build VM and executes it, then removes it.
        """
        print(f"Uploading {self.custom_script} to build VM.")
        subprocess.run(
            [
                "gcloud",
                "compute",
                "scp",
                "--project",
                self.project,
                "--zone",
                self.build_zone,
                str(self.custom_script),
                f"{self.build_instance_name}:~/custom_script_{self.build_uid}.sh",
            ],
            text=True,
            check=True,
        )
        print("Executing custom script...")
        self.execute_command_over_ssh(
            self.build_instance_name, f"sh ~/custom_script_{self.build_uid}.sh"
        )
        print("Removing the custom script from the build VM...")
        self.execute_command_over_ssh(
            self.build_instance_name, f"rm ~/custom_script_{self.build_uid}.sh"
        )

    def build(self) -> None:

        self.start_vm(
            machine_type=self.build_machine_type,
            instance_name=self.build_instance_name,
            base_os_image=self.base_os_image,
            disk_name=self.build_disk_name,
        )

        self.scp_keys(self.build_instance_name)

        # Download the installer script
        self.execute_command_over_ssh(
            self.build_instance_name,
            f"curl -L https://storage.googleapis.com/compute-gpu-installation-{self.multiregion}/installer/{VERSION}/cuda_installer.pyz --output cuda_installer.pyz",
        )

        out = "Rebooting now."

        while "Rebooting now." in out:
            out = self.execute_command_over_ssh(
                self.build_instance_name,
                f"sudo python3 cuda_installer.pyz install_driver "
                f"--secure-boot-pub-key=public.der --secure-boot-priv-key=private.key "
                f"--installation-mode={self.installation_mode} --installation-branch={self.branch} --ignore-no-gpu",
            )
            # Wait for the VM to restart
            time.sleep(60)

        if not self.driver_only:
            out = "Rebooting now."
            while "Rebooting now." in out:
                out = self.execute_command_over_ssh(
                    self.build_instance_name,
                    f"sudo python3 cuda_installer.pyz install_cuda "
                    f"--installation-mode={self.installation_mode} --installation-branch={self.branch} --ignore-no-gpu",
                )
                # Wait for the VM to restart
                time.sleep(30)

        # Remove the keys, so they are not present on the final image
        self.execute_command_over_ssh(
            self.build_instance_name, "shred -uz private.key public.der"
        )

        if self.interactive:
            self.start_interactive_ssh_session()

        if self.custom_script:
            self.execute_custom_script()

        self.shut_down_vm(self.build_instance_name)
        certs = [str(self.pub_key.absolute()), *self.download_certificates()]

        self.build_image(certs)

        if not self.skip_cleanup:
            print("Build process done. Proceeding to cleanup...")
        else:
            print("Build process done. Skipping cleanup.")
