"""Native level/form configuration, following FirstLight's match_factory.py.

Reference: https://gitlab.com/firstlight3/FirstLight_CR/-/blob/main/native_runner/match_factory.py
The native engine, not Python, owns evolution cycles, ability costs and effects.
"""

import json
from pathlib import Path


def make_match(
    decks,
    *,
    level=16,
    forms=None,
    towers=(159000000, 159000000),
    names=("Native-0", "Native-1"),
):
    decks = tuple(tuple(deck) for deck in decks)
    if len(decks) != 2 or any(len(deck) != 8 or len(set(deck)) != 8 for deck in decks):
        raise ValueError("provide two decks of eight distinct card IDs")
    if type(level) is not int or not 1 <= level <= 16:
        raise ValueError("level must be an integer in 1..16")
    forms = (
        ((0,) * 8, (0,) * 8) if forms is None else tuple(tuple(row) for row in forms)
    )
    if len(forms) != 2 or any(
        len(row) != 8 or any(type(v) is not int or v not in (0, 1, 2, 3) for v in row)
        for row in forms
    ):
        raise ValueError(
            "forms must contain two eight-element masks (0=base, 1=evolution, 2=hero, 3=both)"
        )
    if len(towers) != 2 or len(names) != 2:
        raise ValueError("provide two tower IDs and two names")
    match = json.loads(Path(__file__).with_name("standard_match.json").read_text())
    battle = match["battle"]
    battle["lvlcap"] = battle["cardlvlmin"] = level
    for owner in range(2):
        battle[f"deck{owner}"]["sp"] = [
            dict(d=card, el=mask) for card, mask in zip(decks[owner], forms[owner])
        ]
        battle[f"deck{owner}"]["sc"][0]["d"] = towers[owner]
        battle[f"avatar{owner}"]["expLevel"] = level
        battle[f"avatar{owner}"]["name"] = names[owner]
        battle["hbd"][owner]["kt"] = level
    return match
