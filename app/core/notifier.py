"""Desktop notifications for runs that finish while you are elsewhere.

A long extraction or a corner sweep means watching a window for minutes.
Notifications are sent over the freedesktop D-Bus interface, which is what the
desktop shell actually listens to; `notify-send` is a fallback for sessions
where the Qt D-Bus bindings are unavailable.
"""

from __future__ import annotations

import shutil
import subprocess

NOTIFY_SERVICE = "org.freedesktop.Notifications"
NOTIFY_PATH = "/org/freedesktop/Notifications"

URGENCY_LOW = 0
URGENCY_NORMAL = 1
URGENCY_CRITICAL = 2

DEFAULT_TIMEOUT_MS = 8000


class Notifier:
    """Send a desktop notification, or quietly do nothing."""

    def __init__(self, app_name: str = "SKY130 Flow", desktop_entry: str = "sky130-flow-gui") -> None:
        self.app_name = app_name
        self.desktop_entry = desktop_entry
        self._interface = None
        self._checked = False

    # ------------------------------------------------------------ transport

    def _dbus_interface(self):
        """Resolve the session-bus interface once, or give up on it."""
        if self._checked:
            return self._interface
        self._checked = True
        try:
            from PySide6.QtDBus import QDBusConnection, QDBusInterface

            connection = QDBusConnection.sessionBus()
            if not connection.isConnected():
                return None
            interface = QDBusInterface(NOTIFY_SERVICE, NOTIFY_PATH, NOTIFY_SERVICE, connection)
            if not interface.isValid():
                return None
            self._interface = interface
        except (ImportError, RuntimeError):
            self._interface = None
        return self._interface

    @property
    def available(self) -> bool:
        return self._dbus_interface() is not None or bool(shutil.which("notify-send"))

    # -------------------------------------------------------------- sending

    def notify(
        self,
        title: str,
        body: str = "",
        urgency: int = URGENCY_NORMAL,
        timeout_ms: int = DEFAULT_TIMEOUT_MS,
    ) -> bool:
        """Show a notification. Returns whether one was actually sent."""
        if not title:
            return False
        if self._notify_dbus(title, body, urgency, timeout_ms):
            return True
        return self._notify_command(title, body, urgency, timeout_ms)

    def _notify_dbus(self, title: str, body: str, urgency: int, timeout_ms: int) -> bool:
        interface = self._dbus_interface()
        if interface is None:
            return False
        try:
            from PySide6.QtCore import QVariant

            hints = {
                "urgency": QVariant(urgency),
                # Lets the shell attribute the notification to the app.
                "desktop-entry": QVariant(self.desktop_entry),
            }
            reply = interface.call(
                "Notify", self.app_name, 0, self.desktop_entry, title, body, [], hints, timeout_ms
            )
        except (RuntimeError, TypeError, ImportError):
            return False
        try:
            return reply.errorName() == ""
        except (AttributeError, RuntimeError):
            return True

    def _notify_command(self, title: str, body: str, urgency: int, timeout_ms: int) -> bool:
        executable = shutil.which("notify-send")
        if not executable:
            return False
        names = {URGENCY_LOW: "low", URGENCY_NORMAL: "normal", URGENCY_CRITICAL: "critical"}
        command = [
            executable,
            "--app-name", self.app_name,
            "--urgency", names.get(urgency, "normal"),
            "--expire-time", str(timeout_ms),
            "--icon", self.desktop_entry,
            title,
        ]
        if body:
            command.append(body)
        try:
            return subprocess.run(command, check=False, timeout=5).returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False


def describe_outcome(stage: str, succeeded: bool, detail: str = "", spanish: bool = True) -> tuple[str, str, int]:
    """Build the title, body and urgency for a finished run."""
    if succeeded:
        title = f"{stage}: {'listo' if spanish else 'finished'}"
        urgency = URGENCY_NORMAL
    else:
        title = f"{stage}: {'falló' if spanish else 'failed'}"
        urgency = URGENCY_CRITICAL
    return (title, detail, urgency)


def should_notify(
    duration_seconds: float | None,
    window_active: bool,
    enabled: bool = True,
    minimum_seconds: int = 20,
) -> bool:
    """Decide whether a finished run is worth interrupting the user for.

    A notification for a two-second run is noise, and one for a run being
    watched is worse, so both are skipped.
    """
    if not enabled or window_active:
        return False
    if duration_seconds is None:
        return True
    return duration_seconds >= max(0, minimum_seconds)
