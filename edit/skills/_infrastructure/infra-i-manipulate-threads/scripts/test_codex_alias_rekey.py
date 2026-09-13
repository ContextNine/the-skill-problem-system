#!/usr/bin/env python3
"""Focused tests for Codex SSH-alias project reassociation."""

from __future__ import annotations

import argparse
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("codex_alias_rekey.py")
SPEC = importlib.util.spec_from_file_location("codex_alias_rekey", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class AliasRekeyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.state = {
            "remote-projects": [
                {
                    "id": "old-project",
                    "hostId": "old-host",
                    "remotePath": "/code/repo",
                    "label": "repo",
                }
            ],
            "thread-project-assignments": {
                "thread-1": {
                    "projectKind": "remote",
                    "projectId": "old-project",
                    "hostId": "old-host",
                }
            },
        }

    def test_preview_and_apply_clone_one_project(self) -> None:
        args = argparse.Namespace(
            source_host="old-host",
            destination_host="new-host",
            thread=["thread-1"],
            project_template_id=None,
        )
        plan = MODULE.build_plan(self.state, args)
        self.assertEqual(len(plan["planned_projects"]), 1)
        self.assertTrue(plan["actions"][0]["destination_project_will_be_created"])

        applied = MODULE.apply_plan(self.state, plan)
        self.assertEqual(len(applied["created_projects"]), 1)
        assignment = self.state["thread-project-assignments"]["thread-1"]
        self.assertEqual(assignment["hostId"], "new-host")
        self.assertEqual(assignment["path"], "/code/repo")
        self.assertEqual(
            assignment["projectId"], applied["created_projects"][0]["id"]
        )

    def test_template_assigns_a_destination_native_thread(self) -> None:
        args = argparse.Namespace(
            source_host="old-host",
            destination_host="new-host",
            thread=["destination-thread"],
            project_template_id="old-project",
        )
        plan = MODULE.build_plan(self.state, args)
        MODULE.apply_plan(self.state, plan)
        assignment = self.state["thread-project-assignments"]["destination-thread"]
        self.assertEqual(assignment["hostId"], "new-host")


if __name__ == "__main__":
    unittest.main()
