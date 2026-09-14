"""Widgets-only app: PDF images and QML virtual keyboards are unused."""

from pathlib import Path
from PyInstaller.utils.hooks.qt import add_qt6_dependencies

hiddenimports, binaries, datas = add_qt6_dependencies(__file__)
binaries = [
    (src, dst)
    for src, dst in binaries
    if not any(name in Path(src).name.lower() for name in ("qpdf", "qtvirtualkeyboard"))
]
