# AGENTS.md — 开发规范

## 技术栈（强制）
- Python 业务与网络；Kivy GUI；asyncio + socket 异步 TCP；UDP 广播发现；SQLite 存储；
  hashlib SHA-256 校验；PyInstaller（Windows EXE）；Buildozer + python-for-android（APK）。
- 优先标准库，避免不必要依赖。

## 禁止引入
- FastAPI/Django 等 Web 框架、Redis/PostgreSQL、Docker、MQTT、Kafka、云/中心化中继。

## 环境
- 所有依赖安装于项目虚拟环境 `.venv`（已 git 忽略，勿提交）。
- `requirements.txt` 为唯一依赖清单。

## 结构
- 目录职责清晰（`core/` 网络与协议、`storage/` 数据、`ui/` 界面、`plat/` 平台适配），
  避免过度拆分；可按实现微调但保持职责单一。
  > 平台适配包命名为 `plat/` 而非 `platform/`，避免与标准库 `platform` 模块冲突（PyInstaller 依赖后者）。

## 代码规范
- 使用 Python 类型注解；关键函数写简洁中文 docstring/注释；复杂网络协议加注释。
- 业务逻辑不得写入 UI；网络任务与 UI 更新安全隔离（`Clock.schedule_once`）。
- 禁止阻塞式网络 I/O；统一异常处理、日志与错误提示。
- 不用占位代码、不虚构已完成的实现、不为形式引入设计模式；优先简单可读可维护。

## 安全
- 设备配对/认证、传输加密、路径与文件名校验、SHA-256 完整性校验。
- 未经授权的设备不得写入本机文件；不暴露不必要的网络服务。

## 测试
- 测试数据运行时生成（random/faker），不提交大 mock 数据集或二进制。
- 每个阶段完成后运行测试并更新 TODO.md。
