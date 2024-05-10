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

from os_installers.rhel import RHELInstaller


# Turns out, Rocky is so similar to Red Hat, that the same installation process works for both.
# Unfortunately, Rocky 8 comes without lspci, so it needs to be installed before checking what GPU we're facing.
class RockyInstaller(RHELInstaller):
    def __init__(self):
        self.run("dnf install -y pciutils", silent=True)
        RHELInstaller.__init__(self)
