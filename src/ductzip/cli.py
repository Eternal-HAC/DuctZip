from __future__ import annotations

import argparse
import getpass
from pathlib import Path
import sys

from .archive import ArchiveError, SevenZipCliEngine, find_sevenzip, get_sevenzip_version
from .core import BatchQueue, ExtractionService, archive_logical_name
from . import shell as shell_integration

# Batch exit codes: 0 = all tasks completed, 1 = one or more tasks failed,
# 130 = cancelled by the user (Ctrl+C), 2 = usage error (argparse).
EXIT_ALL_COMPLETED = 0
EXIT_SOME_FAILED = 1
EXIT_CANCELLED = 130


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ductzip", description="DuctZip command line interface.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    extract_parser = subparsers.add_parser("extract", help="Extract an archive to an output directory.")
    extract_parser.add_argument("archive_path", help="Path to the archive file.")
    extract_parser.add_argument(
        "-o",
        "--output",
        required=True,
        help="Final extraction directory in normal mode; base directory for Smart mode.",
    )
    extract_parser.add_argument("--sevenzip", help="Path to 7z.exe or 7zz.exe.")
    extract_parser.add_argument("--password", help="Archive password. Prefer --password-prompt for interactive use.")
    extract_parser.add_argument("--password-prompt", action="store_true", help="Prompt for the archive password.")
    extract_parser.add_argument(
        "--overwrite-policy",
        choices=("skip", "overwrite", "rename"),
        default="skip",
        help="How to handle existing files in the output directory.",
    )
    extract_parser.add_argument(
        "--smart-output",
        action="store_true",
        help="Resolve the final directory from the archive layout: a single top-level entry uses the "
        "base directory directly; multiple top-level entries create a same-name-as-archive subdirectory.",
    )
    extract_parser.add_argument(
        "--conflict-strategy",
        choices=("merge", "rename", "cancel"),
        default="merge",
        help="How to handle existing top-level output conflicts.",
    )
    extract_parser.add_argument("--verbose", action="store_true", help="Print diagnostic details.")

    batch_parser = subparsers.add_parser(
        "batch-extract",
        help="Extract multiple archives sequentially into a shared base directory.",
    )
    batch_parser.add_argument("archive_paths", nargs="+", help="Paths to the archive files.")
    batch_parser.add_argument(
        "-o",
        "--output",
        required=True,
        help="Base output directory shared by all archives; Smart Output resolves each task's final directory.",
    )
    batch_parser.add_argument("--sevenzip", help="Path to 7z.exe or 7zz.exe.")
    batch_parser.add_argument("--password", help="Archive password applied to every archive. Prefer --password-prompt.")
    batch_parser.add_argument("--password-prompt", action="store_true", help="Prompt for the archive password.")
    batch_parser.add_argument(
        "--overwrite-policy",
        choices=("skip", "overwrite", "rename"),
        default="skip",
        help="How to handle existing files in the output directory.",
    )
    batch_parser.add_argument(
        "--conflict-strategy",
        choices=("merge", "rename", "cancel"),
        default="merge",
        help="How to handle existing top-level output conflicts.",
    )
    batch_parser.add_argument(
        "--no-smart-output",
        dest="smart_output",
        action="store_false",
        help="Extract every archive directly into the base directory instead of resolving per-archive final directories.",
    )
    batch_parser.set_defaults(smart_output=True)
    batch_parser.add_argument(
        "--retries",
        type=int,
        default=0,
        metavar="N",
        help="Retry each failed task up to N additional times.",
    )
    batch_parser.add_argument("--verbose", action="store_true", help="Print per-task diagnostic details.")

    shell_parser = subparsers.add_parser(
        "shell",
        help="Windows Explorer integration: shell-facing extract verbs and HKCU registration.",
    )
    shell_subparsers = shell_parser.add_subparsers(dest="shell_command", required=True)
    for verb, help_text in (
        (
            shell_integration.VERB_EXTRACT_HERE,
            "Extract each archive into its own parent directory (Explorer 'extract here').",
        ),
        (
            shell_integration.VERB_EXTRACT_TO,
            "Extract each archive into a same-named folder beside it (Explorer 'extract to').",
        ),
    ):
        verb_parser = shell_subparsers.add_parser(verb, help=help_text)
        verb_parser.add_argument("archive_paths", nargs="+", help="Paths to the archive files.")
        verb_parser.add_argument("--sevenzip", help="Path to 7z.exe or 7zz.exe.")
        verb_parser.add_argument("--password", help="Archive password applied to every archive.")
        verb_parser.add_argument("--password-prompt", action="store_true", help="Prompt for the archive password.")
        verb_parser.add_argument(
            "--overwrite-policy",
            choices=("skip", "overwrite", "rename"),
            default="skip",
            help="How to handle existing files in the output directory.",
        )
        verb_parser.add_argument(
            "--conflict-strategy",
            choices=("merge", "rename", "cancel"),
            default="merge",
            help="How to handle existing top-level output conflicts.",
        )
        verb_parser.add_argument(
            "--retries",
            type=int,
            default=0,
            metavar="N",
            help="Retry each failed task up to N additional times.",
        )
        verb_parser.add_argument("--verbose", action="store_true", help="Print per-task diagnostic details.")
    shell_subparsers.add_parser("register", help="Register Explorer context-menu verbs for the current user (HKCU).")
    shell_subparsers.add_parser("unregister", help="Remove all DuctZip Explorer registration (HKCU).")
    shell_subparsers.add_parser("status", help="Show Explorer registration state and launcher health.")

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
            service = ExtractionService(SevenZipCliEngine(args.sevenzip))
            if args.verbose:
                print(f"7-Zip: {service.engine.sevenzip_path}", file=sys.stderr)
                print(f"Archive: {Path(args.archive_path)}", file=sys.stderr)
                print(f"Output: {Path(args.output)}", file=sys.stderr)
                result = None
                for event in service.extract_with_progress(
                    Path(args.archive_path),
                    Path(args.output),
                    password=password,
                    overwrite_policy=args.overwrite_policy,
                    smart_output=args.smart_output,
                    conflict_strategy=args.conflict_strategy,
                ):
                    if event.kind == "progress" and event.percent is not None:
                        print(f"Progress: {event.percent}%", file=sys.stderr)
                    elif event.kind == "completed":
                        result = event.result
                if result is None:
                    raise ArchiveError()
            else:
                result = service.extract(
                    Path(args.archive_path),
                    Path(args.output),
                    password=password,
                    overwrite_policy=args.overwrite_policy,
                    smart_output=args.smart_output,
                    conflict_strategy=args.conflict_strategy,
                )
        except ArchiveError as exc:
            print(str(exc), file=sys.stderr)
            return 1

        print(f"解压完成：{result.output_dir}")
        return 0

    if args.command == "batch-extract":
        return _run_batch_extract(args)

    if args.command == "shell":
        return _run_shell_command(args)

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


def _run_batch_extract(args: argparse.Namespace) -> int:
    """Run a BatchQueue for the CLI, printing one line per task and a summary.

    Exit codes: 0 all completed, 1 at least one failure, 130 cancelled.
    Passwords are consumed but never printed.
    """
    try:
        service = _shell_service(args)
    except _UsageError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except _BackendUnavailable as exc:
        print(str(exc), file=sys.stderr)
        return 1

    queue = BatchQueue(service)
    for archive_path in args.archive_paths:
        queue.add(
            Path(archive_path),
            Path(args.output),
            smart_output=args.smart_output,
            conflict_strategy=args.conflict_strategy,
            overwrite_policy=args.overwrite_policy,
            password=_resolve_password(args),
        )
    return _run_queue_to_completion(queue, args)


def _shell_service(args: argparse.Namespace) -> ExtractionService:
    if getattr(args, "retries", 0) < 0:
        raise _UsageError("--retries must be >= 0")
    try:
        return ExtractionService(SevenZipCliEngine(args.sevenzip))
    except ArchiveError as exc:
        raise _BackendUnavailable(str(exc)) from exc


class _UsageError(Exception):
    """Maps to exit code 2."""


class _BackendUnavailable(Exception):
    """Maps to exit code 1."""


def _run_shell_command(args: argparse.Namespace) -> int:
    """Dispatch the ``ductzip shell`` protocol.

    ``extract-here`` / ``extract-to`` are the stable invocation targets of the
    Explorer context-menu verbs; ``register`` / ``unregister`` / ``status``
    manage the current-user (HKCU) registration. Explorer launches the verb
    command once per selected file, but the verbs also accept several
    archives in one invocation.
    """
    if args.shell_command == "register":
        report = shell_integration.register()
        print(f"已注册（当前用户）：{report.launcher}")
        print(f"覆盖扩展名：{' '.join(report.extensions)}")
        print("卸载：python -m ductzip shell unregister")
        return 0
    if args.shell_command == "unregister":
        removed = shell_integration.unregister()
        if removed:
            print(f"已移除 {len(removed)} 项注册表项。")
        else:
            print("未发现 DuctZip 注册项，无需清理。")
        return 0
    if args.shell_command == "status":
        report = shell_integration.status()
        if not report.registered:
            print("未注册。")
            return 0
        state = "可用" if report.launcher_exists else "已失效（launcher 不存在）"
        print(f"已注册（当前用户）：{report.launcher} — {state}")
        missing = [name for name, present in report.verbs_present.items() if not present]
        if missing:
            print(f"缺失项：{len(missing)}（如 {missing[0]}）；建议重新 register。")
        return 0

    # extract-here / extract-to: one queue, per-archive output roots.
    try:
        service = _shell_service(args)
    except _UsageError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except _BackendUnavailable as exc:
        print(str(exc), file=sys.stderr)
        return 1

    password = _resolve_password(args)
    queue = BatchQueue(service)
    for archive_path in args.archive_paths:
        archive = Path(archive_path)
        if args.shell_command == shell_integration.VERB_EXTRACT_TO:
            requested = archive.parent / archive_logical_name(archive)
        else:
            requested = archive.parent
        queue.add(
            archive,
            requested,
            smart_output=True,
            conflict_strategy=args.conflict_strategy,
            overwrite_policy=args.overwrite_policy,
            password=password,
        )
    return _run_queue_to_completion(queue, args)


def _run_queue_to_completion(queue: BatchQueue, args: argparse.Namespace) -> int:
    """Drain a queue (with retries), print per-task lines, return the exit code."""
    if getattr(args, "verbose", False):
        service = queue.service
        print(f"7-Zip: {service.engine.sevenzip_path}", file=sys.stderr)
        print(f"Tasks: {len(queue.tasks)}", file=sys.stderr)

    try:
        _drain_batch(queue, args)
        for _ in range(getattr(args, "retries", 0)):
            failed = [task for task in queue.tasks if task.state == "failed"]
            if not failed:
                break
            for task in failed:
                queue.retry(task.task_id)
            _drain_batch(queue, args)
    except KeyboardInterrupt:
        # _drain_batch's finally already closed the suspended generator, so
        # the backend process was terminated and reaped deterministically.
        queue.cancel_all()
        print("已取消：正在停止...", file=sys.stderr)
        return EXIT_CANCELLED

    summary = queue.summary
    print(str(summary), file=sys.stderr)
    for task in queue.tasks:
        if task.state == "completed":
            print(f"[完成] {task.archive_path} -> {task.final_output_dir}")
        elif task.state == "failed":
            print(f"[失败] {task.archive_path}: {task.error}")
        else:
            print(f"[取消] {task.archive_path}")
    return EXIT_ALL_COMPLETED if summary.failed == 0 else EXIT_SOME_FAILED


def _drain_batch(queue: BatchQueue, args: argparse.Namespace) -> None:
    """Consume one full queue run, printing per-task progress in verbose mode."""
    run = queue.run()
    try:
        for event in run:
            if event.kind != "task_progress" or event.progress is None:
                continue
            if args.verbose and event.progress.kind == "progress" and event.progress.percent is not None:
                print(
                    f"Progress [{event.task.archive_path.name}]: {event.progress.percent}%",
                    file=sys.stderr,
                )
    finally:
        # On KeyboardInterrupt the generator is suspended inside the engine;
        # closing it triggers GeneratorExit so the process is reaped now.
        run.close()


def _resolve_password(args: argparse.Namespace) -> str | None:
    if getattr(args, "password_prompt", False):
        return getpass.getpass("Archive password: ")
    return getattr(args, "password", None)
