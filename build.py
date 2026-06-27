"""One-click Windows build for INDUS TRANSPORTS LLC Auto Dialer.

Double-click ``Build Auto Dialer.bat`` or run::

    python build.py

Produces ``dist/IndusTransports_AutoDialer.exe`` ready for client delivery.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys


ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)

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
]


def pip_install(*packages: str) -> None:
    subprocess.check_call([sys.executable, "-m", "pip", "install", *packages])


def ensure_config() -> None:
    cfg_path = "dialer_config.json"
    example = "dialer_config.example.json"
    if os.path.exists(cfg_path):
        return
    if os.path.exists(example):
        with open(example, encoding="utf-8") as src:
            data = json.load(src)
        with open(cfg_path, "w", encoding="utf-8") as dst:
            json.dump(data, dst, indent=2)
        print(f"Created {cfg_path} from {example}")
        return
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "theme": "light",
                "n_slots": 1,
                "call_timeout": 60,
                "cooldown": 6.0,
                "voicemail_hangup_sec": 4,
                "excel_path": "",
                "deployment_mode": "admin",
                "enable_ai_audio": False,
                "single_agent_audio": True,
                "hold_message_enabled": True,
                "hold_message_text": "Please wait while we connect your call.",
            },
            f,
            indent=2,
        )
    print(f"Created default {cfg_path}")


def ensure_icon() -> list[str]:
    logo = "indus_transports_logo.jpg"
    ico = "logo.ico"
    if not os.path.exists(logo):
        return []
    try:
        from PIL import Image

        img = Image.open(logo).convert("RGBA")
        sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
        imgs = []
        for size in sizes:
            canvas = Image.new("RGBA", size, (0, 0, 0, 0))
            resized = img.copy()
            resized.thumbnail(size, Image.LANCZOS)
            canvas.paste(
                resized,
                ((size[0] - resized.width) // 2, (size[1] - resized.height) // 2),
            )
            imgs.append(canvas)
        imgs[0].save(ico, format="ICO", sizes=sizes, append_images=imgs[1:])
        print(f"Created {ico}")
        return ["--icon", ico]
    except Exception as exc:
        print(f"ICO creation skipped: {exc}")
        return []


def main() -> int:
    print("=" * 60)
    print("  INDUS TRANSPORTS LLC — Auto Dialer  |  Build")
    print("=" * 60)

    print("\nInstalling build dependencies...")
    for dep in DEPS:
        try:
            pip_install(dep)
            print(f"  OK {dep}")
        except Exception as exc:
            print(f"  WARN {dep}: {exc}")

    ensure_config()
    icon_args = ensure_icon()

    sep = ";" if os.name == "nt" else ":"
    cmd = [
        "pyinstaller",
        "--noconfirm",
        "--onefile",
        "--windowed",
        "--name",
        "IndusTransports_AutoDialer",
        f"--add-data=dialer_config.json{sep}.",
        f"--add-data=src{sep}src",
        f"--add-data=indus_transports_logo.jpg{sep}.",
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
        *icon_args,
        "autodialer_gui.py",
    ]

    print("\nBuilding EXE (this may take several minutes)...")
    result = subprocess.run(cmd)
    print()
    if result.returncode == 0:
        exe = os.path.join(ROOT, "dist", "IndusTransports_AutoDialer.exe")
        print("=" * 60)
        print("  BUILD SUCCESSFUL")
        print(f"  {exe}")
        print("=" * 60)
        print("\nNext steps:")
        print("  1. Test: double-click dist\\IndusTransports_AutoDialer.exe")
        print("  2. Admin: configure Google Voice in Settings")
        print("  3. Administration → Export client package for each agent PC")
        return 0

    print("Build failed — check output above.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
