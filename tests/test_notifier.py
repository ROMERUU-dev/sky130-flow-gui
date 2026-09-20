"""Tests for desktop notifications."""

from __future__ import annotations

import unittest
from unittest import mock

from app.core.notifier import (
    URGENCY_CRITICAL,
    URGENCY_NORMAL,
    Notifier,
    describe_outcome,
    should_notify,
)


class DescribeOutcomeTest(unittest.TestCase):
    def test_success_is_normal_urgency(self) -> None:
        title, body, urgency = describe_outcome("Simulación", True, "12 señales")

        self.assertEqual(title, "Simulación: listo")
        self.assertEqual(body, "12 señales")
        self.assertEqual(urgency, URGENCY_NORMAL)

    def test_failure_is_critical(self) -> None:
        title, _body, urgency = describe_outcome("LVS", False, "no coincide")

        self.assertEqual(title, "LVS: falló")
        self.assertEqual(urgency, URGENCY_CRITICAL)

    def test_english_wording(self) -> None:
        title, _body, _urgency = describe_outcome("Extraction", True, spanish=False)

        self.assertEqual(title, "Extraction: finished")


class NotifierTest(unittest.TestCase):
    def test_an_empty_title_sends_nothing(self) -> None:
        notifier = Notifier()

        with mock.patch.object(notifier, "_notify_dbus") as dbus:
            self.assertFalse(notifier.notify(""))
            dbus.assert_not_called()

    def test_dbus_is_preferred(self) -> None:
        notifier = Notifier()

        with mock.patch.object(notifier, "_notify_dbus", return_value=True) as dbus, \
             mock.patch.object(notifier, "_notify_command") as command:
            self.assertTrue(notifier.notify("hola"))

        dbus.assert_called_once()
        command.assert_not_called()

    def test_the_command_is_used_when_dbus_fails(self) -> None:
        notifier = Notifier()

        with mock.patch.object(notifier, "_notify_dbus", return_value=False), \
             mock.patch.object(notifier, "_notify_command", return_value=True) as command:
            self.assertTrue(notifier.notify("hola", "cuerpo"))

        command.assert_called_once()

    def test_a_session_without_either_transport_is_not_an_error(self) -> None:
        notifier = Notifier()

        with mock.patch.object(notifier, "_dbus_interface", return_value=None), \
             mock.patch("app.core.notifier.shutil.which", return_value=None):
            self.assertFalse(notifier.notify("hola"))
            self.assertFalse(notifier.available)

    def test_available_is_true_when_only_notify_send_exists(self) -> None:
        notifier = Notifier()

        with mock.patch.object(notifier, "_dbus_interface", return_value=None), \
             mock.patch("app.core.notifier.shutil.which", return_value="/usr/bin/notify-send"):
            self.assertTrue(notifier.available)

    def test_a_broken_notify_send_does_not_raise(self) -> None:
        notifier = Notifier()

        with mock.patch.object(notifier, "_notify_dbus", return_value=False), \
             mock.patch("app.core.notifier.shutil.which", return_value="/usr/bin/notify-send"), \
             mock.patch("app.core.notifier.subprocess.run", side_effect=OSError("boom")):
            self.assertFalse(notifier.notify("hola"))

    def test_the_dbus_interface_is_resolved_once(self) -> None:
        notifier = Notifier()
        notifier._checked = True
        notifier._interface = None

        self.assertIsNone(notifier._dbus_interface())

    def test_urgency_reaches_notify_send(self) -> None:
        notifier = Notifier()
        captured = {}

        def fake_run(command, **kwargs):
            captured["command"] = command
            return mock.Mock(returncode=0)

        with mock.patch("app.core.notifier.shutil.which", return_value="/usr/bin/notify-send"), \
             mock.patch("app.core.notifier.subprocess.run", side_effect=fake_run):
            notifier._notify_command("t", "b", URGENCY_CRITICAL, 5000)

        self.assertIn("critical", captured["command"])


if __name__ == "__main__":
    unittest.main()


class ShouldNotifyTest(unittest.TestCase):
    """When a finished run is worth interrupting the user for."""

    def test_a_long_run_behind_the_window_notifies(self) -> None:
        self.assertTrue(should_notify(120.0, window_active=False))

    def test_a_run_you_are_watching_does_not(self) -> None:
        self.assertFalse(should_notify(120.0, window_active=True))

    def test_a_short_run_does_not(self) -> None:
        self.assertFalse(should_notify(5.0, window_active=False, minimum_seconds=20))

    def test_the_threshold_is_inclusive(self) -> None:
        self.assertTrue(should_notify(20.0, window_active=False, minimum_seconds=20))

    def test_a_zero_threshold_notifies_for_anything(self) -> None:
        self.assertTrue(should_notify(0.5, window_active=False, minimum_seconds=0))

    def test_disabled_never_notifies(self) -> None:
        self.assertFalse(should_notify(600.0, window_active=False, enabled=False))

    def test_an_unknown_duration_errs_towards_notifying(self) -> None:
        self.assertTrue(should_notify(None, window_active=False))

    def test_a_negative_threshold_is_treated_as_zero(self) -> None:
        self.assertTrue(should_notify(0.1, window_active=False, minimum_seconds=-5))
