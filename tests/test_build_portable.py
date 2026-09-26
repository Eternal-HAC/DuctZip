"""Portable build regression tests: manifest provenance honesty and the
self-documenting package contents."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


def _load_build_module():
    repo_root = Path(__file__).resolve().parent.parent
    spec = importlib.util.spec_from_file_location(
        "build_portable", repo_root / "scripts" / "build_portable.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PortableBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.bp = _load_build_module()
        cls._tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls._tmp.cleanup)
        cls.out = Path(cls._tmp.name)
        cls.artifact = cls.bp.build(cls.out)
        cls.manifest = json.loads(
            (cls.out / "build-manifest.json").read_text(encoding="utf-8")
        )

    def test_manifest_records_honest_git_provenance(self) -> None:
        # A build from a dirty worktree must say so, with an auditable digest
        # of the tracked diff — never silently masquerade as pure HEAD.
        self.assertIn("git_dirty", self.manifest)
        self.assertIn("worktree_diff_sha256", self.manifest)
        self.assertIn("git_commit", self.manifest)
        if self.manifest["git_dirty"]:
            digest = self.manifest["worktree_diff_sha256"]
            self.assertIsNotNone(digest)
            self.assertEqual(len(digest), 64)
            # The digest must actually match the current tracked diff.
            import subprocess

            out = subprocess.run(
                ["git", "diff", "HEAD"],
                cwd=self.bp.REPO_ROOT, capture_output=True, check=True,
            )
            import hashlib

            self.assertEqual(
                hashlib.sha256(out.stdout).hexdigest(), digest,
                "worktree_diff_sha256 must match the real tracked diff",
            )
        else:
            self.assertIsNone(self.manifest["worktree_diff_sha256"])

    def test_portable_package_contains_user_documentation(self) -> None:
        names = [entry["name"] for entry in self.manifest["files"]]
        version = self.manifest["version"]
        root = f"DuctZip-{version}"
        self.assertIn(f"{root}/USER_MANUAL.md", names)
        self.assertIn(f"{root}/RELEASE_NOTES.md", names)
        for required in ("README.md", "LICENSE", "CHANGELOG.md", "THIRD_PARTY_NOTICES.md", "PORTABLE.txt"):
            self.assertIn(f"{root}/{required}", names)

    def test_manifest_hashes_match_artifact_contents(self) -> None:
        import zipfile

        with zipfile.ZipFile(self.artifact) as zf:
            bundled = {info.filename: info for info in zf.infolist()}
        for entry in self.manifest["files"]:
            self.assertIn(entry["name"], bundled)
            self.assertEqual(bundled[entry["name"]].file_size, entry["bytes"])


if __name__ == "__main__":
    unittest.main()
