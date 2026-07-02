from __future__ import annotations

import argparse
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
    extract_parser.add_argument("--verbose", action="store_true", help="Print diagnostic details.")

    doctor_parser = subparsers.add_parser("doctor", help="Check DuctZip runtime dependencies.")
    doctor_parser.add_argument("--sevenzip", help="Path to 7z.exe or 7zz.exe.")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "extract":
        try:
            engine = SevenZipCliEngine(args.sevenzip)
            if args.verbose:
                print(f"7-Zip: {engine.sevenzip_path}", file=sys.stderr)
                print(f"Archive: {Path(args.archive_path)}", file=sys.stderr)
                print(f"Output: {Path(args.output)}", file=sys.stderr)
            result = engine.extract(Path(args.archive_path), Path(args.output))
        except ArchiveError as exc:
            print(str(exc), file=sys.stderr)
            return 1

        print(f"解压完成：{result.output_dir}")
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
