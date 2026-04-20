#!/usr/bin/env python3
"""Fetch discussion question pages from a CSV of links and save HTML bodies.

Input:
  - CSV file containing a `link` column
  - exam code, e.g. CS0-003

Output:
  - <examcode>/question-response-bodies/*.html
  - <examcode>/question-response-bodies/index.csv

The script filters only links that belong to the requested exam code.
"""

from __future__ import annotations

import argparse
import csv
import re
import time
from pathlib import Path
from typing import Iterable, List
from urllib import error, request


def safe_name(value: str, max_len: int = 140) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._-")
    return cleaned[:max_len] or "item"


def fetch_url(url: str, timeout: int = 20) -> str:
    req = request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible)"})
    with request.urlopen(req, timeout=timeout) as resp:
        payload = resp.read()
    try:
        return payload.decode("utf-8")
    except Exception:
        return payload.decode("latin-1", errors="replace")


def read_links(csv_file: Path) -> List[str]:
    with csv_file.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames and "link" not in reader.fieldnames:
            raise SystemExit(f"CSV must contain a 'link' column: {csv_file}")
        links: List[str] = []
        for row in reader:
            link = (row.get("link") or "").strip()
            if link:
                links.append(link)
        return links


def filter_links_for_exam(links: Iterable[str], exam_code: str) -> List[str]:
    exam_slug = exam_code.strip().lower()
    pattern = re.compile(rf"-exam-{re.escape(exam_slug)}-topic-", re.IGNORECASE)
    filtered: List[str] = []
    seen = set()
    for link in links:
        if not pattern.search(link):
            continue
        if link in seen:
            continue
        seen.add(link)
        filtered.append(link)
    return filtered


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch ExamTopics question discussion HTML pages from a link CSV."
    )
    parser.add_argument("csv_file", help="CSV file containing a link column")
    parser.add_argument("exam_code", help="Exam code to filter, e.g. CS0-003")
    parser.add_argument(
        "-o",
        "--output-base",
        default=".",
        help="Base output directory (default: current directory)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limit number of links to download (0 = no limit)",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=0.5,
        help="Delay between requests in seconds (default: 0.5)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=20,
        help="HTTP timeout in seconds (default: 20)",
    )
    args = parser.parse_args()

    csv_file = Path(args.csv_file)
    if not csv_file.is_file():
        raise SystemExit(f"CSV file not found: {csv_file}")

    all_links = read_links(csv_file)
    links = filter_links_for_exam(all_links, args.exam_code)

    if args.limit:
        links = links[: args.limit]

    out_dir = Path(args.output_base) / args.exam_code / "question-response-bodies"
    out_dir.mkdir(parents=True, exist_ok=True)

    index_rows = []
    for idx, link in enumerate(links, start=1):
        print(f"Downloading ({idx}/{len(links)}): {link}")
        try:
            html = fetch_url(link, timeout=args.timeout)
        except error.HTTPError as exc:
            print(f"  HTTP error: {exc}")
            continue
        except Exception as exc:
            print(f"  Error: {exc}")
            continue

        stem = f"{idx:06d}_{safe_name(link)}"
        out_path = out_dir / f"{stem}.html"
        out_path.write_text(html, encoding="utf-8")
        index_rows.append((link, out_path.name))
        time.sleep(args.sleep)

    index_path = out_dir / "index.csv"
    with index_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(["link", "file"])
        writer.writerows(index_rows)

    print(f"Saved {len(index_rows)} HTML files to: {out_dir}")
    print(f"Index CSV: {index_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
