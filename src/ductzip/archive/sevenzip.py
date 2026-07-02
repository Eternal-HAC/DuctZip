from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import shutil
import subprocess
import sys

from .errors import (
    ArchiveError,
    ArchiveNotFound,
    CorruptedArchive,
    OutputPermissionDenied,
    PasswordRequired,
    SevenZipMissing,
    UnknownArchiveError,
    UnsupportedFormat,
    WrongPassword,
)


@dataclass(frozen=True)
class ExtractResult:
    archive_path: Path
    output_dir: Path
    sevenzip_path: Path
    stdout: str
    stderr: str


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

    def extract(self, archive_path: str | os.PathLike[str], output_dir: str | os.PathLike[str]) -> ExtractResult:
        archive = Path(archive_path)
        output = Path(output_dir)

        if not archive.is_file():
            raise ArchiveNotFound()

        try:
            output.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise OutputPermissionDenied() from exc

        command = [
            str(self.sevenzip_path),
            "x",
            str(archive),
            f"-o{output}",
            "-aos",
        ]

        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                errors="replace",
                check=False,
            )
        except OSError as exc:
            raise UnknownArchiveError() from exc

        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()
            raise _map_sevenzip_error(detail)

        return ExtractResult(
            archive_path=archive.resolve(),
            output_dir=output.resolve(),
            sevenzip_path=self.sevenzip_path,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )


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
