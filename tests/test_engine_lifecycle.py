"""Regression tests for engine reliability: cancellation responsiveness,
subprocess termination/reaping, planning-phase cancellation, and Windows
special-path validation.

The silent-backend fixtures below deliberately sleep far longer than the
assertion bounds, so these tests genuinely fail against the old blocking
``stdout.read(1)`` implementation instead of passing by accident.
"""

from __future__ import annotations

from pathlib import Path
import os
import stat
import subprocess
import tempfile
import threading
import time
import unittest
from unittest import mock
import zipfile

import ductzip.archive.sevenzip as sevenzip
from ductzip.archive import (
    ArchiveCancelled,
    ArchiveNotFound,
    ArchiveEntry,
    ArchiveListing,
    PathTraversalBlocked,
    SevenZipCliEngine,
)
from ductzip.archive.sevenzip import _is_safe_archive_path
from ductzip.core import ExtractionService


def make_silent_fake_7z(directory: Path, silent_commands: tuple[str, ...] = ("x",)) -> Path:
    """A fake backend that produces no output and runs ~15 seconds for the
    given commands (extract by default, list/test fast).

    With the old blocking-read implementation, cancelling while this backend
    runs could only take effect after the process exited (~15s). The fixed
    implementation cancels in well under a second.
    """
    script = directory / ("silent7z.cmd" if os.name == "nt" else "silent7z")
    if os.name == "nt":
        conditions = "\r\n".join(f'if "%~1"=="{command}" ping -n 16 127.0.0.1 >nul' for command in silent_commands)
        script.write_text(f"@echo off\r\n{conditions}\r\necho fake 7z %*\r\nexit /b 0\r\n", encoding="utf-8")
    else:
        conditions = "\n".join(f'[ "$1" = "{command}" ] && sleep 15' for command in silent_commands)
        script.write_text(f"#!/bin/sh\n{conditions}\necho \"fake 7z $@\"\nexit 0\n", encoding="utf-8")
        script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return script


def wait_until(predicate, timeout: float = 5.0, interval: float = 0.02) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


class PopenRecorder:
    """Wraps subprocess.Popen, recording every created process."""

    def __init__(self):
        self.created: list[subprocess.Popen] = []
        self._original = subprocess.Popen

    def __call__(self, *args, **kwargs):
        process = self._original(*args, **kwargs)
        self.created.append(process)
        return process


class SilentBackendCancellationTests(unittest.TestCase):
    def test_cancel_with_silent_backend_is_responsive(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fake = make_silent_fake_7z(root)
            archive = root / "archive.zip"
            archive.write_bytes(b"fake")
            output = root / "out"
            cancel_event = threading.Event()

            generator = SevenZipCliEngine(fake).extract_with_progress(archive, output, cancel_event=cancel_event)
            first_event = next(generator)
            self.assertEqual(first_event.kind, "started")

            def cancel_soon() -> None:
                time.sleep(0.2)
                cancel_event.set()

            threading.Thread(target=cancel_soon, daemon=True).start()

            started = time.monotonic()
            with self.assertRaises(ArchiveCancelled):
                list(generator)
            elapsed = time.monotonic() - started

            # The backend would run for ~15s; cancellation must win quickly.
            self.assertLess(elapsed, 6.0, f"cancellation took {elapsed:.1f}s with a silent backend")

    def test_cancel_reports_single_cancelled_event(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fake = make_silent_fake_7z(root)
            archive = root / "archive.zip"
            archive.write_bytes(b"fake")
            cancel_event = threading.Event()

            generator = SevenZipCliEngine(fake).extract_with_progress(archive, root / "out", cancel_event=cancel_event)
            next(generator)
            cancel_event.set()

            events = []
            with self.assertRaises(ArchiveCancelled):
                for event in generator:
                    events.append(event)

            self.assertEqual([event.kind for event in events], ["cancelled"])

    def test_list_with_cancel_event_raises_and_reaps(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fake = make_silent_fake_7z(root, silent_commands=("l", "x"))
            archive = root / "archive.zip"
            archive.write_bytes(b"fake")

            recorder = PopenRecorder()
            cancel_event = threading.Event()
            with mock.patch.object(sevenzip.subprocess, "Popen", recorder):
                generator_cancel = threading.Event()

                def cancel_soon() -> None:
                    time.sleep(0.2)
                    generator_cancel.set()

                threading.Thread(target=cancel_soon, daemon=True).start()
                with self.assertRaises(ArchiveCancelled):
                    SevenZipCliEngine(fake).list(archive, cancel_event=generator_cancel)

            process = recorder.created[-1]
            self.assertTrue(
                wait_until(lambda: process.poll() is not None),
                "list subprocess was not reaped after cancellation",
            )


class SubprocessReapingTests(unittest.TestCase):
    def test_abandoned_generator_terminates_and_reaps_backend(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fake = make_silent_fake_7z(root)
            archive = root / "archive.zip"
            archive.write_bytes(b"fake")

            recorder = PopenRecorder()
            with mock.patch.object(sevenzip.subprocess, "Popen", recorder):
                generator = SevenZipCliEngine(fake).extract_with_progress(archive, root / "out")
                next(generator)
                generator.close()

            process = recorder.created[-1]
            self.assertTrue(
                wait_until(lambda: process.poll() is not None),
                "backend process survived generator abandonment",
            )

    def test_failed_backend_is_reaped(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            script = root / ("fail7z.cmd" if os.name == "nt" else "fail7z")
            if os.name == "nt":
                script.write_text("@echo off\r\necho Can not open the file as archive\r\nexit /b 2\r\n", encoding="utf-8")
            else:
                script.write_text("#!/bin/sh\necho 'Can not open the file as archive'\nexit 2\n", encoding="utf-8")
                script.chmod(script.stat().st_mode | stat.S_IXUSR)
            archive = root / "broken.zip"
            archive.write_bytes(b"broken")

            recorder = PopenRecorder()
            with mock.patch.object(sevenzip.subprocess, "Popen", recorder):
                with self.assertRaises(Exception):
                    SevenZipCliEngine(script).extract(archive, root / "out")

            process = recorder.created[-1]
            self.assertIsNotNone(process.poll(), "failed backend process was not reaped")


class PlanningCancellationTests(unittest.TestCase):
    def test_service_extract_with_preset_cancel_aborts_during_planning(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fake = make_silent_fake_7z(root)
            archive = root / "archive.zip"
            archive.write_bytes(b"fake")

            cancel_event = threading.Event()
            cancel_event.set()

            started = time.monotonic()
            with self.assertRaises(ArchiveCancelled):
                ExtractionService(SevenZipCliEngine(fake)).extract(
                    archive,
                    root / "out",
                    cancel_event=cancel_event,
                )
            elapsed = time.monotonic() - started

            self.assertLess(elapsed, 6.0, "planning-phase cancellation was not responsive")
            self.assertFalse((root / "out").exists())

    def test_service_plan_passes_cancel_event_to_engine_list(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fake = make_silent_fake_7z(root)
            archive = root / "archive.zip"
            archive.write_bytes(b"fake")

            cancel_event = threading.Event()
            cancel_event.set()

            with self.assertRaises(ArchiveCancelled):
                ExtractionService(SevenZipCliEngine(fake)).plan(archive, root / "out", cancel_event=cancel_event)


class WindowsSpecialPathValidationTests(unittest.TestCase):
    def test_reserved_device_names_are_rejected(self) -> None:
        for unsafe in ("NUL", "nul.txt", "CON", "con.foo.bar", "PRN", "AUX", "COM1", "com9.zip", "LPT1", "lpt9.x"):
            self.assertFalse(_is_safe_archive_path(unsafe), f"{unsafe!r} should be rejected")
            self.assertFalse(_is_safe_archive_path(f"dir/{unsafe}"), f"dir/{unsafe!r} should be rejected")

    def test_normal_paths_still_accepted(self) -> None:
        for safe in ("hello.txt", "dir/hello.txt", "console.txt", "contact.txt", "folder.with.dots/a.txt"):
            self.assertTrue(_is_safe_archive_path(safe), f"{safe!r} should be accepted")

    def test_unc_and_device_style_paths_rejected(self) -> None:
        for unsafe in (r"\\server\share\a.txt", r"\\?\C:\secret.txt", "C:/secret.txt", "C:secret.txt"):
            self.assertFalse(_is_safe_archive_path(unsafe), f"{unsafe!r} should be rejected")

    def test_engine_blocks_reserved_device_names_when_sevenzip_is_available(self) -> None:
        try:
            from ductzip.archive import find_sevenzip, SevenZipMissing

            find_sevenzip()
        except SevenZipMissing:
            self.skipTest("7-Zip backend is not available")

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "device.zip"
            output = root / "output"

            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("evil/NUL.txt", "nope")

            with self.assertRaises(PathTraversalBlocked):
                SevenZipCliEngine().extract(archive, output)

            self.assertFalse(output.exists())


class ArchiveMutationBoundaryTests(unittest.TestCase):
    """Product behavior when caller planning data disagrees with the archive.

    The engine's own fresh listing is the sole safety evidence. For product
    behavior, the service plan (Smart Output dir, conflicts) is advisory: if
    the archive changed after planning, extraction still proceeds into the
    planned directory, but with the archive's real, freshly validated
    contents.
    """

    def _require_sevenzip(self) -> None:
        try:
            from ductzip.archive import find_sevenzip, SevenZipMissing

            find_sevenzip()
        except SevenZipMissing:
            self.skipTest("7-Zip backend is not available")

    def test_extraction_uses_real_archive_contents_with_forged_plan_listing(self) -> None:
        self._require_sevenzip()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "bundle.zip"
            requested = root / "out"

            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("a.txt", "a")
                zf.writestr("b.txt", "b")

            service = ExtractionService()
            real_listing = service.list(archive)
            forged = ArchiveListing(
                archive_path=real_listing.archive_path,
                sevenzip_path=real_listing.sevenzip_path,
                entries=(ArchiveEntry(path="only.txt", size=1, modified=None, attributes=None, is_directory=False),),
                stdout=real_listing.stdout,
                stderr=real_listing.stderr,
            )

            result = service.extract(archive, requested, smart_output=True, listing=forged)

            # Smart Output followed the advisory forged listing (single
            # top-level -> base dir), but the real, engine-validated archive
            # contents were extracted.
            self.assertEqual(result.output_dir, requested.resolve())
            self.assertEqual((requested / "a.txt").read_text(encoding="utf-8"), "a")
            self.assertEqual((requested / "b.txt").read_text(encoding="utf-8"), "b")

    def test_archive_deleted_between_plan_and_extract_raises_not_found(self) -> None:
        self._require_sevenzip()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "gone.zip"
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("a.txt", "a")

            service = ExtractionService()
            listing = service.list(archive)
            archive.unlink()

            with self.assertRaises(ArchiveNotFound):
                service.extract(archive, root / "out", listing=listing)


def make_bulky_listing_fake_7z(directory: Path, entries: int = 3000) -> Path:
    """A fake backend whose listing output is far larger than a pipe buffer.

    Each ``-slt`` record is ~48 bytes, so 3000 entries (~145 KiB) cannot fit in
    the OS pipe buffer. A parent that waits for the child to exit *before*
    reading its stdout deadlocks here: the child blocks in ``write()`` forever.
    """
    script = directory / ("bulky7z.cmd" if os.name == "nt" else "bulky7z")
    if os.name == "nt":
        body = (
            "@echo off\r\n"
            'if not "%~1"=="l" exit /b 0\r\n'
            f"for /L %%i in (1,1,{entries}) do (\r\n"
            "  echo Path = file%%i.bin\r\n"
            "  echo Size = 2048\r\n"
            "  echo Attributes = A\r\n"
            "  echo.\r\n"
            ")\r\n"
            "exit /b 0\r\n"
        )
        script.write_text(body, encoding="utf-8")
    else:
        lines = ['#!/bin/sh\n[ "$1" = "l" ] || exit 0\n']
        lines.append(f"i=1\nwhile [ $i -le {entries} ]; do\n")
        lines.append('  echo "Path = file$i.bin"\n  echo "Size = 2048"\n')
        lines.append('  echo "Attributes = A"\n  echo ""\n  i=$((i+1))\ndone\n')
        script.write_text("".join(lines), encoding="utf-8")
        script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return script


class CancellableListingDrainTests(unittest.TestCase):
    """The cancellable path must keep draining the backend while it polls.

    ``_run(cancel_event=...)`` polls the child for exit to stay responsive to
    cancellation. If it only reads the pipes after the child exits, any listing
    larger than the pipe buffer deadlocks: the child cannot exit until someone
    reads, and the parent will not read until the child exits. GUI preview and
    batch planning both go through this path with a cancel event, so a large
    archive would hang them indefinitely.
    """

    def test_large_listing_does_not_deadlock_on_the_cancellable_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "big.zip"
            archive.write_bytes(b"PK\x03\x04")
            engine = SevenZipCliEngine(make_bulky_listing_fake_7z(root))

            outcome: dict[str, object] = {}

            def run() -> None:
                try:
                    outcome["listing"] = engine.list(archive, cancel_event=threading.Event())
                except BaseException as exc:  # pragma: no cover - reported below
                    outcome["error"] = exc

            worker = threading.Thread(target=run, daemon=True)
            worker.start()
            worker.join(timeout=30)

            self.assertFalse(
                worker.is_alive(),
                "listing deadlocked: the backend filled the pipe buffer and "
                "nothing drained it while the parent waited for exit",
            )
            self.assertNotIn("error", outcome, f"listing raised: {outcome.get('error')!r}")
            listing = outcome["listing"]
            self.assertIsInstance(listing, ArchiveListing)
            self.assertEqual(len(listing.entries), 3000)

    def test_large_listing_is_still_cancellable(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / "big.zip"
            archive.write_bytes(b"PK\x03\x04")
            engine = SevenZipCliEngine(make_bulky_listing_fake_7z(root))

            cancel_event = threading.Event()
            outcome: dict[str, object] = {}

            def run() -> None:
                try:
                    engine.list(archive, cancel_event=cancel_event)
                except BaseException as exc:
                    outcome["error"] = exc

            worker = threading.Thread(target=run, daemon=True)
            worker.start()
            time.sleep(0.15)
            cancel_event.set()
            worker.join(timeout=15)

            self.assertFalse(worker.is_alive(), "cancellation did not take effect")
            self.assertIsInstance(outcome.get("error"), ArchiveCancelled)


if __name__ == "__main__":
    unittest.main()
