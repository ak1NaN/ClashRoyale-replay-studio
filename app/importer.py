"""Public HTML to a validated native replay. No networking or UI dependencies."""

from dataclasses import dataclass, field
from html.parser import HTMLParser
import itertools
import json
from pathlib import Path
import re
from urllib.parse import urlparse, parse_qs, urlencode
from .match_config import make_match
from .html_events import extract

SEED = 1784463263
LAYOUT = (((2, 0, 4, 7), (6, 1, 3, 5)), ((7, 1, 4, 3), (6, 0, 2, 5)))
CATALOG = json.loads(Path(__file__).with_name("catalog.json").read_text(encoding="utf-8-sig"))["cards"]
BY_ID = {c["id"]: c for c in CATALOG}
TOWERS = {
    "tower-princess": 159000000,
    "cannoneer": 159000001,
    "dagger-duchess": 159000002,
    "royal-chef": 159000004,
}


def replay_url(url):
    p = urlparse(url.strip())
    if (
        p.scheme != "https"
        or p.hostname not in ("royaleapi.com", "www.royaleapi.com")
        or p.path != "/replay"
    ):
        raise ValueError("请输入 https://royaleapi.com/replay?... 独立对局链接")
    q = parse_qs(p.query)
    keys = ("tag", "team_tags", "opponent_tags")
    if any(
        len(q.get(k, [])) != 1 or not re.fullmatch("[A-Z0-9]+", q[k][0]) for k in keys
    ):
        raise ValueError("链接缺少有效对局编号或双方玩家编号（仅支持 1v1）")
    clean = {k: q[k][0] for k in keys}
    for k in ("team_crowns", "opponent_crowns"):
        if k in q and len(q[k]) == 1 and q[k][0] in ("0", "1", "2", "3"):
            clean[k] = q[k][0]
    return "https://royaleapi.com/replay?" + urlencode(clean), clean


@dataclass
class Node:
    attrs: dict = field(default_factory=dict)
    children: list = field(default_factory=list)
    text: str = ""

    def all(self, predicate):
        return ([self] if predicate(self) else []) + [
            n for c in self.children for n in c.all(predicate)
        ]

    def has(self, name):
        return name in self.attrs.get("class", "").split()

    def content(self):
        return self.text + "".join(c.content() for c in self.children)


class Tree(HTMLParser):
    def __init__(self):
        super().__init__()
        self.root = Node()
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        n = Node(dict(attrs))
        self.stack[-1].children.append(n)
        if tag not in (
            "img",
            "br",
            "hr",
            "meta",
            "link",
            "input",
            "source",
            "wbr",
            "area",
            "embed",
            "param",
            "col",
            "base",
        ):
            self.stack.append(n)

    def handle_endtag(self, tag):
        if (
            tag
            not in (
                "img",
                "br",
                "hr",
                "meta",
                "link",
                "input",
                "source",
                "wbr",
                "area",
                "embed",
                "param",
                "col",
                "base",
            )
            and len(self.stack) > 1
        ):
            self.stack.pop()

    def handle_data(self, text):
        self.stack[-1].text += text


def norm(s):
    return re.sub("[^a-z0-9]", "", s.lower())


def base(s):
    return re.sub(r"-(ev\d+|hero)$", "", s)


def resolve(slug, allowed):
    token = norm(base(slug))
    matches = [i for i in allowed if i in BY_ID and token in BY_ID[i]["aliases"]]
    if len(matches) != 1:
        raise ValueError(f"当前引擎无法唯一识别卡牌：{slug}。未替换或跳过。")
    return matches[0]


def compatible(hand, queue, plays):
    hand = list(hand)
    queue = list(queue)
    for card in plays:
        if card not in hand:
            return False
        hand[hand.index(card)] = queue.pop(0)
        queue.append(card)
    return True


def choose(ids, plays, layout, fixed=None):
    omitted = {i for i in ids if BY_ID[i]["omitted"]}
    fixed = fixed or {}
    for hand in itertools.combinations(ids, 4):
        if omitted.intersection(hand) or plays and plays[0] not in hand:
            continue
        for queue in itertools.permutations(i for i in ids if i not in hand):
            if any(queue[k] != v for k, v in fixed.items()) or not compatible(
                hand, queue, plays
            ):
                continue
            deck = [0] * 8
            for slot, card in zip(layout[0] + layout[1], hand + queue):
                deck[slot] = card
            return deck, list(hand), list(queue)
    raise ValueError("未找到与完整出牌记录相容的起手牌；没有强制改动出牌规则")


def convert(path, url=None):
    raw = Path(path).read_text(encoding="utf-8-sig")
    if url is None:
        metadata = Tree()
        metadata.feed(raw)
        candidates = metadata.root.all(
            lambda n: n.attrs.get("rel") == "canonical"
            or n.attrs.get("property") == "og:url"
        )
        for node in candidates:
            try:
                url, _ = replay_url(
                    node.attrs.get("href", node.attrs.get("content", ""))
                )
                break
            except ValueError:
                continue
        if url is None:
            raise ValueError("HTML 缺少有效对局信息，请导入完整的独立对局页面")
    canonical, query = replay_url(url)
    if "tag=" + query["tag"] not in raw:
        raise ValueError("HTML 中的对局编号与链接不一致")
    tree = Tree()
    tree.feed(raw)
    segments = tree.root.all(lambda n: n.has("team-segment"))
    if len(segments) != 2:
        raise ValueError("页面尚未加载完整，或不是支持的 1v1 对局；请在网页加载后重试")
    players = []
    for index, segment in enumerate(segments):
        links = segment.all(lambda n: "copyDeck?" in n.attrs.get("href", ""))
        if not links:
            raise ValueError("页面缺少卡组编号")
        ids = [
            int(x)
            for x in re.search(r"deck=([0-9;]+)", links[0].attrs["href"])
            .group(1)
            .split(";")
        ]
        if len(ids) != 8 or len(set(ids)) != 8 or any(i not in BY_ID for i in ids):
            raise ValueError("卡组包含当前原生版本未支持的卡牌")
        names = segment.all(lambda n: n.has("player_name_header"))
        name = names[0].text.strip() if names else f"Player {index+1}"
        if names and query[("team_tags", "opponent_tags")[index]] not in names[
            0
        ].attrs.get("href", ""):
            raise ValueError("保存的 HTML 与链接玩家不一致")
        cards = []
        for block in segment.all(lambda n: n.has("deck_card__four_wide")):
            imgs = block.all(lambda n: n.has("deck_card"))
            levels = block.all(lambda n: n.has("card-level"))
            if not imgs or not levels:
                continue
            slug = imgs[0].attrs.get("data-card-key", "")
            card = resolve(slug, ids)
            level = int(re.search(r"\d+", levels[0].content()).group())
            mask = (
                2 if slug.endswith("-hero") else 1 if re.search(r"-ev\d+$", slug) else 0
            )
            if not 1 <= level <= 16:
                raise ValueError(f"{slug} 等级 {level} 不在当前支持范围")
            if mask == 2 and not BY_ID[card]["hero"]:
                raise ValueError(f"当前原生版本没有已验证的英雄形态：{slug}")
            cards.append(dict(id=card, slug=slug, level=level, form=mask))
        if len(cards) != 8 or {c["id"] for c in cards} != set(ids):
            raise ValueError("网页卡组、等级与编号不完整")
        tower_nodes = segment.all(
            lambda n: "/card/" in n.attrs.get("href", "")
            and any("/card/" + k in n.attrs["href"] for k in TOWERS)
        )
        if not tower_nodes:
            raise ValueError("页面缺少塔兵等级")
        tower_node = tower_nodes[0]
        tower_key = next(k for k in TOWERS if "/card/" + k in tower_node.attrs["href"])
        labels = (
            tower_node.content()
            + " "
            + " ".join(n.attrs.get("alt", "") for n in tower_node.all(lambda n: True))
        )
        level_match = re.search(r"(?:Lvl|Level)\s*(\d+)", labels, re.I)
        if not level_match:
            raise ValueError("无法读取塔兵等级")
        players.append(
            dict(
                name=name,
                cards=cards,
                tower=TOWERS[tower_key],
                tower_level=int(level_match.group(1)),
            )
        )
    data = extract(Path(path))
    flags = {
        e["source_marker_index"]
        for e in data["events"]
        if e["source_marker_index"] is not None
    }
    if len(flags) != 1 or next(iter(flags)) not in (0, 1):
        raise ValueError("无法确定对局真实阵营")
    flag = next(iter(flags))
    # HTML marker coordinates retain the original arena orientation. Present
    # the imported team at the bottom for BOTH source sides: swap native
    # owners together with coordinates, never coordinates alone.
    ordered = players[::-1]
    owner_by_side = {"red": 0, "blue": 1}
    events = []
    for item in data["events"]:
        owner = owner_by_side[item["side"]]
        event = dict(item, owner=owner, tick=item["source_time_value"] + 1)
        if event["tick"] <= 90:
            raise ValueError("此对局的首个动作早于当前引擎安全起点，暂不支持")
        if item["kind"] == "card_play":
            event["card"] = resolve(
                item["card_slug"], [c["id"] for c in ordered[owner]["cards"]]
            )
            x, y = item["source_x"], item["source_y"]
            if x is None or y is None or not 0 <= x <= 18000 or not 0 <= y <= 32000:
                raise ValueError("落点坐标无效")
            event["x"], event["y"] = (x, y) if flag == 0 else (18000 - x, 32000 - y)
        events.append(event)
    prepared = [
        choose(
            [c["id"] for c in player["cards"]],
            [a["card"] for a in events if a["owner"] == o and a["kind"] == "card_play"],
            LAYOUT[o],
        )
        for o, player in enumerate(ordered)
    ]
    prepared_decks = [x[0] for x in prepared]
    opening = [x[1] + x[2] for x in prepared]
    return dict(
        opening=opening,
        prepared_decks=prepared_decks,
        schema="replay-studio.v1",
        tag=query["tag"],
        url=canonical,
        source_sha256=data["source_sha256"],
        players=ordered,
        events=events,
        seed=SEED,
        duration=max(e["tick"] for e in events) + 200,
        expected=[query.get("opponent_crowns"), query.get("team_crowns")],
    )


def match_for(replay, decks):
    p = replay["players"]
    lookup = [{c["id"]: c for c in a["cards"]} for a in p]
    match = make_match(
        decks,
        level=16,
        forms=[[lookup[o][i]["form"] for i in d] for o, d in enumerate(decks)],
        towers=[a["tower"] for a in p],
        names=[a["name"] for a in p],
    )
    b = match["battle"]
    b["cardlvlmin"] = min(c["level"] for a in p for c in a["cards"])
    offsets = {
        "Common": 1,
        "Rare": 3,
        "Epic": 6,
        "Legendary": 9,
        "Hero": 11,
        "Champion": 11,
    }
    for o, d in enumerate(decks):
        for entry, i in zip(b[f"deck{o}"]["sp"], d):
            entry["l"] = max(
                0, lookup[o][i]["level"] - offsets.get(BY_ID[i]["rarity"], 1)
            )
        b[f"deck{o}"]["sc"][0]["l"] = max(0, p[o]["tower_level"] - 1)
        b["hbd"][o]["kt"] = p[o]["tower_level"]
        b[f"avatar{o}"]["expLevel"] = p[o]["tower_level"]
    return match
