# Windows 移植交接

当前目标“导入 HTML 并在游戏内完整播放”已在一台 Windows MuMu 上通过整场实测。原先的场景创建崩溃和断线后停播均已修复；更多对局和版本兼容性仍需验证。

- 用户入口与限制：[README](README.md)
- 构建、诊断、原生修复和验收记录：[Windows 开发说明](docs/windows-development.md)
- Windows 分支：`win`；保留原有 Mac 主分支及 Release。

历史调试中的本机路径、设备信息与失败日志不作为公开交接内容提交。后续开发请使用上述文档及可重复诊断工具，不要恢复旧的固定等待、ARM64 Frida Server 或飞行模式方案。
