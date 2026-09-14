# Third-party notices

Replay Studio is derived from Jason-XII/Clash-Royale-Battle-Engine and FirstLight CR.
Original FirstLight notices and Apache-2.0 terms are in vendor/firstlight/.
Local changes add the HTML importer, desktop interface, per-tick replay cache,
device setup, and macOS distribution tools. No game APK, libg.so, resource pack,
MuMu binary, or saved player HTML is distributed.

The macOS application bundles unmodified Python 3.12, PySide6/Qt 6.8.3,
Shiboken6 6.8.3, Frida 17.17.0 and the PyInstaller bootloader.
MuMu's ADB is used from the user's installation and is not redistributed.

- Python: https://www.python.org/downloads/source/ (PSF license)
- PySide6 / Shiboken6: https://code.qt.io/cgit/pyside/pyside-setup.git/?h=v6.8.3
- Qt: https://code.qt.io/cgit/qt/qtbase.git/?h=v6.8.3 (LGPL-3.0; see included license texts)
- Frida: https://github.com/frida/frida/releases/tag/17.17.0
- Frida Core: https://github.com/frida/frida-core/tree/17.17.0 (wxWindows Library Licence 3.1)
- PyInstaller: https://github.com/pyinstaller/pyinstaller/tree/v6.22.2 (GPL with bootloader exception)

Source builds allow replacement/relinking of Qt/PySide6 libraries. Reverse
engineering for debugging modifications to LGPL-covered libraries is not
restricted by this project. The application is an ordinary onedir bundle;
macOS may require re-signing after a library is replaced.
