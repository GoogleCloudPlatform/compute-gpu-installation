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

from decorators import checkpoint_decorator
from os_installers import RebootRequired
from os_installers.dnf_system import DNFSystemInstaller


class RHELInstaller(DNFSystemInstaller):

    @checkpoint_decorator("prerequisites", "System preparations already done.")
    def _install_prerequisites(self):
        self.run(
            "dnf --refresh install -y kernel kernel-devel kernel-headers gcc gcc-c++ make bzip2"
        )
        raise RebootRequired
