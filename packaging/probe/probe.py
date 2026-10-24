"""Smallest frozen program that imports PyTorch (optionally after PyQt5/numpy); used by the probe workflow to find
why a frozen build cannot load c10.dll on Windows. PROBE_ORDER=comma,separated,modules decides the import order."""
import importlib
import os
import sys
import traceback

print("frozen:", getattr(sys, "frozen", False), "| order:", os.environ.get("PROBE_ORDER", "torch"))
code = 0
for name in os.environ.get("PROBE_ORDER", "torch").split(","):
    try:
        mod = importlib.import_module(name)
        print("  imported", name, getattr(mod, "__version__", getattr(mod, "PYQT_VERSION_STR", "")))
    except BaseException:
        print("  FAILED to import", name)
        traceback.print_exc()
        code = 1
        break
sys.exit(code)
