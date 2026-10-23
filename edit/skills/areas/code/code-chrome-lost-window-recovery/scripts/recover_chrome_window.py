#!/usr/bin/env python3
"""Recover closed Chrome windows from copied SNSS tab-restore files."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import struct
import subprocess
import sys
from pathlib import Path
from typing import Any


CHROME_ROOT = Path.home() / "Library/Application Support/Google/Chrome"
CHROME_BINARY = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
DOWNLOADS = Path.home() / "Downloads"
WINDOWS_EPOCH_US = 11644473600000000


class Reader:
    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0

    def remaining(self) -> int:
        return len(self.data) - self.pos

    def i32(self) -> int:
        if self.pos + 4 > len(self.data):
            raise EOFError
        value = struct.unpack_from("<i", self.data, self.pos)[0]
        self.pos += 4
        return value

    def u32(self) -> int:
        if self.pos + 4 > len(self.data):
            raise EOFError
        value = struct.unpack_from("<I", self.data, self.pos)[0]
        self.pos += 4
        return value

    def i64(self) -> int:
        if self.pos + 8 > len(self.data):
            raise EOFError
        value = struct.unpack_from("<q", self.data, self.pos)[0]
        self.pos += 8
        return value

    def string(self) -> str:
        size = self.u32()
        padded = size + ((4 - size % 4) % 4)
        if self.pos + padded > len(self.data):
            raise EOFError
        raw = self.data[self.pos : self.pos + size]
        self.pos += padded
        return raw.decode("utf-8", "replace")

    def string16(self) -> str:
        size = self.u32()
        byte_size = size * 2
        padded = byte_size + ((4 - byte_size % 4) % 4)
        if self.pos + padded > len(self.data):
            raise EOFError
        raw = self.data[self.pos : self.pos + byte_size]
        self.pos += padded
        return raw.decode("utf-16le", "replace")


def chrome_time(value_us: int) -> str:
    if not value_us:
        return ""
    try:
        unix = (value_us - WINDOWS_EPOCH_US) / 1_000_000
        return dt.datetime.fromtimestamp(unix).isoformat(sep=" ", timespec="seconds")
    except Exception:
        return str(value_us)


def now_stamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d-%H%M%S")


def copy_sessions(profile: str | None) -> Path:
    backup = DOWNLOADS / f"chrome-lost-window-recovery-{now_stamp()}"
    roots = [CHROME_ROOT / profile] if profile else [p for p in CHROME_ROOT.iterdir() if p.is_dir()]
    for root in roots:
        session_dir = root / "Sessions"
        if not session_dir.is_dir():
            continue
        dest = backup / root.name / "Sessions"
        dest.mkdir(parents=True, exist_ok=True)
        for file in session_dir.glob("Tabs_*"):
            shutil.copy2(file, dest / file.name)
    return backup


def iter_commands(path: Path):
    data = path.read_bytes()
    if data[:4] != b"SNSS":
        return
    pos = 8
    while pos + 3 <= len(data):
        size = struct.unpack_from("<H", data, pos)[0]
        pos += 2
        if size <= 0 or pos + size > len(data):
            break
        command_id = data[pos]
        payload = data[pos + 1 : pos + size]
        pos += size
        yield command_id, payload


def parse_update_navigation(payload: bytes) -> dict[str, Any]:
    reader = Reader(payload)
    reader.u32()  # pickle payload size
    tab_id = reader.i32()
    nav_index = reader.i32()
    url = reader.string()
    title = reader.string16()
    return {"tab_id": tab_id, "nav_index": nav_index, "url": url, "title": title}


def parse_window(payload: bytes) -> dict[str, Any]:
    reader = Reader(payload)
    reader.u32()  # pickle payload size
    window_id = reader.i32()
    selected_tab_index = reader.i32()
    num_tabs = reader.i32()
    timestamp_us = reader.i64()
    if reader.remaining() >= 20:
        reader.i32()
        reader.i32()
        reader.i32()
        reader.i32()
        reader.i32()
    if reader.remaining() >= 4:
        try:
            reader.string()
        except Exception:
            pass
    return {
        "kind": "window",
        "id": window_id,
        "selected_tab_index": selected_tab_index,
        "num_tabs": num_tabs,
        "timestamp_us": timestamp_us,
        "tabs": [],
    }


def parse_selected_tab(payload: bytes) -> dict[str, Any]:
    if len(payload) >= 16:
        tab_id, selected_index, timestamp_us = struct.unpack_from("<iiq", payload, 0)
    else:
        tab_id, selected_index = struct.unpack_from("<ii", payload, 0)
        timestamp_us = 0
    return {
        "kind": "tab",
        "id": tab_id,
        "current_navigation_index": selected_index,
        "timestamp_us": timestamp_us,
        "navigations": [],
    }


def parse_tab_restore_file(path: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    current_tab: dict[str, Any] | None = None
    current_window: dict[str, Any] | None = None
    remaining_tabs = 0

    for command_id, payload in iter_commands(path):
        try:
            if command_id == 2:  # restored entry
                restored_id = struct.unpack_from("<i", payload, 0)[0]
                entries = [
                    entry
                    for entry in entries
                    if entry.get("id") != restored_id and entry.get("original_id") != restored_id
                ]
                current_tab = None
                current_window = None
                remaining_tabs = 0
            elif command_id == 9:  # closed window
                window = parse_window(payload)
                entries = [entry for entry in entries if entry.get("id") != window["id"]]
                entries.append(window)
                current_window = window
                current_tab = None
                remaining_tabs = int(window.get("num_tabs", 0))
            elif command_id == 4:  # selected navigation in tab
                tab = parse_selected_tab(payload)
                if current_window is not None and remaining_tabs > 0:
                    current_window["tabs"].append(tab)
                    remaining_tabs -= 1
                    current_tab = tab
                    if remaining_tabs == 0:
                        current_window = None
                else:
                    entries = [entry for entry in entries if entry.get("id") != tab["id"]]
                    entries.append(tab)
                    current_tab = tab
            elif command_id == 1 and current_tab is not None:  # tab navigation
                nav = parse_update_navigation(payload)
                if nav["url"]:
                    current_tab["navigations"].append(nav)
        except Exception:
            continue

    return entries


def current_nav(tab: dict[str, Any]) -> dict[str, Any]:
    navs = tab.get("navigations", [])
    if not navs:
        return {"url": "", "title": ""}
    index = tab.get("current_navigation_index", len(navs) - 1)
    if isinstance(index, int) and 0 <= index < len(navs):
        return navs[index]
    return navs[-1]


def haystack_for_entry(entry: dict[str, Any]) -> str:
    tabs = entry["tabs"] if entry["kind"] == "window" else [entry]
    parts: list[str] = []
    for tab in tabs:
        for nav in tab.get("navigations", []):
            parts.append(nav.get("url", ""))
            parts.append(nav.get("title", ""))
    return "\n".join(parts).lower()


def score_entry(entry: dict[str, Any], queries: list[str]) -> tuple[int, list[str]]:
    haystack = haystack_for_entry(entry)
    matched = []
    score = 0
    for query in queries:
        q = query.lower()
        if q in haystack:
            matched.append(query)
            score += 100
        else:
            words = [w for w in re.split(r"\W+", q) if len(w) >= 4]
            word_hits = sum(1 for word in words if word in haystack)
            if word_hits:
                matched.append(query)
                score += word_hits * 10
    tabs = entry["tabs"] if entry["kind"] == "window" else [entry]
    score += min(len(tabs), 20)
    if entry["kind"] == "window":
        score += 20
    if entry.get("timestamp_us"):
        score += 5
    return score, matched


def compact_entry(entry: dict[str, Any]) -> dict[str, Any]:
    tabs = entry["tabs"] if entry["kind"] == "window" else [entry]
    urls = []
    tab_summaries = []
    for tab in tabs:
        nav = current_nav(tab)
        url = nav.get("url", "")
        title = nav.get("title", "")
        if url:
            urls.append(url)
        tab_summaries.append({"title": title, "url": url})
    return {
        "kind": entry["kind"],
        "id": entry.get("id"),
        "timestamp": chrome_time(entry.get("timestamp_us", 0)),
        "tabs": len(tabs),
        "selected_tab_index": entry.get("selected_tab_index"),
        "tab_summaries": tab_summaries,
        "urls": urls,
    }


def find_candidates(backup: Path, queries: list[str]) -> list[dict[str, Any]]:
    candidates = []
    for tabs_file in backup.glob("*/Sessions/Tabs_*"):
        profile = tabs_file.parts[-3]
        for entry in parse_tab_restore_file(tabs_file):
            score, matched = score_entry(entry, queries)
            if not matched:
                continue
            compact = compact_entry(entry)
            compact.update(
                {
                    "score": score,
                    "matched": matched,
                    "profile": profile,
                    "source": str(tabs_file.relative_to(backup)),
                    "source_mtime": dt.datetime.fromtimestamp(tabs_file.stat().st_mtime).isoformat(
                        sep=" ", timespec="seconds"
                    ),
                }
            )
            candidates.append(compact)
    candidates.sort(
        key=lambda item: (
            item["score"],
            item["tabs"],
            item.get("timestamp") or item.get("source_mtime") or "",
        ),
        reverse=True,
    )
    return candidates


def open_candidate(candidate: dict[str, Any]) -> None:
    urls = [url for url in candidate["urls"] if url]
    if not urls:
        raise SystemExit("No openable URLs in candidate.")
    if not CHROME_BINARY.exists():
        raise SystemExit(f"Chrome binary not found: {CHROME_BINARY}")
    command = [
        str(CHROME_BINARY),
        "--profile-directory=Default",
        "--new-window",
        *urls,
    ]
    subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)


def print_text(candidates: list[dict[str, Any]], limit: int) -> None:
    for index, candidate in enumerate(candidates[:limit], start=1):
        print(
            f"rank={index} score={candidate['score']} profile={candidate['profile']} "
            f"source={candidate['source']} kind={candidate['kind']} tabs={candidate['tabs']} "
            f"timestamp={candidate['timestamp'] or candidate['source_mtime']} matched={','.join(candidate['matched'])}"
        )
        for tab_index, tab in enumerate(candidate["tab_summaries"], start=1):
            print(f"  {tab_index:02d}. {tab['title']} | {tab['url']}")
        print()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", action="append", required=True, help="Remembered URL, domain, or title text.")
    parser.add_argument("--profile", help="Chrome profile directory, e.g. Default or Profile 11.")
    parser.add_argument("--backup", type=Path, help="Use existing copied backup instead of copying live sessions.")
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--json", action="store_true", help="Emit JSON.")
    parser.add_argument("--open", action="store_true", help="Open matched candidate in new Chrome window.")
    parser.add_argument("--open-rank", type=int, default=1, help="1-based rank to open.")
    args = parser.parse_args()

    backup = args.backup or copy_sessions(args.profile)
    candidates = find_candidates(backup, args.query)
    result = {"backup": str(backup), "queries": args.query, "candidates": candidates}
    (backup / "recovery-results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"backup={backup}")
        print_text(candidates, args.limit)

    if args.open:
        rank = args.open_rank
        if rank < 1 or rank > len(candidates):
            raise SystemExit(f"No candidate at rank {rank}.")
        open_candidate(candidates[rank - 1])
        print(f"opened_rank={rank} urls={len([u for u in candidates[rank - 1]['urls'] if u])}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
