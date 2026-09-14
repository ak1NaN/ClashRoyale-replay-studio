"""Offline regression tests: run with python3 -m unittest discover -s tests."""

from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.html_events import extract
from app.protocol import CardPlay


class AbilityImportTests(unittest.TestCase):
    def test_invalid_slug_without_coordinates_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            html = Path(directory) / "battle.html"
            html.write_text(
                '<div class="replay_card" data-t="812" data-s="blue" data-card="_invalid" data-ability="1"></div>'
            )
            event = extract(html)["events"][0]
        self.assertEqual(event["source_time_value"], 812)
        self.assertEqual(event["kind"], "ability")
        self.assertIsNone(event["source_x"])

    def test_consumed_root_identity_is_separate_from_unknown_hero_identity(self):
        play = CardPlay(1, 91, 0, 0, 4, 26000018, 2)
        self.assertEqual(play.root_card, 26000018)
        self.assertEqual(play.card, 0)
        self.assertIsNone(CardPlay(1, 91, 0, 26000018, 4).root_card)


if __name__ == "__main__":
    unittest.main()
