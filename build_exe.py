"""
Build script — INDUS TRANSPORTS LLC Auto Dialer Pro
Run: python build_exe.py
"""
import json
import os
import subprocess
import sys


def pip(*pkgs):
    subprocess.check_call([sys.executable, "-m", "pip", "install", *pkgs])


DEPS = [
    "PyQt6", "PyQt6-WebEngine",
    "pandas", "openpyxl", "Pillow", "pyperclip", "pyinstaller",
]

print("=" * 60)
print("  INDUS TRANSPORTS LLC — Auto Dialer Pro  |  Build")
print("=" * 60)
print("\n📦 Installing dependencies…")
for dep in DEPS:
    try:
        pip(dep)
        print(f"  ✅ {dep}")
    except Exception as e:
        print(f"  ⚠️  {dep}: {e}")

# Default config
if not os.path.exists("dialer_config.json"):
    with open("dialer_config.json", "w") as f:
        json.dump({
            "theme": "dark",
            "n_slots": 2,
            "call_timeout": 60,
            "cooldown": 3.0,
            "voicemail_hangup_sec": 3,
            "excel_path": "",
        }, f, indent=2)
    print("\n✅ Created default dialer_config.json")

# ICO from logo PNG
LOGO_PNG = "Indus_Transports_LLC__1_-removebg-preview (1).png"
LOGO_ICO = "logo.ico"
icon_arg = []
if os.path.exists(LOGO_PNG):
    try:
        from PIL import Image
        img   = Image.open(LOGO_PNG).convert("RGBA")
        sizes = [(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)]
        imgs  = []
        for sz in sizes:
            c = Image.new("RGBA", sz, (0, 0, 0, 0))
            r = img.copy(); r.thumbnail(sz, Image.LANCZOS)
            c.paste(r, ((sz[0]-r.width)//2, (sz[1]-r.height)//2))
            imgs.append(c)
        imgs[0].save(LOGO_ICO, format="ICO",
                     sizes=sizes, append_images=imgs[1:])
        icon_arg = ["--icon", LOGO_ICO]
        print(f"\n✅ Created {LOGO_ICO}")
    except Exception as e:
        print(f"\n⚠️  ICO creation failed (non-fatal): {e}")

sep = ";" if os.name == "nt" else ":"

# PyQt6 WebEngine needs special hooks
cmd = [
    "pyinstaller", "--onefile", "--windowed",
    "--name", "IndusTransports_AutoDialer",
    f"--add-data=dialer_config.json{sep}.",
    f"--add-data=src{sep}src",
    "--hidden-import=PyQt6.QtWebEngineWidgets",
    "--hidden-import=PyQt6.QtWebEngineCore",
    "--hidden-import=PyQt6.sip",
    "--hidden-import=pandas",
    "--hidden-import=openpyxl",
    "--hidden-import=PIL",
    "--hidden-import=pyperclip",
    "--collect-all=PyQt6",
    "--collect-all=PyQt6.QtWebEngineWidgets",
]
for logo in (LOGO_PNG, "Indus Transports LLC (1).jpeg"):
    if os.path.exists(logo):
        cmd.append(f"--add-data={logo}{sep}.")
if icon_arg:
    cmd += icon_arg
cmd.append("autodialer_gui.py")

print("\n🔨 Building EXE…")
result = subprocess.run(cmd)
print()
if result.returncode == 0:
    print("=" * 60)
    print("  ✅  BUILD SUCCESSFUL")
    print("  📁  dist/IndusTransports_AutoDialer.exe")
    print("=" * 60)
else:
    print("❌  Build failed — check output above.")
    sys.exit(1)
