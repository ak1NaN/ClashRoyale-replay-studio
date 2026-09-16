# Windows 开发与验收

本分支优先保证“HTML 导入 → 游戏原生画面播放”。不以 Mac 全功能等价或任意版本兼容为发布承诺。

## 实机诊断

先关闭其他 Replay Studio 控制窗口，打开 MuMu、开启 root，并让匹配版本的游戏完成资源下载。诊断会临时断网，结束或失败后自动尝试恢复联网。

```powershell
.\.venv\Scripts\python.exe tools/check_device.py
.\.venv\Scripts\python.exe -X utf8 tools/check_replay.py '你的独立对局.html'
# 根据对局长度留足时间；只有自然播放到结局才通过：
.\.venv\Scripts\python.exe -X utf8 tools/check_replay.py '你的独立对局.html' --play-seconds 240 --require-end
```

设备检查只读取设备信息，不注入、不修改网络；输出 `device-report.json`。回放诊断与 GUI 使用相同的 `Runtime.load()`，验证播放、跳转和倍速；结果保存在 `data/replay-check-时间/`，包括状态、日志和过程截图。非零退出码表示回放或清理失败。报告可能含设备和对局信息，分享前应检查，不提交仓库。

2026-09-16 本地验收：真实 HTML 含 64 个动作；约 200 秒原生 1× 播放到 tick 4001、`finalized=true`；跳转 90/2000/4001/90 与七档速度均正常，随后恢复联网。回归测试 46 项，43 通过、3 跳过。该记录不代表更多设备或对局均已验证。

## MuMu 适配实现

- `app/device.py` 自动发现 ADB 和实例，校验游戏库；x86_64 Android 使用 x86_64 Frida Server，通过 Native Bridge 加载 ARM64 探针。不要替换为 ARM64 Frida Server。
- `resources/windows-probe.patch` 在游戏管理器主循环提交新场景，保留旧控制器供游戏正常卸载，修复原生画面创建崩溃。
- 已登录会话断网后会产生连接丢失事件 4（`TID_ERROR_POP_UP_CONNECTION_LOST_*`）；原来只处理事件 2/3。Windows 补丁仅在离线控制期间额外处理事件 4，防止应用暂停条件冻结时钟。单纯隐藏 Java 提示不能解决停播。
- `resources/mumu-dialogs.js` 通过 Frida Java Bridge 辅助拦截连接提示。在回放中不要用 Android Back 清除提示，可能触发重新登录。
- MuMu 缺少 iptables `owner` 时使用整实例临时外网规则，保留 loopback 和网关通道；正常退出移除规则、停止注入并重新启动游戏。
- 特定 Native Bridge JNI 返回错误只有在实际探针已就绪、离线协议兼容时才允许恢复；不能忽略任意注入异常。

上述原生偏移只适用于 `resources/engine.json` 固定的游戏库。不要绕过哈希检查、直接套用其他版本。Mac 原有探针不变。

## 重建原生探针

普通运行无需编译。开发者需要 Git 克隆（不能只有源码 ZIP）、Windows Android NDK，以及固定基线标签。本地使用 NDK r29 构建。

```powershell
git fetch origin tag v0.1.0-macos-preview
.\.venv\Scripts\python.exe tools/build_windows_probe.py --ndk 'C:/Android/android-ndk-r29'
```

脚本从 `v0.1.0-macos-preview` 的 `vendor/firstlight/probe` 提取源码，按 `resources/provenance.json` 核对基线哈希，再应用 Windows 补丁。输出 `resources/libcrprobe-mumu.so` 和 `resources/windows-provenance.json`。修改后一起提交补丁、探针和来源记录，运行测试核对产物哈希。

仅更新游戏场景生命周期与离线控制，不应在此过程中无意修改原生战斗逻辑。

## 重建 Java 辅助脚本

需要 Node.js/npm，依赖版本固定于 lockfile：

```powershell
npm ci --prefix tools/frida-agent
npm run --prefix tools/frida-agent build
```

源码为 `tools/frida-agent/mumu-dialogs.js`，产物为 `resources/mumu-dialogs.js`。普通用户不需要 Node.js；许可见 `licenses/README.md`。

## 提交与分发检查

1. 运行单元测试，并在修改回放链路后进行实机整场播放验收。
2. 检查 `git diff --check`，核对探针与来源记录。
3. 不提交 `data/`、`dist/`、`build/`、`.venv/`、`node_modules/`、设备报告、玩家 HTML 或游戏二进制。
4. `win` 推送触发 `.github/workflows/windows.yml`，上传完整应用 ZIP 和 SHA256 校验文件。CI 只验证测试与打包，不验证 MuMu 实机。
5. 不将本分支推送覆盖 `main`，不替换现有 Mac Release。
