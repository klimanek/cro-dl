"""Making the server's log readable in a Czech terminal."""

import logging
from urllib.parse import unquote

# uvicorn's access log record is (client_addr, method, path, http_version, status).
PATH_ARG = 2


class PercentDecodedAccessLog(logging.Filter):
    """
    Logs request paths as text instead of percent-escapes.

    uvicorn writes the target of the request through `urllib.parse.quote`, so
    every Czech URL - `/library/Seriály/…/5 - Díl.aac` - reaches the terminal as
    `%C3%A1`-style gibberish, which is what a user sees when playing a file.
    The ASGI scope holds the path already decoded, so unquoting the logged one
    only restores what the browser actually asked for.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args

        if isinstance(args, tuple) and len(args) > PATH_ARG:
            path = args[PATH_ARG]
            if isinstance(path, str):
                decoded = list(args)
                decoded[PATH_ARG] = unquote(path)
                record.args = tuple(decoded)

        return True


def log_readable_paths(logger_name: str = "uvicorn.access") -> None:
    """Installs the filter on the access logger, at most once."""
    logger = logging.getLogger(logger_name)

    if not any(isinstance(f, PercentDecodedAccessLog) for f in logger.filters):
        logger.addFilter(PercentDecodedAccessLog())
