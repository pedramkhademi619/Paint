"""Compile the application package to native extension modules (Cython) so the installer ships no Python source.

    python packaging/protect.py build/protected

Output folder layout (what PyInstaller freezes):
    paintram.py              tiny launcher stub (portable-mode setup only)
    _freeze_imports.py       `if False:` import list so PyInstaller can see what the compiled code needs
    paintapp/__init__.py     version string only
    paintapp/**/*.so|*.pyd   compiled modules, no .py / .pyc of the real code

Needs a C compiler (gcc/clang, or MSVC on Windows) and `pip install cython setuptools`.
"""
import ast
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = "paintapp"
KEEP_AS_SOURCE = {"__init__.py"}          # package markers only contain trivial code (version string)


def package_modules():
    """[(dotted_name, source_path)] for every non-trivial module of the package."""
    mods = []
    for base, _dirs, files in os.walk(os.path.join(ROOT, PKG)):
        if "__pycache__" in base:
            continue
        for f in sorted(files):
            if f.endswith(".py") and f not in KEEP_AS_SOURCE:
                path = os.path.join(base, f)
                rel = os.path.relpath(path, ROOT)[:-3].replace(os.sep, ".")
                mods.append((rel, path))
    return mods


def package_dirs():
    out = []
    for base, _dirs, files in os.walk(os.path.join(ROOT, PKG)):
        if "__pycache__" not in base and "__init__.py" in files:
            out.append(os.path.relpath(base, ROOT))
    return out


def external_imports(paths):
    """Top-level and dotted absolute imports used anywhere in `paths` (including inside functions)."""
    found = set()
    for path in paths:
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read(), path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                found.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                found.add(node.module)
                found.update("%s.%s" % (node.module, a.name) for a in node.names if a.name != "*")
    return sorted(n for n in found if n.split(".")[0] != PKG)


def write_import_manifest(out, mods):
    names = external_imports([p for _n, p in mods])
    lines = ['"""Import list for PyInstaller analysis only; never executed."""', "if False:  # pragma: no cover"]
    lines += ["    import %s" % n for n in names if not n.startswith("__")]
    lines += ["    import %s" % n for n, _p in mods]
    with open(os.path.join(out, "_freeze_imports.py"), "w") as f:
        f.write("\n".join(lines) + "\n")


def append_message(path):
    """Leave a note for whoever opens the binary: plain text after the end of the file (loaders ignore it)."""
    sys.path.insert(0, ROOT)
    from paintapp import provenance
    with open(path, "ab") as f:
        f.write(b"\n" + provenance.hello().encode("utf-8") + b"\n")


def binaries(out):
    return [os.path.join(b, f) for b, _d, fs in os.walk(os.path.join(out, PKG)) for f in fs
            if f.endswith((".so", ".pyd"))]


def compile_package(out):
    from Cython.Build import cythonize
    from setuptools import Extension, setup

    mods = package_modules()
    tmp = tempfile.mkdtemp(prefix="paint-protect-")
    try:
        exts = [Extension(name, [path]) for name, path in mods]
        cythonized = cythonize(exts, build_dir=os.path.join(tmp, "c"), quiet=True,
                               compiler_directives={"language_level": "3", "embedsignature": False})
        setup(name="paint-protected", ext_modules=cythonized, script_args=[
            "build_ext", "--build-lib", out, "--build-temp", os.path.join(tmp, "o"), "-q"])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return mods


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        raise SystemExit(__doc__)
    out = os.path.abspath(argv[0])
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(out)
    mods = compile_package(out)
    for d in package_dirs():
        os.makedirs(os.path.join(out, d), exist_ok=True)
        shutil.copy(os.path.join(ROOT, d, "__init__.py"), os.path.join(out, d, "__init__.py"))
    shutil.copy(os.path.join(ROOT, "paintram.py"), os.path.join(out, "paintram.py"))
    write_import_manifest(out, mods)
    for path in binaries(out):
        append_message(path)
    leaked = [os.path.join(b, f) for b, _d, fs in os.walk(os.path.join(out, PKG)) for f in fs
              if f.endswith((".py", ".pyc")) and f != "__init__.py"]
    if leaked:
        raise SystemExit("source files leaked into the output: %s" % leaked)
    print("Compiled %d modules into %s" % (len(mods), out))


if __name__ == "__main__":
    main()
