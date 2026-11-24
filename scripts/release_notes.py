"""The GitHub release description, taken from CHANGELOG.md.

Release tooling, not part of the package: `scripts/` is not shipped in the wheel.
"""

import pathlib
import sys

SECTION = "## ["


def section(changelog: str, version: str) -> str:
    """The body of the `## [version]` section, without its heading and date."""
    heading = f"{SECTION}{version}]"
    start = changelog.find(heading)

    if start < 0:
        raise ValueError(f"CHANGELOG.md has no {heading} section")

    _, _, body = changelog[start:].partition("\n")
    end = body.find("\n" + SECTION)
    if end >= 0:
        body = body[:end]

    notes = body.strip()
    if not notes:
        raise ValueError(f"The {heading} section is empty")

    return notes


def main(argv: list[str]) -> None:
    if len(argv) != 2:
        sys.exit("usage: release_notes.py <tag> <notes-file>")

    tag, target = argv
    changelog = pathlib.Path("CHANGELOG.md").read_text(encoding="utf-8")

    try:
        notes = section(changelog, tag.removeprefix("v"))
    except ValueError as error:
        sys.exit(str(error))

    pathlib.Path(target).write_text(notes + "\n", encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1:])
