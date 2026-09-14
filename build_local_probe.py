"""Build the current minimal/resident/rendered probe and record provenance."""

import hashlib
import os
import sys
import json
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parent
if os.environ.get("CXX"):
    compiler = Path(os.environ["CXX"])
elif os.environ.get("ANDROID_NDK_HOME"):
    compiler = (
        Path(os.environ["ANDROID_NDK_HOME"])
        / "toolchains/llvm/prebuilt/darwin-x86_64/bin/aarch64-linux-android24-clang++"
    )
else:
    raise SystemExit(
        "Set ANDROID_NDK_HOME or CXX to an Android ARM64 API24 C++ compiler"
    )

build = root / "build"
build.mkdir(exist_ok=True)
sources = [
    root / "vendor/firstlight/probe" / name
    for name in (
        "cr_replay_probe.cpp",
        "native_touch_interceptor.cpp",
        "native_call_arm64.S",
        "remaining_runtime_arm64.S",
    )
]
output = build / "libcrprobe.so"
command = [
    str(compiler),
    "-DCR_MINIMAL_CAPTURE=1",
    "-DCR_RESIDENT_COMMANDS=1",
    "-std=c++17",
    "-O2",
    "-fPIC",
    "-fvisibility=hidden",
    "-Wall",
    "-Wextra",
    "-shared",
    "-Wl,-z,max-page-size=16384",
    "-o",
    str(output),
    *map(str, sources),
    "-llog",
    "-ldl",
    "-lz",
]
subprocess.run(command, cwd=root, check=True)
provenance = {
    "compiler": subprocess.check_output([str(compiler), "--version"], text=True),
    "command": command,
    "source_hashes": {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (root / "vendor/firstlight/probe").iterdir()
        if p.is_file()
    },
    "output_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
}
(build / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
print(provenance["output_sha256"])
