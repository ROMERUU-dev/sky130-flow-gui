"""Tests for container runtime detection."""

from __future__ import annotations

import unittest
from unittest import mock

from app.core.container_tools import (
    STATUS_DAEMON_DOWN,
    STATUS_MISSING,
    STATUS_PERMISSION,
    STATUS_READY,
    ContainerRuntime,
    detect_runtime,
    image_present,
    image_size_bytes,
)


def _which(available: dict[str, str]):
    return lambda name: available.get(name)


def _runner(responses: dict[tuple, tuple]):
    """Map a command tail to (returncode, stdout, stderr)."""
    def run(command):
        key = tuple(command[1:])
        return responses.get(key, (1, "", "unexpected command"))
    return run


class DetectRuntimeTest(unittest.TestCase):
    def test_no_engine_at_all(self) -> None:
        with mock.patch("app.core.container_tools.shutil.which", _which({})), \
             mock.patch("app.core.container_tools.user_in_docker_group", return_value=(False, False)):
            runtime = detect_runtime()

        self.assertEqual(runtime.status, STATUS_MISSING)
        self.assertFalse(runtime.ready)

    def test_a_working_daemon_is_ready(self) -> None:
        responses = {
            ("--version",): (0, "Docker version 29.1.3\n", ""),
            ("info", "--format", "{{.ServerVersion}}"): (0, "29.1.3\n", ""),
        }
        with mock.patch("app.core.container_tools.shutil.which", _which({"docker": "/usr/bin/docker"})), \
             mock.patch("app.core.container_tools._run", _runner(responses)), \
             mock.patch("app.core.container_tools.user_in_docker_group", return_value=(True, True)):
            runtime = detect_runtime()

        self.assertEqual(runtime.status, STATUS_READY)
        self.assertTrue(runtime.ready)
        self.assertEqual(runtime.engine, "docker")

    def test_permission_denied_after_install_asks_for_a_relogin(self) -> None:
        """The docker group only applies to sessions started after it is granted."""
        responses = {
            ("--version",): (0, "Docker version 29.1.3\n", ""),
            ("info", "--format", "{{.ServerVersion}}"):
                (1, "", "permission denied while trying to connect to the Docker daemon socket"),
        }
        with mock.patch("app.core.container_tools.shutil.which", _which({"docker": "/usr/bin/docker"})), \
             mock.patch("app.core.container_tools._run", _runner(responses)), \
             mock.patch("app.core.container_tools.user_in_docker_group", return_value=(True, True)):
            runtime = detect_runtime()

        self.assertEqual(runtime.status, STATUS_PERMISSION)
        self.assertTrue(runtime.needs_relogin)
        self.assertIn("sesión", runtime.message)

    def test_permission_denied_without_group_membership(self) -> None:
        responses = {
            ("--version",): (0, "Docker version 29.1.3\n", ""),
            ("info", "--format", "{{.ServerVersion}}"): (1, "", "permission denied"),
        }
        with mock.patch("app.core.container_tools.shutil.which", _which({"docker": "/usr/bin/docker"})), \
             mock.patch("app.core.container_tools._run", _runner(responses)), \
             mock.patch("app.core.container_tools.user_in_docker_group", return_value=(True, False)):
            runtime = detect_runtime()

        self.assertEqual(runtime.status, STATUS_PERMISSION)
        self.assertFalse(runtime.needs_relogin)

    def test_a_stopped_daemon_is_distinguished_from_a_permission_problem(self) -> None:
        responses = {
            ("--version",): (0, "Docker version 29.1.3\n", ""),
            ("info", "--format", "{{.ServerVersion}}"):
                (1, "", "Cannot connect to the Docker daemon. Is the docker daemon running?"),
        }
        with mock.patch("app.core.container_tools.shutil.which", _which({"docker": "/usr/bin/docker"})), \
             mock.patch("app.core.container_tools._run", _runner(responses)), \
             mock.patch("app.core.container_tools.user_in_docker_group", return_value=(True, True)):
            runtime = detect_runtime()

        self.assertEqual(runtime.status, STATUS_DAEMON_DOWN)
        self.assertIn("systemctl", runtime.message)

    def test_podman_is_used_when_docker_is_absent(self) -> None:
        responses = {
            ("--version",): (0, "podman version 5.7.0\n", ""),
            ("info", "--format", "{{.ServerVersion}}"): (0, "5.7.0\n", ""),
        }
        with mock.patch("app.core.container_tools.shutil.which", _which({"podman": "/usr/bin/podman"})), \
             mock.patch("app.core.container_tools._run", _runner(responses)), \
             mock.patch("app.core.container_tools.user_in_docker_group", return_value=(False, False)):
            runtime = detect_runtime()

        self.assertEqual(runtime.engine, "podman")
        self.assertTrue(runtime.ready)


class ImageQueryTest(unittest.TestCase):
    READY = ContainerRuntime(status=STATUS_READY, engine="docker", executable="/usr/bin/docker")

    def test_a_present_image_is_reported(self) -> None:
        with mock.patch("app.core.container_tools._run", return_value=(0, "", "")):
            self.assertTrue(image_present("ghcr.io/x/y:1", self.READY))

    def test_an_absent_image_is_reported(self) -> None:
        with mock.patch("app.core.container_tools._run", return_value=(1, "", "No such image")):
            self.assertFalse(image_present("ghcr.io/x/y:1", self.READY))

    def test_nothing_is_queried_without_a_ready_runtime(self) -> None:
        down = ContainerRuntime(status=STATUS_MISSING)

        self.assertFalse(image_present("ghcr.io/x/y:1", down))
        self.assertEqual(image_size_bytes("ghcr.io/x/y:1", down), 0)

    def test_image_size_is_parsed(self) -> None:
        with mock.patch("app.core.container_tools._run", return_value=(0, "4012345678\n", "")):
            self.assertEqual(image_size_bytes("ghcr.io/x/y:1", self.READY), 4012345678)

    def test_unparseable_size_is_zero(self) -> None:
        with mock.patch("app.core.container_tools._run", return_value=(0, "not a number\n", "")):
            self.assertEqual(image_size_bytes("ghcr.io/x/y:1", self.READY), 0)


class DigitalFlowManifestTest(unittest.TestCase):
    def test_the_image_carries_the_whole_digital_toolchain(self) -> None:
        from app.core.dependency_manifest import DependencyManifest

        channel = DependencyManifest().channel()

        self.assertTrue(channel.digital_flow_enabled)
        self.assertIn("librelane", channel.digital_flow_image)
        self.assertIn("openroad", channel.digital_flow_includes)
        self.assertIn("yosys", channel.digital_flow_includes)

    def test_docker_install_needs_privileges_and_the_pull_does_not(self) -> None:
        from app.core.setup_manager import SetupManager

        manager = SetupManager()

        self.assertEqual(manager.docker_install_command()[0], "pkexec")
        self.assertNotIn("pkexec", manager.digital_flow_image_command())
        self.assertTrue(manager.docker_install_script().is_file())
        self.assertTrue(manager.digital_flow_image_script().is_file())


if __name__ == "__main__":
    unittest.main()


class DockerInstallScriptTest(unittest.TestCase):
    """The script has to find the desktop user under pkexec, not just sudo."""

    SCRIPT = "scripts/install_docker_ubuntu.sh"

    def _resolve_user(self, env: dict[str, str]) -> str:
        import pathlib
        import re
        import subprocess

        source = pathlib.Path(self.SCRIPT).read_text(encoding="utf-8")
        function = re.search(r"^resolve_target_user\(\) \{.*?^\}", source, re.S | re.M)
        self.assertIsNotNone(function, "resolve_target_user() is missing from the script")
        script = function.group(0) + "\nresolve_target_user\n"
        result = subprocess.run(
            ["bash", "-c", script], capture_output=True, text=True, env=env, check=False
        )
        return result.stdout.strip()

    def test_pkexec_uid_identifies_the_desktop_user(self) -> None:
        """pkexec leaves SUDO_USER unset and sets USER to root."""
        import os

        env = {"PATH": "/usr/bin:/bin", "PKEXEC_UID": str(os.getuid()), "USER": "root"}

        import pwd

        self.assertEqual(self._resolve_user(env), pwd.getpwuid(os.getuid()).pw_name)

    def test_sudo_user_is_honoured(self) -> None:
        env = {"PATH": "/usr/bin:/bin", "SUDO_USER": "someone", "USER": "root"}

        self.assertEqual(self._resolve_user(env), "someone")

    def test_an_explicit_override_is_honoured(self) -> None:
        env = {"PATH": "/usr/bin:/bin", "SKY130_TARGET_USER": "override", "USER": "root"}

        self.assertEqual(self._resolve_user(env), "override")

    def test_pkexec_wins_over_sudo(self) -> None:
        import os
        import pwd

        env = {
            "PATH": "/usr/bin:/bin",
            "PKEXEC_UID": str(os.getuid()),
            "SUDO_USER": "wrong",
            "USER": "root",
        }

        self.assertEqual(self._resolve_user(env), pwd.getpwuid(os.getuid()).pw_name)
