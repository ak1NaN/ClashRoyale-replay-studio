"""Cache navigation must never step or reload the battle."""
import unittest
from unittest.mock import Mock
from test_ability_import import ROOT
from app.runtime import Runtime

class CacheTests(unittest.TestCase):
    def test_seek_restores_exact_frame_without_advancing(self):
        r=Runtime();r.cache_ready=True;r.cache_end=300;r.match={}
        r.checkpoints={90:{'handle':1},127:{'handle':38},300:{'handle':211}}
        r.checked=Mock(return_value={'ok':True});r.schedule=Mock();r.status=Mock(return_value={'tick':127})
        self.assertEqual(r.seek(127)['tick'],127)
        self.assertEqual([c.args[0] for c in r.checked.call_args_list],['pause','restore 38','replay-schedule-clear'])
        r.schedule.assert_called_once_with(after=127)
    def test_clear_releases_native_and_python_caches(self):
        r=Runtime();r.engine=Mock();r.match={'x':1};r.cache_ready=True
        r.checkpoints={90:{'handle':1}};r.hand_cache={90:[]};r.receipts=[1];r.checked=Mock()
        r.clear_cache()
        self.assertEqual([c.args[0] for c in r.checked.call_args_list],['pause','cache-clear'])
        self.assertFalse(r.cache_ready);self.assertFalse(r.checkpoints);self.assertFalse(r.hand_cache)
        self.assertIsNone(r.match);self.assertFalse(r.receipts)
    def test_seek_before_ready_rejected(self):
        with self.assertRaises(RuntimeError):Runtime().seek(500)

class ReplayRecoveryTests(unittest.TestCase):
    def test_stale_cleanup_does_not_block_next_import(self):
        r=Runtime();r.engine=Mock();r.match={'old':True};r.replay={'old':True}
        r.checkpoints={90:{'handle':1}};r.hand_cache={90:1}
        r.checked=Mock(side_effect=ConnectionError('game closed'))
        r.discard_replay()
        self.assertIsNone(r.engine);self.assertIsNone(r.match);self.assertIsNone(r.replay)
        self.assertTrue(r.reconnect_required);self.assertFalse(r.checkpoints);self.assertFalse(r.hand_cache)
    def test_eight_and_sixteen_speeds_reach_native_protocol(self):
        from app.engine import RenderedEngine
        e=RenderedEngine();e.request=Mock(return_value={'ok':True})
        for speed in (8,16):
            e.set_speed(speed);e.request.assert_called_with(f'speed {speed}')
        with self.assertRaises(ValueError):e.set_speed(32)
