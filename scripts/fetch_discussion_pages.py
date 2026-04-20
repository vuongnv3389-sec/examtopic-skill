#!/usr/bin/env python3
"""Fetch discussion listing pages and output discussion links only.

Usage:
    python3 fetch_discussion_pages.py <topic> [-s START] [-e END] [-o discussion_links.csv] [--limit N]

Example:
    python3 fetch_discussion_pages.py comptia -s 1 -e 3 --limit 50

If -o is omitted, the script writes to ./<topic>/scan_<YYYYMMDD-HHMMSS-ffffff>/discussion_links.csv.

This script only uses the standard library (urllib) and writes a CSV containing
one column: link.
"""

from __future__ import annotations

import argparse
import re
import time
import csv
from datetime import datetime
from pathlib import Path
from typing import List
import socket
from urllib import request, error


def fetch_url(url: str, timeout: int = 15) -> str:
    req = request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible)"})
    with request.urlopen(req, timeout=timeout) as resp:
        data = resp.read()
        # Try decode as utf-8 fallback to latin1
        try:
            return data.decode("utf-8")
        except Exception:
            return data.decode("latin-1", errors="replace")


def find_discussion_links(listing_html: str) -> List[str]:
    # Find hrefs that look like /discussions/.../view/...
    hrefs = re.findall(r'href=["\'](?P<h>/discussions/[^"\']+/view/[^"\']+)["\']', listing_html)
    # Make them unique and return
    seen = set()
    out = []
    for h in hrefs:
        if h not in seen:
            seen.add(h)
            out.append(h)
    return out


def is_retryable_error(exc: Exception) -> bool:
    if isinstance(exc, (error.URLError, socket.timeout, TimeoutError)):
        return True
    if isinstance(exc, error.HTTPError):
        return exc.code in {429, 500, 502, 503, 504}
    return False


def main() -> int:
    p = argparse.ArgumentParser(description="Fetch ExamTopics discussion links for a topic")
    p.add_argument("topic", help="Discussion topic slug (e.g., comptia)")
    p.add_argument("-s", "--start", type=int, default=1, help="Start page (default 1)")
    p.add_argument(
        "-e",
        "--end",
        type=int,
        default=0,
        help="End page (default 0 = continue until no links are found or the safety cap is reached)",
    )
    p.add_argument(
        "-o",
        "--output",
        default=None,
        help="Output CSV file. If omitted, a timestamped path under ./<topic>/scan_<timestamp>/ is used.",
    )
    p.add_argument("--sleep", type=float, default=0.5, help="Delay between requests (seconds)")
    p.add_argument(
        "--batch-size",
        type=int,
        default=1,
        help="Number of pages to request consecutively before waiting the batch delay (default 1)",
    )
    p.add_argument(
        "--batch-delay",
        type=float,
        default=0.0,
        help="Seconds to wait after each batch of pages when --batch-size > 1 (default 0)",
    )
    p.add_argument("--limit", type=int, default=0, help="Limit total discussion pages to download (0 = no limit)")
    p.add_argument(
        "--max-pages",
        type=int,
        default=500,
        help="Hard safety cap for page traversal when --end is not provided (default 500)",
    )
    p.add_argument(
        "--retry-count",
        type=int,
        default=3,
        help="Maximum retries for retryable network errors before stopping pagination (default 3)",
    )
    p.add_argument(
        "--retry-delay",
        type=float,
        default=1.0,
        help="Base delay in seconds for retry backoff (default 1.0)",
    )
    args = p.parse_args()

    if args.output:
        out_path = Path(args.output)
    else:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        out_path = Path.cwd() / args.topic / f"scan_{timestamp}" / "discussion_links.csv"

    domain = "https://www.examtopics.com"
    collected: List[str] = []

    # Iterate listing pages. When --end is 0, keep going until a page returns no links.
    page = args.start
    batch_size = max(1, int(args.batch_size))
    batch_delay = float(args.batch_delay)
    batch_count = 0
    retry_count = max(0, int(args.retry_count))
    retry_delay = max(0.0, float(args.retry_delay))
    exit_code = 0
    while True:
        if args.max_pages and page > args.max_pages:
            print(f"Reached safety cap of {args.max_pages} pages; stopping.")
            break

        if args.end and page > args.end:
            break

        if page == 1:
            url = f"{domain}/discussions/{args.topic}/"
        else:
            url = f"{domain}/discussions/{args.topic}/{page}/"

        print(f"Fetching listing: {url}")
        html = None
        for attempt in range(retry_count + 1):
            try:
                html = fetch_url(url)
                break
            except error.HTTPError as e:
                print(f"HTTP error fetching listing {url}: {e}")
                if getattr(e, "code", None) == 404:
                    print(f"Page {page} returned 404; stopping pagination.")
                    html = None
                    break
                if not is_retryable_error(e):
                    print(f"Non-retryable HTTP error on page {page}; stopping pagination.")
                    exit_code = 1
                    html = None
                    break
            except Exception as e:
                print(f"Error fetching listing {url}: {e}")
                if not is_retryable_error(e):
                    print(f"Non-retryable error on page {page}; stopping pagination.")
                    exit_code = 1
                    html = None
                    break

            if attempt < retry_count:
                wait_seconds = retry_delay * (2 ** attempt)
                print(f"Retrying page {page} in {wait_seconds:.1f}s ({attempt + 1}/{retry_count})")
                time.sleep(wait_seconds)
            else:
                print(f"Exceeded retry limit for page {page}; stopping pagination.")
                exit_code = 1
                html = None
                break

        if html is None:
            break

        before_count = len(collected)
        links = find_discussion_links(html)
        print(f"  Found {len(links)} discussion links on page {page}")

        for rel in links:
            full = rel if rel.startswith("http") else domain + rel
            if full in collected:
                continue
            collected.append(full)
            if args.limit and len(collected) >= args.limit:
                break

        # per-request short sleep
        time.sleep(args.sleep)
        batch_count += 1
        if batch_count >= batch_size:
            if batch_delay > 0:
                print(f"Batch of {batch_count} pages completed; sleeping {batch_delay}s before next batch")
                time.sleep(batch_delay)
            batch_count = 0

        if args.end == 0 and not links:
            print(f"  No links found on page {page}; stopping.")
            break

        if args.end == 0 and len(collected) == before_count:
            print(f"  No new links found on page {page}; stopping.")
            break

        if args.limit and len(collected) >= args.limit:
            break

        page += 1

    print(f"Total unique discussion links collected: {len(collected)}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(["link"])
        for link in collected:
            writer.writerow([link])

    print(f"Saved links CSV: {out_path}")
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
