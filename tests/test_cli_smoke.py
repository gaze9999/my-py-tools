from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

from gui.catalog import TOOLS


MODULES = tuple(tool.module for tool in TOOLS) + ("gui.launcher", "gui.background_launcher")


class CliSmokeTests(unittest.TestCase):
    def test_every_command_exposes_help_without_side_effects(self) -> None:
        repository = Path(__file__).resolve().parents[1]
        for module in MODULES:
            with self.subTest(module=module):
                result = subprocess.run(
                    [sys.executable, "-m", module, "--help"],
                    cwd=repository,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("usage:", result.stdout.casefold())


if __name__ == "__main__":
    unittest.main()
