"""Rebuild the MuMu ARM64 probe from the pinned baseline and reviewed patch."""

import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
BASELINE = "v0.1.0-macos-preview"
SOURCE = Path("vendor/firstlight/probe")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ndk", type=Path, required=True)
    args = parser.parse_args()
    compiler = args.ndk.resolve() / "toolchains/llvm/prebuilt/windows-x86_64/bin/clang++.exe"
    if not compiler.is_file():
        parser.error("--ndk must point to an extracted Windows Android NDK")
    build = ROOT / "build"
    build.mkdir(exist_ok=True)
    archive = subprocess.check_output(
        ["git", "archive", BASELINE, SOURCE.as_posix()], cwd=ROOT
    )
    provenance = json.loads((ROOT / "resources/provenance.json").read_text(encoding="utf-8"))
    patch = ROOT / "resources/windows-probe.patch"
    with tempfile.TemporaryDirectory(prefix="windows-probe-", dir=build) as temp:
        stage = Path(temp)
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            tar.extractall(stage, filter="data")
        for name, expected in provenance["source_hashes"].items():
            source = stage / name
            data = source.read_bytes().replace(b"\r\n", b"\n")
            if hashlib.sha256(data).hexdigest() != expected:
                raise RuntimeError(f"Baseline source hash mismatch: {name}")
            source.write_bytes(data)
        subprocess.run([
            "git", "apply", "--directory=" + stage.relative_to(ROOT).as_posix(), str(patch)
        ], cwd=ROOT, check=True)
        files = ["cr_replay_probe.cpp", "native_touch_interceptor.cpp",
                 "native_call_arm64.S", "remaining_runtime_arm64.S"]
        output = ROOT / "resources/libcrprobe-mumu.so"
        flags = ["--target=aarch64-linux-android24", "-DCR_MINIMAL_CAPTURE=1",
                 "-DCR_RESIDENT_COMMANDS=1", "-DCR_MUMU_MAINLOOP=1", "-std=c++17",
                 "-O2", "-fPIC", "-fvisibility=hidden", "-shared",
                 "-Wl,-z,max-page-size=16384"]
        subprocess.run([str(compiler), *flags, "-o", str(output),
                        *(str(stage / SOURCE / name) for name in files),
                        "-llog", "-ldl", "-lz"], check=True)
        metadata = {
            "baseline": BASELINE,
            "baseline_source_sha256": provenance["source_hashes"],
            "patch": "resources/windows-probe.patch",
            "patch_sha256": hashlib.sha256(patch.read_bytes().replace(b"\r\n", b"\n")).hexdigest(),
            "compiler": subprocess.check_output([str(compiler), "--version"], text=True),
            "flags": flags,
            "output_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        }
        # No machine-specific paths belong in the distributable provenance.
        metadata["compiler"] = metadata["compiler"].replace(str(compiler.parent), "${NDK_BIN}")
        metadata["compiler"] = metadata["compiler"].replace(compiler.parent.as_posix(), "${NDK_BIN}")
        (ROOT / "resources/windows-provenance.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"Built {output.name}: {metadata['output_sha256']}")


if __name__ == "__main__":
    main()
