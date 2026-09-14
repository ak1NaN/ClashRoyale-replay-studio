"""Small synchronous client. One controller owns one standard-deck battle."""

from copy import deepcopy
import json
from pathlib import Path
import socket
import time

from .protocol import State


class Engine:
    def __init__(self, host="127.0.0.1", port=26789, timeout=30):
        self.address = (host, port)
        self.timeout = timeout
        self.state = None
        self.wire_bytes = 0
        self.connection = None
        self.stream = None

    def connect(self):
        if self.connection:
            return
        self.connection = socket.create_connection(self.address, timeout=self.timeout)
        self.stream = self.connection.makefile("rb")
        self.connection.sendall(b"session-v1\n")
        response = self._receive()
        if not response.get("ok"):
            self.close()
            raise RuntimeError(response.get("error", "control session failed"))

    def close(self):
        if self.stream:
            self.stream.close()
        if self.connection:
            self.connection.close()
        self.stream = self.connection = None

    def _receive(self):
        payload = self.stream.readline(65537)
        self.wire_bytes += len(payload)
        if not payload or not payload.endswith(b"\n"):
            raise ConnectionError(
                f"no battle engine responded on port {self.address[1]}; "
                f"check the lane is running and not in resident mode"
            )
        return json.loads(payload)

    def request(self, command):
        """Raw diagnostic access; callers must not mutate a managed episode through it."""
        try:
            self.connect()
            self.connection.sendall((command + "\n").encode())
            return self._receive()
        except Exception:
            self.close()
            raise

    def _capture(self, generation=0, cursor=0):
        state = State.decode(self.request(f"minimal {generation} {cursor}"))
        return state

    def reset(self, seed=1, match=None):
        self.state = None
        match = (
            deepcopy(match)
            if match is not None
            else json.loads(Path(__file__).with_name("standard_match.json").read_text())
        )
        match["rndSeed"] = seed
        self.request("configure " + json.dumps(match, separators=(",", ":")))
        self.request(
            "step 90"
        )  # First playable boundary; execute the first action at tick 91.
        self.state = self._capture()
        return self.state


class RenderedEngine(Engine):
    """One paused, exactly stepped battle drawn by the stock game UI."""

    def reset(self, seed=1, match=None):
        self.state = None
        match = (
            deepcopy(match)
            if match is not None
            else json.loads(Path(__file__).with_name("standard_match.json").read_text())
        )
        match["rndSeed"] = seed
        status = self.request("status")
        if status.get("mode") == "resident-headless":
            raise RuntimeError("device is occupied by another engine session")
        accepted = self.request(
            "configure-native " + json.dumps(match, separators=(",", ":"))
        )
        if not accepted.get("ok"):
            raise RuntimeError(
                accepted.get("error", "native renderer rejected the match")
            )
        sequence = accepted["sequence"]
        deadline = time.monotonic() + self.timeout
        while True:
            status = self.request("status")
            if (
                status.get("nativeRenderReady")
                and status.get("nativeRenderLoaded", 0) >= sequence
            ):
                break
            if time.monotonic() >= deadline:
                raise TimeoutError("native renderer did not create the battle scene")
            time.sleep(0.05)
        paused = self.request("pause")
        current_tick = paused["tick"]
        if current_tick < 90:
            self.request(f"advance-native {90 - current_tick}")
        self.state = self._capture()
        if self.state.tick != 90:
            raise RuntimeError(
                f"native renderer missed the first playable tick: {self.state.tick}"
            )
        return self.state

    def set_speed(self, multiplier):
        if multiplier not in (0.25, 0.5, 1, 2, 4, 8, 16):
            raise ValueError("speed must be 0.25, 0.5, 1, 2, 4, 8, or 16")
        return self.request(f"speed {multiplier:g}")

    def resume(self):
        result = self.request("resume")
        if not result.get("ok"):
            raise RuntimeError(result.get("error", "could not resume native renderer"))
        self.state = None
        return result
