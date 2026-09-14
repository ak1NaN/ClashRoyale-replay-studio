# Mac 发布说明

目标用户只需要准备 MuMu、已支持的 Nulls、root 和保存的对局 HTML。
应用内置 Python/Qt/Frida 客户端、Android Frida 压缩包和原生探针。
使用 MuMu 自带 ADB 避免额外安装 Android SDK。

## 初版范围

- Mac Apple Silicon + ARM64 Android；本地验证环境 MuMu 1.4.11。
- Nulls APK 15.535.13 / 已验证资源 15.535.86；固定 libg 哈希。
- 默认单实例端口 16384；其他安装位置或多实例可手动填写连接设置。
- 应用没有自动启动模拟器或下载游戏的能力。
- 首次准备校验组件、root、ABI、游戏库，然后部署 Frida。
- 不支持游戏自动升级适配，不创建 Windows 分支或发布 Windows 包。

## 发包

关闭待覆盖的应用后运行 `tools/fetch_deps.py` 和 `tools/package.py`。
然后用 `ditto -c -k --keepParent 'dist/Replay Studio.app' dist/ReplayStudio-macOS-arm64.zip` 压缩。
向 GitHub Release 上传压缩包与 SHA256SUMS.txt；不提交应用到 Git。
私有仓库的 Release 同样仅有权限的账号可访问。

当前仅本地 ad-hoc 签名，不是 Apple 公证版本。它可以供知情用户测试，
但不能称为所有 Mac 下载后均可无提示直接打开。
面向公众的顺畅首次运行还需开发者提供 Developer ID 证书，使用 hardened
runtime 对依赖及应用逐层签名、提交 Apple notarization、staple 票据，
然后在带下载隔离标记的干净 Mac 上验证启动、Frida 加载与完整回放。
证书和认证资料不进入 Git。没有证书时不自动修改系统安全设置。

参考：
- https://developer.apple.com/developer-id/
- https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution
- https://www.mumuplayer.com/help/mac/connect-adb.html
- https://frida.re/docs/android/

## 发布验证

离线单元测试覆盖配置、自动查找、Frida 校验/安装、导入、暂停/跳转和释放。
设备验证应覆盖首次部署、整场预演算、随机时间点回看、第二局导入、
退出清理和下一次重新准备。已有开发设备的测试不能替代另一台干净 Mac。
