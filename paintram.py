"""Paintram - launch with `python paintram.py [file ...]`.

Open source (GPL-3.0-or-later): https://github.com/pedramkhademi619/Paint
"""
import os
import sys


def _enable_portable_mode():
    """Installed layout: <root>/Paintram (frozen) or <root>/app/paintram.py, plus <root>/portable.marker.

    In that layout every cache, the AI model and the settings live under <root>, so deleting <root>
    removes all traces. A plain source checkout has no marker and is unaffected.
    """
    if getattr(sys, "frozen", False):                       # installed build: the folder holding the executable
        root = os.path.dirname(sys.executable)
    else:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if not os.path.isfile(os.path.join(root, "portable.marker")):
        return
    cache = os.path.join(root, "cache")
    defaults = {
        "PAINTRAM_PORTABLE_DIR": root,
        "PAINTRAM_MODELS_DIR": os.path.join(root, "models"),
        "HF_HOME": os.path.join(cache, "huggingface"),
        "TORCH_HOME": os.path.join(cache, "torch"),
        "XDG_CACHE_HOME": cache,
    }
    for key, value in defaults.items():
        os.environ.setdefault(key, value)


def _load_torch_before_qt():
    """Windows: PyTorch fails to initialise (c10.dll, WinError 1114) if PyQt5 was loaded first, so load it first.

    Only done when the AI libraries are installed and the user did not just ask for --version/--source.
    """
    if sys.platform != "win32" or any(a in sys.argv[1:] for a in ("--version", "--source")):
        return
    try:
        import torch  # noqa: F401
    except Exception:
        pass                                    # no AI libraries (or broken): the editor still works


_enable_portable_mode()
_load_torch_before_qt()

from paintapp.mainwindow import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
