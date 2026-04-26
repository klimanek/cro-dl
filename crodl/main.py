import sys
import importlib.metadata
import asyncclick as click
from rich import print

from crodl import CroDL
from crodl.program.series import Series
from crodl.program.show import Show
from crodl.settings import AudioFormat
from crodl.persistence.database import init_db


FORMAT_OPTIONS = {
    "mp3": AudioFormat.MP3,
    "hls": AudioFormat.HLS,
    "dash": AudioFormat.DASH,
}

__version__ = importlib.metadata.version("cro-dl")


@click.command()
@click.argument("recording_url")
@click.option(
    "--stream-format",
    "-sf",
    type=click.Choice(list(FORMAT_OPTIONS.keys())),
    default="mp3",
    help="Formát audio streamu. (mp3, hls, dash)",
)
@click.version_option(__version__)
async def main(recording_url: str, stream_format: str) -> None:
    """Hlavní vstupní bod pro CLI aplikaci cro-dl."""
    # Initialize database tables before doing anything else
    await init_db()
    
    dl = CroDL()

    try:
        content = await dl.get_content(recording_url)
    except (ValueError, NotImplementedError) as e:
        print(f"[red]Chyba: {e}[/red]")
        sys.exit(1)

    # Zobrazení informací o obsahu
    if isinstance(content, Show):
        print(f"[bold yellow]{content.title}[/bold yellow]")
        print(f"Celkový počet dílů: {content.episodes.count}")
    elif isinstance(content, Series):
        print(f"[bold yellow]{content.title}[/bold yellow]")
        print(f"[blue]{content.description}[/blue]\n")
        print(f"Stažené díly: {content.downloaded_parts} / {content.parts}")
    else:
        content.info()

    # Kontrola existence na disku (budoucí verze může kontrolovat i DB)
    if content.already_exists():
        if isinstance(content, (Show, Series)):
            print("[bold yellow]Všechny díly byly již staženy.[/bold yellow]")
        else:
            print("[bold magenta]Soubor již existuje.[/bold magenta] :wave:")
        
        # We still run download to ensure metadata is in the database
        await dl.download(content, audio_format=FORMAT_OPTIONS[stream_format])
        sys.exit(0)

    # Potvrzení stahování pro kolekce (Show/Series)
    if isinstance(content, (Show, Series)):
        ans = input("Pokračovat ve stahování? [a/n]  ")
        if ans not in ("a", "A", "y", "Y"):
            print("[bold magenta]OK, končím. :wave:[/bold magenta]")
            sys.exit(0)

    # Samotné stahování přes fasádu (metadata se uloží uvnitř)
    await dl.download(content, audio_format=FORMAT_OPTIONS[stream_format])
