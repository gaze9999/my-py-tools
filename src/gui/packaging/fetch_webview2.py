"""Download a hash-reviewed Microsoft Fixed Version CAB without installing it."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, build_opener

from gui.packaging.webview2 import validate_runtime


def validate_url(value: str) -> str:
    url = urlsplit(value)
    host = (url.hostname or "").lower()
    allowed = host in {"download.microsoft.com", "download.visualstudio.microsoft.com"} or host.endswith(".delivery.mp.microsoft.com")
    if url.scheme != "https" or not allowed or url.username or url.password or url.port not in {None, 443}:
        raise ValueError("Use an HTTPS Fixed Version download URL from Microsoft's official download page")
    return value


class MicrosoftRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        validate_url(newurl)
        return super().redirect_request(request, fp, code, message, headers, newurl)


def fetch(url: str, sha256: str, output: Path, cab: Path | None = None) -> Path:
    validate_url(url)
    expected = sha256.lower()
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise ValueError("Provide the reviewed CAB SHA-256")
    if sys.platform != "win32":
        raise ValueError("Extract the Windows CAB on Windows")
    output = output.expanduser().resolve()
    if output.exists():
        raise ValueError(f"Output already exists, never overwritten: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="webview2-", dir=output.parent) as temporary:
        staging = Path(temporary)
        cabinet = staging / "runtime.cab"
        checksum = hashlib.sha256()
        opener = build_opener(MicrosoftRedirects())
        response = cab.expanduser().resolve().open("rb") if cab is not None else opener.open(url, timeout=60)
        with response, cabinet.open("wb") as stream:
            while block := response.read(1024 * 1024):
                checksum.update(block)
                stream.write(block)
        if checksum.hexdigest() != expected:
            raise ValueError("Fixed Version CAB SHA-256 mismatch, no files were installed")
        extracted = staging / "extracted"
        extracted.mkdir()
        subprocess.run(["expand.exe", str(cabinet), "-F:*", str(extracted)], check=True, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        candidates = list(extracted.rglob("msedgewebview2.exe"))
        if len(candidates) != 1:
            raise ValueError("CAB must contain exactly one Fixed Version runtime")
        runtime = validate_runtime(candidates[0].parent)
        ready = staging / "ready"
        ready.mkdir()
        shutil.move(str(runtime), str(ready / "WebView2"))
        (ready / "runtime-source.json").write_text(json.dumps({"url": url, "sha256": expected}, indent=2) + "\n", encoding="utf-8")
        ready.rename(output)
    return output / "WebView2"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--cab", type=Path, help="Reuse an already downloaded CAB, still verifying its SHA-256")
    args = parser.parse_args(argv)
    try:
        result = fetch(args.url, args.sha256, args.output, args.cab)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"FAIL {error}", file=sys.stderr)
        return 1
    print(f"READY {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
