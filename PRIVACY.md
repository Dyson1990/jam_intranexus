# 隐私与数据安全保障说明

本文回答一个核心问题：**本应用不会、也无法盗取你手机里其他软件的私人信息。**
依据如下，均可在本仓库源码中逐一核实。

## 1. 没有对外传输的通道

所有网络出口只有两类，且都在局域网内：

- UDP 广播（设备发现）：[core/discovery.py](core/discovery.py)
- TCP 直连对端局域网 IP（收发消息/文件）：[core/session.py](core/session.py)

全仓不含 `http://`、`https://`、`urllib`、`requests`、`urlopen`，也没有任何硬编码
域名或公网 IP。要「回传数据」就必须有一台接收服务器，而代码里不存在这个地址。
可自行复核：

```bash
grep -rniE 'http|requests|urlopen|\.com|\.net|\.io' --include='*.py' .
```

## 2. Android 权限最小化 + 系统沙箱

Android 默认隔离各应用的私有数据，无法读取其他 App。本项目声明的权限仅
（[buildozer.spec](buildozer.spec)）：

```
INTERNET, ACCESS_NETWORK_STATE, ACCESS_WIFI_STATE,
CHANGE_WIFI_MULTICAST_STATE, WRITE_EXTERNAL_STORAGE, READ_EXTERNAL_STORAGE
```

未声明通讯录、短信、相册、麦克风、摄像头、定位等敏感权限——系统会直接拒绝。

唯一涉及「其他文件」的 `READ/WRITE_EXTERNAL_STORAGE`，代码只做一件事：读取
**你亲手通过系统选择器选中的那一个文件**（[plat/android.py](plat/android.py) 的
SAF `ACTION_OPEN_DOCUMENT`）。它从不遍历或扫描设备上的其他内容。

## 3. 源码可审计

全项目为明文 Python 源码，无 base64 混淆、无预编译二进制、无压缩/加密的隐藏逻辑。
网络读写集中在 [core/](core/) 五个文件，几分钟可通读。

## 4. 真实的边界（如实说明）

- **主动发送才会外流**：只有你主动发送的文本与「选中发送的文件」会发给
  你连接的那个对端——这是应用本职，非后台行为。
- **传输加密可选**：在设置页「配对密钥」为两端配置相同密钥后，TCP 全帧
  加密（见下方）；留空则不加密。设备名 + 16 字节 device_id 仍会随 UDP
  广播被同网段设备看到。

## 5. 传输加密实现（可选开启）

- 实现：[core/crypto.py](core/crypto.py)。标准库 only，HMAC-SHA256 计数器模式流加密
  + encrypt-then-MAC，避免 Android 编译 C 扩展。
- 开启：两端「设置 → 配对密钥」填入**相同**密钥并保存；密钥不同则无法通信
  （即密钥同时充当配对认证）。
- 效果：消息与文件内容在链路上为密文，同网段被动嗅探者无法读取明文。
- 局限：此加密仅防被动嗅探，不替代 TLS；主动中间人（且已获取密钥）不在防护范围。

## 6. 独立验证方式

代码写得再干净，安装的是谁构建的 APK 才是关键：

- 用本仓库源码自行构建（本机 WSL2 的 `buildozer` 或仓库内 GitHub Actions），
  不安装第三方转发的 APK；
- 运行时用抓包工具（如 Wireshark）观察：仅与局域网对端通信，无公网连接；
- 配置配对密钥后抓包，确认消息/文件载荷为密文。
