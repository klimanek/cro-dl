"""The console entry point, exercised the way a user runs it."""

import subprocess
import sys
import unittest
from unittest import mock

from crodl import __version__
from crodl.main import run


class TestTheEntryPointFunction(unittest.TestCase):
    def test_it_calls_the_command(self):
        with mock.patch("crodl.main.main") as command:
            run()

        command.assert_called_once_with()


class TestTheEntryPoint(unittest.TestCase):
    def test_it_answers_version(self):
        result = subprocess.run(
            [sys.executable, "-m", "crodl.run", "--version"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(__version__, result.stdout)


if __name__ == "__main__":
    unittest.main()
