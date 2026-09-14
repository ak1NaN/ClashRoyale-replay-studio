import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch
from test_ability_import import ROOT
from native_engine.desktop import device
from native_engine.desktop.runtime import Runtime


class SetupTests(TestCase):
    def test_legacy_launcher_is_ignored_and_relative_adb_is_portable(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = Path(tmp) / "settings.json"
            settings.write_text(
                '{"adb":"platform-tools/adb","launch":["unwanted"],"serial":"local:1"}'
            )
            with patch.object(device, "SETTINGS", settings), patch.object(
                device, "APP_DIR", Path(tmp)
            ):
                cfg = device.settings()
            self.assertNotIn("launch", cfg)
            self.assertEqual(cfg["adb"], str(Path(tmp) / "platform-tools/adb"))

    def test_missing_emulator_fails_without_launch_or_wait(self):
        r = Runtime()
        r.adb = Mock(return_value=SimpleNamespace(stdout="offline"))
        r.shell = Mock()
        with patch.object(
            device, "run", return_value=SimpleNamespace(stdout="")
        ) as command:
            with self.assertRaisesRegex(RuntimeError, "先启动模拟器"):
                r.connect_device()
            self.assertEqual(command.call_count, 1)
        r.shell.assert_not_called()

    def test_portable_flag_keeps_settings_beside_app(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "portable.flag").touch()
            with patch.object(device, "APP_DIR", folder), patch.object(
                device, "FROZEN", True
            ), patch.dict(device.os.environ, {}, clear=True):
                self.assertEqual(device.data_directory(), folder / "data")
