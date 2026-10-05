"""Host the built React interface in a native pywebview window."""

from __future__ import annotations

import json
import logging
from pathlib import Path
import sys
from typing import Any

from gui.catalog import DISCOVERY_WARNINGS, TOOLS
from gui.launcher import ProcessManager, SUPPORTED_DOCUMENT_SUFFIXES, append_arguments, command_text
from shared.version import repository_version
from gui.runtime import is_bundled, resource_root, runner_path
from gui.preferences import save_language


def resource_path(relative: str) -> Path:
    return resource_root() / relative


class DesktopApi:
    def __init__(self, defaults: dict[str, object]) -> None:
        self._defaults = defaults
        self._manager = ProcessManager()
        self._window: Any = None

    def bootstrap(self) -> dict[str, object]:
        tools = [tool.payload() for tool in TOOLS]
        if sys.platform != "win32":
            for tool in tools:
                tool["example_args"] = str(tool["example_args"]).replace("C:\\path\\", "/path/").replace("\\", "/")
        return {
            "version": repository_version(resource_path("")),
            "tools": tools,
            "categories": list(dict.fromkeys(tool.category for tool in TOOLS)),
            "warnings": DISCOVERY_WARNINGS,
            "defaults": self._defaults,
            "supportedExtensions": sorted(SUPPORTED_DOCUMENT_SUFFIXES),
            "runtimeLabel": "內建 Python 執行環境" if self._defaults.get("bundled") else str(self._defaults.get("python") or ""),
        }

    def choose_files(self, documents_only: bool = False) -> list[str]:
        import webview

        english = self._defaults.get("language") == "en"
        all_files = "All files (*.*)" if english else "所有檔案 (*.*)"
        documents = "Supported documents" if english else "支援的文件"

        values = self._window.create_file_dialog(
            webview.FileDialog.OPEN,
            allow_multiple=True,
            file_types=(documents + " (*.pdf;*.xlsx;*.docx;*.pptx;*.csv;*.txt)", all_files) if documents_only else (all_files,),
        )
        return list(values or ())

    def set_language(self, language: str) -> None:
        save_language(language)
        self._defaults["language"] = language

    def choose_folder(self) -> str:
        import webview

        values = self._window.create_file_dialog(webview.FileDialog.FOLDER)
        return str(values[0]) if values else ""

    def choose_python(self) -> str:
        import webview

        english = self._defaults.get("language") == "en"
        executable = "Python executable (python*.exe)" if english else "Python 執行檔 (python*.exe)"
        all_files = "All files (*.*)" if english else "所有檔案 (*.*)"

        values = self._window.create_file_dialog(
            webview.FileDialog.OPEN,
            allow_multiple=False,
            file_types=(executable, all_files) if sys.platform == "win32" else (all_files,),
        )
        return str(values[0]) if values else ""

    def normalize_documents(self, paths: list[str], current_args: str = "") -> dict[str, object]:
        candidates = [Path(value).expanduser() for value in paths]
        accepted = list(dict.fromkeys([
            str(path.resolve())
            for path in candidates
            if path.is_file() and path.suffix.casefold() in SUPPORTED_DOCUMENT_SUFFIXES
        ]))
        accepted_set = set(accepted)
        rejected = [str(path) for path in candidates if str(path.resolve()) not in accepted_set]
        return {
            "accepted": accepted,
            "rejected": rejected,
            "args": append_arguments(current_args, accepted),
            "toolId": "document-to-markdown" if accepted else None,
        }

    def preview_command(self, tool_id: str, args_text: str, python: str) -> str:
        tool = next((item for item in TOOLS if item.id == tool_id), None)
        if tool is None:
            return ""
        bundled_tool = is_bundled() and not tool.payload()["source_only"]
        runtime = str(runner_path()) if bundled_tool else python
        base = [runtime, tool.module] if bundled_tool else [runtime, "-u", "-m", tool.module]
        return f"{command_text(base)} {args_text.strip()}".strip()

    def start_tool(self, tool_id: str, args_text: str, cwd: str, python: str) -> dict[str, Any]:
        return self._manager.start(tool_id, args_text, cwd, python)

    def run_status(self, run_id: str) -> dict[str, Any]:
        return self._manager.snapshot(run_id)

    def stop_tool(self, run_id: str) -> dict[str, Any]:
        return self._manager.stop(run_id)

    def send_input(self, run_id: str, value: str) -> dict[str, Any]:
        return self._manager.send_input(run_id, value)

    def append_paths(self, current: str, paths: list[str]) -> str:
        return append_arguments(current, paths)

    def document_arguments(self, files: list[str], mode: str, output: str, dry_run: bool) -> str:
        values = list(files)
        if mode not in {"source", "directory", "combine"}:
            raise ValueError("Unknown output mode")
        if mode != "source" and output:
            values.extend(["--output-dir" if mode == "directory" else "--combine-output", output])
        if dry_run:
            values.append("--dry-run")
        return command_text(values)

    def choose_save(self) -> str:
        import webview

        values = self._window.create_file_dialog(
            webview.FileDialog.SAVE, save_filename="combined.md", file_types=("Markdown (*.md)",),
        )
        return str(values[0]) if values else ""

    def copy_text(self, value: str) -> None:
        self._window.evaluate_js(
            "(function(){const el=document.createElement('textarea');"
            "el.value=" + json.dumps(value) + ";document.body.appendChild(el);el.select();"
            "const ok=document.execCommand('copy');el.remove();if(!ok)throw Error('Unable to copy output');})()"
        )

    def _shutdown(self) -> None:
        self._manager.stop()


def _bind_native_drop(window: Any) -> None:
    from webview.dom import DOMEventHandler

    def prevent(_: dict[str, object]) -> None:
        return None

    def drop(event: dict[str, object]) -> None:
        transfer = event.get("dataTransfer")
        files = transfer.get("files", []) if isinstance(transfer, dict) else []
        paths = [item.get("pywebviewFullPath") for item in files if isinstance(item, dict)]
        paths = [value for value in paths if isinstance(value, str) and value]
        if paths:
            window.run_js(
                "window.dispatchEvent(new CustomEvent('native-files-dropped', {detail: "
                + json.dumps(paths, ensure_ascii=False)
                + "}));"
            )

    document_events = window.dom.document.events
    document_events.dragenter += DOMEventHandler(prevent, True, True)
    document_events.dragover += DOMEventHandler(prevent, True, True, debounce=100)
    document_events.drop += DOMEventHandler(drop, True, True)


def run_app(defaults: dict[str, object], *, smoke_test: bool = False) -> int:
    import webview

    index = resource_path("gui/resources/web/index.html")
    if not index.is_file():
        raise RuntimeError("React GUI bundle is missing; run npm run build in gui/frontend")
    api = DesktopApi(defaults)
    window = webview.create_window(
        f"My Py Tools v{repository_version(resource_path(''))}",
        html=index.read_text(encoding="utf-8"),
        js_api=api,
        width=1320,
        height=880,
        min_size=(940, 700),
        background_color="#090c10",
        text_select=True,
        confirm_close=not smoke_test,
    )
    api._window = window
    window.events.closed += api._shutdown

    def bind(_: Any = None) -> None:
        try:
            _bind_native_drop(window)
        except Exception:
            logging.exception("Native drag-and-drop unavailable; use the file picker")

    window.events.loaded += bind
    smoke_result = {"exit_code": 0}
    if smoke_test:
        from gui.packaging.smoke import smoke_window

        window.events.loaded += lambda _=None: smoke_window(window, api, smoke_result)
    webview.start(gui="edgechromium" if sys.platform == "win32" else "cocoa" if sys.platform == "darwin" else None, debug=False)
    return smoke_result["exit_code"]
