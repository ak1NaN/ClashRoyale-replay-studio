import os
import unittest
from pathlib import Path
from test_ability_import import ROOT
from app.importer import convert

SOURCE = Path(
    os.environ.get(
        "REPLAY_ORIENTATION_HTML", str(ROOT / "tests/fixtures/orientation.html")
    )
)


class OrientationTests(unittest.TestCase):
    def test_true_blue_team_keeps_source_coordinates(self):
        path = ROOT.parent / "artifacts/royaleapi-replay-00VYPQVU2UU9.html"
        if not path.exists():
            self.skipTest("reference replay unavailable")
        r = convert(path)
        self.assertEqual(r["players"][0]["name"], "REYVAJ")
        for a in r["events"]:
            self.assertEqual(a["owner"], 1 if a["side"] == "blue" else 0)
            if a["kind"] == "card_play":
                self.assertEqual((a["x"], a["y"]), (a["source_x"], a["source_y"]))

    @unittest.skipUnless(SOURCE.exists(), "user replay fixture unavailable")
    def test_true_red_team_is_rotated_with_its_owner(self):
        r = convert(SOURCE)
        self.assertEqual([p["name"] for p in r["players"]], ["XIV_Kxrmaa", "AgonyKing"])
        giant = next(a for a in r["events"] if a["card_slug"] == "giant")
        baby = next(a for a in r["events"] if a["card_slug"] == "baby-dragon")
        self.assertEqual((giant["owner"], giant["x"], giant["y"]), (1, 9501, 31500))
        self.assertEqual((baby["owner"], baby["x"], baby["y"]), (0, 9500, 500))
        self.assertEqual(r["expected"], ["0", "1"])
        for a in r["events"]:
            self.assertEqual(a["owner"], 1 if a["side"] == "blue" else 0)
            if a["kind"] == "card_play":
                self.assertIn(
                    a["card"], [c["id"] for c in r["players"][a["owner"]]["cards"]]
                )
                self.assertEqual(
                    (a["x"], a["y"]), (18000 - a["source_x"], 32000 - a["source_y"])
                )
