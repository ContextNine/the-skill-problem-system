"""Integration checks for additive GTM setup."""

from __future__ import annotations

import importlib.util
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/apply.py"
VAULT_ROOT = Path(__file__).resolve().parents[7]
spec = importlib.util.spec_from_file_location("gtm_apply", SCRIPT)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class GTMApplyTests(unittest.TestCase):
    def test_gtm_setup_keeps_shared_docs_out_and_crm_optional(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            context = root / "studio"
            context.mkdir()
            (context / "studio.md").write_text("---\nstatus: active\n---\n", encoding="utf-8")
            for relative in (module.BUSINESS_PACK, module.GTM_PACK):
                shutil.copytree(VAULT_ROOT / relative, root / relative)
            (context / "gtm").mkdir()
            (context / "gtm/gtm.md").write_text("Keep my edits.\n", encoding="utf-8")

            with patch.object(module, "vault_root", return_value=root):
                module.apply("studio", "company", write=True)
                self.assertTrue((context / "company/.gitkeep").is_file())
                self.assertTrue((context / "gtm/funnel.excalidraw").is_file())
                self.assertEqual((context / "gtm/gtm.md").read_text(encoding="utf-8"), "Keep my edits.\n")
                self.assertFalse((context / "relationships").exists())
                self.assertFalse((context / "gtm/README-crm.md").exists())
                self.assertFalse((context / "gtm/README-marketing-stack.md").exists())

                module.apply("studio", "company", write=True, relationships=True)
                self.assertTrue((context / "relationships/people/.gitkeep").is_file())
                self.assertTrue((context / "_obsidian/bases/relationship-crm.base").is_file())
                self.assertFalse((context / "relationships/README-crm.md").exists())


if __name__ == "__main__":
    unittest.main()
