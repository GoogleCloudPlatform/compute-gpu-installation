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

import logging
import logging.handlers
import sys

from config import INSTALLER_DIR


logger = logging.getLogger("GoogleCUDAInstaller")
_file_handler = logging.FileHandler(INSTALLER_DIR / "installer.log", mode="a")
_file_handler.level = logging.DEBUG
logger.addHandler(_file_handler)
_sys_handler = logging.handlers.SysLogHandler(
    "/dev/log", facility=logging.handlers.SysLogHandler.LOG_LOCAL0
)
_sys_handler.ident = "[GoogleCUDAInstaller] "
_sys_handler.level = logging.INFO
logger.addHandler(_sys_handler)
stdout_handler = logging.StreamHandler(sys.stdout)
stdout_handler.level = logging.INFO
logger.addHandler(stdout_handler)
logger.setLevel(logging.DEBUG)

formatter = logging.Formatter("[%(asctime)s] %(levelname)s - %(message)s")
_file_handler.setFormatter(formatter)

__all__ = ["logger"]
