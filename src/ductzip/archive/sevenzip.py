from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import re
import shutil
import subprocess
import sys
import threading
from collections.abc import Iterator
import queue
from typing import Literal

from .errors import (
    ArchiveError,
    ArchiveCancelled,
    ArchiveNotFound,
    CorruptedArchive,
    OutputPermissionDenied,
    PasswordRequired,
    PathTraversalBlocked,
    SevenZipMissing,
    UnknownArchiveError,
    UnsupportedFormat,
    WrongPassword,
)

OverwritePolicy = Literal["skip", "overwrite", "rename"]


@dataclass(frozen=True)
class ExtractResult:
    archive_path: Path
    output_dir: Path
    sevenzip_path: Path
    stdout: str
    stderr: str


@dataclass(frozen=True)
class ArchiveEntry:
    path: str
    size: int | None
    modified: str | None
    attributes: str | None
    is_directory: bool


@dataclass(frozen=True)
class ArchiveListing:
    archive_path: Path
    sevenzip_path: Path
    entries: tuple[ArchiveEntry, ...]
    stdout: str
    stderr: str


@dataclass(frozen=True)
class TestResult:
    archive_path: Path
    sevenzip_path: Path
    stdout: str
    stderr: str


@dataclass(frozen=True)
class ProgressEvent:
    kind: str
    percent: int | None = None
    current_file: str | None = None
    message: str | None = None
    result: ExtractResult | None = None


def find_sevenzip(explicit_path: str | os.PathLike[str] | None = None) -> Path:
    candidates: list[Path] = []

    if explicit_path:
        candidate = Path(explicit_path)
        if candidate.is_file():
            return candidate.resolve()
        raise SevenZipMissing()

    env_path = os.environ.get("DUCTZIP_7Z_PATH")
    if env_path:
        candidates.append(Path(env_path))

    project_root = Path(__file__).resolve().parents[3]
    candidates.extend(
        [
            project_root / "vendor" / "7zip" / "7z.exe",
            Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "7-Zip" / "7z.exe",
            Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "7-Zip" / "7z.exe",
        ]
    )
    candidates.extend(_registry_sevenzip_candidates())

    for executable in ("7z", "7z.exe", "7zz", "7zz.exe"):
        found = shutil.which(executable)
        if found:
            candidates.append(Path(found))

    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()

    raise SevenZipMissing()


def get_sevenzip_version(sevenzip_path: str | os.PathLike[str] | None = None) -> str:
    path = find_sevenzip(sevenzip_path)
    try:
        completed = subprocess.run(
            [str(path)],
            capture_output=True,
            text=True,
            errors="replace",
            check=False,
        )
    except OSError as exc:
        raise SevenZipMissing() from exc

    for line in (completed.stdout or completed.stderr).splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return "Unknown 7-Zip version"


def _registry_sevenzip_candidates() -> list[Path]:
    if sys.platform != "win32":
        return []

    try:
        import winreg
    except ImportError:
        return []

    roots = [
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]
    candidates: list[Path] = []

    for hive, subkey in roots:
        try:
            with winreg.OpenKey(hive, subkey) as root_key:
                count = winreg.QueryInfoKey(root_key)[0]
                for index in range(count):
                    try:
                        child_name = winreg.EnumKey(root_key, index)
                        with winreg.OpenKey(root_key, child_name) as child_key:
                            display_name = _read_registry_string(winreg, child_key, "DisplayName")
                            if "7-Zip" not in display_name:
                                continue

                            install_location = _read_registry_string(winreg, child_key, "InstallLocation")
                            display_icon = _read_registry_string(winreg, child_key, "DisplayIcon")

                            if install_location:
                                candidates.append(Path(install_location) / "7z.exe")
                            if display_icon:
                                candidates.append(Path(display_icon).with_name("7z.exe"))
                    except OSError:
                        continue
        except OSError:
            continue

    return candidates


def _read_registry_string(winreg_module, key, value_name: str) -> str:
    try:
        value, _ = winreg_module.QueryValueEx(key, value_name)
    except OSError:
        return ""
    return str(value).strip().strip('"')


class SevenZipCliEngine:
    def __init__(self, sevenzip_path: str | os.PathLike[str] | None = None):
        self.sevenzip_path = find_sevenzip(sevenzip_path)

    def list(
        self,
        archive_path: str | os.PathLike[str],
        password: str | None = None,
        cancel_event: threading.Event | None = None,
    ) -> ArchiveListing:
        archive = Path(archive_path)
        if not archive.is_file():
            raise ArchiveNotFound()

        completed = self._run(
            ["l", "-slt", *_password_args(password), str(archive)],
            cancel_event=cancel_event,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()
            raise _map_sevenzip_error(detail)

        return ArchiveListing(
            archive_path=archive.resolve(),
            sevenzip_path=self.sevenzip_path,
            entries=tuple(_parse_slt_entries(completed.stdout)),
            stdout=completed.stdout,
            stderr=completed.stderr,
        )

    def test(
        self,
        archive_path: str | os.PathLike[str],
        password: str | None = None,
        cancel_event: threading.Event | None = None,
    ) -> TestResult:
        archive = Path(archive_path)
        if not archive.is_file():
            raise ArchiveNotFound()

        completed = self._run(["t", *_password_args(password), str(archive)], cancel_event=cancel_event)
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()
            raise _map_sevenzip_error(detail)

        return TestResult(
            archive_path=archive.resolve(),
            sevenzip_path=self.sevenzip_path,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )

    def extract(
        self,
        archive_path: str | os.PathLike[str],
        output_dir: str | os.PathLike[str],
        password: str | None = None,
        cancel_event: threading.Event | None = None,
        overwrite_policy: OverwritePolicy = "skip",
    ) -> ExtractResult:
        final_result: ExtractResult | None = None
        for event in self.extract_with_progress(
            archive_path,
            output_dir,
            password=password,
            cancel_event=cancel_event,
            overwrite_policy=overwrite_policy,
        ):
            if event.kind == "completed":
                final_result = event.result

        if final_result is None:
            raise UnknownArchiveError()
        return final_result

    def extract_with_progress(
        self,
        archive_path: str | os.PathLike[str],
        output_dir: str | os.PathLike[str],
        password: str | None = None,
        cancel_event: threading.Event | None = None,
        overwrite_policy: OverwritePolicy = "skip",
    ) -> Iterator[ProgressEvent]:
        archive = Path(archive_path)
        output = Path(output_dir)

        if not archive.is_file():
            raise ArchiveNotFound()

        # Path traversal validation is non-negotiable and must be based on the
        # target archive itself: the engine always takes its own fresh listing
        # and validates those entries before extracting. No caller-supplied
        # data can substitute for this safety check.
        listing = self.list(archive, password=password, cancel_event=cancel_event)
        _validate_archive_paths(listing.entries)

        try:
            output.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise OutputPermissionDenied() from exc

        command = [
            "x",
            *_password_args(password),
            str(archive),
            f"-o{output}",
            _overwrite_arg(overwrite_policy),
            "-bsp1",
            "-bso1",
        ]

        yield ProgressEvent(kind="started", percent=0, message=str(archive))

        try:
            process = subprocess.Popen(
                [str(self.sevenzip_path), *command],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                errors="replace",
                bufsize=1,
            )
        except OSError as exc:
            raise UnknownArchiveError() from exc

        output_parts: list[str] = []
        token_parts: list[str] = []
        last_percent: int | None = None
        char_queue: queue.Queue[str | None] = queue.Queue()
        reader = threading.Thread(
            target=_drain_process_output,
            args=(process, char_queue),
            name="ductzip-7z-output-reader",
            daemon=True,
        )
        reader.start()

        # The backend's stdout is drained on a dedicated thread so that a
        # silent backend cannot delay cancellation: the consumer loop below
        # polls the queue with a short timeout and checks the cancel event on
        # every iteration. Termination/reaping is guaranteed on every exit
        # path, including an abandoned (closed) generator.
        try:
            while True:
                if cancel_event is not None and cancel_event.is_set():
                    _terminate_process(process)
                    yield ProgressEvent(kind="cancelled", message="cancelled")
                    raise ArchiveCancelled()

                try:
                    char = char_queue.get(timeout=0.05)
                except queue.Empty:
                    if process.poll() is not None and not reader.is_alive():
                        break
                    continue

                if char is None:
                    break

                output_parts.append(char)
                token_parts.append(char)
                if char in ("\r", "\n"):
                    token = "".join(token_parts)
                    token_parts = []
                    event = _parse_progress_token(token, last_percent)
                    if event is not None:
                        last_percent = event.percent
                        yield event
        finally:
            _reap_process(process)
            # The reader thread owns closing the stream: closing a pipe while
            # another thread is blocked reading it can block for as long as
            # any process (including a terminated child's surviving
            # grandchildren) keeps the pipe's write end open. The reader
            # closes the stream itself once read() returns, so the worst case
            # here is a bounded join timeout, never a multi-second stall.
            reader.join(timeout=1)

        if token_parts:
            event = _parse_progress_token("".join(token_parts), last_percent)
            if event is not None:
                last_percent = event.percent
                yield event

        returncode = process.wait()
        stdout = "".join(output_parts)

        if returncode != 0:
            detail = stdout.strip()
            yield ProgressEvent(kind="failed", message=detail)
            raise _map_sevenzip_error(detail)

        result = ExtractResult(
            archive_path=archive.resolve(),
            output_dir=output.resolve(),
            sevenzip_path=self.sevenzip_path,
            stdout=stdout,
            stderr="",
        )
        yield ProgressEvent(kind="completed", percent=100, result=result)

    def _run(
        self,
        arguments: list[str],
        cancel_event: threading.Event | None = None,
    ) -> subprocess.CompletedProcess[str]:
        command = [str(self.sevenzip_path), *arguments]
        if cancel_event is None:
            try:
                return subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    errors="replace",
                    check=False,
                )
            except OSError as exc:
                raise UnknownArchiveError() from exc

        # Cancellable variant used by list/test/planning paths: poll with a
        # short timeout so a silent or hung backend cannot block cancellation.
        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                errors="replace",
            )
        except OSError as exc:
            raise UnknownArchiveError() from exc

        try:
            while True:
                if cancel_event.is_set():
                    _terminate_process(process)
                    # Do NOT communicate() here: draining until EOF can block
                    # for as long as a surviving grandchild keeps the pipe's
                    # write end open. No thread reads these pipes, so closing
                    # them directly is safe and immediate.
                    for stream in (process.stdout, process.stderr):
                        if stream is not None:
                            try:
                                stream.close()
                            except OSError:
                                pass
                    raise ArchiveCancelled()
                try:
                    process.wait(timeout=0.05)
                    break
                except subprocess.TimeoutExpired:
                    continue
            stdout, stderr = process.communicate()
            return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
        finally:
            _reap_process(process)


def _drain_process_output(process: subprocess.Popen[str], char_queue: queue.Queue[str | None]) -> None:
    """Feed the backend's merged stdout/stderr into ``char_queue`` char by char.

    Runs on a dedicated thread; the ``None`` sentinel marks end of stream so
    the consumer can distinguish "no data yet" from EOF. This thread also
    owns closing the stream: it is the only reader, so closing here is safe,
    whereas closing from the consumer can block while a read is pending.
    """
    stream = process.stdout
    try:
        if stream is not None:
            while True:
                char = stream.read(1)
                if char == "":
                    break
                char_queue.put(char)
    except (OSError, ValueError):
        pass
    finally:
        try:
            char_queue.put(None)
        except Exception:
            pass
        if stream is not None:
            try:
                stream.close()
            except OSError:
                pass


def _parse_slt_entries(output: str) -> list[ArchiveEntry]:
    entries: list[ArchiveEntry] = []
    current: dict[str, str] = {}

    for line in output.splitlines():
        if not line.strip():
            if current:
                entry = _entry_from_slt_record(current)
                if entry is not None:
                    entries.append(entry)
                current = {}
            continue

        if " = " not in line:
            continue

        key, value = line.split(" = ", 1)
        current[key.strip()] = value.strip()

    if current:
        entry = _entry_from_slt_record(current)
        if entry is not None:
            entries.append(entry)

    return entries


def _terminate_process(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return

    try:
        process.terminate()
    except OSError:
        return
    try:
        process.wait(timeout=2)
        return
    except subprocess.TimeoutExpired:
        pass

    try:
        process.kill()
    except OSError:
        return
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        pass


def _reap_process(process: subprocess.Popen[str]) -> None:
    """Ensure a backend process is terminated and reaped (no zombies/leaks)."""
    if process.poll() is None:
        _terminate_process(process)
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass


def _entry_from_slt_record(record: dict[str, str]) -> ArchiveEntry | None:
    path = record.get("Path")
    if not path or record.get("Type"):
        return None

    attributes = record.get("Attributes")
    folder_value = record.get("Folder", "").strip()
    is_directory = folder_value == "+" or bool(attributes and "D" in attributes)

    return ArchiveEntry(
        path=path.replace("\\", "/"),
        size=_parse_int(record.get("Size")),
        modified=record.get("Modified"),
        attributes=attributes,
        is_directory=is_directory,
    )


def _parse_int(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _parse_progress_token(token: str, last_percent: int | None) -> ProgressEvent | None:
    match = re.search(r"(\d{1,3})%", token)
    if not match:
        return None

    percent = max(0, min(100, int(match.group(1))))
    if percent == last_percent:
        return None

    current_file = _parse_current_file(token)
    return ProgressEvent(kind="progress", percent=percent, current_file=current_file)


def _parse_current_file(token: str) -> str | None:
    cleaned = token.replace("\r", "").replace("\n", "").strip()
    for prefix in ("Extracting", "Testing"):
        if cleaned.startswith(prefix):
            value = cleaned.removeprefix(prefix).strip()
            return value or None
    return None


def _password_args(password: str | None) -> list[str]:
    return [f"-p{password}"] if password else []


def _overwrite_arg(policy: OverwritePolicy) -> str:
    if policy == "skip":
        return "-aos"
    if policy == "overwrite":
        return "-aoa"
    if policy == "rename":
        return "-aou"
    raise ValueError(f"Unsupported overwrite policy: {policy}")


def _validate_archive_paths(entries: tuple[ArchiveEntry, ...]) -> None:
    for entry in entries:
        if not _is_safe_archive_path(entry.path):
            raise PathTraversalBlocked()


_WINDOWS_RESERVED_DEVICE_NAMES = frozenset(
    {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        "CONIN$",
        "CONOUT$",
        *(f"COM{index}" for index in range(1, 10)),
        *(f"LPT{index}" for index in range(1, 10)),
    }
)


def _is_safe_archive_path(path: str) -> bool:
    normalized = path.replace("\\", "/")
    pure = Path(normalized)

    if pure.is_absolute():
        return False
    if len(normalized) >= 2 and normalized[1] == ":":
        return False

    for part in normalized.split("/"):
        if part in ("", ".", ".."):
            return False
        # Windows reserves device names even with an extension (``NUL.txt``)
        # and ignores trailing dots/spaces in path components.
        stem = part.split(".", 1)[0].rstrip(". ").upper()
        if stem in _WINDOWS_RESERVED_DEVICE_NAMES:
            return False

    return True


def _map_sevenzip_error(output: str) -> ArchiveError:
    normalized = output.lower()

    if "wrong password" in normalized or "password is incorrect" in normalized:
        return WrongPassword()
    if "password" in normalized and ("enter" in normalized or "required" in normalized):
        return PasswordRequired()
    if "unsupported method" in normalized or "unsupported" in normalized:
        return UnsupportedFormat()
    if (
        "can not open the file as archive" in normalized
        or "cannot open the file as archive" in normalized
        or "headers error" in normalized
        or "unexpected end of archive" in normalized
        or "data error" in normalized
        or "crc failed" in normalized
    ):
        return CorruptedArchive()
    if "access is denied" in normalized or "permission denied" in normalized:
        return OutputPermissionDenied()

    return UnknownArchiveError(output or None)
