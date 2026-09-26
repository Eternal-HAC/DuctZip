"""Entry-point behaviour of the optional GUI dependency.

LONG_TASK.md §7.4 and ``docs/RELEASE_CHECKLIST.md`` require a comprehensible
error when PySide6 is unavailable. The friendly message in ``gui.app`` used to
be unreachable — it sat *after* an unguarded ``from . import workers``, so the
user saw a raw ``ModuleNotFoundError`` traceback instead. These tests pin the
guarded entry point that fixed it, and check that genuine import failures are
still reported as failures rather than being swallowed as "PySide6 missing".
"""

from __future__ import annotations

import builtins
import contextlib
import io
import sys
import unittest
from unittest import mock

import ductzip.gui as gui

_GUI_SUBMODULES = ("ductzip.gui.app", "ductzip.gui.workers", "ductzip.gui.settings_dialog")


def _failing_import(*module_names: str):
    """Build an ``__import__`` replacement that fails for the given modules."""
    real_import = builtins.__import__
    blocked = tuple(module_names)

    def fake_import(name, *args, **kwargs):
        if any(name == blocked_name or name.startswith(f"{blocked_name}.") for blocked_name in blocked):
            raise ModuleNotFoundError(f"No module named '{name}'", name=name)
        return real_import(name, *args, **kwargs)

    return fake_import


class GuiEntryPointTests(unittest.TestCase):
    def _run_main(self, *blocked: str) -> tuple[int, str]:
        stderr = io.StringIO()
        with mock.patch.dict(sys.modules):
            # The submodules may already be imported by other tests; drop them
            # so `from .app import main` genuinely re-executes the import chain.
            for name in _GUI_SUBMODULES:
                sys.modules.pop(name, None)
            with mock.patch.object(
                builtins, "__import__", side_effect=_failing_import(*blocked)
            ), contextlib.redirect_stderr(stderr):
                return gui.main([]), stderr.getvalue()

    def test_missing_pyside6_returns_failure_with_actionable_message(self) -> None:
        code, message = self._run_main("PySide6")

        self.assertEqual(code, 1)
        self.assertIn("PySide6", message)
        self.assertIn("pip install PySide6", message)
        # The CLI does not depend on the GUI stack; say so, so a user does not
        # conclude the whole tool is broken.
        self.assertIn("ductzip", message)

    def test_other_import_errors_keep_their_traceback(self) -> None:
        """A real defect must not be disguised as a missing optional dependency."""
        with self.assertRaises(ModuleNotFoundError) as caught:
            self._run_main("ductzip.core")

        self.assertEqual(caught.exception.name, "ductzip.core")


if __name__ == "__main__":
    unittest.main()
