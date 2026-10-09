"""The folders the library keeps its audio in.

Two folders are enough to think about, so the list is kept in memory: rendering a
page asks "may this file be served?" for every part, and that question should not
become a database query per part. The database keeps the roots for the next
start (`LibraryRoot`); this module is what the pages read.
"""

from pathlib import Path
from typing import Sequence

from crodl.settings import DOWNLOAD_PATH

#: Every folder the library knows, the default one first.
_roots: list[Path] = []


def load(paths: Sequence[str]) -> None:
    """Takes the folders the database holds, with the default folder first."""
    _roots.clear()
    register(DOWNLOAD_PATH)

    for path in paths:
        register(Path(path))


def register(path: Path) -> None:
    """Remembers a folder for this run (the database is written separately)."""
    resolved = Path(path).expanduser()

    if resolved not in _roots:
        _roots.append(resolved)


def forget(path: Path) -> None:
    """Forgets a folder; the default one always stays."""
    resolved = Path(path).expanduser()

    if resolved != DOWNLOAD_PATH and resolved in _roots:
        _roots.remove(resolved)


def known() -> list[Path]:
    """Every known folder, the default one first."""
    return list(_roots) or [DOWNLOAD_PATH]


def is_default(path: str | Path) -> bool:
    """Whether this is the folder cro-dl downloads into."""
    return Path(path).expanduser() == DOWNLOAD_PATH


def holds(path: Path | str) -> bool:
    """Whether a file lives in one of the known folders (see `where`)."""
    return where(path) is not None


def where(path: Path | str) -> Path | None:
    """The folder a file lives in, or None when it lives in none of them."""
    candidate = Path(path)

    for root in known():
        try:
            candidate.relative_to(root)
        except ValueError:
            continue

        return root

    return None


def missing() -> list[Path]:
    """The known folders that are not there right now (an unplugged disk)."""
    return [root for root in known() if not root.is_dir()]
