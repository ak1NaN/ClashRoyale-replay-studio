"""Keep native failures actionable, including when cleanup also fails."""

import unittest
from unittest.mock import Mock, patch

from test_ability_import import ROOT
from app.engine import Engine, RenderedEngine
from app.runtime import Runtime


class EngineFailureTests(unittest.TestCase):
    def test_rejected_configuration_does_not_advance_old_match(self):
        engine = Engine()
        engine.request = Mock(return_value={"ok": False, "error": "invalid match"})
        with self.assertRaisesRegex(RuntimeError, "invalid match"):
            engine.reset(match={})
        self.assertEqual(engine.request.call_count, 1)

    def test_native_disconnect_identifies_scene_creation(self):
        engine = RenderedEngine()
        engine.request = Mock(side_effect=[
            {"ok": True, "mode": "headless"},
            {"ok": True, "sequence": 1},
            ConnectionError("socket closed"),
        ])
        with self.assertRaisesRegex(ConnectionError, "configure-native") as caught:
            engine.reset(match={})
        self.assertIsInstance(caught.exception.__cause__, ConnectionError)

    def test_rejected_speed_is_not_reported_as_success(self):
        engine = RenderedEngine()
        engine.request = Mock(return_value={"ok": False, "error": "renderer not ready"})
        with self.assertRaisesRegex(RuntimeError, "renderer not ready"):
            engine.set_speed(2)

    def test_load_preserves_original_error_when_cleanup_fails(self):
        runtime = Runtime()
        runtime.engine = Mock()
        runtime.engine.request.return_value = {"mode": "headless"}
        runtime.offline = True
        runtime.discard_replay = Mock()
        runtime.clear_cache = Mock(side_effect=ConnectionError("cleanup failed"))
        replay = {"events": [], "prepared_decks": [[], []],
                  "opening": [[], []], "seed": 1}
        with patch("app.runtime.match_for", return_value={}), patch.object(
            Engine, "reset", side_effect=RuntimeError("original failure")
        ):
            with self.assertRaisesRegex(RuntimeError, "original failure"):
                runtime.load(replay)
        self.assertIsNone(runtime.engine)
        self.assertTrue(runtime.reconnect_required)


if __name__ == "__main__":
    unittest.main()
