from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from shared.config import ToolConfig


class ToolConfigTests(unittest.TestCase):
    def test_invalid_lines_fail_open_and_valid_variables_expand(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory, ".env")
            env_file.write_text(
                "\n".join(
                    (
                        "TOOL_BASE=alpha",
                        "TOOL_EXPANDED=${TOOL_BASE}-beta",
                        "TOOL_BASE=ignored",
                        "INVALID=value",
                        'TOOL_BROKEN="open',
                    )
                ),
                encoding="utf-8",
            )

            config = ToolConfig(env_file)

            self.assertEqual(config.value("TOOL_BASE"), "alpha")
            self.assertEqual(config.value("TOOL_EXPANDED"), "alpha-beta")
            self.assertGreaterEqual(len(config.warnings), 3)

    def test_process_environment_overrides_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory, ".env")
            env_file.write_text("TOOL_TOKENIZER_ENCODING=file-value\n", encoding="utf-8")
            with patch.dict(os.environ, {"TOOL_TOKENIZER_ENCODING": "process-value"}):
                config = ToolConfig(env_file)

            self.assertEqual(config.value("TOOL_TOKENIZER_ENCODING"), "process-value")

    def test_invalid_numbers_and_namespace_use_safe_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory, ".env")
            env_file.write_text(
                "TOOL_RATIO=NaN\nTOOL_HISTORY_NAMESPACE=not valid!\n",
                encoding="utf-8",
            )
            config = ToolConfig(env_file)

            self.assertEqual(config.positive_float("TOOL_RATIO", 4), 4)
            self.assertEqual(config.namespace(), "project-task")
            self.assertEqual(len(config.warnings), 2)

    def test_missing_selected_file_warns_but_does_not_raise(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory, "missing.env")
            config = ToolConfig(missing)

            self.assertEqual(config.value("TOOL_UNKNOWN", "fallback"), "fallback")
            self.assertEqual(len(config.warnings), 1)


if __name__ == "__main__":
    unittest.main()
