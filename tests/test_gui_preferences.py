from __future__ import annotations

import json
import inspect
from pathlib import Path
import tempfile
import unittest

from gui.catalog import ToolSpec
from gui.preferences import load_language, save_language
from gui.webview_app import DesktopApi


class GuiPreferenceTests(unittest.TestCase):
    def test_bridge_parameters_do_not_shadow_javascript_arguments(self) -> None:
        for name, method in inspect.getmembers(DesktopApi, inspect.isfunction):
            if not name.startswith("_"):
                self.assertNotIn("arguments", inspect.signature(method).parameters, name)

    def test_missing_invalid_and_malformed_preferences_use_chinese(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary, "preferences.json")
            self.assertEqual(load_language(path), "zh-TW")
            for value in ('invalid', '{"language": "ja"}', '[]', '{"language": []}'):
                path.write_text(value, encoding="utf-8")
                self.assertEqual(load_language(path), "zh-TW")

    def test_choice_is_saved_and_invalid_choice_preserves_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary, "settings", "preferences.json")
            save_language("en", path)
            self.assertEqual(load_language(path), "en")
            original = path.read_bytes()
            with self.assertRaises(ValueError):
                save_language("ja", path)
            self.assertEqual(path.read_bytes(), original)
            save_language("zh-TW", path)
            self.assertEqual(load_language(path), "zh-TW")
            self.assertFalse(list(path.parent.glob("*.tmp")))

    def test_tool_locale_maps_roundtrip_in_bundled_catalog(self) -> None:
        tool = ToolSpec("example", "example.tool", "Example", "範例", "說明", translations={"en": {"name": "Example"}})
        restored = ToolSpec(**json.loads(json.dumps(tool.payload())))
        self.assertEqual(restored.translations, tool.translations)
