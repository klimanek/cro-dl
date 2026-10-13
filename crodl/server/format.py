"""Turning the library's data into what the pages show."""

from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Optional
from urllib.parse import quote

from crodl.library import roots

# Czech month names in the genitive - the form a written date uses.
MONTHS = (
    "ledna",
    "února",
    "března",
    "dubna",
    "května",
    "června",
    "července",
    "srpna",
    "září",
    "října",
    "listopadu",
    "prosince",
)


def media_url(path: Optional[str]) -> Optional[str]:
    """
    URL of a file under one of the library's folders, as served on /library.

    None for anything the media route would refuse anyway (a file in no known
    folder has no address here), so a page shows a placeholder instead of a link
    that cannot work.
    """
    if not path:
        return None

    root = roots.where(path)
    if root is None:
        return None

    relative = Path(path).relative_to(root)

    if ".." in relative.parts:  # it only *looked* like it was inside
        return None

    if not Path(path).is_file():
        # A file that is not there (a folder that has been unplugged, a cover
        # somebody deleted) gets no address: a placeholder, not a broken player.
        return None

    return "/library/" + quote(relative.as_posix())


def czech_count(count: int, one: str, few: str, many: str) -> str:
    """Czech counting: 1 díl, 3 díly, 12 dílů."""
    if count == 1:
        return f"1 {one}"
    if 2 <= count <= 4:
        return f"{count} {few}"

    return f"{count} {many}"


#: How many genres the top bar spells out before folding the rest away.
GENRES_SHOWN = 10


def parts_label(count: int) -> str:
    """Czech plural of "díl" for a part count."""
    return czech_count(count, "díl", "díly", "dílů")


def records_label(count: int) -> str:
    """Czech plural of "záznam" for a number of deleted rows."""
    return czech_count(count, "záznam", "záznamy", "záznamů")


def new_parts_label(count: int) -> str:
    """Czech for parts that aired and can be fetched: 1 nový díl, 3 nové díly."""
    return czech_count(count, "nový díl", "nové díly", "nových dílů")


def upcoming_parts_label(count: int) -> str:
    """Czech for parts the Czech Radio has announced but not aired yet."""
    return "Ještě " + czech_count(count, "díl", "díly", "dílů")


def expired_parts_label(count: int) -> str:
    """Czech for parts whose streams are gone: 1 díl nedostupný, 2 díly nedostupné."""
    return czech_count(count, "díl nedostupný", "díly nedostupné", "dílů nedostupných")


def check_report(param: str) -> Optional[str]:
    """
    What the page says after "Zkontrolovat nové díly".

    The number of works that gained something comes back in the query string, so
    the note survives the redirect after the check.
    """
    if not param.isdigit():
        return None

    found = int(param)
    if not found:
        return "Zkontrolováno: zatím nic nového."

    return (
        f"Zkontrolováno: u {czech_count(found, 'díla', 'děl', 'děl')} jsou nové díly."
    )


def czech_datetime(value: str | datetime) -> str:
    """A timestamp the way a Czech sentence writes it: 8. října, 2026 v 15:36."""
    moment = value if isinstance(value, datetime) else datetime.fromisoformat(value)

    return f"{moment.day}. {MONTHS[moment.month - 1]}, {moment.year} v {moment:%H:%M}"


def added_line(job: Mapping[str, Any]) -> str:
    """
    When a download was added, and when it finished.

    A download that finished within the same minute says so once: repeating the
    same timestamp reads like a bug.
    """
    added = czech_datetime(job["started_at"])
    line = f"Přidáno {added}"

    finished = job.get("finished_at")
    if finished and czech_datetime(finished) != added:
        line += f" · dokončeno {czech_datetime(finished)}"

    return line


def settings_report(
    *, added: str = "", files: str = "", error: str = "", removed: str = ""
) -> Optional[str]:
    """What the settings page says after a folder was added or removed."""
    if error:
        return "Složku se nepodařilo přidat - musí existovat a být dostupná."

    if removed:
        return "Složka odebrána z knihovny; díla zůstala (soubory se nemazaly)."

    if added:
        count = int(files) if files.isdigit() else 0
        return f"Složka {added} přidána, naimportováno {count} souborů."

    return None


def curated_report(param: str) -> Optional[str]:
    """What the page says after a work's title, genre or description was saved."""
    if not param:
        return None

    written = int(param) if param.isdigit() else 0

    return f"Uloženo a tagy přepsány v {written} souborech." if written else "Uloženo."


def tags_report(param: str) -> Optional[str]:
    """What the page says after tags were written into files."""
    if not param:
        return None

    written = int(param) if param.isdigit() else 0
    if not written:
        return "Tagy se nepodařilo zapsat - soubor se nenašel nebo ho nelze označit."

    # After "do" Czech wants the genitive plural for any count but one.
    return f"Tagy zapsány do {czech_count(written, 'souboru', 'souborů', 'souborů')}."


def link_report(param: str) -> Optional[str]:
    """What the page says after a work's link was added."""
    if param == "ok":
        return (
            "Odkaz uložen - „Aktualizovat data“ se z něj dočte uuid a stáhne, co chybí."
        )

    if param == "ne":
        return "Odkaz se neuložil: musí to být stránka na www.mujrozhlas.cz."

    return None


def changed_line(fields: int, images: int) -> str:
    """What a refresh filled in (from the API, or from the images on disk)."""
    if not fields and not images:
        return "Nic k doplnění - údaje i obrázek už knihovna má."

    parts = []
    if fields:
        parts.append(czech_count(fields, "údaj", "údaje", "údajů"))
    if images:
        parts.append(czech_count(images, "obrázek", "obrázky", "obrázků"))

    return "Doplněno: " + ", ".join(parts) + "."


def refresh_report(param: str) -> Optional[str]:
    """
    What the page says after "Aktualizovat data".

    The route hands the outcome over in the query string ("3-1", or "none" for a
    work the API has never heard of), so the message survives the redirect.
    """
    if param == "none":
        return "Tenhle záznam nemá v API protějšek - nic k doplnění."

    fields, separator, images = param.partition("-")
    if separator and fields.isdigit() and images.isdigit():
        return changed_line(int(fields), int(images))

    return None
