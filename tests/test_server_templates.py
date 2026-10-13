import unittest
from pathlib import Path

TEMPLATES = Path(__file__).resolve().parent.parent / "crodl" / "server" / "templates"


def page_templates() -> list[Path]:
    """The templates that are pages, not the partials they include."""
    return sorted(
        path for path in TEMPLATES.glob("*.html") if not path.name.startswith("_")
    )


class TestThePlayerIsIncludedOnce(unittest.TestCase):
    """
    The player bar belongs to the top bar, and to nothing else.

    Both used to include it, so the library page and the queue page carried two
    bars, two <audio> elements and two copies of player.js. Each copy wired the
    same buttons, so one click on pause called play() and then pause() - the
    reported "Pause nefunguje" - and pressing play in the bar did nothing.
    """

    def test_every_page_brings_the_player_exactly_once(self):
        """
        Either the page includes it, or the top bar it includes does - never both.

        Two copies of player.js wire the same buttons twice, which is what made a
        single click on pause call play() and then pause().
        """
        top = (TEMPLATES / "_top.html").read_text(encoding="utf-8")
        top_brings_it = '{% include "_player.html" %}' in top

        self.assertTrue(page_templates(), "the templates are not where they should be")

        for page in page_templates():
            text = page.read_text(encoding="utf-8")
            count = text.count('{% include "_player.html" %}')

            if top_brings_it and '{% include "_top.html" %}' in text:
                count += 1

            with self.subTest(page=page.name):
                self.assertEqual(
                    count, 1, f"{page.name} would carry the player {count} times"
                )


if __name__ == "__main__":
    unittest.main()
