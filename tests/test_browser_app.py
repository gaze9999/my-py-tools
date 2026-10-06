from __future__ import annotations

import http.client
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from gui.browser_app import BrowserApi, BrowserServer
from gui.launcher import gui_defaults
from gui.runtime import runner_path


class BrowserTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        index = self.directory / "index.html"
        index.write_text("<html><head></head><body>shared interface</body></html>", encoding="utf-8")
        defaults = gui_defaults()
        defaults.update(browser=True, cwd=str(self.directory))
        self.api = BrowserApi(defaults)
        self.server = BrowserServer(self.api, index)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close)

    def close(self):
        if self.thread.is_alive():
            self.server.shutdown()
        self.server.close()
        self.thread.join(3)

    def request(self, name, arguments=None, **overrides):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        headers = {"Origin": self.server.origin, "Cookie": f"{self.server.cookie_name}={self.server.token}", "X-My-Py-Tools": "1", "Content-Type": "application/json"}
        headers.update(overrides)
        try:
            connection.request("POST", "/api/" + name, json.dumps([] if arguments is None else arguments), headers)
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def test_page_is_shared_and_cookie_is_private(self):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port)
        connection.request("GET", "/")
        response = connection.getresponse()
        self.assertIn("HttpOnly; SameSite=Strict", response.getheader("Set-Cookie"))
        self.assertIn("frame-ancestors 'none'", response.getheader("Content-Security-Policy"))
        self.assertIn(b"__MY_PY_TOOLS_BROWSER__=true", response.read())
        connection.close()
        status, data = self.request("bootstrap")
        self.assertEqual(status, 200)
        self.assertTrue(data["value"]["defaults"]["browser"])

    def test_foreign_host_origin_missing_auth_and_private_methods_are_rejected(self):
        for headers in ({"Host": "evil.example"}, {"Origin": "https://evil.example"}, {"Cookie": ""}, {"X-My-Py-Tools": ""}):
            with self.subTest(headers=headers):
                self.assertEqual(self.request("bootstrap", **headers)[0], 403)
        self.assertEqual(self.request("_shutdown")[0], 404)
        self.assertEqual(self.request("bootstrap", Cookie=f'{self.server.cookie_name}="\\351"')[0], 403)
        self.assertEqual(self.request("bootstrap", {})[0], 400)
        self.assertEqual(self.request("bootstrap", **{"Content-Type": "text/plain"})[0], 400)
        self.assertEqual(self.request("start_tool", ["os", "", str(self.directory), ""])[0], 400)

    def test_document_conversion_uses_original_local_path(self):
        source = self.directory / "中文 source.txt"
        source.write_text("本機來源\nBrowser test\n", encoding="utf-8")
        status, arguments = self.request("document_arguments", [[str(source)], "source", "", False])
        self.assertEqual(status, 200)
        status, started = self.request("start_tool", ["document-to-markdown", arguments["value"], str(self.directory), self.api._defaults["python"]])
        self.assertEqual(status, 200)
        run_id = started["value"]["run_id"]
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            status, state = self.request("run_status", [run_id])
            if not state["value"]["running"]:
                break
            time.sleep(0.05)
        self.assertEqual(state["value"]["exit_code"], 0, state)
        self.assertTrue(source.with_suffix(".md").is_file())

    def test_picker_cancel_and_shutdown_preserve_owned_lifecycle(self):
        with patch.object(self.api, "_choose", return_value=[]):
            self.assertEqual(self.request("choose_files", [True])[1]["value"], [])
        self.assertEqual(self.request("choose_files", ["bad"])[0], 400)
        self.assertEqual(self.request("close_service")[0], 200)
        self.thread.join(3)
        self.assertFalse(self.thread.is_alive())
        self.server.close()
        with self.assertRaisesRegex(RuntimeError, "stopped"):
            self.api.start_tool("tokenizer", "--text hello", str(self.directory), "")

    def test_browser_mode_uses_the_cli_executable_as_worker(self):
        with patch("sys.frozen", True, create=True), patch("sys.executable", str(self.directory / "launch-cli.exe")):
            self.assertEqual(runner_path(), self.directory / "launch-cli.exe")
