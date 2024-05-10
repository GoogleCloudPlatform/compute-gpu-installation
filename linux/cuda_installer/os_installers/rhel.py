from decorators import checkpoint_decorator
from os_installers import RebootRequired
from os_installers.dnf_system import DNFSystemInstaller


class RHELInstaller(DNFSystemInstaller):

    @checkpoint_decorator("prerequisites", "System preparations already done.")
    def _install_prerequisites(self):
        self.run("dnf --refresh install -y kernel kernel-devel kernel-headers gcc gcc-c++ make bzip2")
        raise RebootRequired
