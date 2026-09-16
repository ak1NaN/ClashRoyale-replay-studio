"""Device settings, scoped networking, and the injected game session."""

import hashlib
import lzma
import tempfile
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import time
import re
from .engine import RenderedEngine

PACKAGE = "nullsroyale.rel.free"
ACTIVITY = f"{PACKAGE}/com.supercell.clashroyale.GameApp"
RULE_COMMENT = "crack-cr-offline"
GLOBAL_RULE_COMMENT = "crack-cr-offline-emulator"

ROOT = Path(__file__).resolve().parents[1]
FROZEN = getattr(sys, "frozen", False)
APP_DIR = Path(sys.executable).resolve().parent if FROZEN else ROOT
if FROZEN and sys.platform == "darwin":
    APP_DIR = next(
        (p.parent for p in Path(sys.executable).parents if p.suffix == ".app"), APP_DIR
    )


def data_directory():
    if os.environ.get("REPLAY_STUDIO_DATA"):
        return Path(os.environ["REPLAY_STUDIO_DATA"]).expanduser()
    if not FROZEN or (APP_DIR / "portable.flag").exists():
        return APP_DIR / "data"
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/ReplayStudio"
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "ReplayStudio"


DATA = data_directory()
DATA.mkdir(exist_ok=True, parents=True)
SETTINGS = DATA / "settings.json"
_MUMU_SERIAL_CACHE = {}
_MUMU_ROOTS_CACHE = None


def windows_mumu_roots():
    """Find MuMu installations, including non-system-drive installs."""
    global _MUMU_ROOTS_CACHE
    roots = []
    if sys.platform != "win32":
        return roots
    if _MUMU_ROOTS_CACHE is not None:
        return list(_MUMU_ROOTS_CACHE)
    for key in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
        base = os.environ.get(key)
        if base:
            roots.extend((Path(base) / "Netease/MuMu", Path(base) / "MuMu"))
    try:
        import winreg

        locations = (
            (winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_64KEY),
            (winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_32KEY),
            (winreg.HKEY_CURRENT_USER, 0),
        )
        uninstall = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
        for hive, view in locations:
            for subkey in ("MuMuPlayer", "MuMuPlayerGlobal", "MuMuPlayer-12.0", "MuMu"):
                try:
                    with winreg.OpenKey(
                        hive, uninstall + "\\" + subkey, 0, winreg.KEY_READ | view
                    ) as item:
                        name = str(winreg.QueryValueEx(item, "DisplayName")[0])
                        path = str(winreg.QueryValueEx(item, "InstallLocation")[0])
                    if "mumu" in name.lower() and path:
                        roots.append(Path(path))
                except OSError:
                    continue
    except (ImportError, OSError):
        pass
    _MUMU_ROOTS_CACHE = tuple(dict.fromkeys(roots))
    return list(_MUMU_ROOTS_CACHE)


def defaults():
    exe = "adb.exe" if sys.platform == "win32" else "adb"
    candidates = [APP_DIR / "platform-tools" / exe, APP_DIR / exe]
    managers = []
    if sys.platform == "darwin":
        for base in (Path("/Applications"), Path.home() / "Applications"):
            candidates.append(
                base
                / "MuMuPlayer.app/Contents/MacOS/MuMuEmulator.app/Contents/MacOS/tools/adb"
            )
    if sys.platform == "win32":
        for root in windows_mumu_roots():
            candidates.append(root / "nx_main/adb.exe")
            device_root = root / "nx_device"
            if device_root.is_dir():
                candidates.extend(
                    sorted(device_root.glob("*/shell/adb.exe"), reverse=True)
                )
            managers.append(root / "nx_main/MuMuManager.exe")
        for key in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
            base = os.environ.get(key)
            if base:
                for relative in ("Netease/MuMu/nx_device/12.0/shell/adb.exe",
                                 "Netease/MuMuPlayer-12.0/shell/adb.exe",
                                 "Netease/MuMuPlayerGlobal-12.0/shell/adb.exe",
                                 "MuMuPlayer-12.0/shell/adb.exe",
                                 "Nemu/vmonitor/bin/adb_server.exe"):
                    candidates.append(Path(base) / relative)
    for name in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        if os.environ.get(name):
            candidates.append(Path(os.environ[name]) / "platform-tools" / exe)
    if not FROZEN:
        candidates.append(ROOT.parent / ".android/sdk/platform-tools" / exe)
    candidates.extend(
        [
            Path.home() / "Library/Android/sdk/platform-tools" / exe,
            Path.home() / "AppData/Local/Android/Sdk/platform-tools" / exe,
        ]
    )
    local = next((p for p in candidates if p.is_file()), None)
    serial = "127.0.0.1:16384"
    for manager in managers:
        if not manager.is_file():
            continue
        try:
            cache_key = str(manager.resolve())
            if cache_key not in _MUMU_SERIAL_CACHE:
                options = (
                    {"creationflags": subprocess.CREATE_NO_WINDOW}
                    if sys.platform == "win32"
                    else {}
                )
                result = subprocess.run(
                    [str(manager), "info", "--vmindex", "all"],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=3,
                    **options,
                )
                _MUMU_SERIAL_CACHE[cache_key] = result.stdout if result.returncode == 0 else ""
            info = json.loads(_MUMU_SERIAL_CACHE[cache_key])
            instances = info.values() if isinstance(info, dict) and "index" not in info else (info,)
            active = next(
                (item for item in instances if item.get("is_android_started") and item.get("adb_port")),
                None,
            )
            if active:
                serial = f"{active.get('adb_host_ip', '127.0.0.1')}:{active['adb_port']}"
                break
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
            continue
    return {
        "adb": str(local) if local else shutil.which(exe) or exe,
        "serial": serial,
        "port": 26789,
    }


def settings():
    saved = {}
    if SETTINGS.exists():
        loaded = json.loads(SETTINGS.read_text(encoding="utf-8-sig"))
        saved = {k: loaded[k] for k in ("adb", "serial", "port") if k in loaded}
    cfg = saved if len(saved) == 3 else {**defaults(), **saved}
    adb = os.path.expandvars(os.path.expanduser(cfg["adb"]))
    if not Path(adb).is_absolute() and ("/" in adb or "\\" in adb):
        adb = str(APP_DIR / adb)
    cfg["adb"] = adb
    return cfg


def run(args, timeout=30, check=True):
    options = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
    p = subprocess.run(
        [str(a) for a in args], capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=timeout, **options
    )
    if check and p.returncode:
        raise RuntimeError(p.stderr.strip() or p.stdout.strip() or "命令执行失败")
    return p


class DeviceSession:
    """Own one emulator connection and its process-local engine injection."""

    def __init__(self, progress=lambda _: None):
        self.progress = progress
        self.cfg = settings()
        self.engine = None
        self.reconnect_required = False
        self.session = None
        self.script = None
        self.dialog_script = None
        self.offline = False

    def adb(self, *args, check=True):
        return run([self.cfg["adb"], "-s", self.cfg["serial"], *args], check=check)

    def shell(self, *args, check=True):
        return self.adb("shell", *args, check=check)

    def connect_device(self):
        self.cfg = settings()
        if ":" in self.cfg["serial"]:
            run(
                [self.cfg["adb"], "connect", self.cfg["serial"]], timeout=5, check=False
            )
        if self.adb("get-state", check=False).stdout.strip() != "device":
            raise RuntimeError(
                "请先启动模拟器，再点击准备回放；连接设置中可检查 ADB 地址"
            )
        if self.shell("getprop", "sys.boot_completed").stdout.strip() != "1":
            raise RuntimeError("模拟器尚未完成开机，请进入安卓桌面后重试")
        self.progress("已连接模拟器")
        self.adb("forward", f"tcp:{self.cfg['port']}", "tcp:26789")

    def close_connection(self):
        if self.engine:
            self.engine.close()
        self.engine = None

    def abort_prepare(self):
        """Release a failed pre-offline injection without restarting the game."""
        self.close_connection()
        if self.script:
            try:
                self.script.unload()
            except Exception:
                pass
        if self.session:
            try:
                self.session.detach()
            except Exception:
                pass
        self.script = self.session = None
        self.dialog_script = None
        if self.offline:
            self.rules(False)
        self.stop_frida()
        self.progress("准备未完成；已停止 Frida，游戏保持联网，可稍后重试")

    def rules(self, active):
        if self.shell("id", "-u").stdout.strip() != "0":
            self.adb("root")
            self.adb("wait-for-device")
            if self.shell("id", "-u").stdout.strip() != "0":
                raise RuntimeError("请在 MuMu 中开启 root 权限后重试")
        uid = self.shell("stat", "-c", "%u", "/data/user/0/" + PACKAGE).stdout.strip()
        if not uid.isdigit():
            raise RuntimeError("无法读取游戏 UID，请先安装支持的 Nulls Royale")
        tables = ("iptables", "ip6tables")

        def clear_rules():
            for table in tables:
                listing = self.shell(
                    table, "-L", "OUTPUT", "--line-numbers", "-n", check=False
                ).stdout
                nums = [
                    int(line.split()[0])
                    for line in listing.splitlines()
                    if (RULE_COMMENT in line or GLOBAL_RULE_COMMENT in line)
                    and line.split()[0].isdigit()
                ]
                for number in reversed(nums):
                    self.shell(table, "-D", "OUTPUT", number, check=False)

        clear_rules()
        if not active:
            self.offline = False
            return

        owner_supported = all(
            self.shell(table, "-m", "owner", "-h", check=False).returncode == 0
            for table in tables
        )
        gateway = None
        if not owner_supported:
            route = self.shell("ip", "route", "show", "table", "all").stdout.split()
            if "via" in route:
                candidate = route[route.index("via") + 1]
                if re.fullmatch(r"(?:\d{1,3}\.){3}\d{1,3}", candidate):
                    gateway = candidate
            if gateway is None:
                raise RuntimeError("无法识别 MuMu 虚拟网关，未执行模拟器断网")
        try:
            for table in tables:
                command = [table, "-I", "OUTPUT", "!", "-o", "lo"]
                if owner_supported:
                    command += ["-m", "owner", "--uid-owner", uid]
                elif table == "iptables":
                    # MuMu carries ADB and forwarded localhost sockets over its
                    # virtual gateway. Keep that control path reachable.
                    command += ["!", "-d", gateway]
                command += [
                    "-m",
                    "comment",
                    "--comment",
                    RULE_COMMENT if owner_supported else GLOBAL_RULE_COMMENT,
                    "-j",
                    "REJECT",
                ]
                self.shell(*command)
        except Exception:
            clear_rules()
            raise
        if not owner_supported:
            self.progress("MuMu 不支持按应用断网；回放期间已临时断开整个模拟器外网")
        self.offline = True

    def stop_frida(self):
        def pids():
            return {
                p
                for p in self.shell("pidof", "frida-server", check=False).stdout.split()
                if p.isdigit()
            }

        targets = pids()
        if targets:
            self.shell("kill", "-TERM", *sorted(targets), check=False)
            deadline = time.monotonic() + 1
            while pids().intersection(targets) and time.monotonic() < deadline:
                time.sleep(0.05)
            remaining = pids().intersection(targets)
            if remaining:
                self.shell("kill", "-KILL", *sorted(remaining), check=False)
            deadline = time.monotonic() + 1
            while pids().intersection(targets) and time.monotonic() < deadline:
                time.sleep(0.05)
            if pids().intersection(targets):
                raise RuntimeError("未能停止模拟器中的 Frida 服务")
        # Remove only the forwarding pair used by this application's Frida client.
        for line in self.adb("forward", "--list").stdout.splitlines():
            if line.split() == [self.cfg["serial"], "tcp:27042", "tcp:27042"]:
                self.adb("forward", "--remove", "tcp:27042", check=False)

    def start_game(self):
        for attempt in range(5):
            try:
                self.shell("am", "start", "-n", ACTIVITY)
                return
            except RuntimeError as error:
                # MuMu may report boot_completed before Android's activity or
                # compatibility service is ready, especially after adb root.
                transient = "IPlatformCompat" in str(error) or "Can't find service: activity" in str(error)
                if not transient or attempt == 4:
                    raise
                self.progress("等待安卓活动服务就绪…")
                time.sleep(attempt + 1)

    def app_directory(self):
        paths = self.shell("pm", "path", PACKAGE).stdout.splitlines()
        base = next(
            (p.removeprefix("package:") for p in paths if p.endswith("/base.apk")), None
        )
        if base is None:
            raise RuntimeError("请先安装支持的 Nulls Royale")
        return PurePosixPath(base).parent

    def wait_until_ready(self, timeout, script_errors=None):
        deadline = time.monotonic() + timeout
        last_error = None
        while time.monotonic() < deadline:
            if script_errors:
                raise RuntimeError(str(script_errors[0]))
            client = RenderedEngine(port=self.cfg["port"], timeout=1)
            try:
                state = client.request("status")
                if state.get("contentReady"):
                    return state
            except (ConnectionError, OSError, ValueError) as error:
                last_error = error
            finally:
                client.close()
            time.sleep(0.5)
        raise RuntimeError(f"等待游戏资源就绪超时：{last_error or '资源未就绪'}")

    def ensure_root(self):
        if self.shell("id", "-u").stdout.strip() != "0":
            self.adb("root", check=False)
            self.adb("wait-for-device")
        if self.shell("id", "-u").stdout.strip() != "0":
            raise RuntimeError(
                "请在 MuMu 中开启 root 权限后重试；程序不会修改电脑系统权限"
            )

    def enable_dialog_guard(self):
        """Use the host JVM bridge for MuMu's Android connection dialogs."""
        import frida

        if self.dialog_script is None:
            if self.session is None:
                self.adb("forward", "tcp:27042", "tcp:27042")
                pid = int(self.shell("pidof", PACKAGE).stdout.strip().split()[0])
                remote = frida.get_device_manager().add_remote_device("127.0.0.1:27042")
                self.session = remote.attach(pid)
            source = (ROOT / "resources/mumu-dialogs.js").read_text(encoding="utf-8")
            self.dialog_script = self.session.create_script(source)
            self.dialog_script.load()
        self.dialog_script.exports_sync.set_offline(True)

    def wait_probe_ready(self, mode, errors):
        # MuMu can fault when returning through JNI_OnLoad's trampoline after
        # the probe has fully initialized. Accept only this observed return
        # fault, and only after the hash-pinned probe confirms initialized hooks
        # and resources. Protocol version is checked by the offline handshake.
        return_fault = (
            mode == "mumu-native-bridge-x86_64"
            and errors
            and all(
                m.get("description") == "Error: access violation accessing 0xdead1066"
                and "at loadProbe " in m.get("stack", "")
                for m in errors
            )
        )
        if return_fault:
            self.progress("MuMu 加载返回异常，正在核实探针是否已完整启动…")
            try:
                state = self.wait_until_ready(5)
                if state.get("ok") and state.get("coldReady") and state.get("armed"):
                    return state
            except (ConnectionError, OSError, RuntimeError):
                pass
            raise RuntimeError(str(errors[0]))
        return self.wait_until_ready(
            330 if mode == "mumu-native-bridge-x86_64" else 90, errors
        )

    def probe_mode(self):
        """Return the supported injection mode without changing the device."""
        abi = self.shell("getprop", "ro.product.cpu.abi").stdout.strip()
        if abi == "arm64-v8a":
            return "native-arm64"
        bridge = self.shell("getprop", "ro.dalvik.vm.native.bridge").stdout.strip()
        if abi == "x86_64" and bridge == "libnb.so":
            return "mumu-native-bridge-x86_64"
        raise RuntimeError(
            f"当前设备为 {abi}（Native Bridge: {bridge or '无'}）；"
            "仅支持原生 ARM64 Android，或使用 libnb.so ARM 转译的 MuMu x86_64 Android"
        )

    def install_frida(self, architecture="arm64-v8a"):
        """Deploy the bundled, hash-pinned server; never download at runtime."""
        manifest = json.loads((ROOT / "resources/frida.json").read_text(encoding="utf-8-sig"))
        if architecture == "x86_64":
            manifest = manifest["x86_64"]
        elif architecture != "arm64-v8a":
            raise RuntimeError(f"不支持的 Frida Server 架构：{architecture}")
        remote = "/data/local/tmp/frida-server"
        installed = self.shell("sha256sum", remote, check=False).stdout.split()
        if installed and installed[0] == manifest["sha256"]:
            return
        archive = ROOT / "resources" / manifest["file"]
        if not archive.is_file():
            raise RuntimeError("缺少 Frida 服务：源码运行请执行 tools/fetch_deps.py；独立应用请重新下载完整压缩包")
        packed = archive.read_bytes()
        if hashlib.sha256(packed).hexdigest() != manifest["archive_sha256"]:
            raise RuntimeError("内置 Frida 服务校验失败，请重新下载应用")
        binary = lzma.decompress(packed)
        if hashlib.sha256(binary).hexdigest() != manifest["sha256"]:
            raise RuntimeError("Frida 服务解压校验失败")
        self.progress("正在准备回放组件…")
        # Finish local checks before touching an existing server.
        self.stop_frida()
        with tempfile.TemporaryDirectory(prefix="replay-frida-") as temp:
            path = Path(temp) / "frida-server"
            path.write_bytes(binary)
            self.adb("push", path, remote + ".tmp")
            try:
                got = self.shell("sha256sum", remote + ".tmp").stdout.split()[0]
                if got != manifest["sha256"]:
                    raise RuntimeError("Frida 服务传输校验失败")
                self.shell("chmod", "755", remote + ".tmp")
                self.shell("mv", remote + ".tmp", remote)
            finally:
                self.shell("rm", "-f", remote + ".tmp", check=False)

    def prepare_engine(self):
        import frida  # Validate the host runtime before restarting or disconnecting the game.

        self.connect_device()
        mode = self.probe_mode()
        self.ensure_root()
        directory = self.app_directory()
        libdir = directory / "lib/arm64"
        manifest = json.loads((ROOT / "resources/engine.json").read_text(encoding="utf-8-sig"))
        actual = self.shell("sha256sum", libdir / "libg.so").stdout.split()[0]
        if actual != manifest["libg_sha256"]:
            raise RuntimeError("游戏版本不匹配，需要 Nulls Royale 15.535.13 对应资源")
        self.install_frida(
            "x86_64" if mode == "mumu-native-bridge-x86_64" else "arm64-v8a"
        )
        if mode == "native-arm64":
            self.rules(True)
        self.close_connection()
        e = RenderedEngine(port=self.cfg["port"], timeout=90)
        try:
            if self.reconnect_required:
                raise ConnectionError("restart stale replay session")
            state = e.request("status")
            if state.get("contentReady"):
                r = e.request("offline on")
                if r.get("ok") and r.get("replayStudioVersion", 0) >= 5:
                    if mode == "mumu-native-bridge-x86_64":
                        self.enable_dialog_guard()
                        self.rules(True)
                    self.engine = e
                    self.reconnect_required = False
                    return {"offline": True}
        except Exception:
            if mode == "mumu-native-bridge-x86_64" and self.offline:
                self.rules(False)
        e.close()
        self.progress("正在启动原生引擎…")
        if mode == "native-arm64":
            self.shell("am", "force-stop", PACKAGE)
        elif not self.shell("pidof", PACKAGE, check=False).stdout.strip():
            self.start_game()
        if self.session:
            try:
                self.session.detach()
            except Exception:
                pass
        self.session = self.script = None
        self.dialog_script = None
        probe_name = (
            "libcrprobe-mumu.so" if mode == "mumu-native-bridge-x86_64" else "libcrprobe.so"
        )
        probe = getattr(self, "probe_path", ROOT / "resources" / probe_name)
        if not probe.exists():
            raise RuntimeError("缺少 resources/libcrprobe.so，请先构建本地探针")
        digest = hashlib.sha256(probe.read_bytes()).hexdigest()
        if mode == "mumu-native-bridge-x86_64" and not hasattr(self, "probe_path"):
            provenance = json.loads(
                (ROOT / "resources/windows-provenance.json").read_text(encoding="utf-8")
            )
            if digest != provenance["output_sha256"]:
                raise RuntimeError("MuMu 原生探针校验失败，请重新下载完整应用")
        target = libdir / f"libcrprobe_{digest[:12]}.so"
        self.adb("push", probe, target)
        self.shell("chmod", "755", target)
        self.shell("restorecon", target)
        if self.shell("sha256sum", target).stdout.split()[0] != digest:
            raise RuntimeError("探针复制校验失败")
        if not self.shell("pidof", "frida-server", check=False).stdout.strip():
            self.shell(
                "sh",
                "-c",
                "'nohup /data/local/tmp/frida-server >/data/local/tmp/cr-frida.log 2>&1 &' ",
            )
        self.adb("forward", "tcp:27042", "tcp:27042")
        self.start_game()
        import frida

        device = frida.get_device_manager().add_remote_device("127.0.0.1:27042")
        last = None
        for attempt in range(3):
            time.sleep(3 if attempt == 0 else 5)
            pid = self.shell("pidof", PACKAGE).stdout.strip().split()[0]
            try:
                self.session = device.attach(int(pid))
                break
            except frida.TransportError as error:
                last = error
                self.progress("等待游戏完成初始化，重试连接…")
        if self.session is None:
            raise RuntimeError(f"无法连接游戏进程：{last}")
        if mode == "mumu-native-bridge-x86_64":
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                maps = self.shell("cat", f"/proc/{pid}/maps", check=False).stdout
                if "/lib/arm64/libg.so" in maps:
                    break
                time.sleep(1)
            else:
                raise RuntimeError("MuMu 中的 ARM64 游戏核心未完成映射")
            # Loading and content readiness are checked below. A fixed process
            # age does not prevent the Native Bridge return fault and delays
            # every recovery by three minutes.
            self.progress("等待 MuMu 完成 ARM 转译初始化；首次冷启动可能需要几分钟…")
            source = """
    const path=PROBE;
    const getNamespace=new NativeFunction(
      Module.getGlobalExportByName('NativeBridgeGetExportedNamespace'),
      'pointer',['pointer']);
    const loadLibraryExt=new NativeFunction(
      Module.getGlobalExportByName('NativeBridgeLoadLibraryExt'),
      'pointer',['pointer','int','pointer']);
    const loadLibrary=new NativeFunction(
      Module.getGlobalExportByName('NativeBridgeLoadLibrary'),
      'pointer',['pointer','int']);
    const getError=new NativeFunction(
      Module.getGlobalExportByName('NativeBridgeGetError'),'pointer',[]);
    const getTrampoline=new NativeFunction(
      Module.getGlobalExportByName('NativeBridgeGetTrampoline'),
      'pointer',['pointer','pointer','pointer','uint']);
    const getVMs=new NativeFunction(Module.getGlobalExportByName('JNI_GetCreatedJavaVMs'),'int',['pointer','int','pointer']);
    let attempts=0;
    function loadProbe(){
      const pathString=Memory.allocUtf8String(path);
      let probe=loadLibrary(pathString,2);
      if(probe.isNull()){
        for(const name of ['default','classloader-namespace']){
          const ns=getNamespace(Memory.allocUtf8String(name));
          if(!ns.isNull()){
            probe=loadLibraryExt(pathString,2,ns);
            if(!probe.isNull())break;
          }
        }
      }
      if(probe.isNull()){
        attempts++;
        if(attempts>=300){
          const p=getError();
          const detail=p.isNull()?'':p.readUtf8String();
          throw new Error('Native Bridge probe load failed after 300 attempts: '+detail);
        }
        setTimeout(loadProbe,1000);
        return;
      }
      const trampoline=getTrampoline(
        probe,Memory.allocUtf8String('JNI_OnLoad'),Memory.allocUtf8String('ILL'),3);
      if(trampoline.isNull())throw new Error('Native Bridge JNI_OnLoad trampoline unavailable');
      const vms=Memory.alloc(Process.pointerSize),count=Memory.alloc(4);
      if(getVMs(vms,1,count)!==0||count.readS32()!==1)throw new Error('VM unavailable');
      new NativeFunction(trampoline,'int',['pointer','pointer'])(vms.readPointer(),ptr(0));
    }
    loadProbe();
    """.replace("PROBE", json.dumps(str(target)))
        else:
            source = """
    const dir=LIBDIR;
    const dlopen=new NativeFunction(Module.getGlobalExportByName('dlopen'),'pointer',['pointer','int']);
    if(dlopen(Memory.allocUtf8String(dir+'/libc++_shared.so'),0x102).isNull())throw new Error('libc++ load failed');
    const probe=Module.load(PROBE);
    const getVMs=new NativeFunction(Module.getGlobalExportByName('JNI_GetCreatedJavaVMs'),'int',['pointer','int','pointer']);
    const vms=Memory.alloc(Process.pointerSize),count=Memory.alloc(4);
    if(getVMs(vms,1,count)!==0||count.readS32()!==1)throw new Error('VM unavailable');
    new NativeFunction(probe.getExportByName('JNI_OnLoad'),'int',['pointer','pointer'])(vms.readPointer(),ptr(0));
    """.replace(
                "LIBDIR", json.dumps(str(libdir))
            ).replace(
                "PROBE", json.dumps(str(target))
            )
        errors = []
        self.script = self.session.create_script(source)
        self.script.on(
            "message",
            lambda m, d: errors.append(m) if m.get("type") == "error" else None,
        )
        self.script.load()
        # Top-level loader failures are synchronous. Surface them before the
        # longer content-ready wait so a cold Native Bridge race is actionable.
        time.sleep(0.2)
        self.wait_probe_ready(mode, errors)
        self.engine = RenderedEngine(port=self.cfg["port"], timeout=90)
        result = self.engine.request("offline on")
        if not result.get("ok") or result.get("replayStudioVersion", 0) < 5:
            raise RuntimeError("探针不支持独立离线模式，请更新探针")
        if mode == "mumu-native-bridge-x86_64":
            # Arm connection-error suppression before the firewall can cause
            # a disconnect. Otherwise an Android relogin dialog may win the race.
            self.enable_dialog_guard()
            self.rules(True)
        # Only at the freshly restarted login screen, before loading any replay.
        # No synthetic Back press: it can interrupt the first scene load.
        self.dismiss_connection_dialog()
        self.progress("等待游戏场景初始化…")
        time.sleep(6)
        self.reconnect_required = False
        self.progress("离线引擎就绪；连接错误提示已禁用")
        return {"offline": True}

    def dismiss_connection_dialog(self):
        # Only called during the offline cold start, before any battle exists.
        # MuMu's Android image lacks uiautomator. The stock connection error
        # is an Android APPLICATION dialog; the game canvas is BASE_APPLICATION.
        dump = self.shell("dumpsys", "window", "windows").stdout
        windows = re.split(r"(?m)^  Window #", dump)[1:]
        dialog = any(
            ACTIVITY in w.splitlines()[0]
            and "package=" + PACKAGE in w
            and "(wrapxwrap)" in w
            and "ty=APPLICATION " in w
            and "mViewVisibility=0x0" in w
            and "mObscured=false" in w
            for w in windows
        )
        if dialog:
            self.shell("input", "keyevent", "4")
            self.progress("已清除离线启动时的系统提示")
