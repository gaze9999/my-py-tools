from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest

from gui.catalog import EXCLUDED_MODULES, TOOLS, TOOLS_BY_ID, ToolSpec, discover_tools
from gui.launcher import (
    ProcessManager,
    SUPPORTED_DOCUMENT_SUFFIXES,
    append_arguments,
    gui_defaults,
    split_cli_args,
)
from shared.version import repository_version


class GuiCatalogTests(unittest.TestCase):
    def test_catalog_has_unique_importable_modules(self) -> None:
        self.assertGreaterEqual(len(TOOLS), 16)
        self.assertFalse(any(tool.module.startswith("mcp_tools.") for tool in TOOLS))
        self.assertEqual(len(TOOLS_BY_ID), len(TOOLS))
        self.assertTrue(EXCLUDED_MODULES.isdisjoint(tool.module for tool in TOOLS))
        for tool in TOOLS:
            with self.subTest(module=tool.module):
                self.assertIsNotNone(importlib.util.find_spec(tool.module))

    def test_repository_version_is_valid(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "VERSION").write_text("0.3.0\n", encoding="utf-8")
            self.assertEqual(repository_version(root), "0.3.0")
            (root / "VERSION").write_text("invalid\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                repository_version(root)

    def test_new_main_module_is_discovered_without_catalog_edit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            package = root / "new_tools"
            package.mkdir()
            (package / "convert_report.py").write_text(
                '"""Convert a report."""\n\ndef main():\n    return 0\n\n'
                'if __name__ == "__main__":\n    raise SystemExit(main())\n',
                encoding="utf-8",
            )
            (package / "helper.py").write_text("def helper():\n    return True\n", encoding="utf-8")

            tools = discover_tools(root)

        self.assertEqual([tool.module for tool in tools], ["new_tools.convert_report"])
        self.assertEqual(tools[0].category, "New Tools")

    def test_nested_module_and_discovery_error_are_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            package = root / "reports" / "converters"
            package.mkdir(parents=True)
            (package / "nested.py").write_text(
                'if __name__ == "__main__":\n    raise SystemExit(0)\n',
                encoding="utf-8",
            )
            (package / "broken.py").write_text("def broken(:\n", encoding="utf-8")
            warnings: list[str] = []

            tools = discover_tools(root, warnings)

        self.assertEqual([tool.module for tool in tools], ["reports.converters.nested"])
        self.assertEqual(len(warnings), 1)
        self.assertIn("reports/converters/broken.py", warnings[0])

    def test_split_cli_args_preserves_quoted_values(self) -> None:
        self.assertEqual(
            split_cli_args('--text "hello world" --json'),
            ["--text", "hello world", "--json"],
        )

    def test_dragged_document_paths_are_appended_as_cli_arguments(self) -> None:
        paths = [r"C:\source files\spec.docx", r"C:\source files\api.xlsx"]
        value = append_arguments("--dry-run", paths)

        self.assertEqual(split_cli_args(value), ["--dry-run", *paths])
        self.assertEqual(
            SUPPORTED_DOCUMENT_SUFFIXES,
            {".pdf", ".xlsx", ".docx", ".pptx", ".csv", ".txt"},
        )

    def test_dropped_files_preselect_document_conversion(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            source = Path(temporary_directory, "source document.docx")
            source.touch()
            defaults = gui_defaults([source.resolve()])

            self.assertEqual(defaults["tool_id"], "document-to-markdown")
            self.assertEqual(split_cli_args(str(defaults["args"])), [str(source.resolve())])


class GuiProcessTests(unittest.TestCase):
    def test_manager_runs_whitelisted_tool_and_captures_output(self) -> None:
        repository = Path(__file__).resolve().parents[1]
        manager = ProcessManager()
        result = manager.start(
            "tokenizer",
            '--text "hello world" --json',
            str(repository),
            sys.executable,
        )
        deadline = time.monotonic() + 15
        while result["running"] and time.monotonic() < deadline:
            time.sleep(0.05)
            result = manager.snapshot(result["run_id"])
        if result["running"]:
            manager.stop(result["run_id"])
            self.fail("GUI tool process did not finish in time")

        self.assertEqual(result["exit_code"], 0, result["output"])
        payload = json.loads(result["output"])
        self.assertEqual(payload["chars"], 11)
        self.assertIn(payload["method"], {"tiktoken", "fallback"})

    def test_manager_rejects_unknown_tool(self) -> None:
        manager = ProcessManager()
        with self.assertRaisesRegex(ValueError, "Unknown tool"):
            manager.start("not-in-catalog", "", str(Path.cwd()), sys.executable)

    def test_stop_terminates_child_process_tree(self) -> None:
        repository = Path(__file__).resolve().parents[1]
        manager = ProcessManager()
        with tempfile.TemporaryDirectory() as temporary_directory:
            marker = Path(temporary_directory, "child-finished.txt")
            spec = ToolSpec(
                "spawn-child-test",
                "tests.spawn_child_tool",
                "Test",
                "Spawn child",
                "Test helper",
            )
            TOOLS_BY_ID[spec.id] = spec
            try:
                result = manager.start(
                    spec.id,
                    f'"{marker}"',
                    str(repository),
                    sys.executable,
                )
                deadline = time.monotonic() + 5
                while "child started" not in result["output"] and time.monotonic() < deadline:
                    time.sleep(0.05)
                    result = manager.snapshot(result["run_id"])
                self.assertIn("child started", result["output"])
                manager.stop(result["run_id"])
                time.sleep(2.5)
                self.assertFalse(marker.exists())
            finally:
                TOOLS_BY_ID.pop(spec.id, None)


if __name__ == "__main__":
    unittest.main()
