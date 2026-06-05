"""Build script for FT Solutions Auto Dialer Pro.

Run:
    python build_exe.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys


def pip_install(*packages: str) -> None:
    subprocess.check_call([sys.executable, "-m", "pip", "install", *packages])


DEPS = [
    "PyQt6",
    "PyQt6-WebEngine",
    "pandas",
    "openpyxl",
    "Pillow",
    "pyperclip",
    "pyinstaller",
    "psutil",
    "sounddevice",
    "webrtcvad-wheels",
]


print("=" * 60)
print("  FT Solutions - Auto Dialer Pro  |  Build")
print("=" * 60)
print("\nInstalling dependencies...")
for dep in DEPS:
    try:
        pip_install(dep)
        print(f"  OK {dep}")
    except Exception as exc:
        print(f"  WARN {dep}: {exc}")

if not os.path.exists("dialer_config.json"):
    with open("dialer_config.json", "w", encoding="utf-8") as f:
        json.dump(
            {
                "theme": "light",
                "n_slots": 2,
                "call_timeout": 60,
                "cooldown": 3.0,
                "voicemail_hangup_sec": 3,
                "excel_path": "",
                "enable_ai_audio": True,
                "audio_device": "",
                "live_debug_mode": False,
            },
            f,
            indent=2,
        )
    print("\nCreated default dialer_config.json")

LOGO_PNG = "ftsolutionslogo.jpg"
LOGO_ICO = "logo.ico"
icon_arg: list[str] = []
if os.path.exists(LOGO_PNG):
    try:
        from PIL import Image

        img = Image.open(LOGO_PNG).convert("RGBA")
        sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
        imgs = []
        for size in sizes:
            canvas = Image.new("RGBA", size, (0, 0, 0, 0))
            resized = img.copy()
            resized.thumbnail(size, Image.LANCZOS)
            canvas.paste(resized, ((size[0] - resized.width) // 2, (size[1] - resized.height) // 2))
            imgs.append(canvas)
        imgs[0].save(LOGO_ICO, format="ICO", sizes=sizes, append_images=imgs[1:])
        icon_arg = ["--icon", LOGO_ICO]
        print(f"\nCreated {LOGO_ICO}")
    except Exception as exc:
        print(f"\nICO creation failed (non-fatal): {exc}")

sep = ";" if os.name == "nt" else ":"

cmd = [
    "pyinstaller",
    "--onefile",
    "--windowed",
    "--name",
    "FTSolutions_AutoDialer",
    f"--add-data=dialer_config.json{sep}.",
    f"--add-data=src{sep}src",
    "--hidden-import=PyQt6.QtWebEngineWidgets",
    "--hidden-import=PyQt6.QtWebEngineCore",
    "--hidden-import=PyQt6.sip",
    "--hidden-import=pandas",
    "--hidden-import=openpyxl",
    "--hidden-import=PIL",
    "--hidden-import=pyperclip",
    "--hidden-import=psutil",
    "--hidden-import=sounddevice",
    "--exclude-module=webrtcvad",
    "--collect-all=PyQt6",
    "--collect-all=PyQt6.QtWebEngineWidgets",
    "--collect-all=sounddevice",
]

for logo in (LOGO_PNG,):
    if os.path.exists(logo):
        cmd.append(f"--add-data={logo}{sep}.")
if icon_arg:
    cmd += icon_arg
cmd.append("autodialer_gui.py")

print("\nBuilding EXE...")
result = subprocess.run(cmd)
print()
if result.returncode == 0:
    print("=" * 60)
    print("  BUILD SUCCESSFUL")
    print("  dist/FTSolutions_AutoDialer.exe")
    print("=" * 60)
else:
    print("Build failed - check output above.")
    sys.exit(1)
