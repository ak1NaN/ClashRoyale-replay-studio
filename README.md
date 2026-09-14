# Clash Royale Replay Studio

Mac 上的 RoyaleAPI HTML 对局回放工具。导入保存的独立对局 HTML，在 MuMu 中通过 Nulls Royale 的原生游戏画面观看回放。支持暂停、逐 tick 缓存跳转及 0.25×～16× 倍速。

**当前是 Mac Apple Silicon 测试版。Windows 暂不支持。**

## 普通用户怎么用

从本仓库 [Releases](https://github.com/ak1NaN/ClashRoyale-replay-studio/releases) 下载 Mac 应用压缩包，解压后打开 `Replay Studio.app`。无需安装 Python、Qt、Frida、Android SDK 或编译工具。

1. 安装并手动打开 Mac MuMu，开启模拟器 root，等待安卓桌面就绪。
2. 在模拟器安装 **Nulls Royale 15.535.13**，完成首次联网资源下载；已验证资源为 **15.535.86**。随后退出游戏。
3. 打开 Replay Studio，导入已保存的 RoyaleAPI **独立对局 HTML**。
4. 点击 **准备回放**。程序自动使用 MuMu 的 ADB、部署配套组件、让游戏断网，并高速缓存整场对局。
5. 准备完成后播放，或拖动时间轴跳转。画面显示在模拟器里。
6. 正常退出会清理回放缓存、停止 Frida 服务、恢复游戏联网并打开普通游戏。

程序不安装 MuMu 或游戏，不更换游戏版本，也不修改 macOS 安全设置。只导入 HTML 不会断网；首次组件部署只在准备回放时进行。Frida 服务文件保留在模拟器中，退出时停止，下次自动复用。

**兼容条件：** ARM64 Android、可用 root、匹配的 `libg.so` 以及游戏资源。安装了任意最新版 Nulls 并不代表兼容。版本不匹配时程序会拒绝注入。Mac Intel、其他模拟器和其他 Nulls 版本尚未验证。

### 首次打开与连接问题

- 此测试版只有本地签名，**尚未经过 Apple Developer ID 签名与公证**。从网络下载后 macOS 可能阻止首次打开；请自行核对来源并使用系统设置中的正常允许打开流程。程序不会关闭 Gatekeeper。
- 程序优先寻找标准安装目录中的 MuMu ADB。MuMu 不在标准目录、使用多个实例或非默认端口时，在 **连接设置** 中指定 ADB 和设备地址。
- 默认地址 `127.0.0.1:16384`。设备端口可在 MuMu 的工具菜单中查看：[官方 ADB 说明](https://www.mumuplayer.com/help/mac/connect-adb.html)。
- 如果提示 root 不可用，请在 MuMu 设置中启用并按模拟器要求重启。

## 依赖如何处理

| 内容 | 由谁准备 |
| --- | --- |
| MuMu、匹配的 Nulls 和首次游戏资源下载 | 用户 |
| 模拟器 root / ADB 可连接 | 用户开启，程序检查 |
| Python、Qt、Frida Mac 客户端 | 内置于 `.app` |
| ADB | 直接使用已安装 MuMu 自带的工具，不额外分发 SDK |
| Android Frida 服务 | 内置固定版本压缩包，首次准备时校验并自动部署 |
| 原生回放探针 | 内置于 `.app`，版本校验后注入 |
| HTML、设置和缓存 | HTML 由用户提供；设置本地保存；缓存仅驻留内存 |

## 开发者

普通用户只下载 Release；以下环境只供开发者构建。

```sh
python3.12 -m venv .venv
arch -arm64 .venv/bin/python -m pip install -r requirements-build.txt
arch -arm64 .venv/bin/python tools/fetch_deps.py
arch -arm64 .venv/bin/python -m unittest discover -s tests
arch -arm64 .venv/bin/python run_desktop.py
arch -arm64 .venv/bin/python tools/package.py
```

Frida 下载地址及压缩包/解压后哈希固定在 `resources/frida.json`。**应用运行时不下载依赖**，开发构建时才从官方 Release 拉取。Python、Qt 与 Frida 必须都是 ARM64。

仓库包含当前 `build/libcrprobe.so` 及来源记录，因此构建 GUI 不要求 NDK。修改原生源码时设置 `ANDROID_NDK_HOME` 或 `CXX`，再运行 `build_local_probe.py`。源码运行使用同目录 `data/`；独立应用默认使用 `~/Library/Application Support/ReplayStudio/`，可用 `REPLAY_STUDIO_DATA` 覆盖。不要同时用多个程序控制同一游戏实例。

## 文件结构

| 文件/目录 | 职责 |
| --- | --- |
| `run_desktop.py`、`start.command` | Mac 源码入口 |
| `desktop/gui.py` | 简洁控制界面和工作线程 |
| `desktop/importer.py`、`catalog.json` | 卡牌映射、等级/形态、朝向和相容初手 |
| `desktop/device.py` | ADB、root、Frida 部署、版本校验、断网及游戏连接 |
| `desktop/runtime.py` | 预演算、快照缓存、播放、跳转和退出恢复 |
| `replay_import/` | HTML 事件提取和技能转换 |
| `engine.py`、`protocol.py`、`match_config.py` | 单场/原生画面引擎 API、数据协议和对局配置 |
| `batch.py`、`observation.py` | 保留的批量训练接口与观测提取，GUI 不展示 |
| `bootstrap_emulator.py`、`standard_match.json` | 底层设备辅助和默认对局 |
| `vendor/firstlight/` | 原生源码、版本清单和上游许可证 |
| `build/libcrprobe.so`、`provenance.json` | 当前探针及编译来源 |
| `build_local_probe.py` | 原生探针构建 |
| `resources/frida.json` | 固定依赖版本、来源和哈希 |
| `tools/fetch_deps.py` | 开发构建时准备 Frida 文件 |
| `tools/package.py`、`hooks/` | Mac 独立应用打包，自动清理临时目录 |
| `tests/` | 导入、方向、UI、缓存、退出和 Mac 首次准备回归 |
| `licenses/`、`LICENSE` | 第三方归属、许可证及源码来源 |
| `docs/MAC_RELEASE.md` | Mac 分发边界、签名和验证说明 |

不包含游戏 APK、`libg.so`、游戏资源、模拟器、玩家 HTML、个人设置、旧实验记录或历史构建目录。大体积应用只放在 Releases，不进入 Git 历史；Frida 官方二进制也不进 Git。

## 重建模拟的边界

HTML 没有原局随机种子和秘密初手。程序计算相容牌序，因此是重建模拟，不能保证每局的时间、伤害和结局与原局完全一致。无法识别的卡牌或形态会明确报错，不会偷偷替换。

整场演算后每个 tick 都有快照，跳转不依赖从开局重新追赶。序列化缓存上限 256 MiB，游戏时钟最多演算到 6 分钟，换局和正常退出清理缓存。游戏升级后可能需要修改原生偏移、布局与资源适配，不能只修改版本号。

基于 [Jason-XII/Clash-Royale-Battle-Engine](https://github.com/Jason-XII/Clash-Royale-Battle-Engine) 与 [FirstLight CR](https://gitlab.com/firstlight3/FirstLight_CR)。保留 FirstLight Apache-2.0 许可及归属声明；不隶属于 Supercell，游戏及第三方库的权利归各自权利人。
