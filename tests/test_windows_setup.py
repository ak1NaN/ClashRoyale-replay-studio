from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch
import json
import hashlib
from test_ability_import import ROOT
from app import device


class WindowsSetupTests(TestCase):
    def test_bundled_mumu_probe_matches_build_provenance(self):
        manifest = json.loads((ROOT / 'resources/windows-provenance.json').read_text(encoding='utf-8'))
        probe = ROOT / 'resources/libcrprobe-mumu.so'
        self.assertEqual(hashlib.sha256(probe.read_bytes()).hexdigest(), manifest['output_sha256'])
        patch_bytes = (ROOT / manifest['patch']).read_bytes().replace(b'\r\n', b'\n')
        self.assertEqual(hashlib.sha256(patch_bytes).hexdigest(), manifest['patch_sha256'])

    def test_bridge_return_fault_requires_live_compatible_probe(self):
        d = device.DeviceSession()
        error = {'description': 'Error: access violation accessing 0xdead1066',
                 'stack': 'at loadProbe (/script1.js:46)'}
        d.wait_until_ready = Mock(return_value={'ok': True, 'contentReady': True, 'coldReady': True, 'armed': True})
        self.assertTrue(d.wait_probe_ready('mumu-native-bridge-x86_64', [error])['contentReady'])
        d.wait_until_ready.assert_called_once_with(5)
        d.wait_until_ready.return_value = {'ok': True, 'contentReady': True, 'armed': False}
        with self.assertRaisesRegex(RuntimeError, 'dead1066'):
            d.wait_probe_ready('mumu-native-bridge-x86_64', [error])

    def test_other_injection_errors_are_not_ignored(self):
        d = device.DeviceSession()
        errors = [{'description': 'unexpected failure'}]
        d.wait_until_ready = Mock(side_effect=RuntimeError('unexpected failure'))
        with self.assertRaisesRegex(RuntimeError, 'unexpected failure'):
            d.wait_probe_ready('mumu-native-bridge-x86_64', errors)
        d.wait_until_ready.assert_called_once_with(330, errors)

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

    def test_x86_without_mumu_bridge_rejected_before_network_or_install(self):
        d = device.DeviceSession()
        d.connect_device = Mock()
        d.shell = Mock(
            side_effect=[
                SimpleNamespace(stdout='x86_64'),
                SimpleNamespace(stdout='unsupported-bridge'),
            ]
        )
        d.rules = Mock()
        d.install_frida = Mock()
        with self.assertRaisesRegex(RuntimeError, 'libnb.so'):
            d.prepare_engine()
        d.rules.assert_not_called()
        d.install_frida.assert_not_called()

    def test_mumu_x86_native_bridge_mode_is_supported(self):
        d = device.DeviceSession()
        d.shell = Mock(
            side_effect=[
                SimpleNamespace(stdout='x86_64'),
                SimpleNamespace(stdout='libnb.so'),
            ]
        )
        self.assertEqual(d.probe_mode(), 'mumu-native-bridge-x86_64')

    def test_native_arm64_mode_remains_supported(self):
        d = device.DeviceSession()
        d.shell = Mock(return_value=SimpleNamespace(stdout='arm64-v8a'))
        self.assertEqual(d.probe_mode(), 'native-arm64')

    def test_x86_server_manifest_is_selected(self):
        manifest = json.loads((ROOT / 'resources/frida.json').read_text())['x86_64']
        d = device.DeviceSession()
        d.shell = Mock(return_value=SimpleNamespace(stdout=manifest['sha256'] + ' server'))
        d.adb = Mock()
        d.stop_frida = Mock()
        d.install_frida('x86_64')
        d.adb.assert_not_called()
        d.stop_frida.assert_not_called()

    def test_missing_owner_match_uses_gateway_safe_emulator_rule(self):
        def shell(*args, **kwargs):
            if args[:2] == ('id', '-u'):
                return SimpleNamespace(stdout='0', returncode=0)
            if args[:3] == ('stat', '-c', '%u'):
                return SimpleNamespace(stdout='10123', returncode=0)
            if args[:4] == ('ip', 'route', 'show', 'table'):
                return SimpleNamespace(
                    stdout='default via 10.0.2.2 dev wlan0 table wlan0', returncode=0
                )
            if '-m' in args and 'owner' in args:
                return SimpleNamespace(stdout='', returncode=1)
            return SimpleNamespace(stdout='', returncode=0)

        d = device.DeviceSession()
        d.shell = Mock(side_effect=shell)
        d.rules(True)
        self.assertTrue(d.offline)
        self.assertIn(
            ('iptables', '-I', 'OUTPUT', '!', '-o', 'lo', '!', '-d', '10.0.2.2'),
            [call.args[:9] for call in d.shell.call_args_list],
        )
