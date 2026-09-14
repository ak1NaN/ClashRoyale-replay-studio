"""Small synchronous client. One controller owns one standard-deck battle."""
from dataclasses import dataclass
from copy import deepcopy
import json
from pathlib import Path
import socket
import time

from .protocol import State


@dataclass(frozen=True)
class Play:
    owner: int
    slot: int
    x: int
    y: int


@dataclass(frozen=True)
class Ability:
    owner: int
    name_hints: str = "-"  # Resolve the owner's unique ready native ability.


@dataclass(frozen=True)
class Transition:
    state: State
    advanced: int
    executed: tuple[bool | None, ...]  # None means submitted but consumption unverified.


class Engine:
    def __init__(self, host='127.0.0.1', port=26789, timeout=30):
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
        self.stream = self.connection.makefile('rb')
        self.connection.sendall(b'session-v1\n')
        response = self._receive()
        if not response.get('ok'):
            self.close()
            raise RuntimeError(response.get('error', 'control session failed'))

    def close(self):
        if self.stream:
            self.stream.close()
        if self.connection:
            self.connection.close()
        self.stream = self.connection = None

    def _receive(self):
        payload = self.stream.readline(65537)
        self.wire_bytes += len(payload)
        if not payload or not payload.endswith(b'\n'):
            raise ConnectionError(
                f'no battle engine responded on port {self.address[1]}; '
                f'check the lane is running and not in resident mode')
        return json.loads(payload)

    def request(self, command):
        """Raw diagnostic access; callers must not mutate a managed episode through it."""
        try:
            self.connect()
            self.connection.sendall((command + '\n').encode())
            return self._receive()
        except Exception:
            self.close()
            raise

    def _capture(self, generation=0, cursor=0):
        state = State.decode(self.request(f'minimal {generation} {cursor}'))
        return state

    def reset(self, seed=1, match=None):
        self.state = None
        match = deepcopy(match) if match is not None else json.loads(Path(__file__).with_name('standard_match.json').read_text())
        match['rndSeed'] = seed
        self.request('configure ' + json.dumps(match, separators=(',', ':')))
        self.request('step 90')  # First playable boundary; execute the first action at tick 91.
        self.state = self._capture()
        return self.state

    def step(self, actions=(), ticks=5):
        before = self.state
        actions = tuple(actions)
        cards = []
        fields = ['minimal-transition', str(before.generation), str(before.next_sequence),
                  str(ticks), str(len(actions))]
        for action in actions:
            player = before.players[action.owner]
            card = next((c for c in player.hand if c.slot == action.slot), None)
            cards.append(card.card)
            fields.extend(map(str, (action.owner, action.slot, action.x, action.y)))
        # A partial transport failure invalidates this client until reset; never replay writes.
        self.state = None
        after = State.decode(self.request(' '.join(fields)))
        advanced = after.tick - before.tick
        executed = tuple(any(e.owner == a.owner and (e.root_card or e.card) == card and e.tick == before.tick + 1
                             for e in after.plays) for a, card in zip(actions, cards))
        self.state = after
        return Transition(after, advanced, executed)


class RenderedEngine(Engine):
    """One paused, exactly stepped battle drawn by the stock game UI."""

    def reset(self, seed=1, match=None):
        self.state = None
        match = deepcopy(match) if match is not None else json.loads(Path(__file__).with_name('standard_match.json').read_text())
        match['rndSeed'] = seed
        status = self.request('status')
        if status.get('mode') == 'resident-headless':
            raise RuntimeError('close the active Batch and call stop_resident() first')
        accepted = self.request('configure-native ' + json.dumps(match, separators=(',', ':')))
        if not accepted.get('ok'):
            raise RuntimeError(accepted.get('error', 'native renderer rejected the match'))
        sequence = accepted['sequence']
        deadline = time.monotonic() + self.timeout
        while True:
            status = self.request('status')
            if status.get('nativeRenderReady') and status.get('nativeRenderLoaded', 0) >= sequence:
                break
            if time.monotonic() >= deadline:
                raise TimeoutError('native renderer did not create the battle scene')
            time.sleep(0.05)
        paused = self.request('pause')
        current_tick = paused['tick']
        if current_tick < 90:
            self.request(f'advance-native {90 - current_tick}')
        self.state = self._capture()
        if self.state.tick != 90:
            raise RuntimeError(f'native renderer missed the first playable tick: {self.state.tick}')
        return self.state

    def step(self, actions=(), ticks=5):
        before = self.state
        if before is None:
            raise RuntimeError('reset or pause the rendered engine before stepping it')
        if not 1 <= ticks <= 1_000_000:
            raise ValueError('ticks must be between 1 and 1,000,000')
        actions = tuple(actions)
        cards = []
        for action in actions:
            if action.owner not in (0, 1):
                raise ValueError('owner must be 0 or 1')
            if isinstance(action, Ability):
                import re
                if action.name_hints != '-' and (not re.fullmatch(r'[A-Za-z0-9]+(?:,[A-Za-z0-9]+)*', action.name_hints) or len(action.name_hints) > 260):
                    raise ValueError('ability name_hints must contain comma-separated native name tokens')
                cards.append(None)
                continue
            player = before.players[action.owner]
            card = next((card for card in player.hand if card.slot == action.slot), None)
            if card is None:
                raise ValueError(f'hand slot {action.slot} is unavailable for owner {action.owner}')
            cards.append(card.card)
        self.state = None
        sequences = []
        for action, card in zip(actions, cards):
            command = (f'replay-schedule-ability {action.owner} {action.name_hints} {before.tick + 1}'
                       if isinstance(action, Ability) else
                       f'replay-schedule-card {action.owner} {card} {action.x} {action.y} {before.tick + 1}')
            queued = self.request(command)
            if not queued.get('ok'):
                raise RuntimeError(queued.get('error', 'could not queue rendered action'))
            sequences.append(queued['sequence'])
        first_ticks = 1 if any(isinstance(a, Ability) for a in actions) else ticks
        advanced = self.request(f'advance-native {first_ticks}')
        if not advanced.get('ok'):
            raise RuntimeError(advanced.get('error', 'could not advance native renderer'))
        after = self._capture(before.generation, before.next_sequence)
        self.last_action_receipts = tuple(self.request(f'replay-schedule-status {sequence}') for sequence in sequences)
        executed = tuple(
            _ability_execution(before, after, action, receipt)
            if isinstance(action, Ability) else
            any(event.owner == action.owner and (event.root_card or event.card) == card
                and event.tick == before.tick + 1 for event in after.plays)
            for action, card, receipt in zip(actions, cards, self.last_action_receipts))
        if ticks > first_ticks:
            advanced = self.request(f'advance-native {ticks - first_ticks}')
            if not advanced.get('ok'):
                raise RuntimeError(advanced.get('error', 'could not advance native renderer'))
            after = self._capture(before.generation, before.next_sequence)
        self.state = after
        return Transition(after, after.tick - before.tick, executed)

    def set_speed(self, multiplier):
        if multiplier not in (0.25, 0.5, 1, 2, 4, 8, 16):
            raise ValueError('speed must be 0.25, 0.5, 1, 2, 4, 8, or 16')
        return self.request(f'speed {multiplier:g}')

    def pause(self):
        result = self.request('pause')
        if not result.get('ok'):
            raise RuntimeError(result.get('error', 'could not pause native renderer'))
        self.state = self._capture()
        return self.state

    def resume(self):
        result = self.request('resume')
        if not result.get('ok'):
            raise RuntimeError(result.get('error', 'could not resume native renderer'))
        self.state = None
        return result


def _ability_execution(before, after, action, receipt):
    """Queue acceptance alone is not proof that the native command took effect."""
    if receipt.get('state') == 'failed':
        return False
    if receipt.get('state') != 'succeeded':
        return None
    old = (before.players[action.owner].runtime or {}).get('abilityRuntime') or []
    new = (after.players[action.owner].runtime or {}).get('abilityRuntime') or []
    hints = action.name_hints.lower().split(',')
    candidates = [a for a in old if a.get('available') and
                  (hints == ['-'] or any(h in a.get('actionDataName', '').lower() for h in hints))]
    if len(candidates) != 1:
        return None
    previous = candidates[0]
    for current in new:
        if (current.get('controllerSlot'), current.get('actionDataGlobalId')) != (
                previous.get('controllerSlot'), previous.get('actionDataGlobalId')):
            continue
        if (current['remainingChargesRaw'] < previous['remainingChargesRaw'] or
                current['remainingCooldownMs'] > previous['remainingCooldownMs']):
            return True
    return None
