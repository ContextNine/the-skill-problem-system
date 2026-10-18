#!/usr/bin/env python3
"""Focused integration tests for destination-native Codex thread transplants."""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("codex_thread_port.py")
SOURCE_ID = "019ffa8a-e345-7d11-9683-2ab3ac1522bb"
DESTINATION_ID = "01a002ff-1111-7222-8333-444455556666"


class DestinationNativeTransplantTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="codex-thread-port-test-")
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.destination = self.root / "destination"
        self.bundle = self.root / "thread.tgz"
        self._create_home(self.source, SOURCE_ID, "Source title", "source transcript")
        self._create_home(
            self.destination,
            DESTINATION_ID,
            "Destination placeholder",
            "destination transcript",
        )
        self._run(
            "export",
            "--codex-home",
            str(self.source),
            "--id",
            SOURCE_ID,
            "--output",
            str(self.bundle),
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _create_home(self, home: Path, thread_id: str, title: str, marker: str) -> None:
        transcript = home / "sessions" / "2026" / "08" / f"rollout-{thread_id}.jsonl"
        transcript.parent.mkdir(parents=True)
        rows = [
            {
                "type": "session_meta",
                "payload": {
                    "id": thread_id,
                    "session_id": thread_id,
                    "cwd": str(home / "workspace"),
                },
            },
            {
                "type": "turn_context",
                "payload": {
                    "cwd": str(home / "workspace"),
                    "workspace_roots": [str(home / "workspace")],
                },
            },
            {"type": "event_msg", "payload": {"message": marker}},
        ]
        transcript.write_text(
            "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
        )
        with sqlite3.connect(home / "state_5.sqlite") as connection:
            connection.execute(
                """
                CREATE TABLE threads (
                    id TEXT PRIMARY KEY,
                    rollout_path TEXT NOT NULL,
                    cwd TEXT NOT NULL,
                    title TEXT NOT NULL,
                    archived INTEGER NOT NULL DEFAULT 0,
                    archived_at INTEGER,
                    is_pinned INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            connection.execute(
                "INSERT INTO threads VALUES (?, ?, ?, ?, 0, NULL, 0)",
                (thread_id, str(transcript), str(home / "workspace"), title),
            )
        (home / "session_index.jsonl").write_text(
            json.dumps({"id": thread_id, "thread_name": title, "updated_at": "now"})
            + "\n",
            encoding="utf-8",
        )
        (home / ".codex-global-state.json").write_text(
            json.dumps({"pinned-thread-ids": []}) + "\n", encoding="utf-8"
        )

    def _run(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *arguments],
            check=True,
            capture_output=True,
            text=True,
        )

    def test_transplant_preserves_destination_identity_and_backs_up_transcript(self) -> None:
        mapping = f"{SOURCE_ID}={DESTINATION_ID}"
        preview = self._run(
            "import",
            "--codex-home",
            str(self.destination),
            "--bundle",
            str(self.bundle),
            "--existing",
            "update",
            "--destination-id",
            mapping,
        )
        action = json.loads(preview.stdout)["actions"][0]
        self.assertEqual(action["action"], "transplant")
        self.assertEqual(action["id"], DESTINATION_ID)
        self.assertEqual(action["source_id"], SOURCE_ID)

        self._run(
            "import",
            "--codex-home",
            str(self.destination),
            "--bundle",
            str(self.bundle),
            "--existing",
            "update",
            "--destination-id",
            mapping,
            "--apply",
        )

        with sqlite3.connect(self.destination / "state_5.sqlite") as connection:
            row = connection.execute(
                "SELECT id, cwd, title, rollout_path FROM threads WHERE id = ?",
                (DESTINATION_ID,),
            ).fetchone()
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row[0], DESTINATION_ID)
        self.assertEqual(row[1], str(self.destination / "workspace"))
        self.assertEqual(row[2], "Source title")

        transcript = Path(row[3])
        imported = [json.loads(line) for line in transcript.read_text().splitlines()]
        self.assertEqual(imported[0]["payload"]["id"], DESTINATION_ID)
        self.assertEqual(imported[0]["payload"]["session_id"], DESTINATION_ID)
        self.assertEqual(imported[0]["payload"]["cwd"], str(self.destination / "workspace"))
        self.assertEqual(imported[1]["payload"]["cwd"], str(self.destination / "workspace"))
        self.assertEqual(imported[2]["payload"]["message"], "source transcript")

        backups = list((self.destination / "thread-port-backups").glob("*/transcripts/*"))
        self.assertEqual(len(backups), 1)
        self.assertIn("destination transcript", backups[0].read_text())

        with tarfile.open(self.bundle, "r:gz") as archive:
            self.assertIn("bundle/manifest.json", archive.getnames())


if __name__ == "__main__":
    unittest.main()
