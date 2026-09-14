from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch
from test_ability_import import ROOT
from app import device


class WindowsSetupTests(TestCase):
    def test_windows_mumu_adb_discovery(self):
        with patch.object(device.sys, 'platform', 'win32'), patch.dict(
            device.os.environ, {'ProgramFiles': 'C:/Program Files'}
        ), patch.object(device.Path, 'is_file', lambda p: p.as_posix().endswith('Netease/MuMuPlayer-12.0/shell/adb.exe')):
            self.assertTrue(device.Path(device.defaults()['adb']).as_posix().endswith('MuMuPlayer-12.0/shell/adb.exe'))

    def test_adb_hidden_console_and_utf8(self):
        with patch.object(device.sys, 'platform', 'win32'), patch.object(
            device.subprocess, 'CREATE_NO_WINDOW', 0x08000000, create=True
        ), patch.object(device.subprocess, 'run', return_value=SimpleNamespace(returncode=0)) as run:
            device.run(['C:/Program Files/MuMu/adb.exe', 'devices'])
            self.assertEqual(run.call_args.kwargs['creationflags'], 0x08000000)
            self.assertEqual(run.call_args.kwargs['encoding'], 'utf-8')
            self.assertEqual(run.call_args.args[0][0], 'C:/Program Files/MuMu/adb.exe')

    def test_x86_rejected_before_network_or_install(self):
        d = device.DeviceSession()
        d.connect_device = Mock()
        d.shell = Mock(return_value=SimpleNamespace(stdout='x86_64'))
        d.rules = Mock()
        d.install_frida = Mock()
        with self.assertRaisesRegex(RuntimeError, 'ARM.*转译'):
            d.prepare_engine()
        d.rules.assert_not_called()
        d.install_frida.assert_not_called()
