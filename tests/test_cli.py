from __future__ import annotations

import contextlib
import io
from pathlib import Path
import os
import stat
import subprocess
import tempfile
import threading
import unittest
import zipfile
from unittest.mock import patch

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

    def test_cli_extract_without_smart_output_keeps_requested_output(self) -> None:
        try:
            find_sevenzip()
        except SevenZipMissing:
            self.skipTest("7-Zip backend is not available")

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "photos.zip"
            requested = root / "photos"

            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("photos/a.txt", "hello")

            code = main(["extract", str(archive), "--output", str(requested)])

            self.assertEqual(code, 0)
            self.assertEqual((requested / "photos" / "a.txt").read_text(encoding="utf-8"), "hello")

    def test_cli_extract_smart_output_single_top_level_folder(self) -> None:
        try:
            find_sevenzip()
        except SevenZipMissing:
            self.skipTest("7-Zip backend is not available")

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "photos.zip"
            requested = root / "photos"

            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("photos/a.txt", "hello smart")

            code = main(["extract", str(archive), "--output", str(requested), "--smart-output"])

            self.assertEqual(code, 0)
            self.assertEqual((root / "photos" / "a.txt").read_text(encoding="utf-8"), "hello smart")
            self.assertFalse((root / "photos" / "photos").exists())

    def test_cli_extract_smart_output_multiple_top_level_entries(self) -> None:
        try:
            find_sevenzip()
        except SevenZipMissing:
            self.skipTest("7-Zip backend is not available")

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "photos.zip"
            requested = root / "out"

            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("a.txt", "a")
                zf.writestr("b.txt", "b")

            code = main(["extract", str(archive), "--output", str(requested), "--smart-output"])

            self.assertEqual(code, 0)
            self.assertEqual((requested / "photos" / "a.txt").read_text(encoding="utf-8"), "a")
            self.assertEqual((requested / "photos" / "b.txt").read_text(encoding="utf-8"), "b")

    def test_cli_extract_conflict_strategy_cancel_returns_failure(self) -> None:
        try:
            find_sevenzip()
        except SevenZipMissing:
            self.skipTest("7-Zip backend is not available")

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "conflict.zip"
            output = root / "output"
            output.mkdir()
            (output / "same.txt").write_text("old", encoding="utf-8")

            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("same.txt", "new")

            code = main(["extract", str(archive), "--output", str(output), "--conflict-strategy", "cancel"])

            self.assertEqual(code, 1)
            self.assertEqual((output / "same.txt").read_text(encoding="utf-8"), "old")

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


def make_logging_fake_7z(directory: Path, fail_substr: str | None = None) -> Path:
    """Fake 7z that appends every invocation to calls.log and optionally
    fails (as a corrupt archive) when the command line contains a substring."""
    script = directory / "fake7z-batch.cmd"
    lines = ["@echo off", f'echo %*>>"{directory}\\calls.log"']
    if fail_substr is not None:
        lines += [
            f'echo %* | findstr /C:"{fail_substr}" >nul',
            "if %errorlevel%==0 (",
            "echo Can not open the file as archive",
            "exit /b 2",
            ")",
        ]
    lines += ["echo fake 7z ok", "exit /b 0"]
    script.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")
    return script


def make_flaky_fake_7z(directory: Path) -> Path:
    """Fake 7z whose first invocation fails, later ones succeed."""
    counter = directory / "count.txt"
    script = directory / "fake7z-flaky.cmd"
    script.write_text(
        "@echo off\r\n"
        "set n=0\r\n"
        f'if exist "{counter}" set /p n=<"{counter}"\r\n'
        "set /a n+=1\r\n"
        f'(echo %n%)>"{counter}"\r\n'
        "if %n% lss 2 (\r\n"
        "echo Can not open the file as archive\r\n"
        "exit /b 2\r\n"
        ")\r\n"
        "echo fake 7z ok\r\n"
        "exit /b 0\r\n",
        encoding="utf-8",
    )
    return script


class BatchCliTests(unittest.TestCase):
    def run_batch(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_batch_mixed_success_and_failure_exit_code_and_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fake = make_logging_fake_7z(root, fail_substr="broken")
            good_a = root / "测试 a.zip"
            broken = root / "broken.zip"
            good_b = root / "b archive.zip"
            for archive in (good_a, broken, good_b):
                archive.write_bytes(b"fake")

            code, out, err = self.run_batch(
                ["batch-extract", str(good_a), str(broken), str(good_b),
                 "--output", str(root / "输出 目录"), "--sevenzip", str(fake)]
            )

            self.assertEqual(code, 1)
            self.assertIn("[失败] " + str(broken), out)
            self.assertIn("损坏", out)
            self.assertIn(f"[完成] {good_a}", out)
            self.assertIn(f"[完成] {good_b}", out)
            self.assertIn("失败 1", err)

    def test_batch_processes_in_cli_order(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fake = make_logging_fake_7z(root)
            first, second, third = root / "1.zip", root / "2.zip", root / "3.zip"
            for archive in (first, second, third):
                archive.write_bytes(b"fake")

            code, _, _ = self.run_batch(
                ["batch-extract", str(third), str(first), str(second),
                 "--output", str(root / "out"), "--sevenzip", str(fake)]
            )

            self.assertEqual(code, 0)
            calls = (root / "calls.log").read_text(encoding="utf-8", errors="replace")
            positions = [calls.index(name) for name in ("3.zip", "1.zip", "2.zip")]
            self.assertEqual(positions, sorted(positions))
            # Every archive was listed for planning and re-validated by the engine.
            for name in ("1.zip", "2.zip", "3.zip"):
                self.assertGreaterEqual(calls.count(name), 2)

    def test_batch_retry_recovers_flaky_backend(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fake = make_flaky_fake_7z(root)
            archive = root / "flaky.zip"
            archive.write_bytes(b"fake")

            code, out, _ = self.run_batch(
                ["batch-extract", str(archive), "--output", str(root / "out"),
                 "--sevenzip", str(fake), "--retries", "1"]
            )

            self.assertEqual(code, 0)
            self.assertIn("[完成]", out)

    def test_batch_without_retry_reports_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fake = make_flaky_fake_7z(root)
            archive = root / "flaky.zip"
            archive.write_bytes(b"fake")

            code, out, _ = self.run_batch(
                ["batch-extract", str(archive), "--output", str(root / "out"), "--sevenzip", str(fake)]
            )

            self.assertEqual(code, 1)
            self.assertIn("[失败]", out)

    def test_batch_smart_output_per_task_final_dirs(self) -> None:
        try:
            find_sevenzip()
        except SevenZipMissing:
            self.skipTest("7-Zip backend is not available")

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            base = root / "输出 目录"
            photos = root / "photos.zip"
            loose = root / "loose files.zip"
            with zipfile.ZipFile(photos, "w") as zf:
                zf.writestr("photos/a.txt", "hello")
            with zipfile.ZipFile(loose, "w") as zf:
                zf.writestr("one.txt", "1")
                zf.writestr("two.txt", "2")

            code, out, _ = self.run_batch(
                ["batch-extract", str(photos), str(loose), "--output", str(base)]
            )

            self.assertEqual(code, 0)
            # Single top-level dir -> base itself; multi top-level -> base/loose files.
            self.assertIn(f"[完成] {photos} -> {base.resolve()}", out)
            self.assertIn(f"[完成] {loose} -> {(base / 'loose files').resolve()}", out)

    def test_batch_missing_backend_returns_failure(self) -> None:
        code, _, err = self.run_batch(
            ["batch-extract", "whatever.zip", "--output", "out", "--sevenzip", "Z:/missing/7z.exe"]
        )

        self.assertEqual(code, 1)
        self.assertIn("7-Zip", err)

    def test_batch_negative_retries_is_usage_error(self) -> None:
        code, _, err = self.run_batch(
            ["batch-extract", "a.zip", "--output", "out", "--retries", "-1"]
        )

        self.assertEqual(code, 2)
        self.assertIn("retries", err)

    def test_batch_ctrl_c_cancels_and_returns_130(self) -> None:
        class _InterruptingQueue:
            def __init__(self, service):
                self.cancelled = False

            def add(self, *args, **kwargs):
                return None

            def run(self):
                raise KeyboardInterrupt
                yield  # pragma: no cover - makes this a generator

            def cancel_all(self):
                self.cancelled = True

            @property
            def tasks(self):
                return []

        with patch("ductzip.cli.BatchQueue", _InterruptingQueue):
            code, _, _ = self.run_batch(["batch-extract", "a.zip", "--output", "out"])

        self.assertEqual(code, 130)


class ShellCliTests(unittest.TestCase):
    """The Explorer-facing protocol: per-archive output roots, shell exit codes."""

    def run_shell(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_extract_here_uses_each_archives_parent_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fake = make_logging_fake_7z(root)
            dir_a = root / "dir a"
            dir_b = root / "目录 b"
            dir_a.mkdir()
            dir_b.mkdir()
            archive_a = dir_a / "photos.zip"
            archive_b = dir_b / "文档 archive.zip"
            for archive in (archive_a, archive_b):
                archive.write_bytes(b"fake")

            code, out, _ = self.run_shell(
                ["shell", "extract-here", str(archive_a), str(archive_b), "--sevenzip", str(fake)]
            )

            self.assertEqual(code, 0)
            self.assertIn(f"[完成] {archive_a} -> {dir_a.resolve()}", out)
            self.assertIn(f"[完成] {archive_b} -> {dir_b.resolve()}", out)

    def test_extract_to_uses_same_named_folder(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fake = make_logging_fake_7z(root)
            plain = root / "photos.zip"
            multi_suffix = root / "照片 档案.tar.gz"
            for archive in (plain, multi_suffix):
                archive.write_bytes(b"fake")

            code, out, _ = self.run_shell(
                ["shell", "extract-to", str(plain), str(multi_suffix), "--sevenzip", str(fake)]
            )

            self.assertEqual(code, 0)
            self.assertIn(f"[完成] {plain} -> {(root / 'photos').resolve()}", out)
            self.assertIn(
                f"[完成] {multi_suffix} -> {(root / '照片 档案').resolve()}", out
            )

    def test_extract_here_mixed_failure_isolated_and_exit_code(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fake = make_logging_fake_7z(root, fail_substr="broken")
            good = root / "good.zip"
            broken = root / "broken.zip"
            for archive in (good, broken):
                archive.write_bytes(b"fake")

            code, out, err = self.run_shell(
                ["shell", "extract-here", str(good), str(broken), "--sevenzip", str(fake)]
            )

            self.assertEqual(code, 1)
            self.assertIn("[完成]", out)
            self.assertIn("[失败]", out)
            self.assertIn("失败 1", err)

    def test_shell_verbs_reject_negative_retries(self) -> None:
        code, _, err = self.run_shell(["shell", "extract-here", "a.zip", "--retries", "-1"])

        self.assertEqual(code, 2)
        self.assertIn("retries", err)

    def test_shell_verbs_missing_backend_is_failure(self) -> None:
        code, _, err = self.run_shell(
            ["shell", "extract-to", "a.zip", "--sevenzip", "Z:/missing/7z.exe"]
        )

        self.assertEqual(code, 1)
        self.assertIn("7-Zip", err)


if __name__ == "__main__":
    unittest.main()
