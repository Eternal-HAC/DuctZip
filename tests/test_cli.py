from __future__ import annotations

from pathlib import Path
import os
import stat
import subprocess
import tempfile
import unittest
import zipfile

from ductzip.archive import (
    ArchiveNotFound,
    CorruptedArchive,
    SevenZipCliEngine,
    SevenZipMissing,
    UnsupportedFormat,
    WrongPassword,
    find_sevenzip,
)
from ductzip.archive.sevenzip import _map_sevenzip_error
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


class ErrorMappingTests(unittest.TestCase):
    def test_maps_wrong_password(self) -> None:
        self.assertIsInstance(_map_sevenzip_error("Wrong password"), WrongPassword)

    def test_maps_unsupported_format(self) -> None:
        self.assertIsInstance(_map_sevenzip_error("Unsupported Method"), UnsupportedFormat)

    def test_maps_corrupted_archive(self) -> None:
        self.assertIsInstance(_map_sevenzip_error("Can not open the file as archive"), CorruptedArchive)


if __name__ == "__main__":
    unittest.main()
