"""Build the DuctZip portable zip distribution (Windows).

Repeatable build entry point: ``python scripts/build_portable.py`` from the
repository root. Uses only the standard library. Produces, under ``dist/``:

- ``DuctZip-<version>-portable.zip`` — the artifact.
- ``DuctZip-<version>-portable.zip.sha256`` — checksum for the artifact.
- ``build-manifest.json`` — build inputs and per-file digests (evidence).

Contents: the runtime package (``src/ductzip``), user documentation, license,
third-party notices, and Windows launcher scripts. ``vendor/7zip`` is included
only when it already exists on disk, which happens solely after the explicit
user approval recorded in LONG_TASK.md §10.2 #3 — this script never downloads
anything.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_PACKAGE = REPO_ROOT / "src" / "ductzip"
PORTABLE_DIR = REPO_ROOT / "packaging" / "portable"
VENDOR_7ZIP = REPO_ROOT / "vendor" / "7zip"

REQUIRED_ROOT_DOCS = ("README.md", "LICENSE", "CHANGELOG.md", "THIRD_PARTY_NOTICES.md")
REQUIRED_PORTABLE_FILES = ("ductzip.cmd", "DuctZip GUI.cmd", "PORTABLE.txt")

# Refuse to package if any of these path fragments show up inside src/ductzip.
FORBIDDEN_FRAGMENTS = ("__pycache__", ".pyc", "tests")

# Pinned identity of the bundled 7-Zip backend. The build refuses to package a
# vendor/7zip whose contents do not match these digests, so a replaced or
# corrupted backend cannot ship silently. Keep in sync with
# THIRD_PARTY_NOTICES.md and docs/DESIGN_DECISIONS.md (DD-008 amendment).
BUNDLED_7ZIP_SOURCE_URL = "https://www.7-zip.org/a/7z2603-x64.exe"
BUNDLED_7ZIP_INSTALLER_SHA256 = "0859c524b8a63551848f0c246abddcb1d0b7b656b0fbfe879f8d85e61a9e6edd"
BUNDLED_7ZIP_FILES = {
    "7z.exe": "6ee3c0ed0b27663c1b948ae85a7c0bb073aed1498983182f3f0df1f6a8c30b2f",
    "7z.dll": "65e4c1f855f9ef6e8f0f5df8e3f27d9eb5f07311408639da0a1ca0b8f4871b0d",
    "License.txt": "519ac0a4bded9c18ea02e0afb71f663d8c47373bd9facd3ac96a79f51d77765d",
}


def package_version() -> str:
    text = (SRC_PACKAGE / "__init__.py").read_text(encoding="utf-8")
    match = re.search(r'__version__\s*=\s*"([^"]+)"', text)
    if not match:
        raise RuntimeError("could not read __version__ from src/ductzip/__init__.py")
    return match.group(1)


def git_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO_ROOT, capture_output=True, text=True, check=True,
        )
        return out.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_bundled_backend() -> None:
    """Fail the build if vendor/7zip is incomplete or does not match the pins."""
    missing = sorted(name for name in BUNDLED_7ZIP_FILES if not (VENDOR_7ZIP / name).is_file())
    if missing:
        raise RuntimeError(f"vendor/7zip is incomplete; missing: {missing}")
    mismatched = sorted(
        name for name, expected in BUNDLED_7ZIP_FILES.items()
        if sha256_of(VENDOR_7ZIP / name) != expected
    )
    if mismatched:
        raise RuntimeError(
            "vendor/7zip contents do not match the recorded checksums: "
            f"{mismatched}. Update the pins in this script and "
            "THIRD_PARTY_NOTICES.md together (DD-008 amendment)."
        )


def bundled_backend_record() -> dict[str, str] | None:
    """Describe the bundled backend using repo-relative facts only.

    Deliberately records no build-host paths: the manifest accompanies a
    release artifact and must not leak developer-machine locations.
    """
    if not (VENDOR_7ZIP / "7z.exe").is_file():
        return None
    sys.path.insert(0, str(REPO_ROOT / "src"))
    try:
        from ductzip.archive import get_sevenzip_version

        version = get_sevenzip_version(VENDOR_7ZIP / "7z.exe")
    finally:
        sys.path.remove(str(REPO_ROOT / "src"))
    return {
        "path": "vendor/7zip/7z.exe",
        "version": version,
        "installer_source_url": BUNDLED_7ZIP_SOURCE_URL,
        "installer_sha256": BUNDLED_7ZIP_INSTALLER_SHA256,
    }


def collect_source_files() -> list[Path]:
    files = sorted(SRC_PACKAGE.rglob("*.py"))
    rels = [f.relative_to(REPO_ROOT).as_posix() for f in files]
    bad = [rel for rel in rels if any(fragment in rel for fragment in FORBIDDEN_FRAGMENTS)]
    if bad:
        raise RuntimeError(f"refusing to package forbidden paths: {bad}")
    return files


def build(output_dir: Path) -> Path:
    for doc in REQUIRED_ROOT_DOCS:
        if not (REPO_ROOT / doc).is_file():
            raise RuntimeError(f"missing required file: {doc}")
    for name in REQUIRED_PORTABLE_FILES:
        if not (PORTABLE_DIR / name).is_file():
            raise RuntimeError(f"missing portable launcher: {name}")

    version = package_version()
    bundle_backend = VENDOR_7ZIP.is_dir() and any(VENDOR_7ZIP.iterdir())
    if bundle_backend:
        verify_bundled_backend()
    artifact = output_dir / f"DuctZip-{version}-portable.zip"

    output_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, object] = {
        "name": "DuctZip portable",
        "version": version,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "git_commit": git_commit(),
        "built_at_utc": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "bundled_7zip": bool(bundle_backend),
        "bundled_7zip_backend": bundled_backend_record(),
        "files": [],
    }

    entries: list[tuple[Path, str]] = []  # (absolute source, arcname)
    for doc in REQUIRED_ROOT_DOCS:
        entries.append((REPO_ROOT / doc, doc))
    for name in REQUIRED_PORTABLE_FILES:
        entries.append((PORTABLE_DIR / name, name))
    for source in collect_source_files():
        entries.append((source, Path("src") / source.relative_to(REPO_ROOT / "src")))
    if bundle_backend:
        for source in sorted(VENDOR_7ZIP.rglob("*")):
            if source.is_file():
                entries.append((source, source.relative_to(REPO_ROOT).as_posix()))

    with tempfile.TemporaryDirectory() as temp, zipfile.ZipFile(artifact, "w", zipfile.ZIP_DEFLATED) as zf:
        staged = Path(temp)
        for source, arcname in entries:
            target = staged / arcname
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        for target in sorted(staged.rglob("*")):
            if target.is_file():
                arcname = target.relative_to(staged).as_posix()
                zf.write(target, arcname)
                manifest["files"].append({  # type: ignore[index]
                    "name": arcname,
                    "bytes": target.stat().st_size,
                    "sha256": sha256_of(target),
                })

    (output_dir / f"{artifact.name}.sha256").write_text(
        f"{sha256_of(artifact)}  {artifact.name}\n", encoding="ascii"
    )
    (output_dir / "build-manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return artifact


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=REPO_ROOT / "dist")
    args = parser.parse_args(argv)

    if sys.platform != "win32":
        print("warning: portable zip targets Windows; building anyway", file=sys.stderr)
    artifact = build(args.output)
    size = artifact.stat().st_size
    print(f"built {artifact.name} ({size} bytes)")
    print(f"sha256 {sha256_of(artifact)}")
    print(f"manifest {args.output / 'build-manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
