# jam_intranexus

跨平台局域网即时通信与文件传输工具。基于 Python + Kivy，通过 UDP 广播发现同网段设备、
异步 TCP 直连传输消息与文件，不依赖任何云服务器或中心节点。支持 Windows（独立 EXE）
与 Android（APK），界面采用冷色霓虹赛博朋克风格。

## 功能
- 局域网设备自动发现（UDP 广播）与手动 IP 连接
- 设备间双向文本消息，SQLite 本地历史记录
- 大文件分块传输、断点续传、SHA-256 完整性校验、进度/速度/取消
- 设备配对认证与传输加密
- 一键清空本地存储数据（聊天 / 设备 / 传输记录 / 设置）
- 赛博朋克风格跨平台界面（蓝紫 / 青色霓虹）

## 快速开始
> 开发阶段：所有依赖安装于项目虚拟环境 `.venv`（已在 `.gitignore` 中排除，不提交）。

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux / macOS / WSL
source .venv/bin/activate

pip install -r requirements.txt
python main.py          # 桌面端运行
```

打包：
- Windows EXE（已验证可运行）：
  ```bash
  pip install pyinstaller
  pyinstaller --noconfirm --clean jam_intranexus.spec
  # 产物在 dist/jam_intranexus/jam_intranexus.exe
  ```
- Android APK（需 Linux 或 WSL + Android SDK/NDK）：
  ```bash
  buildozer android debug
  ```

## 已知限制
- Android 部分 ROM 会丢弃 UDP 广播，需 MulticastLock；若发现失败，用「手动 IP」兜底。
- Android 10+ 的存储分区限制下，保存目录建议使用默认下载目录；SAF 目录写入能力受限。
- 断点续传/断网恢复/重启恢复已通过单测与回环集成测试，但跨真机验收（5.3/5.4）仍需在
  Android 真机 + Windows 主机上执行。

## 文档
- `FEASIBILITY.md` — 可行性分析与调研
- `TODO.md` — 分阶段开发计划
- `AGENTS.md` — 开发规范与约定

## 许可证
[MIT](LICENSE)
