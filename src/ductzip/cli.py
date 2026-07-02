from __future__ import annotations

import argparse
import getpass
from pathlib import Path
import sys

from .archive import ArchiveError, SevenZipCliEngine, find_sevenzip, get_sevenzip_version


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ductzip", description="DuctZip command line interface.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    extract_parser = subparsers.add_parser("extract", help="Extract an archive to an output directory.")
    extract_parser.add_argument("archive_path", help="Path to the archive file.")
    extract_parser.add_argument("-o", "--output", required=True, help="Output directory.")
    extract_parser.add_argument("--sevenzip", help="Path to 7z.exe or 7zz.exe.")
    extract_parser.add_argument("--password", help="Archive password. Prefer --password-prompt for interactive use.")
    extract_parser.add_argument("--password-prompt", action="store_true", help="Prompt for the archive password.")
    extract_parser.add_argument(
        "--overwrite-policy",
        choices=("skip", "overwrite", "rename"),
        default="skip",
        help="How to handle existing files in the output directory.",
    )
    extract_parser.add_argument("--verbose", action="store_true", help="Print diagnostic details.")

    list_parser = subparsers.add_parser("list", help="List archive entries.")
    list_parser.add_argument("archive_path", help="Path to the archive file.")
    list_parser.add_argument("--sevenzip", help="Path to 7z.exe or 7zz.exe.")
    list_parser.add_argument("--password", help="Archive password. Prefer --password-prompt for interactive use.")
    list_parser.add_argument("--password-prompt", action="store_true", help="Prompt for the archive password.")

    test_parser = subparsers.add_parser("test", help="Test archive integrity.")
    test_parser.add_argument("archive_path", help="Path to the archive file.")
    test_parser.add_argument("--sevenzip", help="Path to 7z.exe or 7zz.exe.")
    test_parser.add_argument("--password", help="Archive password. Prefer --password-prompt for interactive use.")
    test_parser.add_argument("--password-prompt", action="store_true", help="Prompt for the archive password.")

    doctor_parser = subparsers.add_parser("doctor", help="Check DuctZip runtime dependencies.")
    doctor_parser.add_argument("--sevenzip", help="Path to 7z.exe or 7zz.exe.")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "extract":
        try:
            password = _resolve_password(args)
            engine = SevenZipCliEngine(args.sevenzip)
            if args.verbose:
                print(f"7-Zip: {engine.sevenzip_path}", file=sys.stderr)
                print(f"Archive: {Path(args.archive_path)}", file=sys.stderr)
                print(f"Output: {Path(args.output)}", file=sys.stderr)
                result = None
                for event in engine.extract_with_progress(
                    Path(args.archive_path),
                    Path(args.output),
                    password=password,
                    overwrite_policy=args.overwrite_policy,
                ):
                    if event.kind == "progress" and event.percent is not None:
                        print(f"Progress: {event.percent}%", file=sys.stderr)
                    elif event.kind == "completed":
                        result = event.result
                if result is None:
                    raise ArchiveError()
            else:
                result = engine.extract(
                    Path(args.archive_path),
                    Path(args.output),
                    password=password,
                    overwrite_policy=args.overwrite_policy,
                )
        except ArchiveError as exc:
            print(str(exc), file=sys.stderr)
            return 1

        print(f"解压完成：{result.output_dir}")
        return 0

    if args.command == "list":
        try:
            password = _resolve_password(args)
            engine = SevenZipCliEngine(args.sevenzip)
            listing = engine.list(Path(args.archive_path), password=password)
        except ArchiveError as exc:
            print(str(exc), file=sys.stderr)
            return 1

        for entry in listing.entries:
            marker = "d" if entry.is_directory else "f"
            size = "" if entry.size is None else str(entry.size)
            print(f"{marker}\t{size}\t{entry.path}")
        return 0

    if args.command == "test":
        try:
            password = _resolve_password(args)
            engine = SevenZipCliEngine(args.sevenzip)
            engine.test(Path(args.archive_path), password=password)
        except ArchiveError as exc:
            print(str(exc), file=sys.stderr)
            return 1

        print("压缩包测试通过。")
        return 0

    if args.command == "doctor":
        try:
            sevenzip_path = find_sevenzip(args.sevenzip)
            version = get_sevenzip_version(sevenzip_path)
        except ArchiveError as exc:
            print(f"7-Zip: {exc}", file=sys.stderr)
            return 1

        print("DuctZip doctor")
        print(f"7-Zip: {sevenzip_path}")
        print(f"Version: {version}")
        return 0

    parser.print_help()
    return 2


def _resolve_password(args: argparse.Namespace) -> str | None:
    if getattr(args, "password_prompt", False):
        return getpass.getpass("Archive password: ")
    return getattr(args, "password", None)
