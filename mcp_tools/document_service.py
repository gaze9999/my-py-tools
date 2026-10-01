"""Document extraction and guarded Markdown operations, without remote APIs."""
from __future__ import annotations

import datetime as dt
import hashlib
import importlib.metadata
import importlib.util
import io
import os
from pathlib import Path
import re
import threading
import tempfile
from typing import Literal
import zipfile

from audit import source_audit_extract as audit
from markdown import guarded_markdown_update as markdown

IMAGE_TYPES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
MEDIA_PREFIXES = {".docx": "word/media/", ".xlsx": "xl/media/", ".pptx": "ppt/media/"}
MAX_FILE_BYTES = 128 * 1024 * 1024


class DocumentService:
    def __init__(self, read_roots: list[Path], write_roots: list[Path]):
        self.read_roots = tuple(self._root(path) for path in read_roots)
        self.write_roots = tuple(self._root(path) for path in write_roots)
        if not self.read_roots:
            raise ValueError("At least one explicit read root is required")
        self.lock = threading.RLock()
        self.engine = None

    @staticmethod
    def _root(path: Path) -> Path:
        if not path.is_absolute() or not path.is_dir():
            raise ValueError("Roots must be existing absolute directories")
        return path.resolve()

    def path(self, value: str, *, write: bool = False) -> Path:
        candidate = Path(value).expanduser()
        if not candidate.is_absolute():
            raise ValueError("Use an absolute path")
        candidate = candidate.resolve()
        roots = self.write_roots if write else self.read_roots
        if not any(candidate.is_relative_to(root) for root in roots):
            raise ValueError("Path is outside the configured roots")
        if write:
            if candidate.suffix.lower() != ".md" or not candidate.parent.is_dir():
                raise ValueError("Output must be a Markdown file in an existing directory")
        else:
            if not candidate.is_file():
                raise ValueError("Source file does not exist")
            if candidate.stat().st_size > MAX_FILE_BYTES:
                raise ValueError("Source exceeds the 128 MiB file limit")
        return candidate

    @staticmethod
    def clipped(text: str, limit: int) -> dict:
        if not 1 <= limit <= 200_000:
            raise ValueError("max_chars must be between 1 and 200000")
        return {"content": text[:limit], "content_chars": len(text), "truncated": len(text) > limit}

    def status(self) -> dict:
        versions = {}
        for name in ("mcp", "rapidocr", "onnxruntime", "pypdfium2", "pypdf", "pdfplumber", "openpyxl", "python-docx", "python-pptx"):
            try:
                versions[name] = importlib.metadata.version(name)
            except importlib.metadata.PackageNotFoundError:
                versions[name] = None
        try:
            models = [{"role": role, "file": path.name, "sha256": audit.sha256(path)} for role, path in self.models().items()]
        except (RuntimeError, OSError):
            models = []
        return {"status": "ready" if all(versions.values()) and models else "missing_dependencies", "versions": versions, "ocr": "local_cpu", "models": models,
                "formats": sorted(set(audit.SUPPORTED_EXTENSIONS) | IMAGE_TYPES),
                "read_roots": [str(path) for path in self.read_roots],
                "write_roots": [str(path) for path in self.write_roots],
                "source_authority": "original", "max_file_bytes": MAX_FILE_BYTES}

    @staticmethod
    def models() -> dict[str, Path]:
        specification = importlib.util.find_spec("rapidocr")
        if specification is None:
            raise RuntimeError("RapidOCR is not installed")
        root = Path(specification.origin).parent / "models"
        models = {"Det": root / "PP-OCRv6_det_small.onnx", "Cls": root / "ch_ppocr_mobile_v2.0_cls_mobile.onnx", "Rec": root / "PP-OCRv6_rec_small.onnx"}
        if not all(path.is_file() for path in models.values()):
            raise RuntimeError("Packaged OCR models are missing; reinstall the fixed RapidOCR requirement")
        return models

    def _recognize(self, image) -> dict:
        import numpy as np
        from rapidocr import RapidOCR
        if self.engine is None:
            params = {f"{role}.model_path": str(path) for role, path in self.models().items()}
            params.update({"Global.log_level": "warning", "EngineConfig.onnxruntime.intra_op_num_threads": 2,
                           "EngineConfig.onnxruntime.inter_op_num_threads": 1,
                           "EngineConfig.onnxruntime.use_cuda": False, "EngineConfig.onnxruntime.use_dml": False})
            self.engine = RapidOCR(params=params)
        result = self.engine(np.asarray(image.convert("RGB")))
        texts = list(getattr(result, "txts", None) or ())
        scores = list(getattr(result, "scores", None) or ())
        boxes = getattr(result, "boxes", None)
        lines = [{"text": str(text), "confidence": float(scores[index]) if index < len(scores) else None,
                  "box": boxes[index].tolist() if boxes is not None else None}
                 for index, text in enumerate(texts)]
        return {"engine": "rapidocr", "text": "\n".join(str(text) for text in texts), "lines": lines}

    def _ocr(self, source: Path, mode: str, max_items: int, pages: list[int] | None) -> dict:
        from PIL import Image
        records, errors = [], []
        eligible = 0
        if source.suffix.lower() == ".pdf":
            import pypdfium2 as pdfium
            from pypdf import PdfReader
            reader = PdfReader(source)
            count = len(reader.pages)
            if pages is not None and (not pages or any(type(page) is not int or not 1 <= page <= count for page in pages)):
                raise ValueError("OCR pages must contain valid 1-based PDF page numbers")
            selected = list(dict.fromkeys(pages)) if pages is not None else list(range(1, count + 1))
            selected = [page for page in selected if mode == "force" or not (reader.pages[page - 1].extract_text() or "").strip()]
            eligible = len(selected)
            with pdfium.PdfDocument(source) as document:
                for number in selected[:max_items]:
                    page = document[number - 1]
                    bitmap = None
                    try:
                        bitmap = page.render(scale=2)
                        image = bitmap.to_pil()
                        records.append({"location": f"PDF page {number}", **self._recognize(image)})
                    except Exception as exc:
                        errors.append({"location": f"PDF page {number}", "reason": str(exc)})
                    finally:
                        if bitmap is not None:
                            bitmap.close()
                        page.close()
        elif source.suffix.lower() in MEDIA_PREFIXES:
            if pages is not None:
                raise ValueError("pages is supported only for PDFs")
            with zipfile.ZipFile(source) as archive:
                names = sorted(name for name in archive.namelist() if name.startswith(MEDIA_PREFIXES[source.suffix.lower()]) and Path(name).suffix.lower() in IMAGE_TYPES)
                eligible = len(names)
                for name in names[:max_items]:
                    try:
                        if archive.getinfo(name).file_size > 32 * 1024 * 1024:
                            raise ValueError("Embedded image exceeds 32 MiB")
                        with Image.open(io.BytesIO(archive.read(name))) as image:
                            records.append({"location": name, **self._recognize(image)})
                    except Exception as exc:
                        errors.append({"location": name, "reason": str(exc)})
        elif source.suffix.lower() in IMAGE_TYPES:
            if pages is not None:
                raise ValueError("pages is supported only for PDFs")
            eligible = 1
            try:
                with Image.open(source) as image:
                    records.append({"location": source.name, **self._recognize(image)})
            except Exception as exc:
                errors.append({"location": source.name, "reason": str(exc)})
        elif pages is not None:
            raise ValueError("pages is supported only for PDFs")
        return {"status": "partial" if errors or eligible > max_items else ("used" if records else "not_needed"),
                "eligible_items": eligible, "processed_items": len(records),
                "omitted_items": max(0, eligible - max_items), "records": records, "errors": errors}

    def extract(self, source: str, output: str | None = None, write_output: bool = False,
                expected_output_sha256: str | None = None, ocr: Literal["off", "auto", "force"] = "auto",
                ocr_max_items: int = 10, pages: list[int] | None = None, max_chars: int = 30_000,
                text_encoding: str = "utf-8-sig") -> dict:
        if ocr not in {"off", "auto", "force"} or type(ocr_max_items) is not int or not 1 <= ocr_max_items <= 100:
            raise ValueError("Invalid OCR mode or item limit")
        self.clipped("", max_chars)
        if pages is not None and ocr == "off":
            raise ValueError("pages requires OCR")
        if write_output and output is None:
            raise ValueError("write_output requires an explicit output path")
        with self.lock:
            path = self.path(source)
            destination = self.path(output, write=True) if output else None
            if destination == path:
                raise ValueError("Output must not overwrite the source")
            source_hash = audit.sha256(path)
            before = destination.read_bytes() if destination and destination.exists() else None
            if before is not None and write_output and markdown.sha(before) != (expected_output_sha256 or "").lower():
                raise ValueError("Existing output requires its current SHA-256")
            if before is None and expected_output_sha256 is not None:
                raise ValueError("Expected output hash was supplied for a missing file")
            if path.suffix.lower() in IMAGE_TYPES:
                if ocr == "off":
                    raise ValueError("Image sources require OCR")
                content = f"# Image OCR: {path.name}\n\n- Source SHA-256: {source_hash}\n- Source precedence: original image\n"
                summary = "Image OCR"
            else:
                generated = audit.build_audit(path, destination or path.with_suffix(".md"), dt.datetime.now(), text_encoding=text_encoding)
                content, summary = generated.content, generated.summary
            details = self._ocr(path, ocr, ocr_max_items, pages) if ocr != "off" else {"status": "disabled", "records": [], "errors": [], "omitted_items": 0}
            if ocr != "off":
                content += "\n## MCP OCR supplement\n\nOCR text is derived, may contain recognition errors, and does not replace the original layout or native extraction\n"
                for record in details["records"]:
                    content += f"\n### {record['location']}\n\n" + audit._fenced_text(record["text"]) + "\n"
                content += f"\n- OCR status: {details['status']}\n- Omitted items: {details['omitted_items']}\n"
            if audit.sha256(path) != source_hash:
                raise ValueError("Source changed during extraction; retry with the current source")
            written = False
            data = content.encode("utf-8")
            if write_output:
                if before is None:
                    temporary = None
                    try:
                        with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as handle:
                            temporary = Path(handle.name)
                            handle.write(data)
                            handle.flush()
                            os.fsync(handle.fileno())
                        # 原子發布新檔, 若其他程序已建立同名檔則拒絕覆寫
                        os.link(temporary, destination)
                    finally:
                        if temporary is not None:
                            temporary.unlink(missing_ok=True)
                    if destination.read_bytes() != data:
                        raise ValueError("Output readback mismatch; inspect before retry")
                else:
                    markdown.write_guarded(destination, before, data)
                written = True
            response = {"status": "partial" if details["status"] == "partial" else "extracted",
                        "source": str(path), "source_sha256": source_hash, "summary": summary,
                        "output": str(destination) if destination else None, "written": written,
                        "output_sha256": markdown.sha(data), "ocr": details, "source_authority": "original",
                        **self.clipped(content, max_chars)}
            # 限制回傳本文時也限制 OCR 明細, 完整內容仍保留在明確指定的輸出檔
            remaining = max_chars
            for record in response["ocr"]["records"]:
                record["text_truncated"] = len(record["text"]) > remaining
                record["text"] = record["text"][:remaining]
                kept = []
                for line in record["lines"]:
                    if len(line["text"]) > remaining:
                        record["text_truncated"] = True
                        break
                    kept.append(line)
                    remaining -= len(line["text"])
                record["lines"] = kept
            return response

    def inspect_markdown(self, target: str, heading: str | None = None, max_chars: int = 30_000) -> dict:
        self.clipped("", max_chars)
        with self.lock:
            path = self.path(target)
            if path.suffix.lower() != ".md":
                raise ValueError("Target must be a .md file")
            raw, text, _ = markdown.read_target(path)
            result = {"target": str(path), "sha256": markdown.sha(raw),
                      "headings": ["#" * level + " " + title for level, title, _ in markdown.headings(text)]}
            if heading is not None:
                start, end = markdown.section(text, heading)
                result.update(self.clipped(text[start:end], max_chars))
            return result

    def update_markdown(self, target: str, content: str, expected_sha256: str,
                        heading: str | None = None, entry_id: str | None = None,
                        write: bool = False, in_place: bool = False) -> dict:
        if (heading is None) == (entry_id is None):
            raise ValueError("Supply exactly one of heading or entry_id")
        if not re.fullmatch(r"[0-9a-fA-F]{64}", expected_sha256):
            raise ValueError("expected_sha256 must be a SHA-256 hex string")
        if not content.strip() or len(content) > 200_000:
            raise ValueError("content must contain 1-200000 characters")
        with self.lock:
            path = self.path(target, write=True)
            raw, text, bom = markdown.read_target(path)
            if markdown.sha(raw) != expected_sha256.lower():
                raise ValueError("Stale SHA-256; inspect and merge before writing")
            after = markdown.prepare(raw, text, bom, content, heading, entry_id, "project-task")
            if write and after != raw:
                markdown.write_guarded(path, raw, after, in_place)
            return {"status": "written" if write and after != raw else ("unchanged" if after == raw else "preview"),
                    "target": str(path), "sha256": markdown.sha(raw), "next_sha256": markdown.sha(after),
                    "byte_delta": len(after) - len(raw), "remote_sync": "not_performed"}
