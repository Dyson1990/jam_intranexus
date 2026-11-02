# jam_intranexus — 可行性分析

## 1. 概述
jam_intranexus 是一个去中心化的局域网即时通信与文件传输工具，目标是让 2～5 台设备
（Windows / Android）在无互联网、无中心服务器的情况下互发消息与文件。技术路线为
Python + Kivy（GUI）+ asyncio/socket（异步 TCP）+ UDP 广播（发现）+ SQLite（本地存储），
支持文件分块、断点续传与 SHA-256 完整性校验。

## 2. 需求分析

### 功能需求
- 设备发现：UDP 广播自动发现、手动 IP 连接、在线状态定期刷新
- 即时消息：双向文本、发送/接收状态、SQLite 历史记录
- 文件传输：任意文件、分块、断点续传、SHA-256 校验、进度/速度/取消
- 本地数据：设备、聊天记录、传输任务、传输进度、设置（SQLite）
- 安全：设备配对/认证、传输加密、路径与文件名校验

### 非功能需求 / 约束
- 仅双方在线且应用前台运行时通信，不实现离线消息队列
- 不引入 Web 框架、服务端数据库、Docker、MQTT、云中继
- 优先使用 Python 标准库，避免不必要依赖
- 异步网络，不阻塞 GUI；业务逻辑与 UI 分离

### 验收标准
- Windows EXE 与 Android APK 可互发消息与文件
- 断点续传、网络断开/恢复、程序重启后传输恢复
- SHA-256 校验通过后文件才落地

## 3. 现有方案调研
- **Kivy 官方 async 示例**：Kivy ≥2.0 通过 `App.async_run()` / `async_runTouchApp(async_lib='asyncio')`
  把 Kivy 事件循环跑在 asyncio 循环内，是官方推荐的异步用法 `[verified]`。
- **Sideband**：基于 Kivy 的去中心化网格通信应用，用 PyJnius 调用 Android `WifiManager` 的
  `MulticastLock` 来保证 UDP 广播可用 `[verified]`，可作为 Android 广播/多播的参考实现。
- **LocalSend**：局域网文件共享应用（Flutter 实现，非 Python），可参考其 UX 与断点续传思路
  `[inferred]`，但不复用其代码。

## 4. 技术可行性
- **Kivy + asyncio**：官方支持，示例 `examples/async/` 演示了在 asyncio 循环内运行 Kivy
  并并发运行网络任务 `[verified]`。这是本项目网络层的基础，无阻塞风险。
- **TCP / UDP / asyncio 在 Android**：`socket` 与 `asyncio` 为标准库，p4a 打包后可用，但需在
  `buildozer.spec` 声明 `INTERNET` 权限；`asyncio` 不要写进 p4a `requirements`（会误打包旧副本）
  `[verified]`。
- **UDP 广播在 Android**：部分 ROM 默认禁用 UDP 广播/多播接收，需通过 PyJnius 获取
  `MulticastLock` 并声明 `CHANGE_WIFI_MULTICAST_STATE` / `ACCESS_WIFI_STATE` /
  `ACCESS_NETWORK_STATE` 权限 `[verified]`。这是 Android 侧最大的兼容性风险点。
- **Android 打包工具链**：Buildozer 在 Linux/macOS 运行，Windows 需 WSL `[verified]`；
  `cryptography`（AES 加密用）为 C 扩展，p4a 已有 recipe，预计可用但需在 WSL 中实际验证
  `[inferred]`。
- **Windows EXE**：PyInstaller 打包 Kivy 应用为独立 EXE 是常见做法 `[inferred]`，需处理
  防火墙入站放行。

## 5. 许可证
本项目采用 **MIT**（最宽松的常见许可证）。关键依赖许可证：
- Kivy：MIT `[inferred]`
- python-for-android / Buildozer：MIT `[inferred]`
- cryptography：Apache-2.0 / BSD 双许可 `[inferred]`
均与 MIT 兼容，不构成分发约束。

## 6. 风险
| 风险 | 严重度 | 说明 |
| --- | --- | --- |
| Android UDP 广播被 ROM 禁用 | 高 | 需 MulticastLock + 手动 IP 连接兜底 |
| asyncio 与 Kivy 事件循环集成 | 中 | 官方支持，但需严格按示例组织协程生命周期 |
| cryptography 在 p4a 的编译 | 中 | 需在 WSL 中验证 recipe；失败可降级为内置加密方案 |
| 局域网广播跨网段失效 | 中 | 需同网段 + 手动 IP 连接兜底 |
| 断点续传一致性 | 中 | 需以偏移量 + 哈希分片校验保证 |
| Windows 防火墙入站拦截 | 低 | 首次运行提示放行，文档说明 |

## 7. 推荐方案
按 spec 的五阶段推进：先核心网络（发现 + TCP + 协议 + 文件分块/续传/校验 + 测试），
再 Kivy GUI（赛博朋克），再做 Windows/Android 平台适配，最后打包验收。网络层全部走
asyncio，UI 通过 `Clock.schedule_once` 接收网络结果，杜绝阻塞。

## 8. 结论
**Go**。技术栈均为成熟方案，主要风险集中在 Android 广播与打包工具链，均有已知解法与兜底
（手动 IP、WSL 构建），无阻断性障碍。

## 9. 参考资料
- Kivy async 示例：https://github.com/kivy/kivy/blob/master/examples/async/asyncio_advanced.py
- Kivy Android 打包指南：https://github.com/kivy/kivy/blob/22ca453eee15c0294ca664d42b2525ed4c6fbaf4/doc/sources/guide/packaging-android.rst
- asyncio/aiohttp 在 Android 的坑：https://stackoverflow.com/posts/78011917/revisions
- Sideband 的 MulticastLock 实现：https://git.liberatedsystems.co.uk/jacob.eva/Sideband_CE/raw/commit/e58c8a96bec39d2f5725e2d206a7dfcde806c934/sbapp/services/sidebandservice.py

## 假设
- 仓库所有者/版权持有人使用 GitHub 用户名 `Dyson1990`。
- 依赖安装于 `.venv`，该目录不提交（已忽略）。
- 加密方案优先 `cryptography`（AES），若 Android 编译受阻则回退到标准库方案。
