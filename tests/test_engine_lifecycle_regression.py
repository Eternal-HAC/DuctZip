"""Regression tests for the full-suite hang fix."""

from __future__ import annotations

from pathlib import Path
import os
import stat
import sys
import tempfile
import threading
import time
import unittest

from ductzip.archive import ArchiveCancelled, SevenZipCliEngine


def make_delayed_output_wrapper(directory: Path) -> Path:
    """A fake backend whose wrapper exits before its grandchild writes."""
    wrapper = directory / ("delayed7z.cmd" if os.name == "nt" else "delayed7z")
    grandchild = directory / "delayed_grandchild.py"
    grandchild.write_text(
        "import time, sys\n"
        "time.sleep(0.5)\n"
        "print('delayed stdout', flush=True)\n"
        "print('delayed stderr', flush=True, file=sys.stderr)\n"
        "time.sleep(0.5)\n",
        encoding="utf-8",
    )
    if os.name == "nt":
        wrapper.write_text(
            f"@echo off\r\n"
            f"echo wrapper start\r\n"
            f"start /b \"\" \"{sys.executable}\" \"{grandchild}\"\r\n"
            f"exit /b 0\r\n",
            encoding="utf-8",
        )
    else:
        wrapper.write_text(
            "#!/bin/sh\n"
            f'\"{sys.executable}\" \"{grandchild}\" &\n'
            "exit 0\n",
            encoding="utf-8",
        )
        wrapper.chmod(wrapper.stat().st_mode | stat.S_IXUSR)
    return wrapper


def make_wrapper_with_grandchild_lock(directory: Path) -> tuple[Path, Path]:
    """A fake backend that starts a long-running grandchild holding a lock file."""
    wrapper = directory / ("tree7z.cmd" if os.name == "nt" else "tree7z")
    grandchild = directory / "tree_grandchild.py"
    lockfile = directory / "grandchild.lock"
    grandchild.write_text(
        "import time\n"
        f"with open(r'{lockfile}', 'w') as f:\n"
        "    f.write('locked\\n')\n"
        "    f.flush()\n"
        "    time.sleep(30)\n",
        encoding="utf-8",
    )
    if os.name == "nt":
        wrapper.write_text(
            f"@echo off\r\n"
            f"start /b \"\" \"{sys.executable}\" \"{grandchild}\"\r\n"
            f"ping -n 16 127.0.0.1 >nul\r\n"
            f"exit /b 0\r\n",
            encoding="utf-8",
        )
    else:
        wrapper.write_text(
            "#!/bin/sh\n"
            f'\"{sys.executable}\" \"{grandchild}\" &\n'
            "sleep 15\n",
            encoding="utf-8",
        )
        wrapper.chmod(wrapper.stat().st_mode | stat.S_IXUSR)
    return wrapper, lockfile


class DelayedOutputCaptureTests(unittest.TestCase):
    """Output produced by a grandchild after the wrapper exits must be captured."""

    def test_delayed_stdout_after_wrapper_exit_is_captured(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fake = make_delayed_output_wrapper(root)
            archive = root / "archive.zip"
            archive.write_bytes(b"fake")

            completed = SevenZipCliEngine(fake).test(archive)

            self.assertIn("delayed stdout", completed.stdout)

    def test_delayed_stderr_after_wrapper_exit_is_captured(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fake = make_delayed_output_wrapper(root)
            archive = root / "archive.zip"
            archive.write_bytes(b"fake")

            completed = SevenZipCliEngine(fake).test(archive)

            self.assertIn("delayed stderr", completed.stderr)


class WindowsProcessTreeTerminationTests(unittest.TestCase):
    """Cancellation must kill the whole process tree, not just the wrapper."""

    @unittest.skipUnless(sys.platform == "win32", "Windows-only process-tree kill")
    def test_cancel_terminates_grandchild_on_windows(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fake, lockfile = make_wrapper_with_grandchild_lock(root)
            archive = root / "archive.zip"
            archive.write_bytes(b"fake")

            cancel_event = threading.Event()

            def cancel_soon() -> None:
                time.sleep(0.2)
                cancel_event.set()

            threading.Thread(target=cancel_soon, daemon=True).start()
            with self.assertRaises(ArchiveCancelled):
                SevenZipCliEngine(fake).list(archive, cancel_event=cancel_event)

            time.sleep(0.5)

            try:
                lockfile.unlink()
            except PermissionError:
                self.fail("grandchild process survived cancellation (lock file still held)")


if __name__ == "__main__":
    unittest.main()
