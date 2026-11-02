[app]
title = jam_intranexus
package.name = jamintranexus
package.domain = org.intranexus
source.dir = .
source.include_exts = py,kv
version = 0.1.0

# 仅运行时依赖；asyncio 为标准库，勿列入。cryptography 未在代码中引用，已移除（见 FEASIBILITY 回退）
# python3 默认解析到 3.14（pip 26 移除了 BuildDependencyInstallError，会崩），固定到 3.12；
# hostpython3 必须与 python3 同版本（p4a 版本守卫强制校验），故一并固定
requirements = python3==3.12.10,hostpython3==3.12.10,kivy

orientation = all
fullscreen = 0

# 以下 android.* 必须位于 [app] 段——buildozer 只从该段读取，放错段会被静默忽略
android.api = 33
# minapi/ndk_api 须 >= 26：bionic 的 grp.h 仅在 __ANDROID_API__ >= 26 声明
# setgrent/getgrent/endgrent，而 CPython 3.12 的 grpmodule.c 无条件编译它们。
# 若按 21 编译会 "undeclared function" 崩在原生编译阶段。
android.minapi = 26
android.ndk = 28c
android.ndk_api = 26
android.archs = armeabi-v7a, arm64-v8a
android.accept_sdk_license = True

# 权限：网络 + 多播锁 + 旧版外部存储
android.permissions = INTERNET,ACCESS_NETWORK_STATE,ACCESS_WIFI_STATE,CHANGE_WIFI_MULTICAST_STATE,WRITE_EXTERNAL_STORAGE,READ_EXTERNAL_STORAGE
android.allow_backup = True

[buildozer]
log_level = 2
warn_on_root = 1
