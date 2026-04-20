#!/usr/bin/env python3
"""Extract response bodies from Burp XML export files.

This script reads Burp Suite XML exports (items/item/response) and writes one
body file per item plus an index file for quick lookup.
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Iterator, Optional, Tuple
import xml.etree.ElementTree as ET


TEXT_LIKE_TYPES = (
    "text/",
    "application/json",
    "application/javascript",
    "application/xml",
    "application/xhtml+xml",
    "application/x-www-form-urlencoded",
)


@dataclass
class ItemResult:
    index: int
    url: str
    status: str
    method: str
    path: str
    mimetype: str
    body_file: str
    text_file: Optional[str]
    body_size: int
    base64_response: bool
    decompressed: bool
    content_type: str
    content_encoding: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract response bodies from Burp XML export files.",
    )
    parser.add_argument("xml_file", help="Path to Burp XML file")
    parser.add_argument(
        "-o",
        "--output-dir",
        help="Output directory (default: <xml_stem>_response_bodies)",
    )
    parser.add_argument(
        "--no-decompress",
        action="store_true",
        help="Do not decompress body even if Content-Encoding is gzip/deflate.",
    )
    return parser.parse_args()


def safe_name(value: str, max_len: int = 120) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._-")
    if not cleaned:
        cleaned = "item"
    return cleaned[:max_len]


def decode_burp_payload(value: str, is_base64: bool) -> bytes:
    if not value:
        return b""
    if is_base64:
        return base64.b64decode(value)
    return value.encode("utf-8", errors="replace")


def split_headers_body(raw_http: bytes) -> Tuple[bytes, bytes]:
    for marker in (b"\r\n\r\n", b"\n\n"):
        idx = raw_http.find(marker)
        if idx != -1:
            return raw_http[:idx], raw_http[idx + len(marker) :]
    return b"", raw_http


def parse_headers(header_blob: bytes) -> Dict[str, str]:
    headers: Dict[str, str] = {}
    if not header_blob:
        return headers

    text = header_blob.decode("iso-8859-1", errors="replace")
    lines = text.splitlines()
    for line in lines[1:]:
        if ":" not in line:
            continue
        name, value = line.split(":", 1)
        headers[name.strip().lower()] = value.strip()
    return headers


def detect_charset(content_type: str) -> Optional[str]:
    match = re.search(r"charset=([A-Za-z0-9._-]+)", content_type, re.IGNORECASE)
    if match:
        return match.group(1).strip().strip('"')
    return None


def maybe_decompress(body: bytes, encoding: str) -> Tuple[bytes, bool]:
    enc = (encoding or "").lower().strip()
    if not enc or enc == "identity":
        return body, False

    if "gzip" in enc:
        return zlib.decompress(body, zlib.MAX_WBITS | 16), True
    if "deflate" in enc:
        try:
            return zlib.decompress(body), True
        except zlib.error:
            return zlib.decompress(body, -zlib.MAX_WBITS), True

    return body, False


def is_text_like(content_type: str, mimetype: str, body: bytes) -> bool:
    lowered = (content_type or mimetype or "").lower()
    if any(lowered.startswith(prefix) for prefix in TEXT_LIKE_TYPES):
        return True
    if mimetype.lower() in {"html", "json", "xml", "script", "javascript", "css"}:
        return True
    # Heuristic: treat as text when no null bytes exist in the first chunk.
    return b"\x00" not in body[:2048]


def iter_items(xml_file: Path) -> Iterator[ET.Element]:
    context = ET.iterparse(xml_file, events=("end",))
    for event, elem in context:
        if event == "end" and elem.tag == "item":
            yield elem
            elem.clear()


def write_text_variant(path: Path, body: bytes, content_type: str) -> bool:
    charset = detect_charset(content_type) or "utf-8"
    try:
        text = body.decode(charset, errors="replace")
    except LookupError:
        text = body.decode("utf-8", errors="replace")
    path.write_text(text, encoding="utf-8")
    return True


def extract(xml_file: Path, out_dir: Path, decompress: bool) -> Tuple[int, Path]:
    body_dir = out_dir / "bodies"
    body_dir.mkdir(parents=True, exist_ok=True)
    index_path = out_dir / "index.jsonl"

    count = 0
    with index_path.open("w", encoding="utf-8") as index_fh:
        for count, item in enumerate(iter_items(xml_file), start=1):
            url = (item.findtext("url") or "").strip()
            status = (item.findtext("status") or "").strip()
            method = (item.findtext("method") or "").strip()
            path = (item.findtext("path") or "").strip()
            mimetype = (item.findtext("mimetype") or "").strip()

            response_elem = item.find("response")
            response_text = response_elem.text if response_elem is not None and response_elem.text else ""
            response_is_b64 = (
                response_elem is not None
                and (response_elem.attrib.get("base64", "false").strip().lower() == "true")
            )

            raw_http = decode_burp_payload(response_text, response_is_b64)
            raw_headers, body = split_headers_body(raw_http)
            headers = parse_headers(raw_headers)

            content_type = headers.get("content-type", "")
            content_encoding = headers.get("content-encoding", "")

            decompressed = False
            if decompress and body:
                try:
                    body, decompressed = maybe_decompress(body, content_encoding)
                except Exception:
                    decompressed = False

            host = ""
            host_elem = item.find("host")
            if host_elem is not None and host_elem.text:
                host = host_elem.text.strip()

            file_stem = f"{count:06d}_{safe_name(method or 'REQ')}_{safe_name(host)}_{safe_name(path or 'root')}"
            body_file = body_dir / f"{file_stem}.body"
            body_file.write_bytes(body)

            text_file: Optional[Path] = None
            if is_text_like(content_type, mimetype, body):
                text_file = body_dir / f"{file_stem}.txt"
                write_text_variant(text_file, body, content_type)

            result = ItemResult(
                index=count,
                url=url,
                status=status,
                method=method,
                path=path,
                mimetype=mimetype,
                body_file=str(body_file.relative_to(out_dir)),
                text_file=str(text_file.relative_to(out_dir)) if text_file else None,
                body_size=len(body),
                base64_response=response_is_b64,
                decompressed=decompressed,
                content_type=content_type,
                content_encoding=content_encoding,
            )
            index_fh.write(json.dumps(result.__dict__, ensure_ascii=False) + "\n")

    return count, index_path


def main() -> int:
    args = parse_args()
    xml_file = Path(args.xml_file)
    if not xml_file.is_file():
        raise SystemExit(f"Input file not found: {xml_file}")

    out_dir = Path(args.output_dir) if args.output_dir else xml_file.with_name(f"{xml_file.stem}_response_bodies")
    out_dir.mkdir(parents=True, exist_ok=True)

    count, index_path = extract(xml_file, out_dir, decompress=not args.no_decompress)
    print(f"Extracted {count} response bodies")
    print(f"Output directory: {out_dir}")
    print(f"Index file: {index_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
