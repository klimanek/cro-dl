import logging
import os

from crodl.settings import LOG_PATH


def create_log_dir():  # pragma: no cover
    if not os.path.exists(LOG_PATH):
        os.makedirs(LOG_PATH)


crologger = logging.getLogger(__name__)
crologger.setLevel(logging.DEBUG)

create_log_dir()

logfile = logging.FileHandler(os.path.join(LOG_PATH, "crodl.log"))
fileformat = logging.Formatter("%(asctime)s - %(levelname)s - %(module)s - %(message)s")
logfile.setFormatter(fileformat)
crologger.addHandler(logfile)
