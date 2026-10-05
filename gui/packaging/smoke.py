"""Verify real native rendering and the Python bridge without modifying user files."""

from __future__ import annotations

import json
import logging
from pathlib import Path
import tempfile
import time

from gui.runtime import log_root


def call_bridge(window, name: str, *args):
    window.run_js(
        "window.__smokeBridge=null;window.pywebview.api." + name + "("
        + ",".join(json.dumps(value) for value in args)
        + ").then(value=>{window.__smokeBridge={ok:true,value};})"
        + ".catch(error=>{window.__smokeBridge={ok:false,error:String(error)};});"
    )
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        response = window.evaluate_js("window.__smokeBridge")
        if isinstance(response, dict):
            if not response.get("ok"):
                raise RuntimeError(str(response.get("error")))
            return response.get("value")
        time.sleep(0.1)
    raise RuntimeError("Desktop bridge timed out: " + name)


def smoke_window(window, api, result: dict[str, int]) -> None:
    evidence: dict[str, object] = {}
    original_language = api._defaults.get("language", "zh-TW")
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
        data = call_bridge(window, "bootstrap")
        evidence["tool_count"] = len(data["tools"])
        with tempfile.TemporaryDirectory(prefix="my-py-tools-smoke-") as temporary:
            source = Path(temporary) / "中文 source document.txt"
            source.write_text("文件轉換測試\nHello from the portable GUI\n", encoding="utf-8")
            arguments = call_bridge(window, "document_arguments", [str(source)], "source", "", False)
            running = call_bridge(window, "start_tool", "document-to-markdown", arguments, temporary, str(api._defaults.get("python") or ""))
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
            for language, expected_title in (("en", "Documents to Markdown"), ("zh-TW", "文件轉 Markdown")):
                window.run_js(
                    "(()=>{const el=document.querySelector('.language-picker select');"
                    "el.value=" + json.dumps(language) + ";el.dispatchEvent(new Event('change',{bubbles:true}));})()"
                )
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    if window.evaluate_js("document.querySelector('.hero h1').textContent") == expected_title:
                        break
                    time.sleep(0.1)
                else:
                    raise RuntimeError("Language switch did not update the tool: " + language)
                from gui.preferences import load_language

                deadline = time.monotonic() + 5
                while load_language() != language and time.monotonic() < deadline:
                    time.sleep(0.1)
                if load_language() != language:
                    raise RuntimeError("Language preference was not saved")
                if not window.evaluate_js("document.querySelector('.file-list').textContent.includes('source document.txt')"):
                    raise RuntimeError("Language switch cleared selected files")
                if window.evaluate_js("document.documentElement.lang") != language:
                    raise RuntimeError("Document language did not update")
                if window.evaluate_js("document.documentElement.scrollWidth > innerWidth"):
                    raise RuntimeError("Localized desktop page has horizontal overflow")
                evidence["language_" + language] = True
        evidence["passed"] = True
    except Exception as error:
        logging.exception("Desktop smoke test failed")
        evidence.update(passed=False, error=str(error))
        result["exit_code"] = 1
    finally:
        try:
            api.set_language(original_language)
        except OSError:
            logging.exception("Could not restore the language preference after smoke testing")
        folder = log_root()
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "desktop-smoke.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
        window.destroy()
