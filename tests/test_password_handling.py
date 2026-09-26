"""Backend password handling: DuctZip asks, the backend only ever answers.

LONG_TASK.md §7.3 requires the password-required and wrong-password cases to
produce stable user-facing errors, and §7.5 requires that passwords never reach
logs. Two defects lived here, both found by the §7.3 acceptance run:

* Without a password argument 7-Zip prints ``Enter password (will not be
  echoed):`` and reads the console. DuctZip neither displays nor answers that
  prompt, so an interactive run looked like a hang and a non-interactive one
  died with ``Break signaled`` — which was then reported as "the archive may be
  corrupt or unsupported". A bare ``-p`` means "empty password, do not ask" and
  removes the prompt; ``stdin=DEVNULL`` makes it unreachable regardless.
* With the prompt gone, 7-Zip reports the same ``Wrong password?`` text whether
  no password was supplied or the supplied one was wrong. The caller knows
  which, so it tells the classifier.
"""

from __future__ import annotations

import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest
from unittest import mock

import ductzip.archive.sevenzip as sevenzip
from ductzip.archive import (
    CorruptedArchive,
    PasswordRequired,
    SevenZipCliEngine,
    WrongPassword,
)
from ductzip.archive.sevenzip import _map_sevenzip_error, _password_args

# What 7-Zip 26.03 emits for a header-encrypted archive once an empty ``-p``
# suppresses its prompt. The same text appears for a genuinely wrong password.
BACKEND_WRONG_PASSWORD_OUTPUT = (
    "ERROR: archive.7z\n"
    "Cannot open encrypted archive. Wrong password?\n"
    "\n"
    "ERRORS:\n"
    "Headers Error\n"
)


def make_fake_7z(directory: Path) -> Path:
    """A backend that lists successfully but fails every other command."""
    script = directory / ("password7z.cmd" if os.name == "nt" else "password7z")
    if os.name == "nt":
        script.write_text(
            "@echo off\r\n"
            'if "%~1"=="l" goto listing\r\n'
            "echo ERROR: Wrong password?\r\n"
            "exit /b 2\r\n"
            ":listing\r\n"
            "echo Path = photos\r\n"
            "echo Folder = +\r\n"
            "echo.\r\n"
            "echo Path = photos/a.txt\r\n"
            "echo Size = 3\r\n"
            "echo.\r\n"
            "exit /b 0\r\n",
            encoding="utf-8",
        )
    else:
        script.write_text(
            "#!/bin/sh\n"
            'if [ "$1" = "l" ]; then\n'
            '  printf "Path = photos\\nFolder = +\\n\\nPath = photos/a.txt\\nSize = 3\\n\\n"\n'
            "  exit 0\n"
            "fi\n"
            "echo 'ERROR: Wrong password?'\n"
            "exit 2\n",
            encoding="utf-8",
        )
        script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return script


class RecordingProxy:
    """Wrap a subprocess entry point, recording every command and its kwargs."""

    def __init__(self, original):
        self.calls: list[tuple[list[str], dict]] = []
        self._original = original

    def __call__(self, *args, **kwargs):
        command = args[0] if args else kwargs.get("args")
        self.calls.append((list(command), kwargs))
        return self._original(*args, **kwargs)

    def commands(self) -> list[list[str]]:
        return [command for command, _ in self.calls]


class PasswordArgumentTests(unittest.TestCase):
    def test_missing_password_still_passes_the_switch(self) -> None:
        # A bare "-p" is what suppresses 7-Zip's own prompt. Dropping the
        # switch entirely is the defect this pins.
        self.assertEqual(_password_args(None), ["-p"])
        self.assertEqual(_password_args(""), ["-p"])

    def test_supplied_password_is_attached_to_the_switch(self) -> None:
        self.assertEqual(_password_args("s3cret-密码"), ["-ps3cret-密码"])


class MissingPasswordIsNotWrongPasswordTests(unittest.TestCase):
    def test_absent_password_is_reported_as_required(self) -> None:
        error = _map_sevenzip_error(BACKEND_WRONG_PASSWORD_OUTPUT, password_supplied=False)

        self.assertIsInstance(error, PasswordRequired)
        self.assertEqual(str(error), "该压缩包需要密码。")

    def test_supplied_password_is_reported_as_wrong(self) -> None:
        error = _map_sevenzip_error(BACKEND_WRONG_PASSWORD_OUTPUT, password_supplied=True)

        self.assertIsInstance(error, WrongPassword)
        self.assertEqual(str(error), "密码错误。")

    def test_corruption_is_not_reclassified_as_a_password_problem(self) -> None:
        error = _map_sevenzip_error("ERROR: Data Error in encrypted file", password_supplied=False)

        self.assertIsInstance(error, CorruptedArchive)

    def test_raw_backend_output_never_reaches_the_user_message(self) -> None:
        error = _map_sevenzip_error(
            r"ERROR: C:\Users\someone\private\secret.7z : Wrong password?",
            password_supplied=True,
        )

        self.assertNotIn(r"C:\Users", str(error))
        self.assertIn(r"C:\Users", error.detail or "")


class BackendNeverPromptsTests(unittest.TestCase):
    """Every backend invocation must be unable to ask for a password itself."""

    def test_list_passes_a_password_switch_without_a_password(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fake = make_fake_7z(root)
            archive = root / "archive.7z"
            archive.write_bytes(b"fake")

            # The listing path succeeds; the "-p" switch is asserted below.
            listing = SevenZipCliEngine(fake).list(archive)
            self.assertTrue(any(entry.path == "photos/a.txt" for entry in listing.entries))

    def test_all_backend_calls_use_a_devnull_stdin(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fake = make_fake_7z(root)
            archive = root / "archive.7z"
            archive.write_bytes(b"fake")
            engine = SevenZipCliEngine(fake)

            run_proxy = RecordingProxy(sevenzip.subprocess.run)
            popen_proxy = RecordingProxy(sevenzip.subprocess.Popen)
            with mock.patch.object(sevenzip.subprocess, "run", run_proxy), mock.patch.object(
                sevenzip.subprocess, "Popen", popen_proxy
            ):
                engine.list(archive)
                with self.assertRaises(PasswordRequired):
                    engine.test(archive)
                with self.assertRaises(PasswordRequired):
                    list(engine.extract_with_progress(archive, root / "out"))

            invocations = run_proxy.calls + popen_proxy.calls
            self.assertTrue(invocations, "no backend invocation was recorded")
            for command, kwargs in invocations:
                self.assertIs(
                    kwargs.get("stdin"),
                    subprocess.DEVNULL,
                    f"backend was given the console on stdin: {command}",
                )
                self.assertTrue(
                    any(argument == "-p" or argument.startswith("-p") for argument in command),
                    f"backend would prompt for a password itself: {command}",
                )

    def test_extract_without_password_reports_that_one_is_required(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fake = make_fake_7z(root)
            archive = root / "archive.7z"
            archive.write_bytes(b"fake")

            with self.assertRaises(PasswordRequired):
                list(SevenZipCliEngine(fake).extract_with_progress(archive, root / "out"))


if __name__ == "__main__":
    unittest.main()
