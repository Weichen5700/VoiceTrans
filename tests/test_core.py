import json
import tempfile
import unittest
from pathlib import Path

from voice_lab.config import MAX_MODEL_BYTES
from voice_lab.core import create_project, list_runs, validate_model_size


class CoreTests(unittest.TestCase):
    def test_model_above_four_gib_is_blocked(self) -> None:
        result = validate_model_size(MAX_MODEL_BYTES + 1, "demo")
        self.assertFalse(result["allowed"])
        self.assertEqual(result["status"], "BLOCKED")

    def test_four_gib_is_allowed_by_size_policy_but_not_downloaded(self) -> None:
        result = validate_model_size(MAX_MODEL_BYTES, "demo")
        self.assertTrue(result["allowed"])
        self.assertIn("不自動下載", result["reason"])

    def test_unknown_model_size_needs_check(self) -> None:
        self.assertEqual(validate_model_size(None)["status"], "NEEDS_CHECK")

    def test_project_is_saved_and_run_list_is_empty(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            project = create_project(root, "測試專案")
            saved = json.loads((root / "project.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["project_id"], project["project_id"])
            self.assertEqual(list_runs(root), [])


if __name__ == "__main__":
    unittest.main()
