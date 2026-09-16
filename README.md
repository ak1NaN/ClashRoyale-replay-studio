# 皇室战争回放工作室 · Windows 预览版

导入 RoyaleAPI 保存的**独立对局 HTML**，在 Windows MuMu 的 Nulls Royale 原生游戏画面中播放重建回放。支持暂停、时间轴跳转和 0.25×～16× 倍速。

这是 `win` 分支的 Windows 预览版；Mac 用户请使用 [main 分支](https://github.com/ak1NaN/ClashRoyale-replay-studio/tree/main)及现有 [macOS Release](https://github.com/ak1NaN/ClashRoyale-replay-studio/releases)。本分支不替换 Mac Release。

## 已验证环境与限制

**Windows 版必须使用 Android 12 的 MuMu 模拟器实例。不要使用 Android 15：据当前实测反馈，Android 15 下 Nulls Royale 无法打开，原因尚未查明，暂不支持。这里的 12/15 指模拟器的 Android 系统版本，不是 MuMu 软件版本。**

- Windows 11 x64、MuMu 6.6.4.0、Android 12（x86_64 + `libnb.so` ARM 转译）、开启 root。
- Nulls Royale **15.535.13**，匹配游戏库及已下载的资源；程序启动前会校验游戏库哈希，不支持任意最新版。
- 已用一份真实 HTML（64 个动作）验证：导入、预演算、原生画面以 1× 连续播放至结局、精确跳转、各档倍速和退出恢复联网。
- 当前是单机、单局实测，不保证所有 MuMu 或游戏版本兼容。HTML 缺少原始随机种子与秘密初手，回放是相容重建，时间、伤害和结局可能与原局不同。
- 发布包已内置 Frida，程序自动向模拟器部署，无需手动安装；尚未完成全新电脑/全新模拟器的端到端验收。独立 exe 目前完成了主窗口启动检查。

## 下载和使用

优先从 [Windows 预览版发布页](https://github.com/ak1NaN/ClashRoyale-replay-studio/releases/tag/v0.1.1-windows-preview)下载：

- `ReplayStudio-Windows-x64.exe`：独立运行版，直接打开，无需安装 Python；首次启动需要解压内置组件，稍等片刻。
- `ReplayStudio-Windows-x64-preview.zip`：目录版，解压后运行 `Replay Studio.exe`，必须保留整个文件夹。
- `SHA256SUMS.txt`：发布文件的 SHA256 校验值。

开发构建仍可从 [Windows 构建记录](https://github.com/ak1NaN/ClashRoyale-replay-studio/actions/workflows/windows.yml?query=branch%3Awin)的 **Artifacts** 下载（通常需要登录 GitHub）。

解开下载的 artifact，再解压其中的 `ReplayStudio-Windows-x64-preview.zip`，保留完整的 `Replay Studio` 文件夹，运行 `Replay Studio.exe`。**不能只复制 exe**。压缩包附带 `SHA256SUMS.txt`；这是未签名预览程序，请先核对来源与校验值，不要关闭系统安全设置。

1. 手动打开 MuMu，开启 ADB 和 root；安装匹配游戏版本，完成首次联网资源下载并进入游戏主界面。
2. 打开 Replay Studio，导入独立对局 HTML，点击 **准备回放**。
3. 等待预演算与游戏场景加载，点击播放；画面显示在模拟器里，控制窗口提供暂停、跳转和倍速。
4. 正常关闭控制窗口会清理缓存、停止 Frida，并恢复游戏联网。

程序会自动发现 MuMu 安装与运行实例；失败时在连接设置填写 `adb.exe` 路径和实际设备地址，例如 `127.0.0.1:16416`。端口因实例而异，不要照抄示例。不需要以管理员身份启动本程序。

**联网影响：** 仅导入不会断网。准备回放时会临时阻止游戏联网；MuMu 缺少按应用过滤能力时，会临时断开整个模拟器外网，但保留 ADB 和本地回放通道。回放期间不要用该实例进行其他联网活动。正常退出会恢复联网；若程序意外中止，可重新打开程序使用恢复联网操作。程序不会自动下载游戏、升级游戏或启动模拟器。

[如何保存 RoyaleAPI 独立对局 HTML](docs/import-html.md) · [Windows 开发与诊断](docs/windows-development.md)

## 从源码启动

安装 64 位 Python 3.12，在项目根目录执行：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe tools/fetch_deps.py
.\.venv\Scripts\python.exe run.py
```

仓库已包含配套原生探针和 Java 辅助脚本，普通用户无需安装 NDK 或 Node.js。依赖下载需要联网；应用运行时不下载依赖。

## 测试与打包

```powershell
.\.venv\Scripts\python.exe -m pip install -r tools/requirements.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests
# 先关闭待覆盖的独立应用
.\.venv\Scripts\python.exe tools/package.py
# 可选：生成独立 exe
.\.venv\Scripts\python.exe tools/package.py --onefile
```

输出为 `dist/Replay Studio/Replay Studio.exe`。GitHub Actions 会执行测试、打包并上传完整目录压缩包；CI 不具备 MuMu，不能代替实机播放验收。

源码设置位于 `data/`；独立应用默认位于 `%LOCALAPPDATA%/ReplayStudio`。在 exe 旁放置 `portable.flag` 可使用同目录 `data/`，也可通过 `REPLAY_STUDIO_DATA` 指定目录。缓存仅在内存中，换局和正常退出会清理。

## 项目结构

```text
app/          界面、HTML 导入、回放控制和模拟器连接
resources/    原生探针、Java 辅助脚本、版本及来源校验
tools/        依赖下载、Windows/Mac 打包、实机诊断和探针构建
docs/         使用教程和 Windows 开发说明
tests/        回归测试
licenses/     上游及第三方许可
run.py        源码启动入口
```

Windows 使用独立的 `libcrprobe-mumu.so`，Mac 原有 `libcrprobe.so` 保持不变。Windows 原生补丁及构建来源记录随源码提供；详见开发说明。设备报告、玩家 HTML、日志、游戏库、NDK、虚拟环境和打包产物不提交 Git。

Windows 安装包仅包含 x86_64 Frida 服务端，不包含 ARM64 Frida 服务端或 Mac 专用探针。MuMu 转译运行 ARM64 游戏所必需的 `libcrprobe-mumu.so` 仍保留；Mac 打包仍包含其自身的 ARM64 组件。

基于 [Clash-Royale-Battle-Engine](https://github.com/Jason-XII/Clash-Royale-Battle-Engine) 与 [FirstLight CR](https://gitlab.com/firstlight3/FirstLight_CR)。本仓库目前为公开测试版本，暂未为项目整体指定开源许可证。上游和第三方组件的许可保留在 `licenses/`。不包含游戏、MuMu 或玩家 HTML，不隶属于 Supercell。
