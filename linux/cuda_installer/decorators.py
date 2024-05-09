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
            with pathlib.Path(INSTALLER_DIR / file_name).open(mode='w') as flag:
                flag.write(str(datetime.now()))
                flag.flush()
            if reboot_required:
                raise RebootRequired
        return wrapper
    return decorator