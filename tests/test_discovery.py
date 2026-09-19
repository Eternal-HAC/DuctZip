"""Discovery-order tests for the bundled/system 7-Zip backend selection.

Covers the Phase 6 requirement that a bundled backend must not break
explicit user overrides or the system-backend fallback chain.
"""

from __future__ import annotations

from pathlib import Path
import os
import tempfile
import unittest
from unittest import mock

import ductzip.archive.sevenzip as sevenzip_module
from ductzip.archive import SevenZipMissing, find_sevenzip


class DiscoveryOrderTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.root = Path(self._temp.name)
        self.fake_package_dir = self.root / "src" / "ductzip" / "archive"
        self.fake_package_dir.mkdir(parents=True)

    # -- helpers ---------------------------------------------------------

    def _write(self, relative: str) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fake backend")
        return path

    def _run(self, explicit: str | None = None, env: dict[str, str] | None = None):
        base_env = {"ProgramFiles": str(self.root / "pf"), "ProgramFiles(x86)": str(self.root / "pf86")}
        base_env.update(env or {})
        with mock.patch.object(
            sevenzip_module, "__file__", str(self.fake_package_dir / "sevenzip.py")
        ), mock.patch.dict(os.environ, base_env, clear=True), mock.patch.object(
            sevenzip_module, "_registry_sevenzip_candidates", return_value=[]
        ), mock.patch.object(sevenzip_module.shutil, "which", return_value=None):
            return find_sevenzip(explicit)

    # -- explicit override always wins ------------------------------------

    def test_explicit_path_wins_over_everything(self) -> None:
        explicit = self._write("explicit/7z.exe")
        self._write("vendor/7zip/7z.exe")
        self._write("pf/7-Zip/7z.exe")

        self.assertEqual(self._run(str(explicit)), explicit.resolve())

    def test_missing_explicit_path_raises_without_fallback(self) -> None:
        self._write("vendor/7zip/7z.exe")

        with self.assertRaises(SevenZipMissing):
            self._run(str(self.root / "missing" / "7z.exe"))

    # -- environment override ---------------------------------------------

    def test_env_override_beats_vendor_and_install(self) -> None:
        env_backend = self._write("env/7z.exe")
        self._write("vendor/7zip/7z.exe")
        self._write("pf/7-Zip/7z.exe")

        self.assertEqual(self._run(env={"DUCTZIP_7Z_PATH": str(env_backend)}), env_backend.resolve())

    # -- bundled backend priority ------------------------------------------

    def test_vendor_backend_beats_install_and_path(self) -> None:
        vendor = self._write("vendor/7zip/7z.exe")
        self._write("pf/7-Zip/7z.exe")

        self.assertEqual(self._run(), vendor.resolve())

    # -- system fallback chain ----------------------------------------------

    def test_install_dir_is_fallback_when_no_vendor(self) -> None:
        installed = self._write("pf/7-Zip/7z.exe")

        self.assertEqual(self._run(), installed.resolve())

    def test_missing_raises_when_nothing_found(self) -> None:
        with self.assertRaises(SevenZipMissing):
            self._run()


if __name__ == "__main__":
    unittest.main()
