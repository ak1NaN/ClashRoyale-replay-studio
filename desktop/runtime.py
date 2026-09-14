"""Prepare and control one replay through a device session and per-tick cache."""

import json
import threading
import time
from .. import Engine, RenderedEngine
from .. import bootstrap_emulator as boot
from .device import DeviceSession, DATA
from .importer import choose, compatible, match_for, LAYOUT


class Runtime(DeviceSession):
    def __init__(self, progress=lambda _: None):
        super().__init__(progress)
        self.replay = None
        self.match = None
        self.receipts = []
        self.checkpoints = {}
        self.speed = 1
        self.cache_ready = False
        self.hand_cache = {}
        self.cancel = threading.Event()
        self.precompute_audit = []
        self.cache_end = 90
        self.cache_seconds = 0
        self.cache_bytes = 0

    def online(self):
        self.connect_device()
        try:
            self.clear_cache()
        except Exception:
            self.progress("引擎连接已断开，将关闭游戏进程以释放缓存")
        self.close_connection()
        # Unload process-local hooks before restoring networking.
        self.shell("am", "force-stop", boot.PACKAGE)
        if self.session:
            try:
                self.session.detach()
            except Exception:
                pass
        self.session = self.script = None
        self.replay = self.match = None
        self.rules(False)
        try:
            self.stop_frida()
        finally:
            self.start_game()
        self.progress("已停止 Frida 并恢复游戏联网，可正常游玩")
        return {"offline": False}

    def load(self, replay):
        self.cancel.clear()
        if self.engine is None or not self.offline:
            self.prepare_engine()
        self.discard_replay()
        if self.engine is None:
            self.prepare_engine()
        self.replay = replay
        e = self.engine
        status = e.request("status")
        if status.get("mode") == "resident-headless":
            raise RuntimeError(
                "批量引擎正在占用设备；请先关闭 Batch 并调用 stop_resident"
            )
        plays = [
            [
                a["card"]
                for a in replay["events"]
                if a["owner"] == o and a["kind"] == "card_play"
            ]
            for o in (0, 1)
        ]
        decks = replay.get("prepared_decks")
        opening = replay.get("opening")
        if decks is None or opening is None:
            prepared = [
                choose([c["id"] for c in p["cards"]], plays[o], LAYOUT[o])
                for o, p in enumerate(replay["players"])
            ]
            decks = decks if decks is not None else [x[0] for x in prepared]
            opening = (
                opening if opening is not None else [x[1] + x[2] for x in prepared]
            )
        self.progress("正在准备无画面对局…")
        try:
            self.match = match_for(replay, decks)
            Engine.reset(e, seed=replay["seed"], match=self.match)
            self.checked(
                "opening-deal "
                + " ".join(str(card) for order in opening for card in order)
            )
            state = e._capture()
            if not all(
                compatible([c.card for c in p.hand], list(p.cycle), plays[o])
                for o, p in enumerate(state.players)
            ):
                raise RuntimeError("预计算初手校验失败，已停止模拟")
            opening_snapshot = self.checkpoint()
            self.schedule()
            self.precompute()
            if self.cancel.is_set():
                raise RuntimeError("已取消预演算")
            self.progress(
                f"无画面缓存完成（{self.cache_seconds:.2f} 秒），正在打开回放画面…"
            )
            e.reset(seed=replay["seed"], match=self.match)
            self.checked("cache-adopt")
            self.checked(f"restore {opening_snapshot['handle']}")
            self.checked("replay-schedule-clear")
            self.schedule()
            self.cache_ready = True
        except Exception:
            self.clear_cache()
            raise
        self.progress("整场缓存完成，可以播放或拖动时间轴")
        return self.status()

    def schedule(self, after=90):
        self.receipts = []
        for a in self.replay["events"]:
            if a["tick"] <= after:
                continue
            cmd = (
                f"replay-schedule-ability {a['owner']} - {a['tick']}"
                if a["kind"] == "ability"
                else f"replay-schedule-card {a['owner']} {a['card']} {a['x']} {a['y']} {a['tick']}"
            )
            q = self.engine.request(cmd)
            if not q.get("ok"):
                raise RuntimeError(q.get("error", "无法提交回放动作"))
            self.receipts.append(q["sequence"])

    def checked(self, command):
        result = self.engine.request(command)
        if not result.get("ok"):
            raise RuntimeError(result.get("error", "原生操作未完成"))
        return result

    def discard_replay(self):
        connection = self.engine.connection if self.engine else None
        prior_timeout = connection.gettimeout() if connection else None
        if connection:
            connection.settimeout(3)
        try:
            self.clear_cache()
        except (ConnectionError, OSError, RuntimeError):
            # A terminated game cannot acknowledge snapshot release. Its process
            # owns those snapshots; prepare_engine will restart it before reuse.
            self.close_connection()
            self.reconnect_required = True
            self.progress("旧回放连接已失效，将重新准备引擎")
        finally:
            if connection and self.engine:
                connection.settimeout(prior_timeout)
        self.replay = None

    def clear_cache(self):
        try:
            if self.engine and self.match:
                self.checked("pause")
                self.checked("cache-clear")
        finally:
            self.cache_ready = False
            self.checkpoints.clear()
            self.hand_cache.clear()
            self.match = None
            self.receipts = []
            self.precompute_audit = []
            self.cache_end = 90
            self.cache_seconds = 0
            self.cache_bytes = 0

    def checkpoint(self):
        snap = self.checked("snapshot-create")
        self.checkpoints[int(snap["tick"])] = snap
        return snap

    def precompute(self):
        started = time.monotonic()
        current = 90
        # Hands and cycle are serialized on every tick; index those snapshots
        # instead of polling/duplicating the same native state over the socket.
        self.hand_cache[90] = self.checkpoints[90]["handle"]
        while current < 7200:
            if self.cancel.is_set():
                raise RuntimeError("已取消预演算，缓存已清理")
            stop = min(current + 512, 7200)
            result = self.checked(f"cache-step {stop-current}")
            for snap in result["snapshots"]:
                self.checkpoints[int(snap["tick"])] = snap
                self.hand_cache[int(snap["tick"])] = snap["handle"]
            state = self.engine.request("status")
            tick = int(state["tick"])
            if tick <= current:
                raise RuntimeError("预演算没有推进，已停止")
            current = tick
            self.progress(
                f'正在高速演算并缓存… {current/20:.1f} 秒 / 预计 {self.replay["duration"]/20:.0f} 秒'
            )
            if state.get("finalized"):
                break
        if not state.get("finalized"):
            raise RuntimeError("预演算超过 6 分钟仍未结束，未进入回放")
        if set(self.checkpoints) != set(range(90, current + 1)):
            raise RuntimeError("逐帧缓存不完整，未进入回放")
        self.cache_seconds = time.monotonic() - started
        self.cache_end = current
        self.cache_bytes = sum(s["bytes"] for s in self.checkpoints.values())
        self.precompute_audit = [
            self.engine.request(f"replay-schedule-status {seq}")
            for seq in self.receipts
        ]
        if any(a.get("state") == "failed" for a in self.precompute_audit):
            raise RuntimeError("预演算存在失败动作，请检查对局数据")

    def status(self):
        if not self.engine:
            return {"offline": self.offline, "ready": False}
        s = self.engine.request("status")
        s["offline"] = self.offline
        if self.cache_ready:
            s.update(
                cacheEnd=self.cache_end,
                cacheSeconds=self.cache_seconds,
                cacheBytes=self.cache_bytes,
            )
        return s

    def play(self):
        if self.status().get("finalized"):
            self.seek(90)
        self.engine.set_speed(self.speed)
        self.engine.resume()
        return self.status()

    def pause(self):
        self.checked("pause")
        return self.status()

    def set_speed(self, value):
        self.speed = value
        if self.engine:
            self.engine.set_speed(value)
        return self.status()

    def seek(self, tick):
        if not self.cache_ready:
            raise RuntimeError("请等待整场缓存完成")
        target = max(90, min(int(tick), self.cache_end))
        snap = self.checkpoints[target]
        self.checked("pause")
        self.checked(f"restore {snap['handle']}")
        self.checked("replay-schedule-clear")
        self.schedule(after=target)
        return self.status()

    def audit(self):
        statuses = [
            self.engine.request(f"replay-schedule-status {seq}")
            for seq in self.receipts
        ]
        result = {"status": self.status(), "actions": statuses}
        (DATA / (self.replay["tag"] + "-audit.json")).write_text(
            json.dumps(result, indent=2)
        )
        return result

    def demo(self, mode):
        from .. import Engine, Batch, Play, stop_resident

        self.prepare_engine()
        self.close_connection()
        self.replay = self.match = None
        if mode == "batch":
            client = Batch(battles=4, port=self.cfg["port"])
            try:
                states = client.reset(seed=1)
                states = client.step([(Play(0, 0, 3500, 13000),)] * 4, ticks=100)
                result = {
                    "mode": "批量无画面",
                    "battles": 4,
                    "ticks": [s.tick for s in states],
                }
            finally:
                client.close()
                stop_resident(self.cfg["port"])
        else:
            client = Engine(port=self.cfg["port"])
            try:
                client.reset(seed=1)
                t = client.step([Play(0, 0, 3500, 13000)], ticks=100)
                result = {
                    "mode": "单场无画面",
                    "tick": t.state.tick,
                    "executed": t.executed,
                }
            finally:
                client.close()
        self.engine = RenderedEngine(port=self.cfg["port"], timeout=90)
        return result
