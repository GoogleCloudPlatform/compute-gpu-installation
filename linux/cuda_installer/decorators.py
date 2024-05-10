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

import pathlib
from datetime import datetime

from config import INSTALLER_DIR
from logger import logger


def checkpoint_decorator(file_name: str, skip_message: str):
    from os_installers import RebootRequired

    def decorator(func):
        def wrapper(*args, **kwargs):
            if pathlib.Path(INSTALLER_DIR / file_name).exists():
                logger.info(skip_message)
                return
            try:
                func(*args, **kwargs)
            except RebootRequired:
                reboot_required = True
            else:
                reboot_required = False
            with pathlib.Path(INSTALLER_DIR / file_name).open(mode="w") as flag:
                flag.write(str(datetime.now()))
                flag.flush()
            if reboot_required:
                raise RebootRequired

        return wrapper

    return decorator
