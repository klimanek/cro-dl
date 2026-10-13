"""Listing directories, so an import can pick a folder instead of a typed path."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class Browse:
    """One folder, as a browser shows it: where it is, and what is inside it."""

    folder: Path
    children: list[Path] = field(default_factory=list)
    error: Optional[str] = None

    @property
    def parents(self) -> list[Path]:
        """The way back up, the filesystem root first (how a breadcrumb reads)."""
        return list(reversed(self.folder.parents))


def listing(path: Optional[str]) -> Browse:
    """
    The folder to show, with the folders inside it.

    Only directories are listed: a folder browser has no business reading file
    names. A folder that is missing or cannot be read comes back as a message
    rather than an exception - the settings page is where an unplugged disk is
    talked about, not where a stack trace belongs.
    """
    try:
        folder = Path(path or "~").expanduser().resolve()
    except (OSError, RuntimeError):
        return Browse(folder=Path("/"), error="Složku nelze otevřít.")

    try:
        children = sorted(
            (
                child
                for child in folder.iterdir()
                if child.is_dir() and not child.name.startswith(".")
            ),
            key=lambda child: child.name.casefold(),
        )
    except OSError as error:
        return Browse(folder=folder, error=f"Složku nelze otevřít: {error}")

    return Browse(folder=folder, children=children)
