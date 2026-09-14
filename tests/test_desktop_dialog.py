import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from test_ability_import import ROOT
from native_engine.desktop.runtime import Runtime

class DialogTests(unittest.TestCase):
    def test_only_dismisses_visible_game_system_dialog(self):
        base='  Window #5 Window{xyz u0 nullsroyale.rel.free/com.supercell.clashroyale.GameApp}:\n package=nullsroyale.rel.free\n (wrapxwrap) ty=APPLICATION fmt=TRANSLUCENT\n mViewVisibility=0x0 mObscured=false\n'
        for dump,expected in [(base,1),(base.replace('ty=APPLICATION ','ty=BASE_APPLICATION '),0),(base.replace('nullsroyale.rel.free','other.app'),0),(base.replace('mViewVisibility=0x0','mViewVisibility=0x8'),0),('',0)]:
            runtime=Runtime();runtime.shell=Mock(return_value=SimpleNamespace(stdout=dump));runtime.dismiss_connection_dialog()
            calls=[c for c in runtime.shell.call_args_list if c.args[:2]==('input','keyevent')]
            self.assertEqual(len(calls),expected)
