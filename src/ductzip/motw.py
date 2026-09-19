"""Mark-of-the-Web (Zone.Identifier) propagation.

After a successful extraction, DuctZip copies the archive's
``Zone.Identifier`` NTFS alternate data stream onto every extracted file,
so Windows keeps treating the extracted content as originating from the
same security zone as the downloaded archive (Explorer's "Unblock"
origin flag, SmartScreen prompts, and Office Protected View all key off
this stream).

This module is best-effort by design:

- Non-Windows platforms, non-NTFS file systems, and archives that carry
  no MOTW stream are silent no-ops.
- Individual ADS write failures never fail the extraction; they are
  collected in :attr:`MotwReport.failures` for diagnostics.
- Directories are not tagged; reparse points (symlinks, junctions) are
  skipped, mirroring the documented unsupported-link boundary (DD-012).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import os
import stat

ZONE_IDENTIFIER_STREAM = "Zone.Identifier"


@dataclass(frozen=True)
class MotwReport:
    """Outcome of one propagation pass."""

    source_had_motw: bool
    propagated: int = 0
    failures: tuple[Path, ...] = field(default_factory=tuple)


def _stream_name(path: Path) -> str:
    return f"{path}:{ZONE_IDENTIFIER_STREAM}"


def read_zone_identifier(path: str | Path) -> bytes | None:
    """Read the MOTW stream of ``path``; ``None`` when absent or unreadable."""
    try:
        with open(_stream_name(Path(path)), "rb") as stream:
            return stream.read()
    except OSError:
        return None


def write_zone_identifier(path: str | Path, content: bytes) -> bool:
    """Write a MOTW stream onto ``path``; ``False`` on failure."""
    try:
        with open(_stream_name(Path(path)), "wb") as stream:
            stream.write(content)
        return True
    except OSError:
        return False


def _is_reparse_point(path: Path) -> bool:
    try:
        attributes = os.lstat(path).st_file_attributes  # type: ignore[attr-defined]
    except (OSError, AttributeError):
        return False
    return bool(attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def iter_output_files(output_dir: str | Path) -> list[Path]:
    """All regular files under ``output_dir``, excluding reparse points."""
    root = Path(output_dir)
    files: list[Path] = []
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            candidate = Path(dirpath) / name
            if _is_reparse_point(candidate) or os.path.islink(candidate):
                continue
            files.append(candidate)
    return files


def propagate_motw(archive_path: str | Path, output_dir: str | Path) -> MotwReport:
    """Copy the archive's MOTW stream onto every extracted file.

    Silent no-op when the archive carries no MOTW stream or the file
    system does not support ADS; never raises for I/O failures.
    """
    content = read_zone_identifier(archive_path)
    if content is None:
        return MotwReport(source_had_motw=False)

    failures: list[Path] = []
    propagated = 0
    for target in iter_output_files(output_dir):
        if write_zone_identifier(target, content):
            propagated += 1
        else:
            failures.append(target)
    return MotwReport(source_had_motw=True, propagated=propagated, failures=tuple(failures))
