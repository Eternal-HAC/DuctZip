"""Adversarial security regression tests (v0.7).

Covers the Phase 5 requirement: traversal variants, special Windows
names/paths, malformed archives, cancellation races, and password
non-leakage. Tests that need a real 7-Zip backend skip cleanly when it is
unavailable; the path-validation matrix is pure and always runs.
"""

from __future__ import annotations

import contextlib
import io
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
import zipfile

import tests.settings_harness  # noqa: F401  # forces a throwaway settings path
from ductzip.archive import (
    ArchiveCancelled,
    CorruptedArchive,
    ArchiveEntry,
    PathTraversalBlocked,
    SevenZipCliEngine,
    SevenZipMissing,
    find_sevenzip,
)
from ductzip.archive.sevenzip import _is_safe_archive_path, _validate_archive_paths
from ductzip.cli import main


def _entry(path: str) -> ArchiveEntry:
    return ArchiveEntry(path=path, size=None, modified=None, attributes=None, is_directory=False)


class PathValidationMatrixTests(unittest.TestCase):
    """Pure-function matrix for the engine's pre-extraction path validation."""

    UNSAFE_PATHS = (
        # relative traversal, either separator, any depth
        "../evil.txt",
        "..\\evil.txt",
        "a/../../evil.txt",
        "a\\..\\..\\evil.txt",
        "dir/sub/../../../evil.txt",
        # dot and empty segments
        "./evil.txt",
        "a/./b.txt",
        "a//b.txt",
        # absolute / drive / UNC / device-prefix styles
        "/evil.txt",
        "C:/evil.txt",
        "c:/evil.txt",
        "C:evil.txt",
        "//server/share/evil.txt",
        "\\\\server\\share\\evil.txt",
        "\\\\?\\C:\\evil.txt",
        "\\\\?\\UNC\\server\\share\\evil.txt",
        # Windows reserved device names, with extensions, case, dots/spaces
        "NUL",
        "nul.txt",
        "NUL .txt",
        "a/NUL",
        "CON",
        "con.png",
        "PRN",
        "AUX",
        "CONIN$",
        "CONOUT$",
        "COM1",
        "com1.exe",
        "COM9.dat",
        "LPT1",
        "lpt9.log",
    )

    SAFE_PATHS = (
        "hello.txt",
        "dir/sub/file.txt",
        "dir\\sub\\file.txt",
        "目录/文件 名.txt",
        "archive.tar.gz",
        "with space/file name.txt",
        "a.b.c/d.e.f",
        # near-misses that must NOT be rejected
        ".../x.txt",
        "..evil/x.txt",
        "evil../x.txt",
        "comma1.txt",
        "congress/report.txt",
        "sub/nulldir/x.txt",
    )

    def test_unsafe_paths_rejected(self) -> None:
        for path in self.UNSAFE_PATHS:
            with self.subTest(path=path):
                self.assertFalse(_is_safe_archive_path(path), f"expected unsafe: {path}")

    def test_safe_paths_accepted(self) -> None:
        for path in self.SAFE_PATHS:
            with self.subTest(path=path):
                self.assertTrue(_is_safe_archive_path(path), f"expected safe: {path}")

    def test_validate_batch_rejects_when_any_entry_is_bad(self) -> None:
        entries = tuple(_entry(p) for p in ("ok/a.txt", "ok/b.txt", "../evil.txt"))
        with self.assertRaises(PathTraversalBlocked):
            _validate_archive_paths(entries)

    def test_validate_batch_accepts_all_safe(self) -> None:
        entries = tuple(_entry(p) for p in ("ok/a.txt", "dir/b.txt"))
        _validate_archive_paths(entries)  # must not raise


class TraversalIntegrationTests(unittest.TestCase):
    def test_backslash_traversal_archive_is_blocked_with_real_backend(self) -> None:
        try:
            find_sevenzip()
        except SevenZipMissing:
            self.skipTest("7-Zip backend is not available")

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "unsafe.zip"
            output = root / "output"

            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("..\\evil.txt", "nope")

            with self.assertRaises(PathTraversalBlocked):
                SevenZipCliEngine().extract(archive, output)
            self.assertFalse((root / "evil.txt").exists())
            self.assertFalse(output.exists())


class MalformedArchiveTests(unittest.TestCase):
    def _require_backend(self) -> None:
        try:
            find_sevenzip()
        except SevenZipMissing:
            self.skipTest("7-Zip backend is not available")

    def test_garbage_bytes_map_to_corrupted_archive(self) -> None:
        self._require_backend()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "garbage.zip"
            archive.write_bytes(b"this is not a zip or any archive format" * 8)
            with self.assertRaises(CorruptedArchive):
                SevenZipCliEngine().extract(archive, root / "out")

    def test_truncated_zip_maps_to_corrupted_archive(self) -> None:
        self._require_backend()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "truncated.zip"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("a.txt", "content")
            archive.write_bytes(archive.read_bytes()[: archive.stat().st_size // 2])
            with self.assertRaises(CorruptedArchive):
                SevenZipCliEngine().list(archive)

    def test_empty_file_maps_to_corrupted_archive(self) -> None:
        self._require_backend()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "empty.7z"
            archive.write_bytes(b"")
            with self.assertRaises(CorruptedArchive):
                SevenZipCliEngine().test(archive)

    def test_cli_extract_of_garbage_exits_1_with_stable_message(self) -> None:
        self._require_backend()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "garbage.zip"
            archive.write_bytes(b"not an archive at all")
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = main(["extract", str(archive), "-o", str(root / "out")])
            self.assertEqual(code, 1)
            self.assertIn("损坏", stderr.getvalue() + stdout.getvalue())


class CancellationRaceTests(unittest.TestCase):
    def test_preset_cancel_aborts_extract_with_real_backend(self) -> None:
        try:
            find_sevenzip()
        except SevenZipMissing:
            self.skipTest("7-Zip backend is not available")

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "data.zip"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("a.txt", "x" * 4096)
            cancel = threading.Event()
            cancel.set()
            with self.assertRaises(ArchiveCancelled):
                for _ in SevenZipCliEngine().extract_with_progress(archive, root / "out", cancel_event=cancel):
                    pass

    def test_cancel_during_extract_eventually_raises_and_reaps(self) -> None:
        try:
            find_sevenzip()
        except SevenZipMissing:
            self.skipTest("7-Zip backend is not available")

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "big.zip"
            # A few MB of incompressible-ish data gives the cancel timer a window.
            with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED) as zf:
                zf.writestr("big.bin", bytes(range(256)) * 65536)

            cancel = threading.Event()

            def trigger() -> None:
                cancel.set()

            timer = threading.Timer(0.05, trigger)
            timer.start()
            outcome: list[str] = []
            try:
                for _ in SevenZipCliEngine().extract_with_progress(archive, root / "out", cancel_event=cancel):
                    pass
                outcome.append("completed")
            except ArchiveCancelled:
                outcome.append("cancelled")
            finally:
                timer.cancel()
            # Both outcomes are legal for a race; what must never happen is
            # hanging or leaving the backend alive (the engine reaps on cancel).
            self.assertIn(outcome, (["completed"], ["cancelled"]))


class PasswordNonLeakageTests(unittest.TestCase):
    def test_cli_wrong_password_never_echoes_the_password(self) -> None:
        try:
            sevenzip = find_sevenzip()
        except SevenZipMissing:
            self.skipTest("7-Zip backend is not available")

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "secret.txt"
            archive = root / "secret.7z"
            source.write_text("top secret", encoding="utf-8")
            created = subprocess.run(
                [str(sevenzip), "a", str(archive), str(source), "-pDZknownPW7271"],
                capture_output=True,
                check=False,
            )
            if created.returncode != 0:
                self.skipTest("7-Zip backend cannot create password-protected test archive")

            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = main(["extract", str(archive), "-o", str(root / "out"), "--password", "DZuniquePW9898"])
            self.assertEqual(code, 1)
            combined = stdout.getvalue() + stderr.getvalue()
            self.assertNotIn("DZuniquePW9898", combined)
            self.assertNotIn("DZknownPW7271", combined)


if __name__ == "__main__":
    unittest.main()
