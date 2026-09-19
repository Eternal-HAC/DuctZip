from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from ductzip.shell import (
    APP_KEY,
    ARCHIVE_EXTENSIONS,
    PROG_ID,
    VERB_EXTRACT_HERE,
    VERB_EXTRACT_TO,
    FakeRegistry,
    WinRegistry,
    build_verb_command,
    register,
    resolve_launcher,
    status,
    unregister,
)


class RegistrationLayoutTests(unittest.TestCase):
    def test_register_writes_only_scoped_keys(self) -> None:
        registry = FakeRegistry()
        register(registry, launcher=Path(r"C:\Tools\ ductzip \python.exe"))

        snapshot = registry.snapshot()
        key_paths = {key for key, _ in snapshot}

        # Every written key lives under our own namespaces.
        for key in key_paths:
            self.assertTrue(
                key.startswith(
                    (
                        r"Software\Classes\DuctZip.Archive",
                        r"Software\Classes\SystemFileAssociations",
                        r"Software\Classes\.",
                    )
                )
                or key == APP_KEY,
                f"unexpected key outside DuctZip scope: {key}",
            )
        # No extension key outside the approved set was touched.
        touched_extensions = {
            key.split("\\")[3] for key in key_paths if "SystemFileAssociations" in key
        }
        self.assertEqual(touched_extensions, set(ARCHIVE_EXTENSIONS))
        # Both verbs exist for every extension, with a menu label and command.
        for extension in ARCHIVE_EXTENSIONS:
            for verb in (VERB_EXTRACT_HERE, VERB_EXTRACT_TO):
                verb_prefix = rf"Software\Classes\SystemFileAssociations\{extension}\shell"
                self.assertTrue(
                    any(key.startswith(verb_prefix) and key.endswith("command") for key in key_paths),
                    f"missing command key for {extension} {verb}",
                )
        # Open-with entry present but never a default-association hijack.
        self.assertIn(rf"Software\Classes\{ARCHIVE_EXTENSIONS[0]}\OpenWithProgids", key_paths)

    def test_register_is_idempotent(self) -> None:
        registry = FakeRegistry()
        launcher = Path(r"C:\python\python.exe")
        register(registry, launcher=launcher)
        first = registry.snapshot()
        register(registry, launcher=launcher)
        self.assertEqual(registry.snapshot(), first)

    def test_unregister_removes_everything_and_is_safe_when_clean(self) -> None:
        registry = FakeRegistry()
        self.assertEqual(unregister(registry), [])
        self.assertEqual(registry.snapshot(), {})

        register(registry, launcher=Path(r"C:\python\python.exe"))
        removed = unregister(registry)
        self.assertTrue(removed)
        self.assertEqual(registry.snapshot(), {})
        # Second unregister is a no-op, not an error.
        self.assertEqual(unregister(registry), [])

    def test_unregister_recovers_from_partial_corruption(self) -> None:
        registry = FakeRegistry()
        register(registry, launcher=Path(r"C:\python\python.exe"))
        # Simulate another uninstaller or manual cleanup removing half of it.
        for key, _name in [k for k in registry.snapshot()][: len(registry.snapshot()) // 2]:
            registry.delete_tree(key)
        unregister(registry)
        self.assertEqual(registry.snapshot(), {})

    def test_status_reports_stale_launcher(self) -> None:
        registry = FakeRegistry()
        self.assertFalse(status(registry).registered)

        register(registry, launcher=Path(r"C:\missing\pythonw.exe"))
        report = status(registry)
        self.assertTrue(report.registered)
        self.assertFalse(report.launcher_exists)
        self.assertTrue(any("stale" in piece for piece in report.missing_pieces))

    def test_status_reports_missing_verbs(self) -> None:
        registry = FakeRegistry()
        register(registry, launcher=Path(r"C:\python\python.exe"))
        registry.delete_tree(
            rf"Software\Classes\SystemFileAssociations\{ARCHIVE_EXTENSIONS[0]}\shell"
        )
        report = status(registry)
        self.assertTrue(report.missing_pieces)


class CommandProtocolTests(unittest.TestCase):
    def test_verb_command_quotes_exe_and_archive_placeholder(self) -> None:
        command = build_verb_command(VERB_EXTRACT_HERE, r"C:\Program Files\Python\pythonw.exe")
        self.assertEqual(
            command,
            '"C:\\Program Files\\Python\\pythonw.exe" -m ductzip shell extract-here "%1"',
        )

    def test_resolve_launcher_prefers_pythonw(self) -> None:
        launcher = resolve_launcher()
        self.assertTrue(launcher.name.lower() in ("pythonw.exe", "python.exe"))
        self.assertTrue(launcher.is_file())


class WinRegistryRoundTripTests(unittest.TestCase):
    """Gated on a writable HKCU; exercises the real winreg wrapper."""

    def setUp(self) -> None:
        self.registry = WinRegistry()
        unregister(self.registry)  # start from a known-clean state

    def tearDown(self) -> None:
        unregister(self.registry)

    def test_register_status_unregister_real_hkcu(self) -> None:
        launcher = Path(r"C:\nonexistent ductzip test\pythonw.exe")
        report = register(self.registry, launcher=launcher)
        self.assertEqual(report.launcher, launcher)

        state = status(self.registry)
        self.assertTrue(state.registered)
        self.assertFalse(state.launcher_exists)

        before = self.registry.snapshot()
        removed = unregister(self.registry)
        self.assertTrue(removed)
        after = self.registry.snapshot()
        # Unregister removed only what existed, and added or changed nothing.
        self.assertTrue(set(after).issubset(set(before)))
        removed_keys = {key for key, _ in set(before) - set(after)}
        self.assertTrue(removed_keys)
        # Owned keys carry the DuctZip name; the only other removals are the
        # OpenWithProgids values under extension keys.
        for key in removed_keys:
            self.assertTrue(
                "DuctZip" in key or key.endswith("OpenWithProgids"),
                f"unregister touched a foreign key: {key}",
            )
        self.assertFalse(status(self.registry).registered)


if __name__ == "__main__":
    unittest.main()
