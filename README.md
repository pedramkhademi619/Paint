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
  widgets.py          icons, colour picker, layer panel, option bar
  dialogs.py          new / resize / canvas size / filter dialogs
  mainwindow.py       menus, docks, status bar, theme
tests/test_paint.py   headless test suite
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
