"""The cro-dl log file.

The file is opened when the first record arrives, not when the module is
imported: `--help`, `--version` and every library import used to fail wherever
`$HOME` was not writable (a container, a read-only home), even though nothing was
going to be logged. A log that cannot be opened is reported once on stderr and
then dropped - the app still works without it.
"""

import logging
import sys
from pathlib import Path
from typing import Optional

from crodl.settings import LOG_PATH

LOG_FILE = LOG_PATH / "crodl.log"


class LazyFileHandler(logging.Handler):
    """A file handler that creates its file (and folder) on the first record."""

    def __init__(self, path: Path) -> None:
        super().__init__()
        self.path = path
        self._file: Optional[logging.FileHandler] = None
        self._unavailable = False

    def emit(self, record: logging.LogRecord) -> None:
        handler = self._open()

        if handler is None:
            return

        try:
            handler.emit(record)
        except Exception:  # a broken log must never break the download
            self.handleError(record)

    def _open(self) -> Optional[logging.FileHandler]:
        if self._file is not None:
            return self._file

        if self._unavailable:
            return None

        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._file = logging.FileHandler(self.path, encoding="utf-8")
            self._file.setFormatter(self.formatter)
        except OSError as error:
            self._unavailable = True
            print(
                f"cro-dl: cannot write the log to {self.path} ({error}); "
                "continuing without it.",
                file=sys.stderr,
            )
            return None

        return self._file

    def close(self) -> None:
        if self._file is not None:
            self._file.close()
            self._file = None

        super().close()


crologger = logging.getLogger(__name__)
crologger.setLevel(logging.DEBUG)

logfile = LazyFileHandler(LOG_FILE)
logfile.setFormatter(
    logging.Formatter("%(asctime)s - %(levelname)s - %(module)s - %(message)s")
)
crologger.addHandler(logfile)
