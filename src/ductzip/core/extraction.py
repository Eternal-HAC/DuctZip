"""Application-level extraction orchestration.

``ExtractionService`` is the single entry point shared by the CLI, the GUI,
and future batch queueing: it lists the archive, applies the
:class:`~ductzip.core.smart_output.SmartOutputPolicy`, resolves top-level
output conflicts, and delegates the actual 7-Zip work to the engine.

The engine keeps sole ownership of path traversal validation: it takes its
own fresh listing of the target archive before every real extraction and
validates those entries, so no caller-supplied data can substitute for that
safety check. ``ExtractionService`` may list an archive up front for Smart
output / conflict planning (allowing one duplicate ``list`` for planning);
that listing is advisory only and is never passed to the engine as a
substitute for its own safety read.

After the engine reports completion, the service best-effort propagates
the archive's Mark-of-the-Web stream (``Zone.Identifier`` ADS) onto the
extracted files; see :mod:`ductzip.motw`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import threading
from collections.abc import Iterator

from ductzip.archive import (
    ArchiveListing,
    ExtractResult,
    OutputConflictBlocked,
    ProgressEvent,
    SevenZipCliEngine,
    UnknownArchiveError,
)
from ductzip.archive.sevenzip import OverwritePolicy
from ductzip.motw import MotwReport, iter_output_files, propagate_motw, read_zone_identifier

from .smart_output import (
    ConflictStrategy,
    OutputConflict,
    SmartOutputPolicy,
    detect_output_conflicts,
    resolve_conflict_overwrite_policy,
)


@dataclass(frozen=True)
class ExtractionPlan:
    archive_path: Path
    requested_output_dir: Path
    final_output_dir: Path
    conflicts: tuple[OutputConflict, ...]
    effective_overwrite_policy: OverwritePolicy
    listing: ArchiveListing


class ExtractionService:
    """Coordinates listing, smart output, conflict handling, and extraction."""

    def __init__(
        self,
        engine: SevenZipCliEngine | None = None,
        policy: SmartOutputPolicy | None = None,
        sevenzip_path: str | None = None,
    ):
        self.engine = engine if engine is not None else SevenZipCliEngine(sevenzip_path)
        self.policy = policy if policy is not None else SmartOutputPolicy()
        self.last_motw_report: MotwReport | None = None

    def list(self, archive_path: str | Path, password: str | None = None) -> ArchiveListing:
        return self.engine.list(archive_path, password=password)

    def plan(
        self,
        archive_path: str | Path,
        requested_output_dir: str | Path,
        *,
        smart_output: bool = False,
        conflict_strategy: ConflictStrategy = "merge",
        overwrite_policy: OverwritePolicy = "skip",
        password: str | None = None,
        listing: ArchiveListing | None = None,
        cancel_event: threading.Event | None = None,
    ) -> ExtractionPlan:
        archive = Path(archive_path)
        requested = Path(requested_output_dir)
        if listing is None:
            listing = self.engine.list(archive, password=password, cancel_event=cancel_event)

        if smart_output:
            final_output = self.policy.resolve_final_dir(archive, requested, listing.entries)
        else:
            final_output = requested

        conflicts = detect_output_conflicts(final_output, listing.entries)
        if conflicts and conflict_strategy == "cancel":
            names = ", ".join(conflict.entry_path for conflict in conflicts[:3])
            raise OutputConflictBlocked(f"目标目录存在冲突：{names}")
        effective_overwrite_policy = resolve_conflict_overwrite_policy(overwrite_policy, conflict_strategy, conflicts)

        return ExtractionPlan(
            archive_path=archive,
            requested_output_dir=requested,
            final_output_dir=final_output,
            conflicts=conflicts,
            effective_overwrite_policy=effective_overwrite_policy,
            listing=listing,
        )

    def extract(
        self,
        archive_path: str | Path,
        requested_output_dir: str | Path,
        *,
        smart_output: bool = False,
        conflict_strategy: ConflictStrategy = "merge",
        overwrite_policy: OverwritePolicy = "skip",
        password: str | None = None,
        cancel_event: threading.Event | None = None,
        listing: ArchiveListing | None = None,
    ) -> ExtractResult:
        final_result: ExtractResult | None = None
        for event in self.extract_with_progress(
            archive_path,
            requested_output_dir,
            smart_output=smart_output,
            conflict_strategy=conflict_strategy,
            overwrite_policy=overwrite_policy,
            password=password,
            cancel_event=cancel_event,
            listing=listing,
        ):
            if event.kind == "completed":
                final_result = event.result

        if final_result is None:
            raise UnknownArchiveError()
        return final_result

    def extract_with_progress(
        self,
        archive_path: str | Path,
        requested_output_dir: str | Path,
        *,
        smart_output: bool = False,
        conflict_strategy: ConflictStrategy = "merge",
        overwrite_policy: OverwritePolicy = "skip",
        password: str | None = None,
        cancel_event: threading.Event | None = None,
        listing: ArchiveListing | None = None,
    ) -> Iterator[ProgressEvent]:
        plan = self.plan(
            archive_path,
            requested_output_dir,
            smart_output=smart_output,
            conflict_strategy=conflict_strategy,
            overwrite_policy=overwrite_policy,
            password=password,
            listing=listing,
            cancel_event=cancel_event,
        )
        self.last_motw_report = None
        # Snapshot files that already exist in the final output directory so
        # MOTW propagation below tags only files this extraction produced.
        # Pre-existing files (e.g. merge-conflict targets) keep their own
        # provenance; re-tagging them would mislabel local content as
        # downloaded (SECURITY.md MOTW boundary).
        preexisting: frozenset[Path] = frozenset()
        if read_zone_identifier(plan.archive_path) is not None:
            preexisting = frozenset(iter_output_files(plan.final_output_dir))
        for event in self.engine.extract_with_progress(
            plan.archive_path,
            plan.final_output_dir,
            password=password,
            cancel_event=cancel_event,
            overwrite_policy=plan.effective_overwrite_policy,
        ):
            if event.kind == "completed":
                # Best-effort Zone.Identifier propagation (DD-018): never
                # fails the extraction; per-file failures stay on the report.
                self.last_motw_report = propagate_motw(
                    plan.archive_path, plan.final_output_dir, exclude=preexisting
                )
            yield event
