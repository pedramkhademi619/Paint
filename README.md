# Paintram

A layered image editor with **local AI**, for Windows and Linux. Draw a rough scribble and Paintram
recognises what it is and redraws it neatly; generate or restyle pictures from text; all of it runs on
your own computer, nothing is uploaded.

Free and open source ([GPL-3.0-or-later](LICENSE)), by [pedramkhademi619](https://github.com/pedramkhademi619).

## Install (end users)

Download the installer for your system and run it. Everything is inside it (program, Python, AI engine
and the AI models), so nothing else is downloaded. It installs like any commercial application.

| System | File | How |
|---|---|---|
| Windows 10/11 (64-bit) | `PaintramSetup-<version>.exe` (+ the `.bin` files next to it) | Double-click, Next, Next, Finish. Uninstall from *Settings > Apps*. |
| Linux (x86-64) | `Paintram-<version>-linux-x86_64.run` | `sh Paintram-*.run` (no root needed). Uninstall: `~/.local/share/paintram/uninstall.sh`. |

Both remove **everything** when uninstalled (program, models, caches, settings, menu entries).
An NVIDIA GPU makes the AI fast (about 1-2 s per image); without one the AI still works on the CPU, slowly.
Linux installer options: `--prefix DIR`, `--system` (for all users, as root), `--yes`, `--check`, `--uninstall`.

## What it does

**AI**
- **Sketch → Neat**: draw anything rough. A CLIP model names it (cat, house, car, flower, ... 377
  categories, top-3 guesses shown); Stable Diffusion + ControlNet-Scribble redraws it cleanly along your
  lines as clean line art, an illustration, a flat icon, a realistic picture or a watercolor. If the guess is
  wrong, pick or type the right word and press Generate again. Your sketch is hidden, not destroyed.
- **Text → Image**, **Image → Image** (restyle), **Inpaint selection** (repaint just the selected area)
- Everything arrives as a new layer, undoable in one step. Seeds are shown so results can be reproduced.

**Smart pen** (`S`): draw a line, circle, ellipse, rectangle, square, triangle, diamond, star or
heart roughly and it snaps to the clean shape. Hold the pointer still to preview it, hold `Alt` when you
release to keep your own line. No AI model needed.

**Editor**: layers with 12 blend modes, 26 tools (brush, pencil, eraser, airbrush, shapes, bucket, gradient,
text, selections, magic wand, move, ...), symmetry painting, filters with live preview, zoom/pan, undo history
panel, dark/light theme, PNG/JPEG/BMP/WebP/TIFF and a layered `.pnt` project format.

Press `F1` in the app for all shortcuts.

## For the developer

The source lives in this repository. The installers ship the program compiled to native modules
(`packaging/protect.py`, Cython) so it starts fast and looks like any polished product; if you open the
binaries anyway, they point you back here (`paintram --source` prints the note).

```bash
pip install -r requirements.txt                 # editor only
python paintram.py

pip install torch --index-url https://download.pytorch.org/whl/cu128    # NVIDIA GPU build
pip install -r requirements-ai.txt              # + AI
python -m paintapp.ai.models download           # ~3.5 GB of models into the per-user folder
```

Tests (headless): `QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests`
(the AI engine tests use tiny generated models and are skipped when torch is not installed).

### Building the installers

On the target system: `python packaging/build.py` (needs the CUDA build of torch,
`pip install -r requirements-ai.txt pyinstaller cython setuptools`, a C compiler, Inno Setup 6 on Windows, and
network access to huggingface.co). It downloads the models, compiles the package, freezes it with PyInstaller,
runs the frozen program's `--selftest`, then builds the installer into `build/installer/`.

Or let GitHub do it: *Actions > Build Paintram installers > Run workflow* (builds Windows and Linux and
uploads them as artifacts, with SHA-256 sums). The installers are several GB, so host them on your own
storage; GitHub release assets are limited to 2 GiB per file.

Rename the product in one place: `paintapp/brand.py` and `packaging/brand.json`.

### Licences

The models are Stable Diffusion 1.5 (CreativeML OpenRAIL-M), LCM-LoRA (OpenRAIL++), ControlNet v1.1 Scribble
(CreativeML OpenRAIL-M) and OpenAI CLIP ViT-B/32 (MIT). Read the licences before distributing the installers.
**No NSFW/safety filter is included**; add one if you distribute Paintram to others.
PyQt5 is GPL v3, which is why Paintram itself is GPL-3.0-or-later: anyone you give an installer to must be
able to get the source (this repository) and may redistribute it under the same terms.
See `LICENSE` and `THIRD_PARTY_NOTICES.md`; both also ship inside the installers and in *Help > Licences*.

---

## فارسی

**Paintram** یک نرم‌افزار نقاشی لایه‌ای با هوش مصنوعیِ محلی است (ویندوز و لینوکس). یک خط‌خطی کج‌ومعوج بکشید؛
برنامه تشخیص می‌دهد چیست (گربه، خانه، ماشین، گل و...) و نسخه‌ی تمیز و زیبایش را می‌کشد. «قلم هوشمند» (`S`) هم
قلب، دایره، ستاره، مستطیل و... را فوراً صاف و مرتب می‌کند.

**نصب:** فایل نصب‌کننده‌ی سیستم خودتان را اجرا کنید. برنامه، موتور هوش مصنوعی و مدل‌ها همه داخل خودش است، چیزی دانلود
نمی‌شود. حذف برنامه همه‌چیز را پاک می‌کند. پروژه متن‌باز (GPL-3.0) است:
https://github.com/pedramkhademi619/Paint
