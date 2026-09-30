"""Tests for explicit, fail-safe recruitment backend selection."""

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from features.nocobase_sync import backend
from features.nocobase_sync.config import NocoBaseConfig


class CandidateBackendTests(unittest.TestCase):
    def test_missing_corrupt_and_unknown_backend_default_to_sqlite(self):
        with TemporaryDirectory() as directory:
            data_dir = Path(directory)
            self.assertEqual(backend.read_backend(data_dir), "sqlite")
            path = data_dir / "recruitment-backend.json"
            for content in ("not-json", '{"version":1,"backend":"other"}', '{"version":2,"backend":"nocobase"}'):
                path.write_text(content, encoding="utf-8")
                self.assertEqual(backend.read_backend(data_dir), "sqlite")

    def test_enable_requires_valid_api_configuration_and_successful_preflight(self):
        with TemporaryDirectory() as directory:
            data_dir = Path(directory)
            with patch.object(backend, "load", side_effect=ValueError("bad config")):
                with self.assertRaisesRegex(ValueError, "NocoBase 配置"):
                    backend.enable_nocobase(data_dir, lambda: SimpleNamespace(ok=True))
            with patch.object(backend, "load", return_value=NocoBaseConfig("https://example.test", "token", False)):
                with self.assertRaisesRegex(ValueError, "尚未启用"):
                    backend.enable_nocobase(data_dir, lambda: SimpleNamespace(ok=True))
            with patch.object(backend, "load", return_value=NocoBaseConfig("https://example.test", "token", True)):
                with self.assertRaisesRegex(ValueError, "预检"):
                    backend.enable_nocobase(data_dir, lambda: SimpleNamespace(ok=False))
            self.assertEqual(backend.read_backend(data_dir), "sqlite")

    def test_failed_preflight_never_changes_existing_backend(self):
        with TemporaryDirectory() as directory:
            data_dir = Path(directory)
            backend.write_backend(data_dir, "sqlite")
            original = (data_dir / "recruitment-backend.json").read_bytes()
            with patch.object(backend, "load", return_value=NocoBaseConfig("https://example.test", "token", True)):
                with self.assertRaises(RuntimeError):
                    backend.enable_nocobase(data_dir, lambda: (_ for _ in ()).throw(RuntimeError("offline")))
            self.assertEqual((data_dir / "recruitment-backend.json").read_bytes(), original)

    def test_successful_enable_is_atomic_and_persistent(self):
        with TemporaryDirectory() as directory:
            data_dir = Path(directory)
            calls = []
            with patch.object(backend, "load", return_value=NocoBaseConfig("https://example.test", "token", True)):
                backend.enable_nocobase(data_dir, lambda: calls.append("checked") or SimpleNamespace(ok=True))
            self.assertEqual(calls, ["checked"])
            self.assertEqual(backend.read_backend(data_dir), "nocobase")
            self.assertEqual(json.loads((data_dir / "recruitment-backend.json").read_text(encoding="utf-8")), {
                "version": 1, "backend": "nocobase",
            })
            self.assertFalse(any(path.name.startswith(".recruitment-backend-") for path in data_dir.iterdir()))

    def test_legacy_candidate_only_selector_never_enables_unified_backend(self):
        with TemporaryDirectory() as directory:
            data_dir = Path(directory)
            (data_dir / "candidate-backend.json").write_text(
                '{"version":1,"backend":"nocobase"}', encoding="utf-8"
            )
            self.assertEqual(backend.read_backend(data_dir), "sqlite")

    def test_select_only_returns_nocobase_after_runtime_check(self):
        with TemporaryDirectory() as directory:
            data_dir = Path(directory)
            backend.write_backend(data_dir, "nocobase")
            with patch.object(backend, "load", return_value=NocoBaseConfig("https://example.test", "token", True)):
                self.assertEqual(backend.select_candidate_backend(
                    data_dir, preflight=lambda: SimpleNamespace(ok=True)
                ), "nocobase")
                with self.assertRaisesRegex(ValueError, "预检"):
                    backend.select_candidate_backend(data_dir, preflight=lambda: SimpleNamespace(ok=False))
            self.assertEqual(backend.read_backend(data_dir), "nocobase")


if __name__ == "__main__":
    unittest.main()
