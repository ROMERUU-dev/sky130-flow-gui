"""Tests for the persistent run history."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.core.run_history import (
    KIND_EXTRACTION,
    KIND_SIMULATION,
    STATUS_FAILED,
    STATUS_RUNNING,
    STATUS_SUCCESS,
    RunHistory,
    RunRecord,
)


class RunHistoryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.runs = Path(self.tmp.name) / "runs"
        self.history = RunHistory(self.runs)

    def test_a_started_run_is_persisted_immediately(self) -> None:
        """The record has to survive a crash between start and finish."""
        record = self.history.start(KIND_SIMULATION, label="inverter", project="/p")

        reloaded = RunHistory(self.runs).get(record.run_id)

        self.assertIsNotNone(reloaded)
        self.assertEqual(reloaded.status, STATUS_RUNNING)
        self.assertEqual(reloaded.label, "inverter")
        self.assertEqual(reloaded.project, "/p")

    def test_finishing_records_the_outcome_and_artifacts(self) -> None:
        record = self.history.start(KIND_SIMULATION, label="inverter")

        self.history.finish(record.run_id, 0, artifacts={"raw": "/r/out.raw"}, summary="12 señales")

        stored = RunHistory(self.runs).get(record.run_id)
        self.assertEqual(stored.status, STATUS_SUCCESS)
        self.assertEqual(stored.exit_code, 0)
        self.assertEqual(stored.artifacts["raw"], "/r/out.raw")
        self.assertEqual(stored.summary, "12 señales")
        self.assertIsNotNone(stored.duration_seconds)

    def test_a_nonzero_exit_is_recorded_as_failed(self) -> None:
        record = self.history.start(KIND_SIMULATION)

        self.history.finish(record.run_id, 3)

        self.assertEqual(self.history.get(record.run_id).status, STATUS_FAILED)
        self.assertFalse(self.history.get(record.run_id).succeeded)

    def test_records_come_back_newest_first(self) -> None:
        first = self.history.start(KIND_SIMULATION, label="uno")
        second = self.history.start(KIND_SIMULATION, label="dos")

        labels = [record.label for record in self.history.records()]

        self.assertEqual(labels[0], "dos")
        self.assertIn(first.label, labels)
        self.assertEqual(self.history.last().run_id, second.run_id)

    def test_records_can_be_filtered_by_kind(self) -> None:
        self.history.start(KIND_SIMULATION, label="sim")
        self.history.start(KIND_EXTRACTION, label="ext")

        self.assertEqual([r.label for r in self.history.records(kind=KIND_EXTRACTION)], ["ext"])
        self.assertEqual(self.history.last(kind=KIND_SIMULATION).label, "sim")

    def test_the_log_is_capped(self) -> None:
        history = RunHistory(self.runs, limit=5)
        for index in range(9):
            history.start(KIND_SIMULATION, label=f"run{index}")

        records = history.records()

        self.assertEqual(len(records), 5)
        self.assertEqual(records[0].label, "run8")

    def test_a_corrupt_file_does_not_raise(self) -> None:
        self.runs.mkdir(parents=True)
        (self.runs / "history.json").write_text("{not json", encoding="utf-8")

        self.assertEqual(self.history.records(), [])
        self.history.start(KIND_SIMULATION, label="after")
        self.assertEqual(len(self.history.records()), 1)

    def test_unknown_fields_from_a_future_version_are_ignored(self) -> None:
        self.runs.mkdir(parents=True)
        payload = {"schema_version": 99, "runs": [
            {"run_id": "a", "kind": "simulation", "started_at": 1.0, "label": "x", "brand_new": 5}
        ]}
        (self.runs / "history.json").write_text(json.dumps(payload), encoding="utf-8")

        records = self.history.records()

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].label, "x")

    def test_missing_history_reads_as_empty(self) -> None:
        self.assertEqual(self.history.records(), [])
        self.assertIsNone(self.history.last())
        self.assertIsNone(self.history.get("nope"))

    def test_finishing_an_unknown_run_is_a_noop(self) -> None:
        self.assertIsNone(self.history.finish("missing", 0))

    def test_clear_empties_the_log(self) -> None:
        self.history.start(KIND_SIMULATION)

        self.history.clear()

        self.assertEqual(self.history.records(), [])


class RunRecordTest(unittest.TestCase):
    BASE = 1_700_000_000.0

    def test_duration_formatting(self) -> None:
        record = RunRecord(started_at=self.BASE, finished_at=self.BASE + 4.25)
        self.assertEqual(record.describe_duration(), "4.2s")

        record = RunRecord(started_at=self.BASE, finished_at=self.BASE + 95.0)
        self.assertEqual(record.describe_duration(), "1m 35s")

        record = RunRecord(started_at=self.BASE, finished_at=self.BASE + 3725.0)
        self.assertEqual(record.describe_duration(), "1h 02m")

    def test_a_record_with_no_start_has_no_duration(self) -> None:
        """A default-constructed record must not report an epoch-long run."""
        self.assertIsNone(RunRecord(finished_at=self.BASE).duration_seconds)

    def test_a_running_record_has_no_duration(self) -> None:
        self.assertEqual(RunRecord(started_at=10.0).describe_duration(), "")
        self.assertIsNone(RunRecord(started_at=10.0).duration_seconds)

    def test_describe_carries_status_and_label(self) -> None:
        record = RunRecord(run_id="a", label="inverter", status=STATUS_SUCCESS,
                           started_at=1_700_000_000.0, finished_at=1_700_000_012.0)

        line = record.describe()

        self.assertIn("OK", line)
        self.assertIn("inverter", line)
        self.assertIn("12.0s", line)


if __name__ == "__main__":
    unittest.main()


class PerRunOutputTest(unittest.TestCase):
    """Each run needs its own files, or the history can only reopen the newest."""

    def _outputs(self, root: Path):
        from app.core.output_manager import OutputManager

        return OutputManager().resolve(str(root))

    def test_a_run_id_names_the_raw_and_log_files(self) -> None:
        from app.core.settings_manager import AppSettings
        from app.runners.ngspice_runner import NgspiceRunner

        with tempfile.TemporaryDirectory() as tmp:
            outputs = self._outputs(Path(tmp))
            runner = NgspiceRunner(AppSettings())

            _cmd, log_a, raw_a, _cwd = runner.run_spec("n.spice", outputs, run_id="aaa")
            _cmd, log_b, raw_b, _cwd = runner.run_spec("n.spice", outputs, run_id="bbb")

            self.assertNotEqual(raw_a, raw_b)
            self.assertNotEqual(log_a, log_b)
            self.assertTrue(raw_a.endswith("run_aaa.raw"))
            self.assertTrue(log_b.endswith("run_bbb.txt"))

    def test_without_a_run_id_the_legacy_names_are_kept(self) -> None:
        from app.core.settings_manager import AppSettings
        from app.runners.ngspice_runner import NgspiceRunner

        with tempfile.TemporaryDirectory() as tmp:
            outputs = self._outputs(Path(tmp))

            _cmd, log_path, raw_path, _cwd = NgspiceRunner(AppSettings()).run_spec("n.spice", outputs)

            self.assertTrue(raw_path.endswith("raw.raw"))
            self.assertTrue(log_path.endswith("log.txt"))
