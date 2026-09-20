"""Detect and describe the container runtime used for the OpenLane flow.

LibreLane (the maintained successor to OpenLane 2) ships its whole toolchain —
OpenROAD, Yosys, Magic, KLayout, netgen — inside one image, so the digital
flow needs a working container runtime rather than another pile of system
packages.
"""

from __future__ import annotations

import grp
import os
import pwd
import shutil
import subprocess
from dataclasses import dataclass, field

PROBE_TIMEOUT_SECONDS = 12

STATUS_MISSING = "missing"
STATUS_DAEMON_DOWN = "daemon_down"
STATUS_PERMISSION = "permission"
STATUS_READY = "ready"


@dataclass
class ContainerRuntime:
    """What the machine can currently do with containers."""

    status: str = STATUS_MISSING
    engine: str = ""
    executable: str = ""
    version: str = ""
    in_docker_group: bool = False
    group_exists: bool = False
    message: str = ""
    problems: list[str] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        return self.status == STATUS_READY

    @property
    def needs_relogin(self) -> bool:
        """True when the group was granted but this session predates it."""
        return self.status == STATUS_PERMISSION and self.in_docker_group


def _run(command: list[str]) -> tuple[int, str, str]:
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, check=False, timeout=PROBE_TIMEOUT_SECONDS
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return (127, "", str(exc))
    return (result.returncode, result.stdout, result.stderr)


def user_in_docker_group(username: str | None = None) -> tuple[bool, bool]:
    """Return (group exists, user is a member)."""
    name = username or pwd.getpwuid(os.getuid()).pw_name
    try:
        group = grp.getgrnam("docker")
    except KeyError:
        return (False, False)
    if name in group.gr_mem:
        return (True, True)
    try:
        return (True, grp.getgrgid(os.getgid()).gr_name == "docker")
    except KeyError:
        return (True, False)


def detect_runtime(preferred: str = "docker") -> ContainerRuntime:
    """Probe for a usable container engine, preferring Docker."""
    order = [preferred] + [name for name in ("docker", "podman") if name != preferred]
    group_exists, in_group = user_in_docker_group()

    for engine in order:
        executable = shutil.which(engine)
        if not executable:
            continue

        code, out, err = _run([executable, "--version"])
        version = (out or err).strip().splitlines()[0] if (out or err).strip() else ""

        code, _out, err = _run([executable, "info", "--format", "{{.ServerVersion}}"])
        if code == 0:
            return ContainerRuntime(
                status=STATUS_READY, engine=engine, executable=executable, version=version,
                group_exists=group_exists, in_docker_group=in_group,
                message=f"{version} listo.",
            )

        lowered = (err or "").lower()
        if "permission denied" in lowered or "connect: permission" in lowered:
            return ContainerRuntime(
                status=STATUS_PERMISSION, engine=engine, executable=executable, version=version,
                group_exists=group_exists, in_docker_group=in_group,
                message=(
                    "Tu usuario ya está en el grupo `docker`, pero esta sesión empezó antes. "
                    "Cierra sesión y vuelve a entrar."
                    if in_group
                    else "Tu usuario no puede hablar con el demonio de Docker; falta el grupo `docker`."
                ),
                problems=[(err or "").strip()],
            )
        return ContainerRuntime(
            status=STATUS_DAEMON_DOWN, engine=engine, executable=executable, version=version,
            group_exists=group_exists, in_docker_group=in_group,
            message="El binario existe pero el demonio no responde. Prueba `sudo systemctl start docker`.",
            problems=[(err or "").strip()],
        )

    return ContainerRuntime(
        status=STATUS_MISSING, group_exists=group_exists, in_docker_group=in_group,
        message="No se encontró Docker ni Podman en este sistema.",
    )


def image_present(image: str, runtime: ContainerRuntime | None = None) -> bool:
    """Check whether an image is already in the local store."""
    active = runtime or detect_runtime()
    if not active.ready or not image:
        return False
    code, _out, _err = _run([active.executable, "image", "inspect", image])
    return code == 0


def image_size_bytes(image: str, runtime: ContainerRuntime | None = None) -> int:
    """Size of a local image, or 0 when it is absent."""
    active = runtime or detect_runtime()
    if not active.ready or not image:
        return 0
    code, out, _err = _run([active.executable, "image", "inspect", image, "--format", "{{.Size}}"])
    if code != 0:
        return 0
    try:
        return int(out.strip().splitlines()[0])
    except (ValueError, IndexError):
        return 0
