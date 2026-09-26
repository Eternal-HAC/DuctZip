from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
import unittest.mock
import zipfile

import ductzip.motw as motw
from ductzip.archive import SevenZipMissing, find_sevenzip
from ductzip.core import ExtractionService
from ductzip.motw import (
    read_zone_identifier,
    write_zone_identifier,
    propagate_motw,
)


MOTW_CONTENT = b"[ZoneTransfer]\r\nZoneId=3\r\nHostUrl=https://example.test/file.zip\r\n"


def require_ads_support(directory: Path) -> None:
    """Skip unless this file system supports NTFS alternate data streams."""
    probe = directory / "ads_probe.bin"
    probe.write_bytes(b"x")
    try:
        with open(f"{probe}:Zone.Identifier", "wb") as stream:
            stream.write(MOTW_CONTENT)
    except OSError:
        probe.unlink(missing_ok=True)
        raise unittest.SkipTest("file system does not support ADS streams")
    probe.unlink(missing_ok=True)


def require_sevenzip() -> None:
    try:
        find_sevenzip()
    except SevenZipMissing:
        raise unittest.SkipTest("7-Zip backend is not available")


class ZoneStreamTests(unittest.TestCase):
    def test_read_returns_none_when_no_stream(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            plain = Path(temp) / "plain.zip"
            plain.write_bytes(b"not important")
            self.assertIsNone(read_zone_identifier(plain))

    def test_write_then_read_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            require_ads_support(Path(temp))
            target = Path(temp) / "file.txt"
            target.write_text("data", encoding="utf-8")

            self.assertTrue(write_zone_identifier(target, MOTW_CONTENT))

            self.assertEqual(read_zone_identifier(target), MOTW_CONTENT)
            self.assertEqual(target.read_text(encoding="utf-8"), "data")


class PropagateMotwTests(unittest.TestCase):
    def _make_tree(self, root: Path) -> Path:
        archive = root / "download.zip"
        archive.write_bytes(b"archive-bytes")
        out = root / "out"
        (out / "sub" / "deep").mkdir(parents=True)
        (out / "top.txt").write_text("top", encoding="utf-8")
        (out / "sub" / "nested.txt").write_text("nested", encoding="utf-8")
        (out / "sub" / "deep" / "leaf.txt").write_text("leaf", encoding="utf-8")
        return archive

    def test_propagates_to_all_files_recursively_not_directories(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            require_ads_support(root)
            archive = self._make_tree(root)
            out = root / "out"
            write_zone_identifier(archive, MOTW_CONTENT)

            report = propagate_motw(archive, out)

            self.assertTrue(report.source_had_motw)
            self.assertEqual(report.propagated, 3)
            self.assertEqual(report.failures, ())
            self.assertEqual(read_zone_identifier(out / "top.txt"), MOTW_CONTENT)
            self.assertEqual(read_zone_identifier(out / "sub" / "nested.txt"), MOTW_CONTENT)
            self.assertEqual(read_zone_identifier(out / "sub" / "deep" / "leaf.txt"), MOTW_CONTENT)
            self.assertIsNone(read_zone_identifier(out / "sub"))

    def test_no_motw_source_is_silent_noop(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = self._make_tree(root)

            report = propagate_motw(archive, root / "out")

            self.assertFalse(report.source_had_motw)
            self.assertEqual(report.propagated, 0)
            self.assertIsNone(read_zone_identifier(root / "out" / "top.txt"))

    def test_write_failures_are_collected_not_raised(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            require_ads_support(root)
            archive = self._make_tree(root)
            out = root / "out"
            write_zone_identifier(archive, MOTW_CONTENT)
            failing = out / "sub" / "nested.txt"

            original = motw.write_zone_identifier

            def fake_writer(path, content):
                if Path(path) == failing:
                    return False
                return original(path, content)

            with unittest.mock.patch.object(motw, "write_zone_identifier", side_effect=fake_writer, autospec=True):
                report = propagate_motw(archive, out)

            self.assertEqual(report.propagated, 2)
            self.assertEqual(report.failures, (failing,))

    def test_reparse_points_are_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            require_ads_support(root)
            archive = self._make_tree(root)
            out = root / "out"
            write_zone_identifier(archive, MOTW_CONTENT)

            def fake_is_reparse(path):
                return Path(path).name == "nested.txt"

            with unittest.mock.patch.object(motw, "_is_reparse_point", side_effect=fake_is_reparse):
                report = propagate_motw(archive, out)

            self.assertEqual(report.propagated, 2)
            self.assertIsNone(read_zone_identifier(out / "sub" / "nested.txt"))

    def test_missing_output_dir_is_noop_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            require_ads_support(root)
            archive = root / "a.zip"
            archive.write_bytes(b"bytes")
            write_zone_identifier(archive, MOTW_CONTENT)

            report = propagate_motw(archive, root / "does-not-exist")

            self.assertTrue(report.source_had_motw)
            self.assertEqual(report.propagated, 0)
            self.assertEqual(report.failures, ())


class ServiceMotwIntegrationTests(unittest.TestCase):
    def _make_zip(self, root: Path) -> Path:
        archive = root / "download.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("docs/readme.txt", "hello motw")
            zf.writestr("docs/extra/notes.txt", "nested")
        return archive

    def test_extract_propagates_motw_to_extracted_files(self) -> None:
        require_sevenzip()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            require_ads_support(root)
            archive = self._make_zip(root)
            write_zone_identifier(archive, MOTW_CONTENT)
            out = root / "out"

            service = ExtractionService()
            service.extract(archive, out, smart_output=False)

            report = service.last_motw_report
            self.assertIsNotNone(report)
            self.assertTrue(report.source_had_motw)
            self.assertEqual(report.failures, ())
            self.assertEqual(read_zone_identifier(out / "docs" / "readme.txt"), MOTW_CONTENT)
            self.assertEqual(read_zone_identifier(out / "docs" / "extra" / "notes.txt"), MOTW_CONTENT)
            self.assertIsNone(read_zone_identifier(out / "docs"))

    def test_extract_without_motw_leaves_files_untagged(self) -> None:
        require_sevenzip()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            require_ads_support(root)
            archive = self._make_zip(root)
            out = root / "out"

            service = ExtractionService()
            service.extract(archive, out, smart_output=False)

            self.assertIsNotNone(service.last_motw_report)
            self.assertFalse(service.last_motw_report.source_had_motw)
            self.assertIsNone(read_zone_identifier(out / "docs" / "readme.txt"))

    def test_motw_failure_does_not_fail_extraction(self) -> None:
        require_sevenzip()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            require_ads_support(root)
            archive = self._make_zip(root)
            write_zone_identifier(archive, MOTW_CONTENT)
            out = root / "out"

            with unittest.mock.patch.object(motw, "write_zone_identifier", return_value=False):
                service = ExtractionService()
                result = service.extract(archive, out, smart_output=False)

            self.assertEqual((out / "docs" / "readme.txt").read_text(encoding="utf-8"), "hello motw")
            self.assertEqual(service.last_motw_report.propagated, 0)
            self.assertEqual(len(service.last_motw_report.failures), 2)
            self.assertEqual(result.output_dir, out.resolve())

    def test_extract_does_not_tag_preexisting_files(self) -> None:
        """Merge into a directory that already holds local files: MOTW must
        reach only the files this extraction produced, never pre-existing
        local content (SECURITY.md: the stream goes onto every *extracted*
        file). Before the fix, ``propagate_motw`` walked the whole final
        output directory and tagged local files as downloaded."""
        require_sevenzip()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            require_ads_support(root)
            archive = self._make_zip(root)
            write_zone_identifier(archive, MOTW_CONTENT)
            out = root / "out"
            preexisting = out / "docs"
            preexisting.mkdir(parents=True)
            local_file = preexisting / "local.txt"
            local_file.write_text("local content", encoding="utf-8")

            service = ExtractionService()
            service.extract(archive, out, smart_output=False, conflict_strategy="merge")

            report = service.last_motw_report
            self.assertIsNotNone(report)
            self.assertTrue(report.source_had_motw)
            self.assertEqual(report.failures, ())
            # Newly extracted files carry the archive's zone...
            self.assertEqual(read_zone_identifier(out / "docs" / "readme.txt"), MOTW_CONTENT)
            self.assertEqual(read_zone_identifier(out / "docs" / "extra" / "notes.txt"), MOTW_CONTENT)
            # ...but the pre-existing local file keeps its own (empty) state.
            self.assertIsNone(read_zone_identifier(local_file))


if __name__ == "__main__":
    unittest.main()
