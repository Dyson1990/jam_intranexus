# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包：Kivy（走内置 hook）+ kivy_deps 动态库。

Kivy 数据/隐藏导入由 PyInstaller 自带 ``hook-kivy.py`` 收集，此处仅补齐
SDL2/GLEW/ANGLE 的 DLL。
"""
import os

from kivy_deps import angle, glew, sdl2

binaries = []
for dep in (sdl2, glew, angle):
    for bin_dir in dep.dep_bins:
        for name in os.listdir(bin_dir):
            binaries.append((os.path.join(bin_dir, name), "."))

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "tkinter", "setuptools", "jnius", "android"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="jam_intranexus",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="jam_intranexus",
)
