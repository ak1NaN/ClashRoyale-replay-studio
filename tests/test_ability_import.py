"""Offline regression tests: run with python3 -m unittest discover -s tests."""
import importlib.util
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('native_engine', ROOT / '__init__.py', submodule_search_locations=[str(ROOT)])
module = importlib.util.module_from_spec(spec)
sys.modules.setdefault('native_engine', module)
spec.loader.exec_module(module)
from native_engine.replay_import.extract_royaleapi import extract
from native_engine.replay_import.abilities import ability_action
from native_engine.engine import Ability, _ability_execution
from native_engine.protocol import CardPlay


class AbilityImportTests(unittest.TestCase):
    def test_invalid_slug_without_coordinates_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            html = Path(directory) / 'battle.html'
            html.write_text('<div class="replay_card" data-t="812" data-s="blue" data-card="_invalid" data-ability="1"></div>')
            event = extract(html)['events'][0]
        self.assertEqual(event['source_time_value'], 812)
        self.assertEqual(event['kind'], 'ability')
        self.assertIsNone(event['source_x'])
        self.assertEqual(ability_action(event, {'blue': 1}), Ability(1, '-'))

    def test_queue_success_is_not_execution_proof(self):
        runtime = {'available': True, 'controllerSlot': 0, 'actionDataGlobalId': 1,
                   'actionDataName': 'HeroAbility', 'remainingChargesRaw': 1,
                   'remainingCooldownMs': 0}
        def state(value):
            return SimpleNamespace(players=[SimpleNamespace(runtime={'abilityRuntime': [value]})])
        before = state(runtime)
        self.assertIsNone(_ability_execution(before, before, Ability(0), {'state': 'succeeded'}))
        self.assertFalse(_ability_execution(before, before, Ability(0), {'state': 'failed'}))
        self.assertTrue(_ability_execution(before, state(dict(runtime, remainingChargesRaw=0)), Ability(0), {'state': 'succeeded'}))

    def test_consumed_root_identity_is_separate_from_unknown_hero_identity(self):
        play = CardPlay(1, 91, 0, 0, 4, 26000018, 2)
        self.assertEqual(play.root_card, 26000018)
        self.assertEqual(play.card, 0)
        self.assertIsNone(CardPlay(1, 91, 0, 26000018, 4).root_card)


if __name__ == '__main__':
    unittest.main()
