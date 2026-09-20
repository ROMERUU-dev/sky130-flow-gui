"""Tests for the project status summary."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.core.project_status import (
    STATE_FAILED,
    STATE_NEVER_RUN,
    STATE_OK,
    STATE_STALE,
    build_status,
    describe_age,
)
from app.core.run_history import (
    KIND_ANTENNA,
    KIND_EXTRACTION,
    KIND_LVS,
    KIND_SIMULATION,
    RunHistory,
)


class DescribeAgeTest(unittest.TestCase):
    def test_spanish_wording(self) -> None:
        self.assertEqual(describe_age(30), "hace un momento")
        self.assertEqual(describe_age(60 * 10), "hace 10 min")
        self.assertEqual(describe_age(3600 * 5), "hace 5 h")
        self.assertEqual(describe_age(3600 * 24), "ayer")
        self.assertEqual(describe_age(3600 * 24 * 3), "hace 3 días")

    def test_english_wording(self) -> None:
        self.assertEqual(describe_age(30, spanish=False), "just now")
        self.assertEqual(describe_age(3600 * 24, spanish=False), "yesterday")


class BuildStatusTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.runs = Path(self.tmp.name) / "runs"
        self.history = RunHistory(self.runs)
        self.now = 1_700_000_000.0

    def _record(self, kind: str, started: float, exit_code: int = 0, summary: str = "") -> None:
        record = self.history.start(kind, label=kind)
        stored = self.history._load()
        for item in stored:
            if item.run_id == record.run_id:
                item.started_at = started
                item.finished_at = started + 1.0
                item.exit_code = exit_code
                item.status = "success" if exit_code == 0 else "failed"
                item.summary = summary
        self.history._write(stored)

    def test_a_fresh_project_has_never_run_anything(self) -> None:
        status = build_status(self.runs, now=self.now)

        self.assertEqual(len(status.stages), 4)
        self.assertTrue(all(stage.state == STATE_NEVER_RUN for stage in status.stages))
        self.assertFalse(status.has_any_run)

    def test_a_successful_run_is_reported_with_its_age(self) -> None:
        # finished_at is started_at + 1, so this lands exactly one hour back.
        self._record(KIND_SIMULATION, self.now - 3601, summary="4 señales")

        stage = build_status(self.runs, now=self.now).stage(KIND_SIMULATION)

        self.assertEqual(stage.state, STATE_OK)
        self.assertEqual(stage.detail, "4 señales")
        self.assertEqual(stage.describe_age(), "hace 1 h")

    def test_age_wording_sits_on_the_right_side_of_the_hour(self) -> None:
        self._record(KIND_SIMULATION, self.now - 3000)

        self.assertEqual(build_status(self.runs, now=self.now).stage(KIND_SIMULATION).describe_age(), "hace 49 min")

    def test_a_failed_run_is_reported_as_failed(self) -> None:
        self._record(KIND_LVS, self.now - 60, exit_code=1, summary="LVS falló")

        status = build_status(self.runs, now=self.now)

        self.assertEqual(status.stage(KIND_LVS).state, STATE_FAILED)
        self.assertEqual([s.kind for s in status.blocking_stages()], [KIND_LVS])

    def test_a_pass_is_stale_when_an_upstream_stage_ran_afterwards(self) -> None:
        """Passing LVS means nothing if the layout was re-extracted since."""
        self._record(KIND_LVS, self.now - 7200)
        self._record(KIND_EXTRACTION, self.now - 600)

        stage = build_status(self.runs, now=self.now).stage(KIND_LVS)

        self.assertEqual(stage.state, STATE_STALE)
        self.assertEqual(stage.detail, "Extracción corrió después")
        self.assertEqual(stage.stale_after, (KIND_EXTRACTION,))

    def test_several_upstream_stages_agree_in_number(self) -> None:
        from app.core.project_status import describe_stale

        self.assertEqual(describe_stale((KIND_EXTRACTION,)), "Extracción corrió después")
        self.assertEqual(
            describe_stale((KIND_EXTRACTION, KIND_SIMULATION)),
            "Extracción, Simulación corrieron después",
        )
        self.assertEqual(describe_stale((KIND_EXTRACTION,), spanish=False), "Extraction ran afterwards")
        self.assertEqual(describe_stale(()), "")

    def test_a_pass_stays_valid_when_nothing_upstream_moved(self) -> None:
        self._record(KIND_EXTRACTION, self.now - 7200)
        self._record(KIND_LVS, self.now - 600)

        self.assertEqual(build_status(self.runs, now=self.now).stage(KIND_LVS).state, STATE_OK)

    def test_a_downstream_run_does_not_make_an_earlier_stage_stale(self) -> None:
        self._record(KIND_EXTRACTION, self.now - 600)
        self._record(KIND_ANTENNA, self.now - 60)

        self.assertEqual(build_status(self.runs, now=self.now).stage(KIND_EXTRACTION).state, STATE_OK)

    def test_only_the_latest_run_of_a_stage_counts(self) -> None:
        self._record(KIND_SIMULATION, self.now - 7200, exit_code=1)
        self._record(KIND_SIMULATION, self.now - 60, exit_code=0)

        self.assertEqual(build_status(self.runs, now=self.now).stage(KIND_SIMULATION).state, STATE_OK)

    def test_stages_come_back_in_flow_order(self) -> None:
        kinds = [stage.kind for stage in build_status(self.runs, now=self.now).stages]

        self.assertEqual(kinds, [KIND_EXTRACTION, KIND_SIMULATION, KIND_LVS, KIND_ANTENNA])

    def test_titles_are_translated(self) -> None:
        status = build_status(self.runs, now=self.now)

        self.assertEqual(status.stage(KIND_EXTRACTION).title(), "Extracción")
        self.assertEqual(status.stage(KIND_EXTRACTION).title(spanish=False), "Extraction")


if __name__ == "__main__":
    unittest.main()
