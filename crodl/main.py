import sys
import subprocess
import importlib.metadata
from pathlib import Path
from typing import Optional
import asyncclick as click
from rich import print

from crodl import CroDL
from crodl.library.database import init_db
from crodl.library.scan import LibraryScan
from crodl.library.service import LibraryService
from crodl.program.audiowork import AudioWork
from crodl.program.series import Series
from crodl.program.show import Show
from crodl.settings import AudioFormat
from crodl.streams.utils import HMS, file_size


FORMAT_OPTIONS = {
    "mp3": AudioFormat.MP3,
    "hls": AudioFormat.HLS,
    "dash": AudioFormat.DASH,
}

__version__ = importlib.metadata.version("cro-dl")


def check_ffmpeg() -> bool:
    """Checks if ffmpeg is installed and accessible in the system path."""
    try:
        subprocess.run(
            ["ffmpeg", "-version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


def print_audiowork_info(audio_work: AudioWork) -> None:
    """Renders the available variants and the description of one audio work."""
    print(f"\n[bold yellow]{audio_work.title}[/bold yellow]")

    for variant in audio_work.info():
        duration = variant["duration_seconds"]
        size = variant["size_bytes"]
        duration_text = HMS(duration) if duration is not None else "--:--:--"
        size_text = file_size(size) if isinstance(size, int) else "Stream"
        print(
            f"- {duration_text} - {size_text} - "
            f"{variant['bitrate']} kbps - {variant['variant']}"
        )

    print(f"\n[blue]{audio_work.description}[/blue]\n")


@click.command()
@click.argument("recording_url", required=False)
@click.option(
    "--sync",
    is_flag=True,
    help="Synchronizuje stažené soubory na disku s knihovnou.",
)
@click.option(
    "--stream-format",
    "-sf",
    type=click.Choice(list(FORMAT_OPTIONS.keys())),
    default="mp3",
    help="Formát audio streamu. (mp3, hls, dash)",
)
@click.option(
    "--title",
    "-t",
    help="Vlastní název díla nebo složky seriálu.",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    help="Cesta, kam se má soubor/složka uložit.",
)
@click.option(
    "--no-accents",
    is_flag=True,
    help="Odstraní diakritiku z názvů souborů a složek.",
)
@click.version_option(__version__)
async def main(
    recording_url: Optional[str],
    stream_format: str,
    sync: bool,
    title: Optional[str],
    output: Optional[Path],
    no_accents: bool,
) -> None:
    """
    Hlavní vstupní bod pro CLI aplikaci cro-dl.

    První slovo "server" spustí webovou knihovnu (totéž jako
    `python -m crodl.server.run`); jinak se první slovo bere jako odkaz na dílo,
    které se má stáhnout.
    """
    if recording_url == "server":
        # Not a URL, so there is no ambiguity; a click group would instead read
        # `cro-dl <url>` as a command name, and that is the everyday use.
        from crodl.server.run import start

        start()
        return

    if sync:
        await sync_library()
        return

    if not recording_url:
        print("[red]Chyba: zadejte URL pořadu, nebo použijte --sync.[/red]")
        sys.exit(1)

    # Check for ffmpeg at startup
    if not check_ffmpeg():
        print("[bold red]Chyba: 'ffmpeg' nebyl nalezen ve vašem systému.[/bold red]")
        print("\nPro spojování stažených kousků (DASH/HLS) je ffmpeg nezbytný.")
        print("Prosím nainstalujte jej pomocí:")
        print("  [bold cyan]winget install ffmpeg[/bold cyan] (Windows)")
        print("  [bold cyan]scoop install ffmpeg[/bold cyan] (Windows - Scoop)")
        print("  [bold cyan]brew install ffmpeg[/bold cyan] (macOS)")
        print("\nVíce informací naleznete na [blue]https://ffmpeg.org[/blue]")

        if FORMAT_OPTIONS[stream_format] != AudioFormat.MP3:
            sys.exit(1)
        else:
            print(
                "[yellow]Upozornění: MP3 stahování bude fungovat, ale ostatní formáty selžou.[/yellow]\n"
            )

    await download_logic(recording_url, stream_format, title, output, no_accents)


async def sync_library() -> None:
    """Merges the audio files on disk into the library database."""
    await init_db()
    results = await LibraryScan().sync_all()

    print("[bold yellow]Synchronizace knihovny[/bold yellow]")
    print(f"Spárováno: {results['success']}, selhalo: {results['failed']}")


async def download_logic(
    recording_url: str,
    stream_format: str,
    title: Optional[str] = None,
    output: Optional[Path] = None,
    no_accents: bool = False,
) -> None:
    """Internal logic for the download process."""
    await init_db()
    dl = CroDL(library=LibraryService())

    try:
        content = await dl.get_content(
            recording_url, title=title, output_dir=output, remove_accents=no_accents
        )
    except (ValueError, NotImplementedError) as e:
        print(f"[red]Chyba: {e}[/red]")
        sys.exit(1)

    # Info display
    if isinstance(content, Show):
        print(f"[bold yellow]{content.title}[/bold yellow]")
        print(f"Celkový počet dílů: {content.episodes.count}")
    elif isinstance(content, Series):
        print(f"[bold yellow]{content.title}[/bold yellow]")
        print(f"Stažené díly: {content.downloaded_parts} / {content.parts}")
    else:
        print_audiowork_info(content)
        if not content.audio_formats:
            print(f"[red]{content.unavailable_reason}[/red]")
            sys.exit(1)

    # Existence check
    if content.already_exists():
        if isinstance(content, (Show, Series)):
            print("[bold yellow]Všechny díly byly již staženy.[/bold yellow]")
        else:
            print("[bold magenta]Soubor již existuje.[/bold magenta] :wave:")
        await dl.download(content, audio_format=FORMAT_OPTIONS[stream_format])
        sys.exit(0)

    # Confirmation for collections
    if isinstance(content, (Show, Series)):
        ans = input("Pokračovat ve stahování? [a/n]  ")
        if ans not in ("a", "A", "y", "Y"):
            print("[bold magenta]OK, končím. :wave:[/bold magenta]")
            sys.exit(0)

    await dl.download(content, audio_format=FORMAT_OPTIONS[stream_format])


def run():
    import asyncio

    asyncio.run(main())
