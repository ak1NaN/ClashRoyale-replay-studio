"""Exercise the real replay lifecycle and preserve diagnostics on failure."""

import argparse
import json
from pathlib import Path
import sys
import time
import traceback

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.device import DATA
from app.engine import Engine
from app.importer import convert
from app.runtime import Runtime


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("html", type=Path)
    parser.add_argument("--probe", type=Path, help="Use a locally built probe for development")
    parser.add_argument("--play-seconds", type=int, default=0, help="Continuously play at 1x before other checks")
    parser.add_argument("--require-end", action="store_true", help="Fail unless continuous playback reaches the match result")
    args = parser.parse_args()
    if args.play_seconds < 0 or (args.require_end and not args.play_seconds):
        parser.error("--require-end needs a positive --play-seconds value")
    replay = convert(args.html)
    folder = DATA / time.strftime("replay-check-%Y%m%d-%H%M%S")
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / "trace.log").open("w", encoding="utf-8") as trace:
        def log(message, quiet=False):
            line = f"{time.strftime('%H:%M:%S')} {message}"
            if not quiet:
                print(line, flush=True)
            trace.write(line + "\n")
            trace.flush()

        runtime = Runtime(log)
        if args.probe:
            runtime.probe_path = args.probe.resolve(strict=True)
        original = Engine.request

        def request(engine, command):
            log("command " + command.split(" ", 1)[0], quiet=command == "status")
            result = original(engine, command)
            if result.get("ok") is False:
                log("rejected " + json.dumps(result, ensure_ascii=True))
            if command == "status":
                log("status " + json.dumps(result, ensure_ascii=True), quiet=True)
            return result

        Engine.request = request
        success = False
        try:
            log(f"Imported {len(replay['events'])} events")
            log("loaded " + json.dumps(runtime.load(replay), ensure_ascii=True))
            if args.play_seconds:
                runtime.play()
                previous = 90
                for elapsed in range(0, args.play_seconds, 5):
                    time.sleep(min(5, args.play_seconds - elapsed))
                    state = runtime.status()
                    log(f"continuous playback tick={state['tick']} finalized={state.get('finalized')}")
                    if state['tick'] <= previous and not state.get('finalized'):
                        raise RuntimeError('Visible playback stopped advancing')
                    previous = state['tick']
                    if elapsed % 20 == 0:
                        runtime.shell('screencap', '-p', '/sdcard/replay-studio-check.png')
                        runtime.adb('pull', '/sdcard/replay-studio-check.png', folder / f'play-{elapsed + 5}.png')
                    if state.get('finalized'):
                        break
                runtime.pause()
                if args.require_end and not state.get('finalized'):
                    raise RuntimeError('Continuous playback did not reach the match result')
            for tick in (90, runtime.cache_end // 2, runtime.cache_end, 90):
                state = runtime.seek(tick)
                if state["tick"] != tick:
                    raise RuntimeError(f"Seek mismatch: {state['tick']} != {tick}")
                log(f"seek verified {tick}")
            for speed in (0.25, 0.5, 1, 2, 4, 8, 16):
                runtime.set_speed(speed)
                before = runtime.status()['tick']
                runtime.play()
                time.sleep(0.5)
                state = runtime.pause()
                if state['tick'] <= before and not state.get('finalized'):
                    raise RuntimeError(f'Playback did not advance at {speed}x')
                log(f"play/pause {speed}x tick={state['tick']}")
            success = True
        except Exception:
            log(traceback.format_exc())
        finally:
            try:
                result = runtime.shell("logcat", "-d", "-t", "1500", check=False)
                (folder / "logcat.txt").write_text(result.stdout, encoding="utf-8")
                uid = runtime.shell(
                    "stat", "-c", "%u", "/data/user/0/nullsroyale.rel.free", check=False
                ).stdout.strip()
                if uid.isdigit():
                    result = runtime.shell(
                        "cat", f"/data/tombstones/app/nullsroyale.rel.free/{uid}.log", check=False
                    )
                    (folder / "tombstone.txt").write_text(result.stdout, encoding="utf-8")
            except Exception as error:
                log(f"logcat unavailable: {error}")
            try:
                if runtime.offline:
                    runtime.online()
                else:
                    runtime.abort_prepare()
            except Exception:
                success = False
                log("Cleanup failed: " + traceback.format_exc())
            Engine.request = original
        log(f"{'PASS' if success else 'FAIL'} diagnostics: {folder}")
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
