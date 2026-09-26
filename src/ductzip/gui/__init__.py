"""DuctZip GUI package.

The GUI depends on PySide6, which is an *optional* dependency: importing this
package must not require it. :func:`main` is the guarded entry point used by
the ``ductzip-gui`` script and by ``python -m ductzip.gui``, so a missing
PySide6 produces a comprehensible message instead of an import traceback.
"""

from __future__ import annotations

import sys

MISSING_PYSIDE6_MESSAGE = (
    "DuctZip GUI requires PySide6, which is not installed in this Python "
    "environment.\n\n"
    "Install it with:\n"
    "    python -m pip install PySide6\n\n"
    "The command-line interface (ductzip) works without PySide6."
)


def _report_missing_pyside6() -> None:
    """Surface the missing-dependency message where the user can actually see it.

    ``pythonw`` (used by the portable GUI launcher) has no console, so
    ``sys.stderr`` is ``None`` and a printed message would vanish silently.
    Fall back to a native message box there. Reporting never raises: a failure
    to explain the problem must not become a second crash.
    """
    if sys.stderr is not None:
        print(MISSING_PYSIDE6_MESSAGE, file=sys.stderr)
        return
    if sys.platform != "win32":
        return
    try:  # pragma: no cover - requires a console-less Windows GUI process.
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, MISSING_PYSIDE6_MESSAGE, "DuctZip", 0x10)
    except Exception:
        pass


def main(argv: list[str] | None = None) -> int:
    """Launch the GUI, or explain the missing optional dependency."""
    try:
        from .app import main as run_gui
    except ImportError as exc:
        # Only the optional GUI dependency is reported friendly; any other
        # import failure is a real defect and must keep its traceback.
        if (exc.name or "").split(".")[0] != "PySide6":
            raise
        _report_missing_pyside6()
        return 1
    return run_gui(argv)
