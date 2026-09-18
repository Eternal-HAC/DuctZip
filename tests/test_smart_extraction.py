from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from ductzip.archive import ArchiveEntry
from ductzip.core import (
    SmartOutputPolicy,
    archive_logical_name,
    detect_output_conflicts,
    resolve_conflict_overwrite_policy,
)


def entry(path: str, is_directory: bool = False) -> ArchiveEntry:
    return ArchiveEntry(
        path=path,
        size=None,
        modified=None,
        attributes="D" if is_directory else None,
        is_directory=is_directory,
    )


def resolve(archive: Path, requested: Path, entries) -> Path:
    return SmartOutputPolicy().resolve_final_dir(archive, requested, entries)


class ArchiveLogicalNameTests(unittest.TestCase):
    def test_logical_name_derives_same_name_output_dir(self) -> None:
        archive = Path("D:/Downloads/photos.zip")
        self.assertEqual(archive.parent / archive_logical_name(archive), Path("D:/Downloads/photos"))
        bundle = Path("D:/Downloads/bundle.tar.gz")
        self.assertEqual(bundle.parent / archive_logical_name(bundle), Path("D:/Downloads/bundle"))

    def test_strips_common_archive_extensions(self) -> None:
        cases = {
            "photos.zip": "photos",
            "photos.7z": "photos",
            "photos.rar": "photos",
            "bundle.tar.gz": "bundle",
            "bundle.tgz": "bundle",
            "bundle.tar.bz2": "bundle",
            "bundle.tar.xz": "bundle",
        }
        for filename, expected in cases.items():
            with self.subTest(filename=filename):
                self.assertEqual(archive_logical_name(Path("D:/Downloads") / filename), expected)

    def test_strips_volume_naming(self) -> None:
        self.assertEqual(archive_logical_name("photos.7z.001"), "photos")
        self.assertEqual(archive_logical_name("photos.7z.099"), "photos")
        self.assertEqual(archive_logical_name("movie.part01.rar"), "movie")
        self.assertEqual(archive_logical_name("movie.part1.rar"), "movie")
        self.assertEqual(archive_logical_name("movie.part99.rar"), "movie")

    def test_handles_chinese_and_spaces(self) -> None:
        self.assertEqual(archive_logical_name("让子弹飞（二）.rar"), "让子弹飞（二）")
        self.assertEqual(archive_logical_name("my photos.tar.gz"), "my photos")
        self.assertEqual(archive_logical_name("我的 照片.7z.001"), "我的 照片")

    def test_unknown_extension_is_kept(self) -> None:
        self.assertEqual(archive_logical_name("notes.txt"), "notes.txt")
        self.assertEqual(archive_logical_name("no_extension"), "no_extension")


class SmartOutputPolicyTests(unittest.TestCase):
    def test_empty_listing_keeps_requested_output(self) -> None:
        requested = Path("D:/Downloads/empty")

        self.assertEqual(resolve(Path("D:/Downloads/empty.zip"), requested, ()), requested)

    def test_single_top_level_file_keeps_requested_output(self) -> None:
        requested = Path("D:/Downloads/photos")

        output = resolve(Path("D:/Downloads/photos.zip"), requested, (entry("readme.txt"),))

        self.assertEqual(output, requested)

    def test_single_top_level_file_same_name_still_keeps_requested_output(self) -> None:
        requested = Path("D:/Downloads/readme.txt")

        output = resolve(Path("D:/Downloads/readme.zip"), requested, (entry("readme.txt"),))

        self.assertEqual(output, requested)

    def test_single_top_level_folder_uses_parent_when_requested_folder_matches(self) -> None:
        requested = Path("D:/Downloads/photos")
        entries = (
            entry("photos", is_directory=True),
            entry("photos/a.jpg"),
            entry("photos/b.jpg"),
        )

        output = resolve(Path("D:/Downloads/photos.zip"), requested, entries)

        self.assertEqual(output, Path("D:/Downloads"))

    def test_single_top_level_folder_match_is_case_insensitive(self) -> None:
        requested = Path("D:/Downloads/Photos")
        entries = (
            entry("photos", is_directory=True),
            entry("photos/a.jpg"),
        )

        output = resolve(Path("D:/Downloads/photos.zip"), requested, entries)

        self.assertEqual(output, Path("D:/Downloads"))

    def test_single_top_level_folder_children_only_still_detects_directory(self) -> None:
        requested = Path("D:/Downloads/photos")

        output = resolve(Path("D:/Downloads/photos.zip"), requested, (entry("photos/a.jpg"),))

        self.assertEqual(output, Path("D:/Downloads"))

    def test_case_variants_of_same_top_level_count_as_one(self) -> None:
        requested = Path("D:/Downloads/folder")
        entries = (
            entry("Folder", is_directory=True),
            entry("Folder/a.txt"),
            entry("folder/b.txt"),
        )

        output = resolve(Path("D:/Downloads/folder.zip"), requested, entries)

        self.assertEqual(output, Path("D:/Downloads"))

    def test_case_variant_children_only_count_as_one_top_level(self) -> None:
        requested = Path("D:/ExtractHere")
        entries = (entry("Folder/a.txt"), entry("folder/b.txt"))

        output = resolve(Path("D:/Downloads/folder.zip"), requested, entries)

        self.assertEqual(output, requested)

    def test_top_level_names_deduplicate_case_insensitively(self) -> None:
        from ductzip.core.smart_output import top_level_names

        names = top_level_names((entry("Folder/a.txt"), entry("folder/b.txt"), entry("other.txt")))

        self.assertEqual(len(names), 2)
        self.assertIn("Folder", names)
        self.assertIn("other.txt", names)

    def test_single_top_level_folder_keeps_different_requested_output(self) -> None:
        requested = Path("D:/ExtractHere")
        entries = (
            entry("photos", is_directory=True),
            entry("photos/a.jpg"),
        )

        output = resolve(Path("D:/Downloads/photos.zip"), requested, entries)

        self.assertEqual(output, requested)

    def test_multiple_top_level_entries_use_archive_name_subdir(self) -> None:
        requested = Path("D:/Downloads")
        entries = (entry("a.txt"), entry("b.txt"))

        output = resolve(Path("D:/Downloads/photos.zip"), requested, entries)

        self.assertEqual(output, Path("D:/Downloads/photos"))

    def test_multiple_top_level_entries_with_tar_gz_archive(self) -> None:
        requested = Path("D:/Downloads")

        output = resolve(Path("D:/Downloads/bundle.tar.gz"), requested, (entry("a.txt"), entry("b.txt")))

        self.assertEqual(output, Path("D:/Downloads/bundle"))

    def test_multiple_top_level_entries_avoid_name_name_when_base_matches(self) -> None:
        requested = Path("D:/Downloads/photos")
        entries = (entry("a.txt"), entry("b.txt"))

        output = resolve(Path("D:/Downloads/photos.zip"), requested, entries)

        self.assertEqual(output, requested)

    def test_multiple_top_level_entries_match_is_case_insensitive(self) -> None:
        requested = Path("D:/Downloads/PHOTOS")

        output = resolve(Path("D:/Downloads/photos.zip"), requested, (entry("a.txt"), entry("b.txt")))

        self.assertEqual(output, requested)

    def test_policy_has_no_filesystem_side_effects(self) -> None:
        requested = Path("D:/nonexistent-dir-xyz/out")
        entries = (entry("a.txt"), entry("b.txt"))

        output = resolve(Path("D:/nonexistent-dir-xyz/photos.zip"), requested, entries)

        self.assertEqual(output, requested / "photos")
        self.assertFalse(output.exists())


class ConflictDetectionTests(unittest.TestCase):
    def test_detects_existing_top_level_directory_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            (output / "photos").mkdir()
            conflicts = detect_output_conflicts(output, (entry("photos/a.jpg"), entry("photos/b.jpg")))

            self.assertEqual(len(conflicts), 1)
            self.assertEqual(conflicts[0].entry_path, "photos")
            self.assertEqual(conflicts[0].target_path, output / "photos")

    def test_detects_existing_top_level_file_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            (output / "readme.txt").write_text("old", encoding="utf-8")

            conflicts = detect_output_conflicts(output, (entry("readme.txt"), entry("other.txt")))

            self.assertEqual(len(conflicts), 1)
            self.assertEqual(conflicts[0].entry_path, "readme.txt")

    def test_no_conflicts_when_top_level_targets_do_not_exist(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)

            conflicts = detect_output_conflicts(output, (entry("new/a.txt"), entry("other.txt")))

            self.assertEqual(conflicts, ())

    def test_rename_conflict_strategy_forces_rename_overwrite_policy(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            (output / "readme.txt").write_text("old", encoding="utf-8")
            conflicts = detect_output_conflicts(output, (entry("readme.txt"),))

            policy = resolve_conflict_overwrite_policy("overwrite", "rename", conflicts)

            self.assertEqual(policy, "rename")

    def test_merge_conflict_strategy_keeps_existing_overwrite_policy(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            (output / "readme.txt").write_text("old", encoding="utf-8")
            conflicts = detect_output_conflicts(output, (entry("readme.txt"),))

            policy = resolve_conflict_overwrite_policy("skip", "merge", conflicts)

            self.assertEqual(policy, "skip")


if __name__ == "__main__":
    unittest.main()
