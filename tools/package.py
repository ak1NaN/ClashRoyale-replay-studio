"""Build on the target host: macOS ARM64 or Windows x64."""

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
DATA_FILES = (
    "app/catalog.json",
    "app/icon.png",
    "app/standard_match.json",
    "resources/engine.json",
    "resources/libcrprobe.so",
    "resources/provenance.json",
    "resources/frida.json",
    "resources/frida-server-17.17.0-android-arm64.xz",
)


def main():
    if sys.platform not in ("darwin", "win32"):
        raise SystemExit("Build on macOS or Windows.")
    for name in DATA_FILES:
        if not (ROOT / name).is_file():
            raise SystemExit(f"Missing {name}; run tools/fetch_deps.py first.")
    (ROOT / "build").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="package-", dir=ROOT / "build") as temp:
        stage = Path(temp)
        icon = ROOT / "app/icon.png"
        if sys.platform == "darwin":
            iconset = stage / "ReplayStudio.iconset"
            iconset.mkdir()
            for size in (16, 32, 128, 256, 512):
                for scale in (1, 2):
                    pixels = str(size * scale)
                    suffix = "@2x" if scale == 2 else ""
                    subprocess.run(
                        ["sips", "-z", pixels, pixels, str(ROOT / "app/icon.png"),
                         "--out", str(iconset / f"icon_{size}x{size}{suffix}.png")],
                        check=True, stdout=subprocess.DEVNULL,
                    )
            icon = stage / "ReplayStudio.icns"
            subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(icon)], check=True)
        cmd = [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--windowed",
            "--icon",
            str(icon),
            "--onedir",
            "--name",
            "Replay Studio",
            "--distpath",
            str(ROOT / "dist"),
            "--workpath",
            str(stage / "work"),
            "--specpath",
            str(stage),
            "--paths",
            str(ROOT),
            "--additional-hooks-dir",
            str(ROOT / "tools/hooks"),
            "--hidden-import",
            "frida",
        ]
        if sys.platform == "darwin":
            cmd += ["--osx-bundle-identifier", "local.replay.studio", "--target-arch", "arm64"]
        for name in (
            "QtWebEngineWidgets",
            "QtWebEngineCore",
            "QtQml",
            "QtQuick",
            "QtPdf",
            "QtVirtualKeyboard",
        ):
            cmd += ["--exclude-module", "PySide6." + name]
        for name in DATA_FILES:
            cmd += ["--add-data", f"{ROOT/name}:{Path(name).parent.as_posix()}"]
        cmd += ["--add-data", f'{ROOT/"licenses"}:licenses', str(ROOT / "run.py")]
        subprocess.run(
            (["arch", "-arm64"] if sys.platform == "darwin" else []) + cmd,
            check=True,
            cwd=ROOT,
            env={**os.environ, "PYINSTALLER_CONFIG_DIR": str(stage / "cache")},
        )
        if sys.platform == "darwin":
            shutil.rmtree(ROOT / "dist/Replay Studio")


if __name__ == "__main__":
    main()
