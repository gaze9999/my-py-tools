"""Verify real native rendering and the Python bridge without modifying user files."""

from __future__ import annotations

import json
import logging
from pathlib import Path
import tempfile
import time

from gui.runtime import log_root


def smoke_window(window, api, result: dict[str, int]) -> None:
    evidence: dict[str, object] = {}
    try:
        deadline = time.monotonic() + 20
        title = ""
        while time.monotonic() < deadline:
            title = window.evaluate_js("document.querySelector('.hero h1')?.textContent || ''")
            if title:
                break
            time.sleep(0.1)
        if not title:
            raise RuntimeError("React did not render")
        evidence["rendered_tool"] = title
        evidence["horizontal_overflow"] = window.evaluate_js("document.documentElement.scrollWidth > innerWidth")
        if evidence["horizontal_overflow"]:
            raise RuntimeError("Desktop page has horizontal overflow")
        data = api.bootstrap()
        evidence["tool_count"] = len(data["tools"])
        with tempfile.TemporaryDirectory(prefix="my-py-tools-smoke-") as temporary:
            source = Path(temporary) / "中文 source document.txt"
            source.write_text("文件轉換測試\nHello from the portable GUI\n", encoding="utf-8")
            arguments = api.document_arguments([str(source)], "source", "", False)
            running = api.start_tool("document-to-markdown", arguments, temporary, str(api._defaults.get("python") or ""))
            deadline = time.monotonic() + 30
            while running["running"] and time.monotonic() < deadline:
                time.sleep(0.1)
                running = api.run_status(running["run_id"])
            if running["running"] or running["exit_code"] != 0:
                raise RuntimeError("Bundled extraction failed: " + running["output"])
            evidence["document_conversion"] = source.with_suffix(".md").is_file()
            if not evidence["document_conversion"]:
                raise RuntimeError("Markdown output was not created")
            window.run_js("window.dispatchEvent(new CustomEvent('native-files-dropped', {detail:" + json.dumps([str(source)]) + "}));")
            time.sleep(0.3)
            evidence["drop_ui_updated"] = bool(window.evaluate_js("document.querySelector('.file-list')?.textContent.includes('source document.txt')"))
            if not evidence["drop_ui_updated"]:
                raise RuntimeError("Drop event did not update React")
        evidence["passed"] = True
    except Exception as error:
        logging.exception("Desktop smoke test failed")
        evidence.update(passed=False, error=str(error))
        result["exit_code"] = 1
    finally:
        folder = log_root()
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "desktop-smoke.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
        window.destroy()
