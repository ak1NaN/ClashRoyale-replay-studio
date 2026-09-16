import unittest
from tools.package import data_files


class PackageResourcesTests(unittest.TestCase):
    def test_windows_keeps_translated_game_probe_not_arm_server(self):
        files = data_files('win32')
        self.assertIn('resources/libcrprobe-mumu.so', files)
        self.assertIn('resources/mumu-dialogs.js', files)
        self.assertIn('resources/windows-provenance.json', files)
        self.assertIn('resources/frida-server-17.17.0-android-x86_64.xz', files)
        self.assertNotIn('resources/libcrprobe.so', files)
        self.assertFalse(any('android-arm64' in name for name in files))

    def test_mac_keeps_native_arm_resources(self):
        files = data_files('darwin')
        self.assertIn('resources/libcrprobe.so', files)
        self.assertIn('resources/frida-server-17.17.0-android-arm64.xz', files)
        self.assertNotIn('resources/libcrprobe-mumu.so', files)
        self.assertNotIn('resources/mumu-dialogs.js', files)
        self.assertFalse(any('android-x86_64' in name for name in files))

    def test_unsupported_platform_rejected(self):
        with self.assertRaises(ValueError):
            data_files('linux')
