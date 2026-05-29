# -*- mode: python ; coding: utf-8 -*-
# INDUS TRANSPORTS LLC — Auto Dialer Pro spec file
import os

LOGO_PNG  = "Indus_Transports_LLC__1_-removebg-preview (1).png"
LOGO_JPEG = "Indus Transports LLC (1).jpeg"
LOGO_ICO  = "logo.ico"

datas = [("dialer_config.json", ".")]
if os.path.exists(LOGO_PNG):
    datas.append((LOGO_PNG, "."))
if os.path.exists(LOGO_JPEG):
    datas.append((LOGO_JPEG, "."))

icon = LOGO_ICO if os.path.exists(LOGO_ICO) else None

a = Analysis(
    ["autodialer_gui.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "PIL",
        "PIL.Image",
        "PIL.ImageTk",
        "pyperclip",
        "selenium",
        "pygetwindow",
        "pandas",
        "openpyxl",
        "pynput",
        "pynput.keyboard",
        "pynput.mouse",
        "ttkbootstrap",
    ],
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
    name="IndusTransports_AutoDialer",
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
    icon=icon,
)
