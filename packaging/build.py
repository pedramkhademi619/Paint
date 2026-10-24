"""Build a finished installer for the platform you are running on.

    python packaging/build.py [--no-protect] [--skip-models] [--skip-bundle] [--version X.Y.Z]

Steps: download the AI models -> compile the package to native modules (so no Python source ships) ->
freeze with PyInstaller -> run the frozen program's --selftest -> wrap into the platform installer:
  Windows  build/installer/PaintramSetup-<ver>.exe (+ .bin slices)   needs Inno Setup 6
  Linux    build/installer/Paintram-<ver>-linux-x86_64.run           one self-extracting file

Needs: the CUDA build of torch on Windows/Linux, `pip install -r requirements-ai.txt pyinstaller cython setuptools`,
a C compiler, and network access to huggingface.co for the models.
"""
import argparse
import json
import os
import platform
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
BRAND = json.load(open(os.path.join(ROOT, "packaging", "brand.json")))
NAME = BRAND["name"]


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


def windows_version_file(brand, version):
    """PyInstaller version resource: what Explorer shows under Properties > Details."""
    v = tuple((list(int(x) for x in version.split(".") if x.isdigit()) + [0, 0, 0, 0])[:4])
    dotted = ".".join(str(x) for x in v)
    fields = [("CompanyName", brand["name"]), ("FileDescription", brand["name"] + " - " + brand["tagline"]),
              ("FileVersion", dotted), ("InternalName", brand["name"]), ("OriginalFilename", brand["name"] + ".exe"),
              ("LegalCopyright", "Copyright (C) 2024-2026 %s. %s." % (brand["author"], brand["license"])),
              ("ProductName", brand["name"]), ("ProductVersion", dotted),
              ("Comments", "Open source: " + brand["source_url"])]
    strings = ", ".join("StringStruct(%r, %r)" % kv for kv in fields)
    return ("VSVersionInfo(\n  ffi=FixedFileInfo(filevers=%r, prodvers=%r, mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1,"
            " subtype=0x0, date=(0, 0)),\n  kids=[\n    StringFileInfo([StringTable('040904B0', [%s])]),\n"
            "    VarFileInfo([VarStruct('Translation', [1033, 1200])])\n  ]\n)\n" % (v, v, strings))


def copy_docs(dist_dir):
    """Licence texts and the open-source note go next to the executable, as in any redistributable package."""
    from paintapp import provenance
    for name in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
        shutil.copy(os.path.join(ROOT, name), os.path.join(dist_dir, name))
    with open(os.path.join(dist_dir, "OPEN_SOURCE.txt"), "w", encoding="utf-8") as f:
        f.write(provenance.hello())
        f.write("\nThis program is free software (%s). The complete source code is at %s\n"
                "The AI models it uses have their own licences: see THIRD_PARTY_NOTICES.md.\n"
                % (BRAND["license"], BRAND["source_url"]))


def fetch_vc_redist():
    """The Visual C++ runtime installer, bundled so PyTorch starts on a clean Windows."""
    import urllib.request
    path = os.path.join(ROOT, "build", "redist", "vc_redist.x64.exe")
    if not os.path.isfile(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        print("Downloading the Visual C++ runtime installer…")
        urllib.request.urlretrieve("https://aka.ms/vs/17/release/vc_redist.x64.exe", path)
    return path


VC_RUNTIME = {"vcruntime140.dll", "vcruntime140_1.dll", "msvcp140.dll", "msvcp140_1.dll", "msvcp140_2.dll",
              "msvcp140_atomic_wait.dll", "msvcp140_codecvt_ids.dll", "concrt140.dll", "vcomp140.dll"}


def refresh_vc_runtime(dist_dir):
    """Replace the Visual C++ runtime DLLs PyInstaller copied (often old) with the current system ones.

    Current PyTorch fails with `WinError 1114` in c10.dll when it meets an older msvcp140/vcruntime140 than
    the one it was built with, and the bundled folder is searched before System32.
    """
    system32 = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32")
    replaced = []
    for base, _dirs, files in os.walk(os.path.join(dist_dir, "_internal")):
        for name in files:
            source = os.path.join(system32, name.lower())
            if name.lower() in VC_RUNTIME and os.path.isfile(source):
                shutil.copy2(source, os.path.join(base, name))
                replaced.append(os.path.relpath(os.path.join(base, name), dist_dir))
    print("Refreshed Visual C++ runtime DLLs from System32:", replaced or "none found")


def frozen_executable():
    if sys.platform == "win32":
        return os.path.join(ROOT, "dist", NAME, NAME + ".exe")
    return os.path.join(ROOT, "dist", NAME, NAME)


def selftest_diagnostics(exe, out, why):
    """Print everything useful about a failed self-test of the frozen program."""
    print("=== self-test FAILED: %s" % why)
    for path in (out, out + ".log"):
        if os.path.isfile(path):
            print("--- %s\n%s" % (path, open(path, errors="replace").read()[-6000:]))
    root = os.path.dirname(exe)
    plugins = [os.path.join(b, f) for b, _d, fs in os.walk(root) for f in fs if "platforms" in b and f.lower().startswith(("qoffscreen", "qwindows", "libqoffscreen", "libqxcb"))]
    print("--- Qt platform plugins in the bundle: %s" % (plugins or "NONE FOUND"))


def selftest(exe, want_models):
    """Run the frozen program headless and insist that it drew, undid, sees the AI libraries and the models."""
    import tempfile
    out = os.path.join(tempfile.mkdtemp(prefix="paintram-selftest-"), "report.json")
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", PAINTRAM_SELFTEST_OUT=out, PAINTRAM_SELFTEST_TIMEOUT="300")
    try:
        proc = subprocess.run([exe, "--selftest"], capture_output=True, text=True, env=env, timeout=420)
    except subprocess.TimeoutExpired:
        selftest_diagnostics(exe, out, "timed out after 420 s")
        raise SystemExit("Self-test of the frozen program timed out")
    if not os.path.isfile(out):
        selftest_diagnostics(exe, out, "no report written (exit code %s)\n%s\n%s" % (proc.returncode, proc.stdout[-1500:], proc.stderr[-1500:]))
        raise SystemExit("Self-test of the frozen program produced no report")
    report = json.load(open(out))
    print("self-test:", report)
    problems = []
    if proc.returncode != 0:
        problems.append("exit code %s (drew=%r)" % (proc.returncode, report.get("drew")))
    if not report.get("frozen"):
        problems.append("not running as a frozen program")
    if not report.get("ai_libs"):
        problems.append("AI libraries missing from the bundle: " + report.get("ai_note", ""))
    if want_models and not report.get("sketch_models"):
        problems.append("the AI models were not found next to the program")
    if problems:
        selftest_diagnostics(exe, out, "; ".join(problems))
        raise SystemExit("Self-test problems: " + "; ".join(problems))
    return report


def main():
    from paintapp import __version__
    from paintapp.ai import models
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-models", action="store_true", help="reuse build/models")
    ap.add_argument("--skip-bundle", action="store_true", help="reuse dist/")
    ap.add_argument("--no-protect", action="store_true", help="freeze the plain sources (development only)")
    ap.add_argument("--no-models", action="store_true", help="build an installer without the AI models (small, for testing)")
    ap.add_argument("--models-dir", default=os.path.join(ROOT, "build", "models"))
    ap.add_argument("--version", default=__version__)
    args = ap.parse_args()

    models_dir = args.models_dir
    if not args.no_models:
        if not args.skip_models:
            print("Downloading models into", models_dir)
            models.download(models_dir, lambda d, n, t: None)
        paths = models.ModelPaths(models_dir)
        if not (paths.complete() and paths.has_smart()):
            raise SystemExit("Model files are incomplete in %s: %s" % (models_dir, paths.missing()))

    if not args.skip_bundle:
        env = dict(os.environ)
        if not args.no_protect:
            protected = os.path.join(ROOT, "build", "protected")
            run([sys.executable, "packaging/protect.py", protected])
            env["PAINTRAM_PROTECTED"] = protected
        if sys.platform == "win32":
            with open(os.path.join(ROOT, "packaging", "win_version.txt"), "w", encoding="utf-8") as f:
                f.write(windows_version_file(BRAND, args.version))
        run([sys.executable, "-m", "PyInstaller", "packaging/paintram.spec", "--noconfirm", "--clean"], env=env)
    exe = frozen_executable()
    if not os.path.isfile(exe):
        raise SystemExit("%s missing: the PyInstaller step failed or was skipped" % exe)

    copy_docs(os.path.join(ROOT, "dist", NAME))
    if sys.platform == "win32":
        refresh_vc_runtime(os.path.join(ROOT, "dist", NAME))
    if not args.no_models:
        # put the models where the frozen program looks for them, then prove it finds them
        target = os.path.join(ROOT, "dist", NAME, "models")
        shutil.rmtree(target, ignore_errors=True)
        shutil.copytree(models_dir, target)
    selftest(exe, want_models=not args.no_models)

    out_dir = os.path.join(ROOT, "build", "installer")
    os.makedirs(out_dir, exist_ok=True)
    if sys.platform == "win32":
        make_ico()
        fetch_vc_redist()
        defines = ["/DAppVersion=" + args.version] + ([] if not args.no_models else ["/DNoModels=1"])
        run([find_iscc()] + defines + ["packaging/paintram.iss"])
    else:
        run([sys.executable, "packaging/linux/build_run.py", "--dist", os.path.join("dist", NAME), "--out", out_dir])
    print("\nInstaller written to build/installer/ (%s %s)" % (platform.system(), platform.machine()))


if __name__ == "__main__":
    main()
