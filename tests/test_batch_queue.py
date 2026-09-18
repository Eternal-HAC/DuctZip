"""Batch queue core tests: state-machine legality, ordering, failure
isolation, retry, cancellation (current/all), per-task Smart Output against
a shared output root, path-validation preservation, password redaction, and
structured batch logs. All tests are deterministic: the queue is driven
through scripted service/engine stand-ins, never a real 7-Zip backend."""

from __future__ import annotations

from pathlib import Path
import tempfile
import threading
import time
import unittest

from ductzip.archive import (
    ArchiveCancelled,
    ArchiveEntry,
    ArchiveError,
    ArchiveListing,
    CorruptedArchive,
    ExtractResult,
    ProgressEvent,
)
from ductzip.core import (
    CANCELLED,
    COMPLETED,
    FAILED,
    PLANNING,
    QUEUED,
    RUNNING,
    BatchQueue,
    ExtractionService,
    IllegalTaskTransition,
)

ROOT = Path(tempfile.gettempdir())


def _result(output_dir: Path) -> ExtractResult:
    return ExtractResult(
        archive_path=Path("archive.zip"),
        output_dir=output_dir,
        sevenzip_path=Path("7z.exe"),
        stdout="",
        stderr="",
    )


def ok_script(output_dir: Path | None = None):
    def factory(**kwargs):
        yield ProgressEvent(kind="started", percent=0)
        yield ProgressEvent(kind="progress", percent=42)
        yield ProgressEvent(kind="completed", percent=100, result=_result(output_dir or Path("out")))

    return factory


def fail_script(exc: Exception, after_start: bool = True):
    def factory(**kwargs):
        if after_start:
            yield ProgressEvent(kind="started", percent=0)
        raise exc
        yield  # pragma: no cover - makes this a generator

    return factory


def failed_output_script(message: str, exc: Exception):
    """Yield a raw-backend-output ``failed`` event, then raise."""

    def factory(**kwargs):
        yield ProgressEvent(kind="started", percent=0)
        yield ProgressEvent(kind="failed", message=message)
        raise exc
        yield  # pragma: no cover - makes this a generator

    return factory


def block_until_cancel_script():
    """Emit progress until the cancel event fires, like a silent backend."""

    def factory(**kwargs):
        cancel_event = kwargs["cancel_event"]
        yield ProgressEvent(kind="started", percent=0)
        while not cancel_event.wait(0.01):
            yield ProgressEvent(kind="progress", percent=1)
        yield ProgressEvent(kind="cancelled", message="cancelled")
        raise ArchiveCancelled()
        yield  # pragma: no cover - makes this a generator

    return factory


class ScriptedService:
    """Deterministic stand-in for ExtractionService.

    Each archive name has a FIFO of generator factories replayed by
    ``extract_with_progress``. ``calls`` records invocation/start/end
    markers so tests can prove sequential, non-overlapping execution.
    """

    def __init__(self):
        self.scripts: dict[str, list] = {}
        self.calls: list[str] = []

    def script(self, name: str, factory) -> None:
        self.scripts.setdefault(name, []).append(factory)

    def extract_with_progress(self, archive_path, requested_output_dir, **kwargs):
        name = Path(archive_path).name
        scripts = self.scripts.get(name)
        factory = scripts.pop(0) if scripts else ok_script()
        service = self

        def drive():
            service.calls.append(f"start:{name}")
            try:
                yield from factory(**kwargs)
            finally:
                service.calls.append(f"end:{name}")

        self.calls.append(f"invoked:{name}")
        return drive()


def wait_until(predicate, timeout: float = 10.0, interval: float = 0.01) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError("condition not met before timeout")
        time.sleep(interval)


def run_in_thread(queue: BatchQueue) -> tuple[threading.Thread, list]:
    events: list = []
    done = threading.Event()

    def consume():
        for event in queue.run():
            events.append(event)
        done.set()

    thread = threading.Thread(target=consume, daemon=True)
    thread.start()
    return thread, events, done


class TransitionLegalityTests(unittest.TestCase):
    def test_completed_is_terminal_but_removable(self):
        queue = BatchQueue(ScriptedService())
        task = queue.add("a.zip", ROOT)
        list(queue.run())
        self.assertEqual(task.state, COMPLETED)
        with self.assertRaises(IllegalTaskTransition):
            queue.retry(task.task_id)
        queue.remove(task.task_id)  # removal of a finished task is legal
        self.assertEqual(queue.tasks, ())

    def test_retry_legal_only_from_failed_or_cancelled(self):
        queue = BatchQueue(ScriptedService())
        queued = queue.add("a.zip", ROOT)
        with self.assertRaises(IllegalTaskTransition):
            queue.retry(queued.task_id)

        service = ScriptedService()
        service.script("a.zip", fail_script(CorruptedArchive()))
        queue = BatchQueue(service)
        failed = queue.add("a.zip", ROOT)
        list(queue.run())
        self.assertEqual(failed.state, FAILED)
        self.assertTrue(queue.can_retry(failed.task_id))
        queue.retry(failed.task_id)
        self.assertEqual(failed.state, QUEUED)
        self.assertIsNone(failed.error)

    def test_illegal_transition_names_both_states(self):
        queue = BatchQueue(ScriptedService())
        task = queue.add("a.zip", ROOT)
        with self.assertRaisesRegex(IllegalTaskTransition, "queued.*completed"):
            queue._transition(task, COMPLETED)

    def test_remove_illegal_while_running(self):
        service = ScriptedService()
        service.script("a.zip", block_until_cancel_script())
        queue = BatchQueue(service)
        task = queue.add("a.zip", ROOT)
        thread, _, done = run_in_thread(queue)
        wait_until(lambda: task.state == RUNNING)

        with self.assertRaises(IllegalTaskTransition):
            queue.remove(task.task_id)

        self.assertTrue(queue.cancel_current())
        thread.join(timeout=10)
        self.assertTrue(done.is_set())
        self.assertEqual(task.state, CANCELLED)


class OrderingAndIsolationTests(unittest.TestCase):
    def test_sequential_in_enqueue_order_without_overlap(self):
        service = ScriptedService()
        queue = BatchQueue(service)
        queue.add("a.zip", ROOT)
        queue.add("b.zip", ROOT)
        queue.add("c.zip", ROOT)
        list(queue.run())

        self.assertEqual(
            service.calls,
            [
                "invoked:a.zip", "start:a.zip", "end:a.zip",
                "invoked:b.zip", "start:b.zip", "end:b.zip",
                "invoked:c.zip", "start:c.zip", "end:c.zip",
            ],
        )

    def test_one_task_failure_does_not_stop_later_tasks(self):
        service = ScriptedService()
        service.script("b.zip", fail_script(CorruptedArchive()))
        queue = BatchQueue(service)
        ok_a = queue.add("a.zip", ROOT)
        bad = queue.add("b.zip", ROOT)
        ok_c = queue.add("c.zip", ROOT)
        list(queue.run())

        self.assertEqual(ok_a.state, COMPLETED)
        self.assertEqual(bad.state, FAILED)
        self.assertEqual(ok_c.state, COMPLETED)
        self.assertIn("损坏", bad.error)
        self.assertIn("invoked:c.zip", service.calls)

    def test_planning_failure_marks_failed_and_continues(self):
        service = ScriptedService()
        service.script("b.zip", fail_script(ArchiveError("listing blew up"), after_start=False))
        queue = BatchQueue(service)
        queue.add("a.zip", ROOT)
        bad = queue.add("b.zip", ROOT)
        queue.add("c.zip", ROOT)
        list(queue.run())

        self.assertEqual(bad.state, FAILED)
        self.assertEqual(bad.error, "listing blew up")
        self.assertEqual(len([c for c in service.calls if c.startswith("invoked")]), 3)

    def test_unexpected_exception_is_isolated_and_labeled(self):
        service = ScriptedService()
        service.script("b.zip", fail_script(RuntimeError("boom")))
        queue = BatchQueue(service)
        queue.add("a.zip", ROOT)
        bad = queue.add("b.zip", ROOT)
        queue.add("c.zip", ROOT)
        list(queue.run())

        self.assertEqual(bad.state, FAILED)
        self.assertIn("Unexpected error: RuntimeError", bad.error)
        self.assertEqual(queue.summary.completed, 2)


class RetryTests(unittest.TestCase):
    def test_retry_reruns_only_requested_task(self):
        service = ScriptedService()
        service.script("a.zip", fail_script(CorruptedArchive()))
        service.script("a.zip", ok_script())
        queue = BatchQueue(service)
        task = queue.add("a.zip", ROOT)
        queue.add("b.zip", ROOT)
        list(queue.run())
        self.assertEqual(task.state, FAILED)
        self.assertEqual(task.attempts, 1)

        queue.retry(task.task_id)
        list(queue.run())

        self.assertEqual(task.state, COMPLETED)
        self.assertEqual(task.attempts, 2)
        self.assertIsNone(task.error)
        self.assertEqual(queue.summary.completed, 2)
        self.assertEqual(queue.summary.failed, 0)

    def test_cancelled_task_can_be_retried(self):
        service = ScriptedService()
        service.script("a.zip", block_until_cancel_script())
        service.script("a.zip", ok_script())
        queue = BatchQueue(service)
        task = queue.add("a.zip", ROOT)
        thread, _, done = run_in_thread(queue)
        wait_until(lambda: task.state == RUNNING)
        queue.cancel_current()
        thread.join(timeout=10)
        self.assertTrue(done.is_set())
        self.assertEqual(task.state, CANCELLED)

        queue.retry(task.task_id)
        list(queue.run())
        self.assertEqual(task.state, COMPLETED)
        self.assertEqual(task.attempts, 2)


class CancellationTests(unittest.TestCase):
    def test_cancel_current_leaves_queued_tasks_untouched(self):
        service = ScriptedService()
        service.script("a.zip", block_until_cancel_script())
        queue = BatchQueue(service)
        first = queue.add("a.zip", ROOT)
        second = queue.add("b.zip", ROOT)
        thread, _, done = run_in_thread(queue)
        wait_until(lambda: first.state == RUNNING)

        self.assertTrue(queue.cancel_current())
        thread.join(timeout=10)
        self.assertTrue(done.is_set())

        self.assertEqual(first.state, CANCELLED)
        self.assertEqual(second.state, COMPLETED)

    def test_cancel_all_cancels_in_flight_and_never_starts_queued(self):
        service = ScriptedService()
        service.script("a.zip", block_until_cancel_script())
        queue = BatchQueue(service)
        first = queue.add("a.zip", ROOT)
        second = queue.add("b.zip", ROOT)
        third = queue.add("c.zip", ROOT)
        thread, _, done = run_in_thread(queue)
        wait_until(lambda: first.state == RUNNING)

        queue.cancel_all()
        thread.join(timeout=10)
        self.assertTrue(done.is_set())

        self.assertEqual(first.state, CANCELLED)
        self.assertEqual(second.state, CANCELLED)
        self.assertEqual(third.state, CANCELLED)
        self.assertNotIn("invoked:b.zip", service.calls)
        self.assertNotIn("invoked:c.zip", service.calls)
        self.assertEqual(queue.summary.cancelled, 3)

    def test_cancel_all_before_run_never_invokes_service(self):
        queue = BatchQueue(ScriptedService())
        queue.add("a.zip", ROOT)
        queue.add("b.zip", ROOT)
        queue.cancel_all()  # transitions queued tasks immediately, outside any run
        self.assertEqual(queue.summary.cancelled, 2)

        events = list(queue.run())
        # Nothing left to run; the immediate transitions are already in the log.
        self.assertEqual([event.kind for event in events], ["batch_started", "batch_finished"])
        log_states = [event.state for event in queue.log if event.kind == "task_state"]
        self.assertEqual(log_states, [CANCELLED, CANCELLED])
        self.assertEqual(queue.summary.cancelled, 2)

    def test_external_cancel_event_cancels_everything_pending(self):
        service = ScriptedService()
        queue = BatchQueue(service)
        queue.add("a.zip", ROOT)
        queue.add("b.zip", ROOT)
        cancel_event = threading.Event()
        cancel_event.set()
        list(queue.run(cancel_event=cancel_event))
        self.assertEqual(queue.summary.cancelled, 2)
        self.assertEqual(service.calls, [])

    def test_queued_task_removed_mid_run_is_skipped(self):
        service = ScriptedService()
        service.script("a.zip", block_until_cancel_script())
        queue = BatchQueue(service)
        running = queue.add("a.zip", ROOT)
        victim = queue.add("b.zip", ROOT)
        thread, _, done = run_in_thread(queue)
        wait_until(lambda: running.state == RUNNING)

        queue.remove(victim.task_id)  # legal: victim is still queued
        queue.cancel_current()
        thread.join(timeout=10)
        self.assertTrue(done.is_set())

        self.assertNotIn(victim, queue.tasks)
        self.assertNotIn("invoked:b.zip", service.calls)
        self.assertEqual(running.state, CANCELLED)


class _SmartEngine:
    """Engine stand-in returning canned listings and recording real calls."""

    def __init__(self, entries_by_stem: dict[str, tuple[ArchiveEntry, ...]]):
        self.entries_by_stem = entries_by_stem
        self.list_calls: list[str] = []
        self.extract_calls: list[tuple[str, Path]] = []

    def list(self, archive_path, password=None, cancel_event=None):
        stem = Path(archive_path).stem
        self.list_calls.append(stem)
        return ArchiveListing(
            archive_path=Path(archive_path).resolve(),
            sevenzip_path=Path("7z.exe"),
            entries=self.entries_by_stem[stem],
            stdout="",
            stderr="",
        )

    def extract_with_progress(self, archive_path, output_dir, password=None, cancel_event=None, overwrite_policy="skip"):
        self.extract_calls.append((Path(archive_path).name, Path(output_dir)))
        yield ProgressEvent(kind="started", percent=0)
        yield ProgressEvent(
            kind="completed",
            percent=100,
            result=ExtractResult(
                archive_path=Path(archive_path).resolve(),
                output_dir=Path(output_dir),
                sevenzip_path=Path("7z.exe"),
                stdout="",
                stderr="",
            ),
        )


def _file(path: str) -> ArchiveEntry:
    return ArchiveEntry(path, 1, None, None, False)


def _dir(path: str) -> ArchiveEntry:
    return ArchiveEntry(path, None, None, "D", True)


class SmartOutputPerTaskTests(unittest.TestCase):
    def test_shared_queue_root_with_per_task_smart_output(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            engine = _SmartEngine(
                {
                    # Multi top-level files -> root/multi
                    "multi": (_file("m1.txt"), _file("m2.txt")),
                    # Single top-level dir, name != requested -> root itself
                    "docs": (_dir("docs"), _file("docs/x.txt")),
                    # Single top-level dir with same name as requested -> parent
                    "same": (_dir("same"), _file("same/y.txt")),
                }
            )
            queue = BatchQueue(ExtractionService(engine=engine))
            queue.add(root / "multi.zip", root)
            queue.add(root / "docs.zip", root)
            queue.add(root / "same.zip", root / "same")
            list(queue.run())

            outputs = {name: out for name, out in engine.extract_calls}
            self.assertEqual(outputs["multi.zip"], root / "multi")
            self.assertEqual(outputs["docs.zip"], root)
            self.assertEqual(outputs["same.zip"], root)
            # Each archive is planned once and executed once through the service.
            self.assertEqual(sorted(engine.list_calls), ["docs", "multi", "same"])
            self.assertEqual(len(engine.extract_calls), 3)

    def test_queue_never_accepts_callers_listing(self):
        # The queue API has no listing parameter at all; each task is exactly
        # one service operation and the engine remains the sole validator.
        import inspect

        from ductzip.core import BatchQueue as _BatchQueue

        signature = inspect.signature(_BatchQueue.add)
        self.assertNotIn("listing", signature.parameters)
        self.assertNotIn("listing", inspect.signature(_BatchQueue.run).parameters)


class RedactionAndLogTests(unittest.TestCase):
    def test_password_redacted_from_error_and_failed_progress(self):
        service = ScriptedService()
        raw = "Command line: 7z x -ps3cret-pw archive.zip"
        service.script("a.zip", failed_output_script(raw, ArchiveError(f"解压失败：{raw}")))
        queue = BatchQueue(service)
        task = queue.add("a.zip", ROOT, password="s3cret-pw")
        events = list(queue.run())

        self.assertEqual(task.state, FAILED)
        self.assertNotIn("s3cret-pw", task.error)
        self.assertIn("***", task.error)
        failed_progress = [
            event.progress
            for event in events
            if event.kind == "task_progress" and event.progress.kind == "failed"
        ]
        self.assertEqual(len(failed_progress), 1)
        self.assertNotIn("s3cret-pw", failed_progress[0].message)
        for event in queue.log:
            self.assertNotIn("s3cret-pw", event.message)

    def test_structured_log_records_states_but_not_progress(self):
        service = ScriptedService()
        queue = BatchQueue(service)
        queue.add("a.zip", ROOT)
        queue.add("b.zip", ROOT)
        list(queue.run())

        kinds = [event.kind for event in queue.log]
        self.assertEqual(kinds[0], "batch_started")
        self.assertEqual(kinds[-1], "batch_finished")
        self.assertNotIn("task_progress", kinds)
        state_events = [event for event in queue.log if event.kind == "task_state"]
        states = [event.state for event in state_events]
        self.assertEqual(states.count(PLANNING), 2)
        self.assertEqual(states.count(RUNNING), 2)
        self.assertEqual(states.count(COMPLETED), 2)

    def test_final_output_visible_on_completed_task(self):
        service = ScriptedService()
        queue = BatchQueue(service)
        task = queue.add("a.zip", ROOT)
        list(queue.run())
        self.assertEqual(task.final_output_dir, Path("out"))


if __name__ == "__main__":
    unittest.main()
