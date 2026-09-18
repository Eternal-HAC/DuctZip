"""Pure Smart Output semantics for DuctZip.

This module computes the final extraction directory from an archive listing
without touching the file system (besides read-only ``exists()`` checks in
conflict detection). It is shared by the CLI, the GUI, and future batch
queueing code.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Literal, Protocol

ConflictStrategy = Literal["merge", "rename", "cancel"]
OverwritePolicy = Literal["skip", "overwrite", "rename"]


class ArchivePathEntry(Protocol):
    path: str
    is_directory: bool


@dataclass(frozen=True)
class OutputConflict:
    entry_path: str
    target_path: Path


_VOLUME_PATTERNS = (
    re.compile(r"\.7z\.\d{3}$", re.IGNORECASE),
    re.compile(r"\.zip\.\d{3}$", re.IGNORECASE),
    re.compile(r"\.rar\.\d{3}$", re.IGNORECASE),
    re.compile(r"\.part\d+\.rar$", re.IGNORECASE),
)

_MULTI_SUFFIXES = (
    ".tar.gz",
    ".tar.bz2",
    ".tar.xz",
    ".tar.zst",
    ".tar.br",
    ".tgz",
    ".tbz2",
    ".tbz",
    ".txz",
    ".tzst",
    ".tbr",
)

_SINGLE_SUFFIXES = (
    ".zip",
    ".7z",
    ".rar",
    ".tar",
    ".gz",
    ".bz2",
    ".xz",
    ".zst",
    ".br",
    ".cab",
    ".iso",
    ".jar",
    ".war",
    ".apk",
    ".wim",
)


def archive_logical_name(archive_path: str | Path) -> str:
    """Derive the logical archive name used for the same-name output folder.

    Strips common archive extensions, including multi-suffix formats such as
    ``tar.gz`` and volume naming such as ``.7z.001`` or ``part01.rar``. This
    is name derivation only; volume completeness diagnostics live elsewhere.
    """

    name = Path(archive_path).name
    for pattern in _VOLUME_PATTERNS:
        stripped = pattern.sub("", name)
        if stripped != name:
            return stripped or name

    lowered = name.lower()
    for suffix in _MULTI_SUFFIXES:
        if lowered.endswith(suffix) and len(name) > len(suffix):
            return name[: -len(suffix)]
    for suffix in _SINGLE_SUFFIXES:
        if lowered.endswith(suffix) and len(name) > len(suffix):
            return name[: -len(suffix)]
    return name


def top_level_names(entries: Iterable[ArchivePathEntry]) -> set[str]:
    """Top-level entry names, deduplicated case-insensitively.

    Windows paths are case-insensitive, so ``Folder/a.txt`` and
    ``folder/b.txt`` count as one top-level name. The returned set keeps one
    stable original display name (the first-seen spelling) per group for
    conflict prompts.
    """
    canonical: dict[str, str] = {}
    for entry in entries:
        name = _top_level_name(entry.path)
        if name is None:
            continue
        canonical.setdefault(name.casefold(), name)
    return set(canonical.values())


def detect_output_conflicts(output_dir: str | Path, entries: Iterable[ArchivePathEntry]) -> tuple[OutputConflict, ...]:
    output = Path(output_dir)
    conflicts: list[OutputConflict] = []
    seen_targets: set[Path] = set()

    for name in sorted(top_level_names(entries)):
        target = output / name
        if target in seen_targets:
            continue
        seen_targets.add(target)
        if target.exists():
            conflicts.append(OutputConflict(entry_path=name, target_path=target))

    return tuple(conflicts)


def resolve_conflict_overwrite_policy(
    overwrite_policy: OverwritePolicy,
    conflict_strategy: ConflictStrategy,
    conflicts: tuple[OutputConflict, ...],
) -> OverwritePolicy:
    if conflict_strategy == "rename" and conflicts:
        return "rename"
    return overwrite_policy


def _top_level_name(path: str) -> str | None:
    normalized = path.replace("\\", "/").strip("/")
    if not normalized:
        return None
    return normalized.split("/", 1)[0]


def _is_directory_name(entries: Iterable[ArchivePathEntry], name: str) -> bool:
    folded = name.casefold()
    for entry in entries:
        top = _top_level_name(entry.path)
        if top is None or top.casefold() != folded:
            continue
        if entry.is_directory or entry.path.replace("\\", "/").strip("/") != top:
            return True
    return False


@dataclass(frozen=True)
class SmartOutputPolicy:
    """Side-effect-free computation of the final extraction directory."""

    def resolve_final_dir(
        self,
        archive_path: str | Path,
        requested_output_dir: str | Path,
        entries: Iterable[ArchivePathEntry],
    ) -> Path:
        requested = Path(requested_output_dir)
        entries = tuple(entries)
        names = top_level_names(entries)

        if not names:
            return requested

        if len(names) == 1:
            name = next(iter(names))
            if _is_directory_name(entries, name) and requested.name.casefold() == name.casefold():
                return requested.parent
            return requested

        logical_name = archive_logical_name(archive_path)
        if requested.name.casefold() == logical_name.casefold():
            return requested
        return requested / logical_name
