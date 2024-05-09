import re

from decorators import checkpoint_decorator
from os_installers import LinuxInstaller, RebootRequired
from logger import logger


class DebianInstaller(LinuxInstaller):
    KERNEL_IMAGE_PACKAGE = "linux-image-{version}"
    KERNEL_VERSION_FORMAT = "{major}.{minor}.{patch}-{micro}-cloud-amd64"
    KERNEL_HEADERS_PACKAGE = "linux-headers-{version}"
    KERNEL_PACKAGE_REGEX = r"linux-image-{major}.{minor}.([\d]+)-([\d]+)-cloud-amd64"

    @checkpoint_decorator("prerequisites", "System preparations already done.")
    def _install_prerequisites(self):
        """
        Installs packages required for the proper driver installation on Debian.
        """
        self.run("apt-get update", silent=True)

        major, minor, *_ = self.kernel_version.split(".")
        kernel_package_regex = re.compile(self.KERNEL_PACKAGE_REGEX.format(major=major, minor=minor))

        # Find the newest version of kernel to update to, but staying with the same major version
        packages = self.run("apt-cache search linux-image").stdout
        patch, micro = max(kernel_package_regex.findall(packages))

        wanted_kernel_version = self.KERNEL_VERSION_FORMAT.format(major=major, minor=minor, patch=patch, micro=micro)
        wanted_kernel_package = self.KERNEL_IMAGE_PACKAGE.format(version=wanted_kernel_version)
        wanted_kernel_headers = self.KERNEL_HEADERS_PACKAGE.format(version=wanted_kernel_version)

        self.run(f"apt-get install -y make gcc {wanted_kernel_package} {wanted_kernel_headers} "
                 f"software-properties-common pciutils gcc make dkms")
        raise RebootRequired

    def lock_kernel_updates(self):
        """
        Marks kernel related packages, so they don't get auto-updated. This would cause the driver to stop working.
        """
        logger.info("Locking kernel updates...")
        self.run(f"apt-mark hold "
                 f"linux-image-{self.kernel_version} "
                 f"linux-headers-{self.kernel_version}"
                 f"linux-image-cloud-amd64"
                 f"linux-headers-cloud-amd64"
                 )

    def unlock_kernel_updates(self):
        """
        Allows the kernel related packages to be upgraded.
        """
        logger.info("Unlocking kernel updates...")
        self.run(f"apt-mark unhold "
                 f"linux-image-{self.kernel_version} "
                 f"linux-headers-{self.kernel_version}"
                 f"linux-image-cloud-amd64"
                 f"linux-headers-cloud-amd64"
                 )

    def uninstall_driver(self):
        pass

    def uninstall_cuda(self):
        pass

    def verify_cuda(self):
        pass

    def upgrade_kernel(self):
        # Update package: linux-image-cloud-amd64
        pass

