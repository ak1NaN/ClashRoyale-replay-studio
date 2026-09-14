"""Build a host-native standalone app or a small portable source distribution."""

import argparse
from pathlib import Path
import os, shutil, subprocess, sys, tempfile, zipfile

ROOT = Path(__file__).resolve().parents[1]
MODULES = (
    "__init__.py",
    "engine.py",
    "protocol.py",
    "batch.py",
    "observation.py",
    "match_config.py",
    "bootstrap_emulator.py",
    "standard_match.json",
)
DATA_FILES = (
    "standard_match.json",
    "desktop/catalog.json",
    "desktop/icon.svg",
    "vendor/firstlight/supported_engine.json",
    "vendor/firstlight/LICENSE",
    "vendor/firstlight/NOTICE",
    "build/libcrprobe.so",
    "resources/frida.json",
    "resources/frida-server-17.17.0-android-arm64.xz",
)


def copy_runtime(target):
    for name in MODULES:
        shutil.copy2(ROOT / name, target / name)
    for folder in ("desktop", "replay_import"):
        dest = target / folder
        dest.mkdir(exist_ok=True)
        (dest / "__init__.py").touch()
        names = [
            p
            for p in (ROOT / folder).iterdir()
            if p.is_file() and p.suffix in (".py", ".json", ".svg")
        ]
        for p in names:
            if folder == "desktop" or p.name in (
                "__init__.py",
                "extract_royaleapi.py",
                "abilities.py",
            ):
                shutil.copy2(p, dest / p.name)
    shutil.copytree(ROOT / "licenses", target / "licenses", dirs_exist_ok=True)
    for name in DATA_FILES:
        dest = target / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, dest)


def main():
    if sys.platform != "darwin":
        raise SystemExit("This branch builds macOS only.")
    parser = argparse.ArgumentParser()
    parser.add_argument("--portable", action="store_true")
    args = parser.parse_args()
    (ROOT / "build").mkdir(exist_ok=True)
    (ROOT / "dist").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="package-", dir=ROOT / "build"
    ) as directory:
        stage = Path(directory)
        if args.portable:
            pkg = stage / "ReplayStudio"
            pkg.mkdir()
            copy_runtime(pkg)
            for name in (
                "run_desktop.py",
                "start.command",
                "requirements.txt",
                "README.md",
            ):
                shutil.copy2(ROOT / name, pkg / name)
            (pkg / "README.txt").write_text(
                "Mac source bundle. Use Python 3.12 and start.command. See README.md. For normal use, download the standalone .app release instead.\n"
            )
            output = ROOT / "dist/ReplayStudio-portable-source.zip"
            with zipfile.ZipFile(
                output, "w", zipfile.ZIP_DEFLATED, compresslevel=9
            ) as archive:
                for path in sorted(pkg.rglob("*")):
                    if path.is_file():
                        archive.write(path, path.relative_to(stage))
            print(f"{output}: {output.stat().st_size:,} bytes")
            return
        pkg = stage / "studio_native"
        pkg.mkdir()
        copy_runtime(pkg)
        (stage / "main.py").write_text(
            "from studio_native.desktop.gui import main\nmain()\n"
        )
        cmd = [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--windowed",
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
            str(stage),
            "--additional-hooks-dir",
            str(ROOT / "tools/hooks"),
            "--hidden-import",
            "frida",
        ]
        if sys.platform == "darwin":
            cmd += [
                "--osx-bundle-identifier",
                "local.replay.studio",
                "--target-arch",
                "arm64",
            ]
        for module in (
            "QtWebEngineWidgets",
            "QtWebEngineCore",
            "QtQml",
            "QtQuick",
            "QtPdf",
            "QtVirtualKeyboard",
        ):
            cmd += ["--exclude-module", "PySide6." + module]
        for name in DATA_FILES:
            cmd += [
                "--add-data",
                f"{pkg/name}:studio_native/{Path(name).parent.as_posix()}",
            ]
        cmd += ["--add-data", f"{pkg/'licenses'}:studio_native/licenses"]
        cmd += [str(stage / "main.py")]
        if sys.platform == "darwin":
            cmd = ["arch", "-arm64"] + cmd
        subprocess.run(
            cmd,
            check=True,
            cwd=ROOT,
            env={**os.environ, "PYINSTALLER_CONFIG_DIR": str(stage / "cache")},
        )
        if sys.platform == "darwin":
            # BUNDLE copies COLLECT into .app; keep only the user-facing bundle.
            shutil.rmtree(ROOT / "dist/Replay Studio")


if __name__ == "__main__":
    main()
