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
python main.py          # 桌面端运行（阶段三后可用）
```

打包（阶段五）：
- Windows EXE：`pyinstaller jam_intranexus.spec`
- Android APK：`buildozer android debug`（需 Linux 或 WSL）

## 文档
- `FEASIBILITY.md` — 可行性分析与调研
- `TODO.md` — 分阶段开发计划
- `AGENTS.md` — 开发规范与约定

## 许可证
[MIT](LICENSE)
