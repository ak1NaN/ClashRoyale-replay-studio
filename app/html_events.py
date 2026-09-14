"""Extract displayed replay events from a Safari-saved RoyaleAPI replay HTML.

Outputs an intermediate archival format, not an engine-ready match config.
No network access or third-party packages required.
"""

from collections import Counter, defaultdict, deque
import hashlib
from html.parser import HTMLParser
from pathlib import Path


class ReplayHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.timeline = []
        self.markers = []

    def handle_starttag(self, tag, attrs):
        data = dict(attrs)
        if "data-t" not in data:
            return
        classes = data.get("class", "").split()
        if "replay_card" in classes:
            self.timeline.append(data)
        elif "marker" in classes and "data-x" in data:
            self.markers.append(data)


def extract(path):
    raw = path.read_bytes()
    parser = ReplayHTML()
    parser.feed(raw.decode("utf-8"))
    markers = defaultdict(deque)
    for item in parser.markers:
        side = {"t": "blue", "o": "red"}[item["data-s"]]
        markers[(side, item["data-t"], item["data-c"])].append(item)
    events = []
    for item in parser.timeline:
        key = item["data-s"], item["data-t"], item["data-card"]
        ability = item.get("data-ability") == "1"
        if not markers[key] and not ability:
            raise ValueError(f"Timeline event has no matching map marker: {key}")
        marker = markers[key].popleft() if markers[key] else {}
        tick = int(item["data-t"])
        events.append(
            {
                "side": item["data-s"],
                "kind": "ability" if ability else "card_play",
                "ability_policy": "native_activate_and_charge" if ability else None,
                "card_slug": item["data-card"],
                "source_time_value": tick,
                "display_elapsed_seconds": tick / 20,
                "source_x": (
                    None
                    if marker.get("data-x") in (None, "None")
                    else int(marker["data-x"])
                ),
                "source_y": (
                    None
                    if marker.get("data-y") in (None, "None")
                    else int(marker["data-y"])
                ),
                "source_marker_index": (
                    int(marker["data-i"]) if marker.get("data-i") is not None else None
                ),
            }
        )
    if not events or any(markers.values()):
        raise ValueError("Missing events or unmatched map markers")
    events.sort(key=lambda event: event["source_time_value"])
    counts = Counter((event["side"], event["kind"]) for event in events)
    return {
        "schema": "royaleapi-displayed-replay.v1",
        "source_file": str(path.resolve()),
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "engine_ready": False,
        "time_interpretation": "20 source units per displayed second, inferred from HTML: 211 -> 105.5px and 15 seconds -> 150px. Native engine time origin not calibrated.",
        "coordinate_interpretation": "Original HTML coordinates preserved; native owner mapping and coordinate transformation not calibrated.",
        "unresolved": [
            "native time/coordinate mapping",
            "initial hand and random seed",
            "card levels, forms and rules compatibility",
            "ability identity and parameters",
            "exact terminal tick",
        ],
        "counts": {
            side: {kind: counts[side, kind] for kind in ("card_play", "ability")}
            for side in ("blue", "red")
        },
        "events": events,
    }
