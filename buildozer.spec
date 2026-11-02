[app]
title = jam_intranexus
package.name = jamintranexus
package.domain = org.intranexus
source.dir = .
source.include_exts = py,kv
version = 0.1.0

# 仅运行时依赖：cryptography 提供传输加密；asyncio 为标准库，勿列入（见 FEASIBILITY）
requirements = python3,kivy,cryptography

orientation = all
fullscreen = 0

[buildozer]
log_level = 2
warn_on_root = 1

# Android SDK/NDK 版本（可由 buildozer 自动下载）
android.api = 33
android.minapi = 21
android.ndk = 25b
android.archs = armeabi-v7a, arm64-v8a
android.accept_sdk_license = True

# 权限：网络 + 多播锁 + 旧版外部存储
android.permissions = INTERNET,ACCESS_NETWORK_STATE,ACCESS_WIFI_STATE,CHANGE_WIFI_MULTICAST_STATE,WRITE_EXTERNAL_STORAGE,READ_EXTERNAL_STORAGE
android.allow_backup = True
