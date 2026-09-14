Mac Apple Silicon 私有测试版。

- 导入 RoyaleAPI 独立对局 HTML，在 MuMu 的 Nulls 原生画面回放。
- 无画面预演算、逐 tick 缓存、暂停、时间轴跳转、0.25×～16×。
- 应用内置 Python/Qt/Frida 客户端和 Android 服务；优先使用 MuMu 自带 ADB。
- 首次准备自动校验并部署组件，退出停止 Frida、清理缓存并恢复游戏联网。

使用前准备：开启 root 的 ARM64 MuMu，Nulls 15.535.13 及已验证资源 15.535.86；其他版本未验证。手动启动模拟器后导入 HTML，点击准备回放。

此版本只有 ad-hoc 本地签名，没有 Apple Developer ID 签名或公证；首次下载可能被 macOS 拦截。请核对来源，按系统正常允许打开流程操作。程序不会关闭安全设置。Windows 和 Mac Intel 不在本版支持范围内。

下载 ZIP 并解压打开 Replay Studio.app，不需要自行安装 Python、Qt、Frida 或 Android SDK。SHA256SUMS.txt 用于校验下载。

验证：33 项测试，31 项通过、2 项可选样本跳过；MuMu 上首次 Frida 部署、连续两场加载、精确跳转和退出联网恢复已验证。详见 docs/VERIFICATION.md。尚未在第二台干净 Mac 完成验证。
