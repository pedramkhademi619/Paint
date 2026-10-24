# PyInstaller spec:  pyinstaller packaging/paintram.spec --noconfirm --clean   (from the repo root)
# Set PAINTRAM_PROTECTED=<folder made by packaging/protect.py> to freeze the compiled modules instead of the sources.
import json
import os
import re
import sys

from PyInstaller.utils.hooks import collect_all

ROOT = os.path.dirname(SPECPATH)          # SPECPATH = this file's folder; keep every path independent of the cwd
BRAND = json.load(open(os.path.join(ROOT, "packaging", "brand.json")))
NAME = BRAND["name"]
VERSION = re.search(r'__version__\s*=\s*"([^"]+)"', open(os.path.join(ROOT, "paintapp", "__init__.py")).read()).group(1)
PROTECTED = os.environ.get("PAINTRAM_PROTECTED")
SRC = os.path.abspath(PROTECTED) if PROTECTED else ROOT
ICON = os.path.join(ROOT, "icons", "paint.png")

datas, binaries, hiddenimports = [(os.path.join(ROOT, "icons"), "icons")], [], []
for pkg in ("torch", "diffusers", "transformers", "accelerate", "safetensors", "peft", "huggingface_hub",
            "tokenizers", "regex", "numpy", "PIL"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h
if PROTECTED:                              # compiled modules hide their imports from PyInstaller's analysis
    hiddenimports.append("_freeze_imports")

a = Analysis(
    [os.path.join(SRC, "paintram.py")],
    pathex=[SRC],
    datas=datas,
    binaries=binaries,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "matplotlib", "pytest", "IPython", "tensorboard", "torch.utils.tensorboard"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name=NAME, console=False, icon=ICON)
coll = COLLECT(exe, a.binaries, a.datas, name=NAME, upx=False)
