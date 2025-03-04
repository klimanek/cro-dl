import sys
from urllib.parse import urlparse

import asyncclick as click
from rich import print

from crodl.program.audiowork import AudioWork
from crodl.program.series import Series
from crodl.program.show import Show
from crodl.tools.scrap import cro_session, is_series, is_show
from crodl.tools.logger import crologger
from crodl.settings import SUPPORTED_DOMAINS, AudioFormat


def is_domain_supported(url: str) -> bool:
    """Checks whether the website with 'hidden' audio lies in a supported domain."""
    domain = urlparse(url).netloc

    if not domain:
        err = "The URL is invalid!"
        crologger.error(err)
        print(err)
        raise ValueError(err)

    return domain in SUPPORTED_DOMAINS


FORMAT_OPTIONS = {
    "mp3": AudioFormat.MP3,
    "hls": AudioFormat.HLS,
    "dash": AudioFormat.DASH,
}


@click.command()
@click.argument("recording_url")
# @click.option("-d", "--download", is_flag=True, help="Spustí stahování")
@click.option(
    "--stream-format",
    "-sf",
    type=click.Choice(list(FORMAT_OPTIONS.keys())),
    default="mp3",
    help="Formát audio streamu. (mp3, hls, dash)",
)
async def main(recording_url: str, stream_format: str, download: bool = True) -> None:
    if not is_domain_supported(recording_url):
        raise NotImplementedError(
            f"Unsuported domain: {urlparse(recording_url).netloc}"
        )

    show, series = False, False

    if is_show(recording_url, cro_session):
        show = True
        audiowork = Show(url=recording_url)
        print(f"[bold yellow]{audiowork.title}[/bold yellow]")
        print(f"Celkový počet dílů: {audiowork.episodes.count}")

        if audiowork.are_all_parts_downloaded():
            print("[bold yellow]Pořad byl již celý stažen.[/bold yellow]")
            sys.exit(0)

    elif is_series(recording_url, cro_session):
        series = True
        audiowork = Series(url=recording_url)
        print(f"[bold yellow]{audiowork.title}[/bold yellow]")
        print(f"Celkový počet dílů: {audiowork.parts}")

        if audiowork.are_all_parts_downloaded():
            print("[bold yellow]Seriál byl již celý stažen.[/bold yellow]")
            sys.exit(0)
    else:
        audiowork = AudioWork(url=recording_url)
        audiowork.info()

    if show or series:
        ans = input("Pokračovat ve stahování? [a/n]  ")
        if ans in ("a", "A", "y", "Y"):
            await audiowork.download(audio_format=FORMAT_OPTIONS[stream_format])
        else:
            print("[bold magenta]OK, končím. :wave:[/bold magenta]")
            sys.exit(0)
    else:
        if audiowork.already_exists():
            print("[bold magenta]Soubor již existuje.[/bold magenta] :wave:")
            sys.exit(0)
        await audiowork.download(audio_format=FORMAT_OPTIONS[stream_format])
