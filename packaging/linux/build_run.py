"""Build the self-extracting Linux installer from a PyInstaller folder (and optionally the AI models).

    python packaging/linux/build_run.py --dist dist/Paintram --models build/models [--out build/installer]

The result is ONE file: a shell-script header followed by a gzip-compressed tar of the program folder with
the models in <install>/models. Run it with `sh Paintram-2.1.0-linux-x86_64.run`.
"""
import argparse
import gzip
import json
import os
import re
import stat
import tarfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HEADER = os.path.join(ROOT, "packaging", "linux", "header.sh")
MARKER = "__PAYLOAD_BELOW__\n"


def tree_size(path):
    return sum(os.path.getsize(os.path.join(b, f)) for b, _d, fs in os.walk(path) for f in fs
               if os.path.isfile(os.path.join(b, f)))


def version():
    src = open(os.path.join(ROOT, "paintapp", "__init__.py")).read()
    return re.search(r'__version__\s*=\s*"([^"]+)"', src).group(1)


def render_header(brand, ver, out_name, unpacked_kb):
    text = open(HEADER).read()
    for key, value in {"__NAME__": brand["name"], "__SLUG__": brand["slug"], "__VERSION__": ver,
                       "__APP_ID__": brand["app_id"], "__TAGLINE__": brand["tagline"], "__EXE__": brand["name"],
                       "__FILE__": out_name, "__UNPACKED_KB__": str(unpacked_kb)}.items():
        text = text.replace(key, value)
    # the payload starts on the line after the marker; substituting the number does not change the line count
    return text.replace("__PAYLOAD_LINE__", str(text.count("\n") + 1))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dist", required=True, help="PyInstaller output folder (contains the executable)")
    ap.add_argument("--models", help="folder with the AI models to bundle (copied to <install>/models)")
    ap.add_argument("--out", default=os.path.join(ROOT, "build", "installer"))
    ap.add_argument("--level", type=int, default=3, help="gzip level (1 fastest .. 9 smallest)")
    args = ap.parse_args(argv)

    brand = json.load(open(os.path.join(ROOT, "packaging", "brand.json")))
    ver = version()
    dist = os.path.abspath(args.dist)
    if not os.path.isfile(os.path.join(dist, brand["name"])):
        raise SystemExit("%s/%s not found: run PyInstaller first" % (dist, brand["name"]))
    sources = [(dist, "")]
    if args.models:
        sources.append((os.path.abspath(args.models), "models"))
    unpacked = sum(tree_size(p) for p, _ in sources)
    os.makedirs(args.out, exist_ok=True)
    out_name = "%s-%s-linux-x86_64.run" % (brand["name"], ver)
    out_path = os.path.join(args.out, out_name)
    header = render_header(brand, ver, out_name, unpacked // 1024 + 1)
    assert header.endswith(MARKER), "header must end with the payload marker"

    with open(out_path, "wb") as f:
        f.write(header.encode())
        with gzip.GzipFile(fileobj=f, mode="wb", compresslevel=args.level, mtime=0) as gz:
            with tarfile.open(fileobj=gz, mode="w|", format=tarfile.GNU_FORMAT) as tar:
                for base, prefix in sources:
                    for name in sorted(os.listdir(base)):
                        tar.add(os.path.join(base, name), arcname=os.path.join(prefix, name) if prefix else name)
    os.chmod(out_path, os.stat(out_path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    print("Wrote %s (%.0f MB, unpacks to %.0f MB)" % (out_path, os.path.getsize(out_path) / 1e6, unpacked / 1e6))
    return out_path


if __name__ == "__main__":
    main()
