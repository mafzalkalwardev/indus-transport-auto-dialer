"""
Build script — INDUS TRANSPORTS LLC Auto Dialer Pro
Run: python build_exe.py
"""
import subprocess
import sys
import os
import json


def pip_install(pkg):
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet", pkg])


DEPS = [
    "ttkbootstrap",
    "pyautogui",
    "pynput",
    "pandas",
    "openpyxl",
    "Pillow",
    "pyperclip",
    "selenium",
    "pygetwindow",
    "pyinstaller",
]

print("=" * 60)
print("  INDUS TRANSPORTS LLC — Auto Dialer Pro  |  Build Script")
print("=" * 60)
print("\n📦 Installing / verifying dependencies…")
for dep in DEPS:
    try:
        pip_install(dep)
        print(f"  ✅ {dep}")
    except Exception as e:
        print(f"  ⚠️  {dep} failed (non-fatal): {e}")

# ── Create default config if missing ───────────────────────────────
if not os.path.exists("dialer_config.json"):
    cfg = {
        "number_field":      [1514, 315],
        "call_button":       [1848, 309],
        "end_call_button":   [1693, 934],
        "excel_path":        "",
        "initial_delay":     5,
        "autocut_duration":  10,
        "browser_mode":      False,
        "chrome_debug_port": 9222,
    }
    with open("dialer_config.json", "w") as f:
        json.dump(cfg, f, indent=2)
    print("\n✅ Created default dialer_config.json")

# ── Convert logo PNG → ICO for EXE icon ────────────────────────────
LOGO_PNG = "Indus_Transports_LLC__1_-removebg-preview (1).png"
LOGO_ICO = "logo.ico"
icon_arg = []

if os.path.exists(LOGO_PNG):
    try:
        from PIL import Image
        img  = Image.open(LOGO_PNG).convert("RGBA")
        sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
        imgs  = []
        for sz in sizes:
            resized = img.copy()
            resized.thumbnail(sz, Image.LANCZOS)
            canvas = Image.new("RGBA", sz, (0, 0, 0, 0))
            offset = ((sz[0] - resized.width) // 2, (sz[1] - resized.height) // 2)
            canvas.paste(resized, offset)
            imgs.append(canvas)
        imgs[0].save(LOGO_ICO, format="ICO",
                     sizes=sizes, append_images=imgs[1:])
        print(f"\n✅ Created {LOGO_ICO} from PNG logo")
        icon_arg = ["--icon", LOGO_ICO]
    except Exception as e:
        print(f"\n⚠️  Could not create ICO (non-fatal): {e}")
else:
    print(f"\n⚠️  Logo PNG not found — building without custom icon")

# ── PyInstaller command ─────────────────────────────────────────────
sep = ";" if os.name == "nt" else ":"

cmd = [
    "pyinstaller",
    "--onefile",
    "--windowed",
    "--name", "IndusTransports_AutoDialer",
    "--add-data", f"dialer_config.json{sep}.",
]

# Include logo files if present
for logo in [LOGO_PNG, "Indus Transports LLC (1).jpeg"]:
    if os.path.exists(logo):
        cmd += ["--add-data", f"{logo}{sep}."]

if icon_arg:
    cmd += icon_arg

cmd.append("autodialer_gui.py")

print("\n🔨 Building EXE with PyInstaller…")
print("   Command:", " ".join(f'"{c}"' if " " in c else c for c in cmd))
print()

result = subprocess.run(cmd)

print()
if result.returncode == 0:
    print("=" * 60)
    print("  ✅  BUILD SUCCESSFUL!")
    print("  📁  EXE location:  dist/IndusTransports_AutoDialer.exe")
    print("=" * 60)
else:
    print("=" * 60)
    print("  ❌  BUILD FAILED — check output above.")
    print("=" * 60)
    sys.exit(1)
