# Paint

A layered raster editor written in Python with PyQt5. It started as a one-file doodle app and is now a
small but serious image editor: layers with blend modes, selections, 25 tools, filters with live preview,
symmetry painting, a full undo history and a project format that keeps your layers.

## Run it

```bash
pip install -r requirements.txt        # PyQt5 + numpy
python paint.py                        # or: python paint.py picture.png project.pnt
```

Python 3.8+ is required. Drag image files onto the window to open them.

## Features

**Painting**
- Brush (soft/hard, smoothing/stabiliser), pixel Pencil, Eraser, Airbrush
- Mirror painting: horizontal, vertical, both, or 6-fold radial symmetry
- Per-stroke opacity (overlapping strokes never double-darken), right mouse button paints with the secondary colour
- `Alt`+click picks a colour while using the brush, pencil or bucket

**Shapes**
- Line, arrow, rectangle, rounded rectangle, ellipse, triangle, diamond, star (adjustable points), heart, polygon
- Outline / fill / both, dashed and dotted lines, anti-aliasing switch
- `Shift` constrains (square, circle, 45° lines), `Alt` draws from the centre

**Fill and colour**
- Paint bucket with tolerance, contiguous or global mode, sampling from the layer or the merged image
- Linear and radial gradients (to the secondary colour or to transparent)
- Colour picker, HSV square, hue and alpha sliders, hex input, palette and recent colours
- Text tool with font, size, bold and italic

**Layers**
- Unlimited layers: add, duplicate, delete, reorder, merge down, flatten, rename, lock, hide
- Per-layer opacity and 12 blend modes (Multiply, Screen, Overlay, Soft Light, Difference, …)
- Paste always creates a new layer; thumbnails in the layer panel

**Selections**
- Rectangle, ellipse, lasso and magic wand; `Ctrl` adds, `Alt` subtracts, `Ctrl+Alt` intersects
- Move selected pixels (or the whole layer; `Alt`-drag copies), invert, crop to selection
- Marching-ants outline; painting, filters, fill and delete all respect the selection

**Image**
- Resize image, canvas size with anchor, rotate, flip, flatten, crop
- Filters with live preview: brightness/contrast, hue/saturation, grayscale, sepia, invert, blur,
  sharpen, pixelate, posterize, noise, edge detect

**Workflow**
- Undo/redo history panel (click any step to jump), memory-efficient (stores only the changed rectangle)
- Zoom at cursor, pan with `Space`/middle mouse, fit, 100 %, pixel grid, custom grid
- Dark and light themes, recent files, unsaved-changes prompt, multiple windows
- Open/save PNG, JPEG, BMP, WebP, TIFF and the layered `.pnt` project format (a zip of PNG layers + JSON)

## AI image generation (local, offline)

Paint can generate and edit images with **Stable Diffusion 1.5 + LCM-LoRA** running on your own GPU.
Nothing is sent to a server. LCM makes it fast: a 512×512 image takes about 1–2 s on a recent NVIDIA card
with 4–6 steps. Results always arrive as a **new layer**, so they are non-destructive and undoable.

| Mode | What it does |
|---|---|
| Text → Image | Generate a picture from a prompt (clipped to the selection if there is one) |
| Image → Image | Restyle what you see on the canvas (or inside the selection); *Strength* sets how far it may drift |
| Inpaint selection | Select an area, describe what should be there, and the AI repaints only that area |

Open the **AI** panel (right side, `Ctrl+Shift+G`). Style presets, negative prompt, steps, guidance, seed
(random seeds are shown after a run so you can reproduce them) and Cancel are included.

### Install

*Windows installer* (everything bundled: app, CUDA runtime, model): build it with
`python packaging/build.py` or the **Build Windows installer** GitHub Action (see below).

*From source*:

```bash
pip install torch --index-url https://download.pytorch.org/whl/cu128   # NVIDIA GPU build
pip install -r requirements-ai.txt
python -m paintapp.ai.models download      # ~2.2 GB into ~/.local/share/paint/models (or %LOCALAPPDATA%\Paint\models)
python paint.py
```

You can also press **Download model** inside the AI panel. The model is looked up in `$PAINT_MODELS_DIR`,
then `models/` next to the program (where the installer puts it), then the per-user folder above.
Without a GPU it still works on the CPU, but slowly. Cards under ~5.5 GB VRAM use a low-memory mode automatically.

### Building the installer

`packaging/build.py` downloads the model, freezes the app with PyInstaller (`packaging/paint.spec`) and
compiles `packaging/paint.iss` with Inno Setup 6, producing `build/installer/PaintSetup-<version>.exe`
plus `.bin` slices (keep them in the same folder; each is < 2 GiB). The workflow
`.github/workflows/build-installer.yml` does this on `windows-latest` and attaches the files to a release
when you push a `v*` tag.

### Licences and safety

The bundled weights are Stable Diffusion 1.5 (CreativeML OpenRAIL-M) and LCM-LoRA (OpenRAIL++). Read and
accept their licences before distributing the installer. **No NSFW/safety filter is included**; add one if
you distribute this to others.

## Shortcuts

Press `F1` in the app for the full list. The most useful ones:

| Key | Action | Key | Action |
|---|---|---|---|
| `B` `N` `E` `A` | Brush, Pencil, Eraser, Airbrush | `V` `H` `Z` | Move, Pan, Zoom |
| `L` `R` `O` `P` | Line, Rectangle, Ellipse, Polygon | `M` `Q` `W` | Rect select, Lasso, Magic wand |
| `G` `I` `T` | Bucket, Picker, Text | `[` `]` | Brush size |
| `X` `D` | Swap / reset colours | `Ctrl+Z` `Ctrl+Y` | Undo / Redo |
| `Ctrl+C/X/V` | Copy / Cut / Paste as layer | `Ctrl+J` `Ctrl+E` | Duplicate / Merge layer |
| `Ctrl+0` `Ctrl+1` | Fit / 100 % | `Delete` | Clear selection |

> Note: `Ctrl+C` is now *Copy* (it used to clear the canvas). Use `Select All` + `Delete` to clear.

## Project layout

```
paint.py              entry point
paintapp/
  document.py         layers, selection, undo commands, file I/O
  canvas.py           view transform, rendering, input dispatch
  tools.py            all tools (freehand, shapes, fill, selection, move, ...)
  imageutil.py        NumPy flood fill and filters
  ai/                 local Stable Diffusion: models.py (paths/download), engine.py, worker.py, panel.py
  widgets.py          icons, colour picker, layer panel, option bar
  dialogs.py          new / resize / canvas size / filter dialogs
  mainwindow.py       menus, docks, status bar, theme
packaging/            PyInstaller spec, Inno Setup script, build.py
tests/                headless test suites (editor, AI panel, AI engine)
```

## Tests

```bash
QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests
```

---

## فارسی

`Paint` یک نرم‌افزار نقاشی لایه‌ای با PyQt5 است: لایه‌ها با حالت‌های ترکیب (Blend)، انتخاب‌گرهای متنوع،
۲۵ ابزار، فیلترها با پیش‌نمایش زنده، نقاشی متقارن، تاریخچه‌ی کامل Undo/Redo و فرمت پروژه‌ی `.pnt`
که لایه‌ها را نگه می‌دارد.

اجرا: `pip install -r requirements.txt` و سپس `python paint.py`. برای دیدن همه‌ی میانبرها `F1` را بزنید.
