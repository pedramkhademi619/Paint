# PyInstaller spec: `pyinstaller packaging/paintram.spec --noconfirm` (run from the repo root)
import os

from PyInstaller.utils.hooks import collect_all

ROOT = os.path.dirname(SPECPATH)          # SPECPATH = this file's folder; paths below must not depend on the cwd
datas, binaries, hiddenimports = [(os.path.join(ROOT, "icons"), "icons")], [], []
for pkg in ("torch", "diffusers", "transformers", "accelerate", "safetensors", "peft", "huggingface_hub",
            "tokenizers", "regex", "numpy"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

a = Analysis(
    [os.path.join(ROOT, "paintram.py")],
    pathex=[ROOT],
    datas=datas,
    binaries=binaries,
    hiddenimports=hiddenimports + ["paintapp.ai.models", "paintapp.ai.engine"],
    excludes=["tkinter", "matplotlib", "pytest", "IPython", "tensorboard"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Paintram", console=False, icon=os.path.join(ROOT, "icons", "paint.png"))
coll = COLLECT(exe, a.binaries, a.datas, name="Paintram", upx=False)
