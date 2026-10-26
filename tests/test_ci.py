import re
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def _version(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in text.split("."))


def declared_floor() -> str:
    """The lowest Python `pyproject.toml` promises, as the workflow writes it."""
    project = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    specifier = re.search(r'requires-python\s*=\s*"([^"]+)"', project)

    assert specifier is not None, "pyproject.toml has no requires-python"

    floor = re.search(r">=\s*(\d+\.\d+)", specifier.group(1))

    assert floor is not None, f"no lower bound in {specifier.group(1)!r}"

    return floor.group(1)


class TestThePythonFloorIsTested(unittest.TestCase):
    """
    The pipeline has to try the version the project claims.

    `pyproject.toml` and both READMEs say 3.10; a floor nobody installs is a
    promise nobody keeps, so the CI matrix starts there. Raising the floor means
    changing the project metadata, the README and the matrix together - these
    tests are what makes that hard to forget.
    """

    def setUp(self):
        self.workflow = yaml.safe_load(
            (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        )

    def test_the_matrix_starts_at_the_declared_floor(self):
        matrix = self.workflow["jobs"]["tests"]["strategy"]["matrix"]["python"]

        self.assertEqual(
            matrix, sorted(matrix, key=_version), "keep the matrix ordered"
        )
        self.assertEqual(matrix[0], declared_floor(), f"the workflow tries {matrix}")

    def test_every_workflow_parses(self):
        # A typo in a workflow only shows up when it runs - and the release one
        # only runs on a tag, which is the worst possible moment to find out.
        files = sorted((ROOT / ".github").rglob("*.yml"))

        self.assertTrue(files, "no workflow files found")

        for path in files:
            with self.subTest(file=str(path.relative_to(ROOT))):
                self.assertIsInstance(
                    yaml.safe_load(path.read_text(encoding="utf-8")), dict
                )

    def test_the_readme_repeats_the_same_floor(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        floor = declared_floor()

        self.assertIn(f"Python {floor}+", readme)
        self.assertIn(f"alespoň {floor}", readme)


if __name__ == "__main__":
    unittest.main()
