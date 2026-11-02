[app]
title = jam_intranexus
package.name = jamintranexus
package.domain = org.intranexus
source.dir = .
source.include_exts = py,kv
version = 0.1.0

# 仅运行时依赖；asyncio 为标准库，勿列入。cryptography 未在代码中引用，已移除（见 FEASIBILITY 回退）
requirements = python3,kivy

orientation = all
fullscreen = 0

# 以下 android.* 必须位于 [app] 段——buildozer 只从该段读取，放错段会被静默忽略
android.api = 33
android.minapi = 21
android.ndk = 28c
android.archs = armeabi-v7a, arm64-v8a
android.accept_sdk_license = True

# 权限：网络 + 多播锁 + 旧版外部存储
android.permissions = INTERNET,ACCESS_NETWORK_STATE,ACCESS_WIFI_STATE,CHANGE_WIFI_MULTICAST_STATE,WRITE_EXTERNAL_STORAGE,READ_EXTERNAL_STORAGE
android.allow_backup = True

[buildozer]
log_level = 2
warn_on_root = 1
