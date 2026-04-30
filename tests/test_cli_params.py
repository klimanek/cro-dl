import unittest
from pathlib import Path
from unittest.mock import MagicMock
from crodl.program.audiowork import AudioWork
from crodl.program.series import Series
from crodl.settings import DOWNLOAD_PATH


class TestCLIParamsIntegration(unittest.TestCase):
    def setUp(self):
        self.mock_client = MagicMock()
        # Mock episode data
        self.mock_client.get_episode_data.return_value = {
            "data": {
                "attributes": {
                    "title": "Příliš žluťoučký kůň",
                    "since": "2024-04-29T12:00:00Z",
                    "audioLinks": [
                        {"variant": "mp3", "url": "http://example.com/a.mp3"}
                    ],
                }
            }
        }
        # Mock series data
        self.mock_client.get_series_data.return_value = {
            "data": {
                "attributes": {
                    "title": "Seriál s diakritikou",
                    "totalParts": 5,
                    "playable": True,
                }
            }
        }

    def test_audiowork_custom_title_and_accents(self):
        """Test AudioWork with custom title and accent removal."""
        aw = AudioWork(
            url="http://example.com/show",
            title="Můj Vlastní Název",
            remove_accents=True,
            client=self.mock_client,
        )
        self.assertEqual(aw.title, "Můj Vlastní Název")
        # Check that download dir is sanitized and has no accents
        self.assertEqual(aw.audiowork_dir.name, "Muj Vlastni Nazev")

    def test_audiowork_custom_output_dir(self):
        """Test AudioWork with custom output directory."""
        custom_path = Path("/tmp/my_audio")
        aw = AudioWork(
            url="http://example.com/show",
            audiowork_dir=custom_path,
            client=self.mock_client,
        )
        self.assertEqual(aw.audiowork_dir, custom_path)

    def test_series_custom_title_and_accents(self):
        """Test Series with custom title and accent removal."""
        # We need to mock get_series_id since it's called in __post_init__
        self.mock_client.get_series_id.return_value = "123"

        s = Series(
            url="http://example.com/series",
            title="Custom Series",
            remove_accents=True,
            client=self.mock_client,
        )
        self.assertEqual(s.title, "Custom Series")
        # Check download_dir (should be under SERIES_DOWNLOAD_DIR / processed_title)
        self.assertIn("Custom Series", str(s.download_dir))


if __name__ == "__main__":
    unittest.main()
