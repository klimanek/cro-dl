import shutil
import pytest

from crodl.settings import DOWNLOAD_PATH


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_dirs():
    """Removing dirs created during testing."""
    yield  # Running tests

    shutil.rmtree(DOWNLOAD_PATH / "audio_title", ignore_errors=True)
    shutil.rmtree(DOWNLOAD_PATH / "Some Title", ignore_errors=True)
