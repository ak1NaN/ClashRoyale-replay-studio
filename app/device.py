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


def defaults():
    exe = "adb.exe" if os.name == "nt" else "adb"
    candidates = [APP_DIR / "platform-tools" / exe, APP_DIR / exe]
    if sys.platform == "darwin":
        for base in (Path("/Applications"), Path.home() / "Applications"):
            candidates.append(
                base
                / "MuMuPlayer.app/Contents/MacOS/MuMuEmulator.app/Contents/MacOS/tools/adb"
            )
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
    return {
        "adb": str(local) if local else shutil.which(exe) or exe,
        "serial": "127.0.0.1:16384",
        "port": 26789,
    }


def settings():
    cfg = defaults()
    if SETTINGS.exists():
        saved = json.loads(SETTINGS.read_text())
        cfg.update({k: v for k, v in saved.items() if k in cfg})
    adb = os.path.expandvars(os.path.expanduser(cfg["adb"]))
    if not Path(adb).is_absolute() and ("/" in adb or "\\" in adb):
        adb = str(APP_DIR / adb)
    cfg["adb"] = adb
    return cfg


def run(args, timeout=30, check=True):
    p = subprocess.run(
        [str(a) for a in args], capture_output=True, text=True, timeout=timeout
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

    def rules(self, active):
        if self.shell("id", "-u").stdout.strip() != "0":
            self.adb("root")
            self.adb("wait-for-device")
            if self.shell("id", "-u").stdout.strip() != "0":
                raise RuntimeError("请在 MuMu 中开启 root 权限后重试")
        uid = self.shell("stat", "-c", "%u", "/data/user/0/" + PACKAGE).stdout.strip()
        if not uid.isdigit():
            raise RuntimeError("无法读取游戏 UID，请先安装支持的 Nulls Royale")
        for table in ("iptables", "ip6tables"):
            listing = self.shell(table, "-L", "OUTPUT", "--line-numbers", "-n").stdout
            nums = [
                int(line.split()[0])
                for line in listing.splitlines()
                if RULE_COMMENT in line and line.split()[0].isdigit()
            ]
            for number in reversed(nums):
                self.shell(table, "-D", "OUTPUT", number)
            if active:
                self.shell(
                    table,
                    "-I",
                    "OUTPUT",
                    "!",
                    "-o",
                    "lo",
                    "-m",
                    "owner",
                    "--uid-owner",
                    uid,
                    "-m",
                    "comment",
                    "--comment",
                    RULE_COMMENT,
                    "-j",
                    "REJECT",
                )
        self.offline = active

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
        try:
            self.shell("am", "start", "-n", ACTIVITY)
        except RuntimeError as error:
            # MuMu may report boot_completed before Android's compat service is ready.
            if "IPlatformCompat" not in str(error):
                raise
            self.progress("等待安卓活动服务就绪…")
            time.sleep(1)
            self.shell("am", "start", "-n", ACTIVITY)

    def app_directory(self):
        paths = self.shell("pm", "path", PACKAGE).stdout.splitlines()
        base = next(
            (p.removeprefix("package:") for p in paths if p.endswith("/base.apk")), None
        )
        if base is None:
            raise RuntimeError("请先安装支持的 Nulls Royale")
        return PurePosixPath(base).parent

    def wait_until_ready(self, timeout):
        deadline = time.monotonic() + timeout
        last_error = None
        while time.monotonic() < deadline:
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
                "请在 MuMu 中开启 root 权限后重试；程序不会修改 macOS 权限"
            )

    def install_frida(self):
        """Deploy the bundled, hash-pinned server; never download at runtime."""
        manifest = json.loads((ROOT / "resources/frida.json").read_text())
        remote = "/data/local/tmp/frida-server"
        installed = self.shell("sha256sum", remote, check=False).stdout.split()
        if installed and installed[0] == manifest["sha256"]:
            return
        archive = ROOT / "resources" / manifest["file"]
        if not archive.is_file():
            raise RuntimeError("缺少内置 Frida 服务，请重新下载完整 Mac 应用")
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
        abi = self.shell("getprop", "ro.product.cpu.abi").stdout.strip()
        if abi != "arm64-v8a":
            raise RuntimeError(
                f"当前设备为 {abi}；此引擎需要 ARM64 Android，不能直接注入 x86 游戏进程"
            )
        self.ensure_root()
        directory = self.app_directory()
        libdir = directory / "lib/arm64"
        manifest = json.loads((ROOT / "resources/engine.json").read_text())
        actual = self.shell("sha256sum", libdir / "libg.so").stdout.split()[0]
        if actual != manifest["libg_sha256"]:
            raise RuntimeError("游戏版本不匹配，需要 Nulls Royale 15.535.13 对应资源")
        self.install_frida()
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
                    self.engine = e
                    self.reconnect_required = False
                    return {"offline": True}
        except Exception:
            pass
        e.close()
        self.progress("正在启动原生引擎…")
        self.shell("am", "force-stop", PACKAGE)
        if self.session:
            try:
                self.session.detach()
            except Exception:
                pass
        self.session = self.script = None
        probe = ROOT / "resources/libcrprobe.so"
        if not probe.exists():
            raise RuntimeError("缺少 resources/libcrprobe.so，请先构建本地探针")
        digest = hashlib.sha256(probe.read_bytes()).hexdigest()
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
        self.wait_until_ready(90)
        if errors:
            raise RuntimeError(str(errors[0]))
        self.engine = RenderedEngine(port=self.cfg["port"], timeout=90)
        result = self.engine.request("offline on")
        if not result.get("ok"):
            raise RuntimeError("探针不支持独立离线模式，请更新探针")
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
