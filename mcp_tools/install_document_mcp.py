"""Preview or register Local Documents in Codex without changing other settings."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import uuid

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", type=Path, required=True, help="Python from the dedicated environment")
    parser.add_argument("--config", type=Path, default=Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")) / "config.toml")
    parser.add_argument("--read-root", type=Path, action="append", required=True)
    parser.add_argument("--write-root", type=Path, action="append", default=[])
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    executable = args.python.expanduser().resolve(strict=True)
    config = args.config.expanduser().resolve(strict=True)
    script = Path(__file__).with_name("document_server.py").resolve(strict=True)
    from mcp_tools.document_service import DocumentService
    service = DocumentService(args.read_root, args.write_root)
    subprocess.run([str(executable), "-c", "import mcp,rapidocr,onnxruntime,pypdfium2,pypdf,pdfplumber,openpyxl,docx,pptx"], check=True)
    arguments = ["-B", str(script)]
    for kind, roots in (("--read-root", service.read_roots), ("--write-root", service.write_roots)):
        for root in roots:
            arguments.extend((kind, str(root)))
    section = "[mcp_servers.local_documents]\n" + "command = " + json.dumps(str(executable), ensure_ascii=False) + "\n"
    section += "args = " + json.dumps(arguments, ensure_ascii=False) + "\n"
    section += 'enabled = true\nstartup_timeout_sec = 120\ntool_timeout_sec = 300\nenabled_tools = ["document_status", "extract_document", "inspect_markdown", "update_markdown"]\n'
    before = config.read_bytes()
    text = before.decode("utf-8-sig")
    match = re.search(r"(?m)^\[mcp_servers\.local_documents\][ \t]*\r?$", text)
    if match:
        following = re.search(r"(?m)^\[", text[match.end():])
        end = match.end() + following.start() if following else len(text)
        text = text[:match.start()] + section + "\n" + text[end:]
    else:
        text = text.rstrip() + "\n\n" + section
    parsed = tomllib.loads(text)
    original = tomllib.loads(before.decode("utf-8-sig"))
    if parsed == original:
        print(json.dumps({"status": "unchanged", "config": str(config)}, ensure_ascii=False))
        return
    old_servers = original.get("mcp_servers", {}).copy()
    old_servers.pop("local_documents", None)
    other_servers = parsed.get("mcp_servers", {}).copy()
    other_servers.pop("local_documents", None)
    if other_servers != old_servers or {k: v for k, v in parsed.items() if k != "mcp_servers"} != {k: v for k, v in original.items() if k != "mcp_servers"}:
        raise ValueError("Unrelated settings changed")
    if args.apply:
        backup = config.with_name(config.name + ".before-local-documents-" + uuid.uuid4().hex[:8] + ".bak")
        with backup.open("xb") as handle:
            handle.write(before)
        after = (b"\xef\xbb\xbf" if before.startswith(b"\xef\xbb\xbf") else b"") + text.encode("utf-8")
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=config.parent, delete=False) as handle:
                temporary = Path(handle.name)
                handle.write(after)
                handle.flush()
                os.fsync(handle.fileno())
            if config.read_bytes() != before:
                raise ValueError("Config changed; inspect before retry")
            os.replace(temporary, config)
            temporary = None
            if config.read_bytes() != after:
                raise ValueError("Config readback mismatch; inspect backup")
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        print(json.dumps({"status": "installed", "config": str(config), "backup": str(backup)}, ensure_ascii=False))
    else:
        print(json.dumps({"status": "preview", "server": parsed["mcp_servers"]["local_documents"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
