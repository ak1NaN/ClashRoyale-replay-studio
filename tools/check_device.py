"""Read-only compatibility report; never roots, injects, or changes networking."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.device import PACKAGE, run, settings


def main():
    cfg = settings()
    adb = cfg['adb']
    serial = cfg['serial']
    if ':' in serial:
        run([adb, 'connect', serial], timeout=5)
    def shell(*args):
        return run([adb, '-s', serial, 'shell', *args], check=False).stdout.strip()
    run([adb, '-s', serial, 'get-state'])
    report = {
        'host': sys.platform,
        'abi': shell('getprop', 'ro.product.cpu.abi'),
        'kernel_arch': shell('uname', '-m'),
        'abis': shell('getprop', 'ro.product.cpu.abilist'),
        'native_bridge': shell('getprop', 'ro.dalvik.vm.native.bridge'),
        'android': shell('getprop', 'ro.build.version.release'),
        'shell_uid': shell('id', '-u'),
    }
    package = shell('dumpsys', 'package', PACKAGE)
    report['game'] = [line.strip() for line in package.splitlines()
                      if any(key in line for key in ('versionName=', 'primaryCpuAbi=', 'nativeLibraryDir='))]
    report['probe_architecture_supported'] = (
        report['abi'] == 'arm64-v8a'
        or (report['abi'] == 'x86_64' and report['native_bridge'] == 'libnb.so')
    )
    report['injection_mode'] = (
        'native-arm64'
        if report['abi'] == 'arm64-v8a'
        else 'mumu-native-bridge-x86_64'
        if report['probe_architecture_supported']
        else 'unsupported'
    )
    target = Path.cwd() / 'device-report.json'
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print('Report:', target)


if __name__ == '__main__':
    main()
