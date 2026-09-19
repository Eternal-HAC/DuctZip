"""Tests for the v0.7 settings model: per-user storage, corrupt recovery,
atomic saves, value validation, and runtime precedence helpers."""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest

from ductzip import settings as settings_module
from ductzip.settings import (
    Settings,
    effective_sevenzip,
    load_settings,
    save_settings,
    set_value,
    settings_path,
    unset_value,
)


class SettingsPathTests(unittest.TestCase):
    def test_env_override_wins(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            forced = Path(temp) / "custom" / "prefs.json"
            old = os.environ.get("DUCTZIP_SETTINGS_PATH")
            os.environ["DUCTZIP_SETTINGS_PATH"] = str(forced)
            try:
                self.assertEqual(settings_path(), forced)
            finally:
                if old is None:
                    del os.environ["DUCTZIP_SETTINGS_PATH"]
                else:
                    os.environ["DUCTZIP_SETTINGS_PATH"] = old

    def test_default_location_is_per_user(self) -> None:
        old = os.environ.pop("DUCTZIP_SETTINGS_PATH", None)
        try:
            path = settings_path()
            self.assertEqual(path.name, "settings.json")
            home = Path.home().resolve()
            self.assertIn(str(home), str(path.resolve()))
        finally:
            if old is not None:
                os.environ["DUCTZIP_SETTINGS_PATH"] = old


class RoundTripTests(unittest.TestCase):
    def test_missing_file_yields_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            result = load_settings(Path(temp) / "nope.json")
            self.assertEqual(result.settings, Settings())
            self.assertFalse(result.corrupt_recovered)

    def test_save_then_load_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "settings.json"
            original = Settings(
                sevenzip_path=str(Path(temp) / "backend" / "7z.exe"),
                overwrite_policy="rename",
                conflict_strategy="cancel",
                smart_output=False,
            )
            save_settings(original, path)
            loaded = load_settings(path)
            self.assertFalse(loaded.corrupt_recovered)
            self.assertEqual(loaded.settings, original)

    def test_atomic_save_leaves_no_temp_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "settings.json"
            save_settings(Settings(), path)
            leftovers = [p.name for p in Path(temp).iterdir() if p.name != "settings.json"]
            self.assertEqual(leftovers, [])

    def test_survives_restart_simulation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "settings.json"
            save_settings(set_value(Settings(), "overwrite_policy", "overwrite"), path)
            reloaded = load_settings(path)
            self.assertEqual(reloaded.settings.overwrite_policy, "overwrite")
            reloaded_again = load_settings(path)
            self.assertEqual(reloaded_again.settings.overwrite_policy, "overwrite")


class CorruptRecoveryTests(unittest.TestCase):
    def test_invalid_json_resets_to_defaults_and_backups(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "settings.json"
            path.write_text("{ not json !!!", encoding="utf-8")
            result = load_settings(path)
            self.assertTrue(result.corrupt_recovered)
            self.assertEqual(result.settings, Settings())
            self.assertFalse(path.exists())
            backup = path.with_name("settings.json.corrupt")
            self.assertEqual(backup.read_text(encoding="utf-8"), "{ not json !!!")

    def test_non_object_json_resets_to_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "settings.json"
            path.write_text(json.dumps(["a", "list"]), encoding="utf-8")
            result = load_settings(path)
            self.assertTrue(result.corrupt_recovered)
            self.assertEqual(result.settings, Settings())

    def test_wrong_typed_fields_fall_back_per_field(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "settings.json"
            path.write_text(
                json.dumps(
                    {
                        "overwrite_policy": "bogus",
                        "conflict_strategy": "rename",
                        "smart_output": "yes",
                    }
                ),
                encoding="utf-8",
            )
            result = load_settings(path)
            self.assertFalse(result.corrupt_recovered)
            self.assertEqual(result.settings.overwrite_policy, "skip")
            self.assertEqual(result.settings.conflict_strategy, "rename")
            self.assertIsNone(result.settings.smart_output)

    def test_app_recovers_and_can_save_after_corruption(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "settings.json"
            path.write_text("garbage", encoding="utf-8")
            recovered = load_settings(path)
            self.assertTrue(recovered.corrupt_recovered)
            save_settings(set_value(recovered.settings, "smart_output", "false"), path)
            reloaded = load_settings(path)
            self.assertFalse(reloaded.corrupt_recovered)
            self.assertFalse(reloaded.settings.smart_output)


class ValueValidationTests(unittest.TestCase):
    def test_set_and_unset_each_key(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            backend = Path(temp) / "7z.exe"
            backend.write_bytes(b"fake")
            current = Settings()
            current = set_value(current, "sevenzip_path", str(backend))
            current = set_value(current, "overwrite_policy", "rename")
            current = set_value(current, "conflict_strategy", "cancel")
            current = set_value(current, "smart_output", "false")
            self.assertEqual(
                current,
                Settings(
                    sevenzip_path=str(backend.resolve()),
                    overwrite_policy="rename",
                    conflict_strategy="cancel",
                    smart_output=False,
                ),
            )
            current = unset_value(current, "overwrite_policy")
            self.assertEqual(current.overwrite_policy, "skip")

    def test_unknown_key_rejected(self) -> None:
        with self.assertRaises(ValueError):
            set_value(Settings(), "theme", "dark")
        with self.assertRaises(ValueError):
            unset_value(Settings(), "theme")

    def test_invalid_enum_rejected(self) -> None:
        with self.assertRaises(ValueError):
            set_value(Settings(), "overwrite_policy", "clobber")
        with self.assertRaises(ValueError):
            set_value(Settings(), "smart_output", "maybe")

    def test_nonexistent_backend_path_rejected(self) -> None:
        with self.assertRaises(ValueError):
            set_value(Settings(), "sevenzip_path", r"C:\does\not\exist\7z.exe")

    def test_settings_never_store_passwords(self) -> None:
        fields = Settings().__dataclass_fields__
        self.assertFalse(any("password" in name for name in fields))


class PrecedenceTests(unittest.TestCase):
    def test_stale_configured_backend_falls_back(self) -> None:
        prefs = Settings(sevenzip_path=r"C:\gone\7z.exe")
        self.assertIsNone(effective_sevenzip(prefs))

    def test_live_configured_backend_is_used(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            backend = Path(temp) / "7z.exe"
            backend.write_bytes(b"fake")
            prefs = Settings(sevenzip_path=str(backend))
            self.assertEqual(effective_sevenzip(prefs), str(backend))


if __name__ == "__main__":
    unittest.main()
