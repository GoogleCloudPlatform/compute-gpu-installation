from os_installers.rhel import RHELInstaller


# Turns out, Rocky is so similar to Red Hat, that the same installation process works for both.
# Unfortunately, Rocky 8 comes without lspci, so it needs to be installed before checking what GPU we're facing.
class RockyInstaller(RHELInstaller):
    def __init__(self):
        self.run("dnf install -y pciutils", silent=True)
        RHELInstaller.__init__(self)
