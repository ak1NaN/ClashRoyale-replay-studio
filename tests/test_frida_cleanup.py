from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock
from test_ability_import import ROOT
from native_engine.desktop.runtime import Runtime

class FridaCleanupTests(TestCase):
    def test_stops_server_and_only_removes_its_forward(self):
        r=Runtime();live={'123'};calls=[]
        def shell(*args,**kwargs):
            calls.append(args)
            if args[0]=='pidof':return SimpleNamespace(stdout=' '.join(live))
            if args[:2]==('kill','-TERM'):live.clear()
            return SimpleNamespace(stdout='')
        r.shell=shell;r.adb=Mock(return_value=SimpleNamespace(stdout=f"{r.cfg['serial']} tcp:27042 tcp:27042\nother tcp:27043 tcp:27042\n"))
        r.stop_frida()
        self.assertIn(('kill','-TERM','123'),calls)
        r.adb.assert_any_call('forward','--remove','tcp:27042',check=False)
        self.assertFalse(live)
    def test_missing_server_is_successful_without_kill(self):
        r=Runtime();r.shell=Mock(return_value=SimpleNamespace(stdout=''));r.adb=Mock(return_value=SimpleNamespace(stdout=''))
        r.stop_frida()
        r.shell.assert_called_once_with('pidof','frida-server',check=False)
    def test_online_detaches_before_stopping_frida(self):
        r=Runtime();calls=[];r.connect_device=Mock();r.clear_cache=Mock();r.close_connection=Mock()
        r.session=Mock();r.session.detach.side_effect=lambda:calls.append('detach')
        r.rules=Mock();r.shell=Mock();r.stop_frida=Mock(side_effect=lambda:calls.append('stop'))
        r.online();self.assertEqual(calls,['detach','stop']);r.rules.assert_called_once_with(False)
