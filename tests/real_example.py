import asyncio
import shutil

from collections.abc import Callable
from typing import Optional
from pathlib import Path

from rich import print

from crodl.program.audiowork import AudioWork
from crodl.program.series import Series
from crodl.streams.utils import create_dir_if_does_not_exist

from crodl.settings import AudioFormat
from crodl.tools.logger import crologger

TEST_DOWNLOAD_DIR = Path.cwd() / "tests" / "test_downloads"

create_dir_if_does_not_exist(TEST_DOWNLOAD_DIR)


class NovelDownloadError(Exception):
    pass


class SeriesDownloadError(Exception):
    pass


class DeleteTmpDirError(Exception):
    pass


def delete_tmp_download() -> None:
    print("Uklízím po sobě...", end=" ")
    crologger.info("Vymazávám dočasně stažené soubory.")
    try:
        shutil.rmtree(TEST_DOWNLOAD_DIR)
    except DeleteTmpDirError as e:
        print(e)
    print("OK")


async def download_single_novel(
    url: str, audio_format: Optional[AudioFormat] = None
) -> None:
    """
    Download just a single novel. This one should be available anytime on Mujrozhlas.cz.

    Works by Cesky Rozhlas are usually available in mp3 format.
    """
    novel = AudioWork(url=url, audiowork_dir=TEST_DOWNLOAD_DIR)
    try:
        print(novel.audio_formats)
        await novel.download(audio_format)
    except NovelDownloadError as e:
        print(e)


async def download_a_series(
    url: str, audio_format: Optional[AudioFormat] = None
) -> None:
    """A series by Cesky Rozhlas. Consists of 5 episodes."""

    series = Series(url=url, download_dir=TEST_DOWNLOAD_DIR)
    try:
        await series.download(audio_format)
    except SeriesDownloadError as e:
        print(e)


def download_example(
    message: str, test: Callable, url: str, audio_format: Optional[AudioFormat] = None
) -> None:
    print(
        "-------------------------------------------------------------------------------------------------------"
    )
    print(f"[bold blue]Test: {message}[/bold blue]")
    print(
        "-------------------------------------------------------------------------------------------------------"
    )

    asyncio.run(test(url, audio_format))
    print("Hotovo.\n")


def run_tests() -> None:
    """Run all tests."""

    # --------------------------------- MP3 ---------------------------------
    download_example(
        "Povídka ve formátu MP3",
        download_single_novel,
        url="https://www.mujrozhlas.cz/hororove-povidky/lukas-vavrecka-kousacek-ve-starem-mlyne-za-vsi-ziji-bytosti-ktere-nemel-nikdo",
        audio_format=AudioFormat.MP3,
    )

    # --------------------------------- HLS ---------------------------------
    # Shows broadcasted in streams (HSL, DASH) are usually time-limited. In case they are not available at the time of testing,
    # try some newer show.

    download_example(
        "Seriál ve formátu streamu MP3",
        download_a_series,
        url="https://www.mujrozhlas.cz/tip-mujrozhlas/lewis-carroll-alenka-v-kraji-divu",
        audio_format=AudioFormat.MP3,
    )

    # --------------------------------- DASH ---------------------------------
    # download_example(
    #     "Povídka ve formátu streamu DASH",
    #     download_single_novel,
    #     url="https://www.mujrozhlas.cz/setkani-s-literaturou/montague-rhodes-james-album-kanovnika-alberika-straslivy-pribeh-o-setkani-s",
    #     audio_format=AudioFormat.DASH,
    # )

    # Delete tmp folder with downloaded files
    delete_tmp_download()


if __name__ == "__main__":
    run_tests()
