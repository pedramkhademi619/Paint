"""Paintram - launch with `python paintram.py [file ...]`."""
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


_enable_portable_mode()

from paintapp.mainwindow import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
