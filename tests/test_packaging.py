import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = (ROOT / "pyproject.toml").read_text(encoding="utf-8")


class TestTheWebFilesArePackaged(unittest.TestCase):
    """
    The pages and the player script have to reach an installed copy.

    They did not in 2.0.0: the wheel carried the Python code only, so `cro-dl
    server` died in `StaticFiles` with "Directory ... does not exist" before it
    answered anything. Nothing else in the suite notices, because the source tree
    has both directories whatever the packaging says.
    """

    def test_the_data_directories_are_declared_as_package_data(self):
        self.assertIn("[tool.setuptools.package-data]", PYPROJECT)
        section = PYPROJECT.split("[tool.setuptools.package-data]", 1)[1]

        self.assertIn('"crodl.server"', section)
        self.assertIn('"static/*"', section)
        self.assertIn('"templates/*"', section)

    def test_the_directories_are_where_the_packaging_expects_them(self):
        server = ROOT / "crodl" / "server"

        self.assertTrue((server / "static" / "player.js").is_file())
        self.assertTrue(list((server / "templates").glob("*.html")))


if __name__ == "__main__":
    unittest.main()
