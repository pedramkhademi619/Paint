"""Smallest possible frozen program that imports PyTorch; used by the probe workflow to find why a frozen
build cannot load c10.dll on Windows."""
import os
import sys
import traceback

print("frozen:", getattr(sys, "frozen", False), "| exe:", sys.executable)
try:
    import torch
    print("OK torch", torch.__version__, "| cuda available:", torch.cuda.is_available())
except BaseException:
    traceback.print_exc()
    sys.exit(1)
