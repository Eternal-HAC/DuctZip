"""Reversible Windows Explorer integration (current-user scope, HKCU).

This module owns the *registration surface* only: it writes and removes
current-user registry entries that expose DuctZip in Explorer's context menu
and "Open with" list. It never installs a native shell extension, never
touches machine-wide (HKLM) keys, and never modifies another application's
registration.

Registry layout created by :func:`register` (all under ``HKEY_CURRENT_USER``;
``<root>`` defaults to ``Software`` and is injectable for tests):

- ``<root>\\DuctZip`` — app key: ``RegisteredExe`` (absolute launcher path),
  ``Version``, ``RegisteredAt`` (ISO timestamp). Pure metadata; removing it is
  part of unregister.
- ``<root>\\Classes\\DuctZip.Archive`` — ProgID with ``shell\\open`` (launches
  the GUI on the file) and the two extraction verbs.
- ``<root>\\Classes\\SystemFileAssociations\\<ext>\\shell\\DuctZip.ExtractHere``
  and ``...\\DuctZip.ExtractTo`` — the context-menu verbs for each supported
  archive extension. Only these two verb subkeys are ever written or removed
  under ``SystemFileAssociations``; sibling keys owned by other applications
  are left untouched.
- ``<root>\\Classes\\<ext>\\OpenWithProgids`` — a ``DuctZip.Archive`` value so
  DuctZip appears in "Open with" without changing the default program.

:func:`unregister` removes exactly the keys and values :func:`register`
created, and is safe to run when partially registered, fully registered, or
not registered at all. After normal unregister no manual registry cleanup is
required.

The verbs invoke the stable CLI protocol ``python -m ductzip shell <verb>
"%1"`` — Explorer launches the command once per selected file; the protocol
itself also accepts several archives in one invocation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import os
import sys

VERB_EXTRACT_HERE = "extract-here"
VERB_EXTRACT_TO = "extract-to"

MENU_LABELS = {
    VERB_EXTRACT_HERE: "用 DuctZip 解压到当前目录",
    VERB_EXTRACT_TO: "用 DuctZip 解压到同名文件夹",
}

# Extensions that get context-menu verbs and an Open-with entry. Multi-suffix
# archives (.tar.gz) are covered by their final suffix entry, matching the
# engine's own format support surface.
ARCHIVE_EXTENSIONS = (".zip", ".7z", ".rar", ".tar", ".gz", ".bz2", ".xz", ".zst")

PROG_ID = "DuctZip.Archive"
APP_KEY = r"Software\DuctZip"
_CLASSES = r"Software\Classes"


# --------------------------------------------------------------------- registry


class Registry:
    """Minimal current-user registry surface.

    Implementations: :class:`WinRegistry` (winreg-backed, HKCU) and
    :class:`FakeRegistry` (dict-backed, for tests). ``key_path`` values are
    relative to HKCU; use ``name=""`` for the default value.
    """

    def set_value(self, key_path: str, name: str, value: str) -> None:
        raise NotImplementedError

    def get_value(self, key_path: str, name: str) -> str | None:
        """Return the value, or ``None`` when the key or value is absent."""
        raise NotImplementedError

    def delete_value(self, key_path: str, name: str) -> None:
        """Remove one value; absent key/value is not an error."""
        raise NotImplementedError

    def delete_tree(self, key_path: str) -> None:
        """Remove a key and everything below it; absent key is not an error."""
        raise NotImplementedError

    def key_exists(self, key_path: str) -> bool:
        raise NotImplementedError

    def snapshot(self) -> dict[tuple[str, str], str]:
        """Every (key, value-name) pair, for scoped-diff assertions."""
        raise NotImplementedError


class WinRegistry(Registry):
    """HKCU-backed registry access via ``winreg`` (imported lazily)."""

    def set_value(self, key_path: str, name: str, value: str) -> None:
        import winreg

        # CreateKey creates the full path when missing and opens it otherwise.
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            winreg.SetValueEx(key, name or "", 0, winreg.REG_SZ, value)

    def get_value(self, key_path: str, name: str) -> str | None:
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                value, _ = winreg.QueryValueEx(key, name or "")
        except OSError:
            return None
        return value

    def delete_value(self, key_path: str, name: str) -> None:
        import winreg

        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE
            ) as key:
                winreg.DeleteValue(key, name or "")
        except OSError:
            pass  # absent key or value: nothing to clean

    def delete_tree(self, key_path: str) -> None:
        import winreg

        access = winreg.KEY_READ | winreg.KEY_SET_VALUE | getattr(winreg, "KEY_WOW64_64KEY", 0)

        def delete_recursive(path: str) -> None:
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path, 0, access) as key:
                    subkeys = []
                    index = 0
                    while True:
                        try:
                            subkeys.append(winreg.EnumKey(key, index))
                        except OSError:
                            break
                        index += 1
            except OSError:
                return  # absent: nothing to clean
            for subkey in subkeys:
                delete_recursive(path + "\\" + subkey)
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)
            except OSError:
                pass

        delete_recursive(key_path)

    def key_exists(self, key_path: str) -> bool:
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path):
                return True
        except OSError:
            return False

    def snapshot(self) -> dict[tuple[str, str], str]:
        import winreg

        result: dict[tuple[str, str], str] = {}

        def walk(key_path: str) -> None:
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                    index = 0
                    while True:
                        try:
                            name, value, _ = winreg.EnumValue(key, index)
                        except OSError:
                            break
                        result[(key_path, name)] = value
                        index += 1
                    index = 0
                    while True:
                        try:
                            subkey = winreg.EnumKey(key, index)
                        except OSError:
                            break
                        walk(key_path + "\\" + subkey)
                        index += 1
            except OSError:
                return

        for top in (_CLASSES, APP_KEY):
            walk(top)
        return result


class FakeRegistry(Registry):
    """In-memory registry double for hermetic tests."""

    def __init__(self) -> None:
        self._values: dict[tuple[str, str], str] = {}

    def set_value(self, key_path: str, name: str, value: str) -> None:
        self._values[(key_path, name)] = value

    def get_value(self, key_path: str, name: str) -> str | None:
        return self._values.get((key_path, name))

    def delete_value(self, key_path: str, name: str) -> None:
        self._values.pop((key_path, name), None)

    def delete_tree(self, key_path: str) -> None:
        prefix = key_path + "\\"
        for path, name in [k for k in self._values if k[0] == key_path or k[0].startswith(prefix)]:
            del self._values[(path, name)]

    def key_exists(self, key_path: str) -> bool:
        prefix = key_path + "\\"
        return any(k[0] == key_path or k[0].startswith(prefix) for k in self._values)

    def snapshot(self) -> dict[tuple[str, str], str]:
        return dict(self._values)


# ------------------------------------------------------------------ key layout


def _verb_command_key(extension: str | None, verb: str) -> str:
    verb_key = "DuctZip.ExtractHere" if verb == VERB_EXTRACT_HERE else "DuctZip.ExtractTo"
    if extension is None:  # ProgID verbs
        return rf"{_CLASSES}\{PROG_ID}\shell\{verb_key}\command"
    return rf"{_CLASSES}\SystemFileAssociations\{extension}\shell\{verb_key}\command"


def _verb_menu_key(extension: str | None, verb: str) -> str:
    return _verb_command_key(extension, verb).rsplit("\\", 1)[0]


def _open_with_key(extension: str) -> str:
    return rf"{_CLASSES}\{extension}\OpenWithProgids"


def _prog_id_open_key() -> str:
    return rf"{_CLASSES}\{PROG_ID}\shell\open\command"


def build_verb_command(verb: str, exe_path: str | Path) -> str:
    """The command string Windows stores for a verb.

    ``"%1"`` is quoted so paths with spaces or Unicode survive Explorer's
    command-line substitution; the DuctZip CLI parses argv with Python's
    Unicode-aware Windows argv handling. Works for both interpreter
    launchers and portable ``.cmd`` launchers (which dispatch to
    ``python -m ductzip`` themselves).
    """
    return f'"{Path(exe_path)}" shell {verb} "%1"'


def build_open_command(exe_path: str | Path) -> str:
    """The ProgID open command: GUI with an archive argument.

    An interpreter launcher needs the ``-m ductzip.gui`` module selector;
    a portable ``.cmd``/``.bat`` launcher already embeds it, so the archive
    path alone is passed through.
    """
    launcher = Path(exe_path)
    if launcher.suffix.lower() in (".cmd", ".bat"):
        return f'"{launcher}" "%1"'
    return f'"{launcher}" -m ductzip.gui "%1"'


def resolve_launcher() -> Path:
    """The executable recorded in verb commands.

    ``pythonw.exe`` keeps context-menu runs free of a console window; plain
    ``python.exe`` is the fallback when pythonw is missing.
    """
    executable = Path(sys.executable)
    pythonw = executable.with_name("pythonw.exe")
    return pythonw if pythonw.exists() else executable


def resolve_portable_launchers() -> tuple[Path, Path] | None:
    """Launchers of a portable DuctZip copy, when registered from one.

    The portable launchers set ``DUCTZIP_PORTABLE_ROOT``; when present, the
    bundled ``ductzip.cmd`` / ``DuctZip GUI.cmd`` become the recorded
    launchers so Explorer invocations find the package without a pip
    install. Returns ``(cli_launcher, gui_launcher)`` or ``None``.
    """
    root = os.environ.get("DUCTZIP_PORTABLE_ROOT")
    if not root:
        return None
    cli = Path(root) / "ductzip.cmd"
    gui = Path(root) / "DuctZip GUI.cmd"
    if cli.is_file():
        return cli, gui if gui.is_file() else cli
    return None


# ------------------------------------------------------------ register/unregister


@dataclass(frozen=True)
class RegisterReport:
    launcher: Path
    keys_written: tuple[str, ...]
    extensions: tuple[str, ...] = tuple(ARCHIVE_EXTENSIONS)


@dataclass(frozen=True)
class StatusReport:
    registered: bool
    launcher: Path | None
    launcher_exists: bool
    verbs_present: dict[str, bool]
    missing_pieces: tuple[str, ...] = field(default_factory=tuple)


def register(
    registry: Registry | None = None,
    launcher: Path | None = None,
    gui_launcher: Path | None = None,
) -> RegisterReport:
    """Write all current-user registration entries. Idempotent by design."""
    registry = registry if registry is not None else WinRegistry()
    if launcher is None:
        portable = resolve_portable_launchers()
        if portable is not None:
            launcher, portable_gui = portable
            gui_launcher = gui_launcher if gui_launcher is not None else portable_gui
        else:
            launcher = resolve_launcher()
    launcher = Path(launcher)
    gui_launcher = Path(gui_launcher) if gui_launcher is not None else launcher

    written: list[str] = []
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    registry.set_value(APP_KEY, "RegisteredExe", str(launcher))
    registry.set_value(APP_KEY, "Version", _ductzip_version())
    registry.set_value(APP_KEY, "RegisteredAt", now)
    written.append(APP_KEY)

    # ProgID: open -> GUI; the two extraction verbs also live here so the
    # "Open with" entry is itself functional.
    registry.set_value(_prog_id_open_key(), "", build_open_command(gui_launcher))
    written.append(_prog_id_open_key())
    for verb in (VERB_EXTRACT_HERE, VERB_EXTRACT_TO):
        registry.set_value(
            _verb_command_key(None, verb), "", build_verb_command(verb, launcher)
        )
        registry.set_value(_verb_menu_key(None, verb), "MUIVerb", MENU_LABELS[verb])
        written.append(_verb_command_key(None, verb))

    for extension in ARCHIVE_EXTENSIONS:
        for verb in (VERB_EXTRACT_HERE, VERB_EXTRACT_TO):
            registry.set_value(
                _verb_command_key(extension, verb), "", build_verb_command(verb, launcher)
            )
            registry.set_value(_verb_menu_key(extension, verb), "MUIVerb", MENU_LABELS[verb])
            written.append(_verb_command_key(extension, verb))
        registry.set_value(_open_with_key(extension), PROG_ID, "")
        written.append(_open_with_key(extension))

    return RegisterReport(launcher=launcher, keys_written=tuple(written))


def unregister(registry: Registry | None = None) -> list[str]:
    """Remove exactly what :func:`register` created.

    Safe on a clean machine, a fully registered machine, or a partially
    corrupted one. Returns the key paths that were actually removed.
    """
    registry = registry if registry is not None else WinRegistry()
    removed: list[str] = []

    for extension in ARCHIVE_EXTENSIONS:
        for verb in (VERB_EXTRACT_HERE, VERB_EXTRACT_TO):
            key = _verb_command_key(extension, verb).rsplit("\\", 1)[0]
            if registry.key_exists(key):
                registry.delete_tree(key)
                removed.append(key)
        open_with = _open_with_key(extension)
        if registry.key_exists(open_with):
            registry.delete_value(open_with, PROG_ID)
            removed.append(open_with)

    prog_id = rf"{_CLASSES}\{PROG_ID}"
    if registry.key_exists(prog_id):
        registry.delete_tree(prog_id)
        removed.append(prog_id)
    if registry.key_exists(APP_KEY):
        registry.delete_tree(APP_KEY)
        removed.append(APP_KEY)
    return removed


def status(registry: Registry | None = None) -> StatusReport:
    """Report the registration state, including stale-launcher detection."""
    registry = registry if registry is not None else WinRegistry()

    launcher_value = registry.get_value(APP_KEY, "RegisteredExe")
    launcher = Path(launcher_value) if launcher_value else None
    launcher_exists = launcher.is_file() if launcher is not None else False

    verbs_present = {
        f"{extension}:{verb}": registry.key_exists(_verb_command_key(extension, verb))
        for extension in ARCHIVE_EXTENSIONS
        for verb in (VERB_EXTRACT_HERE, VERB_EXTRACT_TO)
    }
    verbs_missing = [name for name, present in verbs_present.items() if not present]
    missing_pieces = list(verbs_missing)
    if launcher is not None and not launcher_exists:
        missing_pieces.append(f"stale launcher: {launcher}")

    # Registered means the entries exist; a stale launcher is reported as a
    # problem but does not make the registration disappear.
    registered = launcher is not None and not verbs_missing
    return StatusReport(
        registered=registered,
        launcher=launcher,
        launcher_exists=launcher_exists,
        verbs_present=verbs_present,
        missing_pieces=tuple(missing_pieces),
    )


def _ductzip_version() -> str:
    try:
        from . import __version__

        return __version__
    except Exception:  # noqa: BLE001 - version metadata is best-effort here.
        return "unknown"
