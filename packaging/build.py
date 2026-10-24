"""Build the Windows installer: model -> PyInstaller bundle -> Inno Setup.

    python packaging/build.py [--skip-models] [--skip-bundle] [--version 2.0.0]

Needs (on Windows): the CUDA build of torch + `pip install -r requirements-ai.txt pyinstaller`,
Inno Setup 6 (`iscc` on PATH or in Program Files), and network access to huggingface.co for the model.
"""
import argparse
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def run(cmd, **kw):
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True, cwd=ROOT, **kw)


def find_iscc():
    found = shutil.which("iscc")
    if found:
        return found
    for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles")):
        if base:
            cand = os.path.join(base, "Inno Setup 6", "ISCC.exe")
            if os.path.isfile(cand):
                return cand
    raise SystemExit("Inno Setup compiler (iscc) not found. Install Inno Setup 6.")


def make_ico():
    """Inno Setup needs a .ico; derive it from the PNG."""
    from PIL import Image
    ico = os.path.join(ROOT, "icons", "paint.ico")
    Image.open(os.path.join(ROOT, "icons", "paint.png")).convert("RGBA").save(
        ico, sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])


def main():
    from paintapp import __version__
    from paintapp.ai import models
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-models", action="store_true", help="reuse build/models")
    ap.add_argument("--skip-bundle", action="store_true", help="reuse dist/Paintram")
    ap.add_argument("--version", default=__version__)
    args = ap.parse_args()

    models_dir = os.path.join(ROOT, "build", "models")
    if not args.skip_models:
        from paintapp.ai import models
        print("Downloading model into", models_dir)
        models.download(models_dir, lambda d, n, t: None)
    if not models.ModelPaths(models_dir).complete():
        raise SystemExit("Model files are incomplete in %s" % models_dir)

    if not args.skip_bundle:
        run([sys.executable, "-m", "PyInstaller", "packaging/paintram.spec", "--noconfirm", "--clean"])
    if not os.path.isfile(os.path.join(ROOT, "dist", "Paintram", "Paintram.exe")):
        raise SystemExit("dist/Paintramram/Paintram.exe missing: PyInstaller step failed or was skipped")

    make_ico()
    run([find_iscc(), "/DAppVersion=" + args.version, "packaging/paintram.iss"])
    print("\nInstaller written to build/installer/")


if __name__ == "__main__":
    main()
