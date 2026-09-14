import os
import json
import tempfile
import unittest
from pathlib import Path
from test_ability_import import ROOT
from app.importer import (
    convert,
    replay_url,
    choose,
    compatible,
    LAYOUT,
    match_for,
    resolve,
)


class ImporterTests(unittest.TestCase):
    def test_ice_spirit_public_name_and_evolution(self):
        for slug in ("ice-spirit", "ice-spirit-ev1", "ice- spirit"):
            self.assertEqual(resolve(slug, [26000030, 26000031]), 26000030)
        with self.assertRaises(ValueError):
            resolve("ice-spirit", [26000031])

    def test_saved_ice_spirit_replay(self):
        source = Path(
            os.environ.get(
                "REPLAY_ICE_SPIRIT_HTML", str(ROOT / "tests/fixtures/ice-spirit.html")
            )
        )
        if not source.exists():
            self.skipTest("user HTML unavailable")
        replay = convert(source)
        events = [a for a in replay["events"] if a["card_slug"] == "ice-spirit"]
        self.assertTrue(events)
        for event in events:
            self.assertEqual(event["card"], 26000030)
            self.assertIn(
                26000030, [c["id"] for c in replay["players"][event["owner"]]["cards"]]
            )
        for owner, opening in enumerate(replay["opening"]):
            plays = [
                a["card"]
                for a in replay["events"]
                if a["owner"] == owner and a["kind"] == "card_play"
            ]
            self.assertTrue(compatible(opening[:4], opening[4:], plays))

    def test_url_rejects_foreign_hosts_and_multi_players(self):
        for url in (
            "http://royaleapi.com/replay?tag=X",
            "https://royaleapi.com.evil.test/replay?tag=X",
            "https://royaleapi.com/player/X",
        ):
            with self.assertRaises(ValueError):
                replay_url(url)
        clean, q = replay_url(
            "https://royaleapi.com/replay?tag=ABC&team_tags=DEF&opponent_tags=GHI&extra=ignored"
        )
        self.assertNotIn("extra", clean)

    def test_full_cycle_and_omitted_card(self):
        ids = (
            26000000,
            26000001,
            26000005,
            28000001,
            28000000,
            26000003,
            26000014,
            26000033,
        )
        plays = (26000000, 26000001, 26000005, 28000001, 26000033, 26000000)
        deck, hand, queue = choose(ids, plays, LAYOUT[0])
        self.assertTrue(compatible(hand, queue, plays))
        self.assertNotIn(26000033, hand)
        self.assertEqual(set(deck), set(ids))

    def test_saved_real_replays_preserve_cards_forms_levels(self):
        cases = [
            ("00VYPQVU2UU9", "CRV2L8GGV", "VULGLVC2", 75),
            ("020YPQCY09JL", "CVVCU2JJ8", "8JRU2CVQ", 88),
            ("02YYY08G90C2", "9PYLJ0CR", "8RG0YG2U", 43),
        ]
        for tag, a, b, count in cases:
            path = ROOT.parent / "artifacts" / f"royaleapi-replay-{tag}.html"
            if not path.exists():
                continue
            replay = convert(
                path,
                f"https://royaleapi.com/replay?tag={tag}&team_tags={a}&opponent_tags={b}",
            )
            self.assertEqual(len(replay["events"]), count)
            standalone = convert(path)
            self.assertEqual(standalone["events"], replay["events"])
            self.assertEqual(standalone["tag"], tag)
            for owner, opening in enumerate(standalone["opening"]):
                plays = [
                    e["card"]
                    for e in standalone["events"]
                    if e["owner"] == owner and e["kind"] == "card_play"
                ]
                self.assertTrue(compatible(opening[:4], opening[4:], plays))
                self.assertEqual(
                    set(opening),
                    {c["id"] for c in standalone["players"][owner]["cards"]},
                )
            self.assertEqual(
                sum(e["kind"] == "ability" for e in replay["events"]),
                3 if count == 75 else 5,
            )
            if count == 88:
                hero = next(
                    c for c in replay["players"][1]["cards"] if c["id"] == 26000102
                )
                self.assertEqual((hero["level"], hero["form"]), (15, 2))
            with self.assertRaises(ValueError):
                convert(
                    path,
                    f"https://royaleapi.com/replay?tag=WRONG&team_tags={a}&opponent_tags={b}",
                )

    def test_mixed_level_encoding(self):
        deck = [
            26000000,
            26000001,
            26000005,
            28000001,
            28000000,
            26000003,
            26000014,
            26000102,
        ]
        p = {
            "name": "Test",
            "tower": 159000000,
            "tower_level": 16,
            "cards": [
                {
                    "id": i,
                    "level": 15 if i == 26000102 else 16,
                    "form": 2 if i == 26000102 else 0,
                }
                for i in deck
            ],
        }
        match = match_for({"players": [p, p]}, [deck, deck])
        self.assertEqual(match["battle"]["cardlvlmin"], 15)
        cards = {c["d"]: c for c in match["battle"]["deck0"]["sp"]}
        self.assertEqual(cards[26000102]["l"], 14)
        self.assertEqual(cards[26000014]["l"], 13)


if __name__ == "__main__":
    unittest.main()
