from __future__ import annotations

from pathlib import Path
import os
import stat
import subprocess
import tempfile
import threading
import unittest
import zipfile

from ductzip.archive import (
    ArchiveCancelled,
    ArchiveNotFound,
    CorruptedArchive,
    PathTraversalBlocked,
    SevenZipCliEngine,
    SevenZipMissing,
    UnsupportedFormat,
    WrongPassword,
    find_sevenzip,
)
from ductzip.archive.sevenzip import _map_sevenzip_error, _parse_progress_token
from ductzip.cli import main


def make_fake_7z(directory: Path, exit_code: int = 0, output: str = "fake 7z") -> Path:
    script = directory / ("fake7z.cmd" if os.name == "nt" else "fake7z")
    if os.name == "nt":
        script.write_text(f"@echo off\r\necho {output} %*\r\nexit /b {exit_code}\r\n", encoding="utf-8")
    else:
        script.write_text(f"#!/bin/sh\necho {output} \"$@\"\nexit {exit_code}\n", encoding="utf-8")
        script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return script


class SevenZipDiscoveryTests(unittest.TestCase):
    def test_explicit_path_is_used(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            fake = make_fake_7z(Path(temp))
            self.assertEqual(find_sevenzip(fake), fake.resolve())

    def test_missing_explicit_path_raises(self) -> None:
        with self.assertRaises(SevenZipMissing):
            find_sevenzip("Z:/definitely/missing/7z.exe")


class ExtractTests(unittest.TestCase):
    def test_extract_creates_output_and_succeeds_with_fake_7z(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fake = make_fake_7z(root)
            archive = root / "测试 archive.zip"
            archive.write_bytes(b"not a real zip; fake backend handles it")
            output = root / "输出 目录"

            engine = SevenZipCliEngine(fake)
            result = engine.extract(archive, output)

            self.assertTrue(output.is_dir())
            self.assertEqual(result.output_dir, output.resolve())
            self.assertIn("fake 7z x", result.stdout)

    def test_missing_archive_raises(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fake = make_fake_7z(root)
            engine = SevenZipCliEngine(fake)

            with self.assertRaises(ArchiveNotFound):
                engine.extract(root / "missing.zip", root / "out")

    def test_failed_backend_maps_corrupted_archive(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fake = make_fake_7z(root, exit_code=2, output="Can not open the file as archive")
            archive = root / "broken.zip"
            archive.write_bytes(b"broken")

            engine = SevenZipCliEngine(fake)

            with self.assertRaises(CorruptedArchive):
                engine.extract(archive, root / "out")

    def test_extract_real_zip_when_sevenzip_is_available(self) -> None:
        try:
            find_sevenzip()
        except SevenZipMissing:
            self.skipTest("7-Zip backend is not available")

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "测试 archive.zip"
            output = root / "输出 目录"

            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("中文 文件.txt", "hello ductzip")

            engine = SevenZipCliEngine()
            engine.extract(archive, output)

            self.assertEqual((output / "中文 文件.txt").read_text(encoding="utf-8"), "hello ductzip")

    def test_extract_real_7z_when_sevenzip_is_available(self) -> None:
        try:
            sevenzip = find_sevenzip()
        except SevenZipMissing:
            self.skipTest("7-Zip backend is not available")

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            output = root / "output"
            archive = root / "sample.7z"
            source.mkdir()
            (source / "sample.txt").write_text("hello 7z", encoding="utf-8")

            completed = subprocess.run(
                [str(sevenzip), "a", str(archive), str(source / "*")],
                capture_output=True,
                text=True,
                errors="replace",
                check=False,
            )
            if completed.returncode != 0:
                self.skipTest("7-Zip backend cannot create 7z test archive")

            engine = SevenZipCliEngine()
            engine.extract(archive, output)

            self.assertEqual((output / "sample.txt").read_text(encoding="utf-8"), "hello 7z")

    def test_extract_password_protected_7z_when_sevenzip_is_available(self) -> None:
        try:
            sevenzip = find_sevenzip()
        except SevenZipMissing:
            self.skipTest("7-Zip backend is not available")

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "secret.txt"
            output = root / "output"
            archive = root / "secret.7z"
            source.write_text("top secret", encoding="utf-8")

            completed = subprocess.run(
                [str(sevenzip), "a", str(archive), str(source), "-psecret"],
                capture_output=True,
                text=True,
                errors="replace",
                check=False,
            )
            if completed.returncode != 0:
                self.skipTest("7-Zip backend cannot create password-protected test archive")

            engine = SevenZipCliEngine()
            engine.extract(archive, output, password="secret")

            self.assertEqual((output / "secret.txt").read_text(encoding="utf-8"), "top secret")

    def test_wrong_password_maps_error_when_sevenzip_is_available(self) -> None:
        try:
            sevenzip = find_sevenzip()
        except SevenZipMissing:
            self.skipTest("7-Zip backend is not available")

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "secret.txt"
            archive = root / "secret.7z"
            source.write_text("top secret", encoding="utf-8")

            completed = subprocess.run(
                [str(sevenzip), "a", str(archive), str(source), "-psecret"],
                capture_output=True,
                text=True,
                errors="replace",
                check=False,
            )
            if completed.returncode != 0:
                self.skipTest("7-Zip backend cannot create password-protected test archive")

            with self.assertRaises(WrongPassword):
                SevenZipCliEngine().test(archive, password="wrong")

    def test_path_traversal_is_blocked_when_sevenzip_is_available(self) -> None:
        try:
            find_sevenzip()
        except SevenZipMissing:
            self.skipTest("7-Zip backend is not available")

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "unsafe.zip"
            output = root / "output"
            outside = root / "evil.txt"

            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("../evil.txt", "nope")

            with self.assertRaises(PathTraversalBlocked):
                SevenZipCliEngine().extract(archive, output)

            self.assertFalse(outside.exists())

    def test_extract_with_progress_emits_lifecycle_events_when_sevenzip_is_available(self) -> None:
        try:
            find_sevenzip()
        except SevenZipMissing:
            self.skipTest("7-Zip backend is not available")

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "progress.zip"
            output = root / "output"

            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("hello.txt", "hello")

            events = list(SevenZipCliEngine().extract_with_progress(archive, output))

            self.assertEqual(events[0].kind, "started")
            self.assertEqual(events[-1].kind, "completed")
            self.assertEqual(events[-1].percent, 100)
            self.assertIsNotNone(events[-1].result)

    def test_extract_with_progress_can_be_cancelled(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fake = make_fake_7z(root)
            archive = root / "archive.zip"
            archive.write_bytes(b"fake")
            output = root / "out"
            cancel_event = threading.Event()

            generator = SevenZipCliEngine(fake).extract_with_progress(archive, output, cancel_event=cancel_event)
            first_event = next(generator)
            cancel_event.set()

            self.assertEqual(first_event.kind, "started")
            with self.assertRaises(ArchiveCancelled):
                list(generator)

    def test_overwrite_policy_skip_keeps_existing_file_when_sevenzip_is_available(self) -> None:
        try:
            find_sevenzip()
        except SevenZipMissing:
            self.skipTest("7-Zip backend is not available")

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "overwrite.zip"
            output = root / "output"
            output.mkdir()
            (output / "same.txt").write_text("old", encoding="utf-8")

            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("same.txt", "new")

            SevenZipCliEngine().extract(archive, output, overwrite_policy="skip")

            self.assertEqual((output / "same.txt").read_text(encoding="utf-8"), "old")

    def test_overwrite_policy_overwrite_replaces_existing_file_when_sevenzip_is_available(self) -> None:
        try:
            find_sevenzip()
        except SevenZipMissing:
            self.skipTest("7-Zip backend is not available")

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "overwrite.zip"
            output = root / "output"
            output.mkdir()
            (output / "same.txt").write_text("old", encoding="utf-8")

            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("same.txt", "new")

            SevenZipCliEngine().extract(archive, output, overwrite_policy="overwrite")

            self.assertEqual((output / "same.txt").read_text(encoding="utf-8"), "new")

    def test_overwrite_policy_rename_preserves_existing_file_when_sevenzip_is_available(self) -> None:
        try:
            find_sevenzip()
        except SevenZipMissing:
            self.skipTest("7-Zip backend is not available")

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "overwrite.zip"
            output = root / "output"
            output.mkdir()
            (output / "same.txt").write_text("old", encoding="utf-8")

            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("same.txt", "new")

            SevenZipCliEngine().extract(archive, output, overwrite_policy="rename")

            files = sorted(path.name for path in output.iterdir())
            self.assertEqual((output / "same.txt").read_text(encoding="utf-8"), "old")
            self.assertGreaterEqual(len(files), 2)

    def test_extract_real_rar_fixture_when_available(self) -> None:
        try:
            find_sevenzip()
        except SevenZipMissing:
            self.skipTest("7-Zip backend is not available")

        fixture = Path(__file__).with_name("让子弹飞（二）.rar")
        if not fixture.is_file():
            self.skipTest("RAR fixture is not available")

        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            engine = SevenZipCliEngine()
            engine.extract(fixture, output)

            extracted = output / "让子弹飞（二）.pdf"
            self.assertTrue(extracted.is_file())
            self.assertEqual(extracted.stat().st_size, 961505)


class ArchiveInspectionTests(unittest.TestCase):
    def test_list_real_zip_when_sevenzip_is_available(self) -> None:
        try:
            find_sevenzip()
        except SevenZipMissing:
            self.skipTest("7-Zip backend is not available")

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "list-test.zip"

            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("folder/hello.txt", "hello")

            listing = SevenZipCliEngine().list(archive)

            self.assertTrue(any(entry.path == "folder/hello.txt" for entry in listing.entries))

    def test_test_real_zip_when_sevenzip_is_available(self) -> None:
        try:
            find_sevenzip()
        except SevenZipMissing:
            self.skipTest("7-Zip backend is not available")

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "test-ok.zip"

            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("hello.txt", "hello")

            result = SevenZipCliEngine().test(archive)

            self.assertEqual(result.archive_path, archive.resolve())

    def test_list_real_rar_fixture_when_available(self) -> None:
        try:
            find_sevenzip()
        except SevenZipMissing:
            self.skipTest("7-Zip backend is not available")

        fixture = Path(__file__).with_name("让子弹飞（二）.rar")
        if not fixture.is_file():
            self.skipTest("RAR fixture is not available")

        listing = SevenZipCliEngine().list(fixture)

        self.assertTrue(any(entry.path == "让子弹飞（二）.pdf" for entry in listing.entries))


class CliTests(unittest.TestCase):
    def test_cli_extract_success(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fake = make_fake_7z(root)
            archive = root / "archive.zip"
            archive.write_bytes(b"fake")

            code = main(["extract", str(archive), "--output", str(root / "out"), "--sevenzip", str(fake)])

            self.assertEqual(code, 0)

    def test_cli_extract_missing_archive_returns_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fake = make_fake_7z(root)

            code = main(["extract", str(root / "missing.zip"), "--output", str(root / "out"), "--sevenzip", str(fake)])

            self.assertEqual(code, 1)

    def test_cli_doctor_success_with_fake_backend(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            fake = make_fake_7z(Path(temp), output="7-Zip fake version")

            code = main(["doctor", "--sevenzip", str(fake)])

            self.assertEqual(code, 0)

    def test_cli_doctor_missing_backend_returns_failure(self) -> None:
        code = main(["doctor", "--sevenzip", "Z:/definitely/missing/7z.exe"])

        self.assertEqual(code, 1)

    def test_cli_list_success(self) -> None:
        try:
            find_sevenzip()
        except SevenZipMissing:
            self.skipTest("7-Zip backend is not available")

        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / "cli-list.zip"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("hello.txt", "hello")

            code = main(["list", str(archive)])

            self.assertEqual(code, 0)

    def test_cli_test_success(self) -> None:
        try:
            find_sevenzip()
        except SevenZipMissing:
            self.skipTest("7-Zip backend is not available")

        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / "cli-test.zip"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("hello.txt", "hello")

            code = main(["test", str(archive)])

            self.assertEqual(code, 0)


class ErrorMappingTests(unittest.TestCase):
    def test_maps_wrong_password(self) -> None:
        self.assertIsInstance(_map_sevenzip_error("Wrong password"), WrongPassword)

    def test_maps_unsupported_format(self) -> None:
        self.assertIsInstance(_map_sevenzip_error("Unsupported Method"), UnsupportedFormat)

    def test_maps_corrupted_archive(self) -> None:
        self.assertIsInstance(_map_sevenzip_error("Can not open the file as archive"), CorruptedArchive)


class ProgressParsingTests(unittest.TestCase):
    def test_parses_percent_progress(self) -> None:
        event = _parse_progress_token(" 42%\r", None)

        self.assertIsNotNone(event)
        self.assertEqual(event.percent, 42)

    def test_skips_duplicate_percent(self) -> None:
        self.assertIsNone(_parse_progress_token(" 42%\r", 42))


if __name__ == "__main__":
    unittest.main()
