from __future__ import annotations

import inspect
from pathlib import Path
import tempfile
import unittest
import zipfile

from ductzip.archive import (
    ArchiveEntry,
    ArchiveListing,
    OutputConflictBlocked,
    PathTraversalBlocked,
    SevenZipCliEngine,
    SevenZipMissing,
    find_sevenzip,
)
from ductzip.core import ExtractionService, SmartOutputPolicy


def require_sevenzip() -> None:
    try:
        find_sevenzip()
    except SevenZipMissing:
        raise unittest.SkipTest("7-Zip backend is not available")


class EngineInterfaceTests(unittest.TestCase):
    def test_engine_extract_has_no_policy_parameters(self) -> None:
        extract_params = set(inspect.signature(SevenZipCliEngine.extract).parameters)
        progress_params = set(inspect.signature(SevenZipCliEngine.extract_with_progress).parameters)

        for params in (extract_params, progress_params):
            self.assertNotIn("smart_output", params)
            self.assertNotIn("conflict_strategy", params)

    def test_engine_extract_has_no_listing_parameter(self) -> None:
        extract_params = set(inspect.signature(SevenZipCliEngine.extract).parameters)
        progress_params = set(inspect.signature(SevenZipCliEngine.extract_with_progress).parameters)

        for params in (extract_params, progress_params):
            self.assertNotIn("listing", params)

    def test_service_uses_configured_policy(self) -> None:
        policy = SmartOutputPolicy()
        service = ExtractionService(policy=policy)

        self.assertIs(service.policy, policy)


class ExtractionServiceSmartTests(unittest.TestCase):
    def test_smart_output_disabled_keeps_requested_output(self) -> None:
        require_sevenzip()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "photos.zip"
            requested = root / "photos"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("photos/a.txt", "hello")

            service = ExtractionService()
            result = service.extract(archive, requested, smart_output=False)

            self.assertEqual(result.output_dir, requested.resolve())
            self.assertEqual((requested / "photos" / "a.txt").read_text(encoding="utf-8"), "hello")

    def test_smart_output_single_top_level_folder_uses_parent(self) -> None:
        require_sevenzip()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "photos.zip"
            requested = root / "photos"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("photos/a.txt", "hello smart output")

            result = ExtractionService().extract(archive, requested, smart_output=True)

            self.assertEqual(result.output_dir, root.resolve())
            self.assertEqual((root / "photos" / "a.txt").read_text(encoding="utf-8"), "hello smart output")
            self.assertFalse((root / "photos" / "photos").exists())

    def test_smart_output_multiple_top_level_entries_use_name_subdir(self) -> None:
        require_sevenzip()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "photos.zip"
            requested = root / "out"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("a.txt", "a")
                zf.writestr("b/b.txt", "b")

            result = ExtractionService().extract(archive, requested, smart_output=True)

            self.assertEqual(result.output_dir, (requested / "photos").resolve())
            self.assertEqual((requested / "photos" / "a.txt").read_text(encoding="utf-8"), "a")
            self.assertEqual((requested / "photos" / "b" / "b.txt").read_text(encoding="utf-8"), "b")

    def test_smart_output_multiple_top_level_avoids_name_name(self) -> None:
        require_sevenzip()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "photos.zip"
            requested = root / "photos"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("a.txt", "a")
                zf.writestr("b.txt", "b")

            result = ExtractionService().extract(archive, requested, smart_output=True)

            self.assertEqual(result.output_dir, requested.resolve())

    def test_plan_reuses_provided_listing(self) -> None:
        require_sevenzip()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "photos.zip"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("photos/a.txt", "hello")

            service = ExtractionService()
            listing = service.list(archive)
            original_list = service.engine.list

            def counting_list(*args, **kwargs):
                counting_list.calls += 1
                return original_list(*args, **kwargs)

            counting_list.calls = 0
            service.engine.list = counting_list  # type: ignore[method-assign]

            plan = service.plan(archive, root / "out", smart_output=True, listing=listing)

            self.assertEqual(counting_list.calls, 0)
            self.assertEqual(plan.final_output_dir, root / "out")


class ExtractionServiceConflictTests(unittest.TestCase):
    def test_conflict_strategy_cancel_blocks_extract(self) -> None:
        require_sevenzip()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "conflict.zip"
            output = root / "output"
            output.mkdir()
            (output / "same.txt").write_text("old", encoding="utf-8")

            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("same.txt", "new")

            with self.assertRaises(OutputConflictBlocked):
                ExtractionService().extract(archive, output, conflict_strategy="cancel")

            self.assertEqual((output / "same.txt").read_text(encoding="utf-8"), "old")

    def test_conflict_strategy_rename_preserves_existing_file(self) -> None:
        require_sevenzip()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "conflict.zip"
            output = root / "output"
            output.mkdir()
            (output / "same.txt").write_text("old", encoding="utf-8")

            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("same.txt", "new")

            ExtractionService().extract(archive, output, overwrite_policy="overwrite", conflict_strategy="rename")

            self.assertEqual((output / "same.txt").read_text(encoding="utf-8"), "old")
            files = sorted(path.name for path in output.iterdir())
            self.assertGreaterEqual(len(files), 2)

    def test_conflict_strategy_merge_keeps_overwrite_policy(self) -> None:
        require_sevenzip()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "conflict.zip"
            output = root / "output"
            output.mkdir()
            (output / "same.txt").write_text("old", encoding="utf-8")

            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("same.txt", "new")

            ExtractionService().extract(archive, output, overwrite_policy="skip", conflict_strategy="merge")

            self.assertEqual((output / "same.txt").read_text(encoding="utf-8"), "old")


class ExtractionServiceSecurityTests(unittest.TestCase):
    def test_path_traversal_blocked_with_smart_output_enabled(self) -> None:
        require_sevenzip()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "unsafe.zip"
            output = root / "output"
            outside = root / "evil.txt"

            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("../evil.txt", "nope")

            with self.assertRaises(PathTraversalBlocked):
                ExtractionService().extract(archive, output, smart_output=True)

            self.assertFalse(outside.exists())

    def test_path_traversal_not_bypassed_by_precomputed_listing(self) -> None:
        require_sevenzip()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "unsafe.zip"
            output = root / "output"
            outside = root / "evil.txt"

            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("../evil.txt", "nope")

            service = ExtractionService()
            listing = service.list(archive)

            with self.assertRaises(PathTraversalBlocked):
                service.extract(archive, output, smart_output=True, listing=listing)

            self.assertFalse(outside.exists())

    def test_path_traversal_not_bypassed_by_forged_safe_listing(self) -> None:
        require_sevenzip()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "unsafe.zip"
            output = root / "output"
            outside = root / "evil.txt"

            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("../evil.txt", "nope")

            service = ExtractionService()
            real_listing = service.list(archive)
            forged = ArchiveListing(
                archive_path=real_listing.archive_path,
                sevenzip_path=real_listing.sevenzip_path,
                entries=(
                    ArchiveEntry(
                        path="safe.txt",
                        size=4,
                        modified=None,
                        attributes=None,
                        is_directory=False,
                    ),
                ),
                stdout=real_listing.stdout,
                stderr=real_listing.stderr,
            )

            with self.assertRaises(PathTraversalBlocked):
                service.extract(archive, output, smart_output=True, listing=forged)

            self.assertFalse(outside.exists())
            self.assertFalse(output.exists())

    def test_path_traversal_blocked_at_engine_level_without_service(self) -> None:
        require_sevenzip()
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

    def test_smart_output_treats_case_variants_as_single_top_level(self) -> None:
        require_sevenzip()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "bundle.zip"
            requested = root / "out"

            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("Folder/a.txt", "a")
                zf.writestr("folder/b.txt", "b")

            result = ExtractionService().extract(archive, requested, smart_output=True)

            self.assertEqual(result.output_dir, requested.resolve())
            self.assertEqual((requested / "Folder" / "a.txt").read_text(encoding="utf-8"), "a")
            self.assertEqual((requested / "folder" / "b.txt").read_text(encoding="utf-8"), "b")


if __name__ == "__main__":
    unittest.main()
