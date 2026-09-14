import hashlib
import json
import lzma
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch
from test_ability_import import ROOT
from app import device


class MacSetupTests(TestCase):
    def test_mumu_adb_is_found_without_sdk(self):
        with patch.object(device.sys, "platform", "darwin"), patch.object(
            device.Path,
            "is_file",
            lambda p: str(p).endswith("MuMuEmulator.app/Contents/MacOS/tools/adb"),
        ):
            self.assertIn("MuMuPlayer.app", device.defaults()["adb"])

    def test_matching_server_is_reused(self):
        d = device.DeviceSession()
        m = json.loads((ROOT / "resources/frida.json").read_text())
        d.shell = Mock(return_value=SimpleNamespace(stdout=m["sha256"] + " server"))
        d.adb = Mock()
        d.stop_frida = Mock()
        d.install_frida()
        d.adb.assert_not_called()
        d.stop_frida.assert_not_called()

    def test_corrupt_archive_does_not_touch_server(self):
        with TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "resources").mkdir()
            (folder / "resources/frida.json").write_text(
                json.dumps(
                    {"file": "server.xz", "sha256": "abc", "archive_sha256": "def"}
                )
            )
            (folder / "resources/server.xz").write_bytes(b"corrupted")
            d = device.DeviceSession()
            d.shell = Mock(return_value=SimpleNamespace(stdout=""))
            d.stop_frida = Mock()
            d.adb = Mock()
            with patch.object(device, "ROOT", folder), self.assertRaisesRegex(
                RuntimeError, "校验失败"
            ):
                d.install_frida()
            d.stop_frida.assert_not_called()
            d.adb.assert_not_called()

    def test_new_server_is_verified_before_atomic_install(self):
        m = json.loads((ROOT / "resources/frida.json").read_text())
        d = device.DeviceSession()
        d.stop_frida = Mock()
        d.adb = Mock()
        d.shell = Mock(
            side_effect=lambda *a, **k: SimpleNamespace(
                stdout=(
                    m["sha256"] + " temp"
                    if a == ("sha256sum", "/data/local/tmp/frida-server.tmp")
                    else ""
                )
            )
        )
        d.install_frida()
        d.adb.assert_called_once()
        d.shell.assert_any_call(
            "mv", "/data/local/tmp/frida-server.tmp", "/data/local/tmp/frida-server"
        )

    def test_root_denied_has_actionable_error(self):
        d = device.DeviceSession()
        d.shell = Mock(return_value=SimpleNamespace(stdout="2000"))
        d.adb = Mock()
        with self.assertRaisesRegex(RuntimeError, "MuMu.*root"):
            d.ensure_root()

    def test_cold_android_service_is_retried_once(self):
        d = device.DeviceSession()
        d.shell = Mock(side_effect=[RuntimeError("IPlatformCompat is null"), None])
        with patch.object(device.time, "sleep"):
            d.start_game()
        self.assertEqual(d.shell.call_count, 2)

    def test_other_start_errors_are_not_hidden(self):
        d = device.DeviceSession()
        d.shell = Mock(side_effect=RuntimeError("activity unavailable"))
        with self.assertRaisesRegex(RuntimeError, "activity unavailable"):
            d.start_game()
        self.assertEqual(d.shell.call_count, 1)
