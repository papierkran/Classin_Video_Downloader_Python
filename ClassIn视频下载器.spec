# -*- mode: python ; coding: utf-8 -*-

# 说明：
# - 不再对 msedgedriver.exe 做硬依赖。
# - 程序运行时会通过 driver_auto.py 自动检测浏览器并下载/复制匹配 driver。
# - 这样打包时不需要预先把驱动放在项目目录里，也更适合分发。


a = Analysis(
    ['gui.py'],
    pathex=[],
    binaries=[],
    datas=[('image', 'image')],
    hiddenimports=['selenium', 'requests', 'webdriver_manager'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='ClassIn视频下载器',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
