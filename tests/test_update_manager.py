"""Tests for release-based and git-based update checks."""

from __future__ import annotations

import io
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path

from tests.qt_stubs import install_qtcore_stub

install_qtcore_stub()

from app.core.update_manager import UpdateManager, parse_version


class _Response:
    def __init__(self, payload: dict) -> None:
        self._buffer = io.BytesIO(json.dumps(payload).encode("utf-8"))

    def read(self) -> bytes:
        return self._buffer.read()

    def __enter__(self):
        return self

    def __exit__(self, *_exc) -> bool:
        return False


def _opener(payload: dict):
    def open_url(_request, timeout=None):
        return _Response(payload)
    return open_url


class ParseVersionTest(unittest.TestCase):
    def test_ordering(self) -> None:
        self.assertGreater(parse_version("0.3.1"), parse_version("0.3.0"))
        self.assertGreater(parse_version("v0.3.0"), parse_version("0.2.9"))
        self.assertGreater(parse_version("0.10.0"), parse_version("0.9.0"))

    def test_prerelease_sorts_below_the_final_version(self) -> None:
        self.assertLess(parse_version("0.3.0-beta.2"), parse_version("0.3.0"))
        self.assertGreater(parse_version("0.3.0-beta.11"), parse_version("0.3.0-beta.2"))

    def test_unparseable_text_is_empty(self) -> None:
        self.assertEqual(parse_version(""), ())
        self.assertEqual(parse_version("unknown"), ())


class UpdateCheckTest(unittest.TestCase):
    def _manager(self, installed: str) -> UpdateManager:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root / "VERSION").write_text(installed, encoding="utf-8")
        self.addCleanup(self.tmp.cleanup)
        return UpdateManager(root)

    @staticmethod
    def _release(tag: str) -> dict:
        return {
            "tag_name": tag,
            "html_url": f"https://github.com/ROMERUU-dev/sky130-flow-gui/releases/tag/{tag}",
            "assets": [
                {"name": "notes.txt", "browser_download_url": "https://example/notes.txt"},
                {"name": f"sky130-flow-gui_{tag.lstrip('v')}_amd64.deb",
                 "browser_download_url": f"https://example/{tag}.deb"},
            ],
        }

    def test_a_newer_release_is_reported(self) -> None:
        manager = self._manager("0.3.0")

        result = manager.check(opener=_opener(self._release("v0.4.0")))

        self.assertTrue(result.update_available)
        self.assertEqual(result.latest, "v0.4.0")
        self.assertTrue(result.download_url.endswith(".deb"))

    def test_the_same_version_is_up_to_date(self) -> None:
        manager = self._manager("0.3.0")

        result = manager.check(opener=_opener(self._release("v0.3.0")))

        self.assertEqual(result.status, "up_to_date")
        self.assertFalse(result.update_available)

    def test_a_local_build_ahead_of_the_release_is_not_an_update(self) -> None:
        manager = self._manager("0.4.0")

        result = manager.check(opener=_opener(self._release("v0.3.0")))

        self.assertEqual(result.status, "ahead")
        self.assertFalse(result.update_available)

    def test_network_failure_is_reported_without_raising(self) -> None:
        manager = self._manager("0.3.0")

        def failing(_request, timeout=None):
            raise urllib.error.URLError("no route to host")

        result = manager.check(opener=failing)

        self.assertEqual(result.status, "unreachable")
        self.assertIn("no route", result.message)
        self.assertFalse(result.update_available)

    def test_a_packaged_install_is_not_a_git_checkout(self) -> None:
        """This is what made the old git-only update check fail on a .deb."""
        manager = self._manager("0.3.0")

        self.assertFalse(manager.is_git_checkout())

    def test_a_clone_is_detected_as_a_git_checkout(self) -> None:
        manager = self._manager("0.3.0")
        (manager.repo_root / ".git").mkdir()

        self.assertTrue(manager.is_git_checkout())


if __name__ == "__main__":
    unittest.main()
