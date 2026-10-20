"""Modal dialogs: new image, resize, canvas size, filters, shortcuts."""
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QColor, QPainter
from PyQt5.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel,
                             QSlider, QSpinBox, QTextBrowser, QVBoxLayout)

from . import imageutil
from .tools import TOOL_CLASSES

PRESETS = [("Custom", None), ("800 × 600", (800, 600)), ("1280 × 720 (HD)", (1280, 720)),
           ("1920 × 1080 (Full HD)", (1920, 1080)), ("512 × 512 (Icon)", (512, 512)),
           ("1080 × 1080 (Square)", (1080, 1080)), ("2480 × 3508 (A4 @300dpi)", (2480, 3508))]


def _buttons(dialog):
    box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    box.accepted.connect(dialog.accept)
    box.rejected.connect(dialog.reject)
    return box


def _size_spin(value):
    sp = QSpinBox()
    sp.setRange(1, 16000)
    sp.setValue(value)
    sp.setSuffix(" px")
    return sp


class NewImageDialog(QDialog):
    def __init__(self, parent, secondary):
        super().__init__(parent)
        self.setWindowTitle("New Image")
        self.secondary = secondary
        self.preset = QComboBox()
        for name, _ in PRESETS:
            self.preset.addItem(name)
        self.preset.setCurrentIndex(2)
        self.w, self.h = _size_spin(1280), _size_spin(720)
        self.bg = QComboBox()
        self.bg.addItems(["White", "Transparent", "Black", "Secondary colour"])
        form = QFormLayout(self)
        form.addRow("Preset", self.preset)
        form.addRow("Width", self.w)
        form.addRow("Height", self.h)
        form.addRow("Background", self.bg)
        form.addRow(_buttons(self))
        self.preset.currentIndexChanged.connect(self._preset)

    def _preset(self, i):
        size = PRESETS[i][1]
        if size:
            self.w.setValue(size[0])
            self.h.setValue(size[1])

    def result_values(self):
        color = {0: QColor("white"), 1: QColor(0, 0, 0, 0), 2: QColor("black"), 3: self.secondary}[self.bg.currentIndex()]
        return self.w.value(), self.h.value(), color


class ResizeDialog(QDialog):
    def __init__(self, parent, width, height):
        super().__init__(parent)
        self.setWindowTitle("Resize Image")
        self.ratio = width / float(height)
        self.w, self.h = _size_spin(width), _size_spin(height)
        self.keep = QCheckBox("Keep aspect ratio")
        self.keep.setChecked(True)
        self.smooth = QCheckBox("Smooth resampling")
        self.smooth.setChecked(True)
        form = QFormLayout(self)
        form.addRow("Width", self.w)
        form.addRow("Height", self.h)
        form.addRow(self.keep)
        form.addRow(self.smooth)
        form.addRow(_buttons(self))
        self.w.valueChanged.connect(lambda v: self._link(self.h, round(v / self.ratio)))
        self.h.valueChanged.connect(lambda v: self._link(self.w, round(v * self.ratio)))

    def _link(self, other, value):
        if self.keep.isChecked():
            other.blockSignals(True)
            other.setValue(max(1, value))
            other.blockSignals(False)


ANCHORS = {"Center": (0.5, 0.5), "Top left": (0, 0), "Top": (0.5, 0), "Top right": (1, 0), "Left": (0, 0.5),
           "Right": (1, 0.5), "Bottom left": (0, 1), "Bottom": (0.5, 1), "Bottom right": (1, 1)}


class CanvasSizeDialog(QDialog):
    def __init__(self, parent, width, height):
        super().__init__(parent)
        self.setWindowTitle("Canvas Size")
        self.w, self.h = _size_spin(width), _size_spin(height)
        self.anchor = QComboBox()
        self.anchor.addItems(list(ANCHORS))
        form = QFormLayout(self)
        form.addRow("Width", self.w)
        form.addRow("Height", self.h)
        form.addRow("Anchor", self.anchor)
        form.addRow(QLabel("New area is transparent."))
        form.addRow(_buttons(self))

    def anchor_value(self):
        return ANCHORS[self.anchor.currentText()]


class FilterDialog(QDialog):
    """Parameter dialog with live preview applied directly to the layer."""

    def __init__(self, parent, doc, name, func, params):
        super().__init__(parent)
        self.setWindowTitle(name)
        self.doc, self.func, self.name = doc, func, name
        self.layer = doc.active_layer
        self.original = self.layer.image.copy()
        self.values = {k: d for k, _l, _mn, _mx, d in params}
        form = QFormLayout(self)
        for key, label, lo, hi, default in params:
            row = QHBoxLayout()
            sl = QSlider(Qt.Horizontal)
            sl.setRange(lo, hi)
            sl.setValue(default)
            sl.setMinimumWidth(220)
            val = QLabel(str(default))
            val.setMinimumWidth(34)
            row.addWidget(sl)
            row.addWidget(val)
            form.addRow(label, row)
            sl.valueChanged.connect(lambda v, key=key, val=val: self._changed(key, v, val))
        if not params:
            form.addRow(QLabel("No options."))
        self.preview = QCheckBox("Preview")
        self.preview.setChecked(True)
        self.preview.toggled.connect(self._schedule)
        form.addRow(self.preview)
        form.addRow(_buttons(self))
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(90)
        self._timer.timeout.connect(self._render)
        self._schedule()

    def _changed(self, key, v, label):
        self.values[key] = v
        label.setText(str(v))
        self._schedule()

    def _schedule(self):
        self._timer.start()

    def _render(self):
        if not self.preview.isChecked():
            self.layer.image = self.original.copy()
        else:
            filtered = imageutil.from_array(self.func(imageutil.to_array(self.original), **self.values))
            img = self.original.copy()
            p = QPainter(img)
            if self.doc.selection is not None:
                p.setClipPath(self.doc.selection)
            p.setCompositionMode(QPainter.CompositionMode_Source)
            p.drawImage(0, 0, filtered)
            p.end()
            self.layer.image = img
        self.doc.invalidate()

    def done(self, result):
        self._timer.stop()
        self.layer.image = self.original            # restore, then apply through the undo stack
        self.doc.invalidate()
        if result == QDialog.Accepted:
            self.doc.modify_layer(self.name, lambda im: imageutil.from_array(
                self.func(imageutil.to_array(im), **self.values)), self.layer)
        super().done(result)


def shortcuts_html():
    rows = "".join("<tr><td><b>%s</b></td><td>%s</td></tr>" % (c.shortcut or "–", c.label)
                   for c in TOOL_CLASSES if c.shortcut)
    other = [("Ctrl+N / O / S", "New / Open / Save"), ("Ctrl+Shift+S", "Save As"),
             ("Ctrl+Z / Ctrl+Y", "Undo / Redo"), ("Ctrl+C / X / V", "Copy / Cut / Paste (as new layer)"),
             ("Ctrl+A / Ctrl+D", "Select all / Deselect"), ("Ctrl+Shift+I", "Invert selection"),
             ("Delete / Backspace", "Clear selection · Alt+Backspace fills with primary"),
             ("Ctrl+Shift+N", "New layer"), ("Ctrl+J", "Duplicate layer"), ("Ctrl+E", "Merge down"),
             ("X / D", "Swap / reset colours"), ("[ / ]", "Smaller / bigger brush"),
             ("Space + drag, middle mouse", "Pan"), ("Mouse wheel", "Zoom at cursor"),
             ("Ctrl+0 / Ctrl+1", "Fit to window / 100%"), ("Ctrl+' ", "Toggle grid"),
             ("Alt + click", "Pick colour (brush, pencil, bucket)"), ("Shift while dragging", "Constrain shape / line"),
             ("Alt while dragging a shape", "Draw from centre"), ("Right mouse button", "Draw with secondary colour")]
    rows2 = "".join("<tr><td><b>%s</b></td><td>%s</td></tr>" % o for o in other)
    return "<h3>Tools</h3><table cellspacing=6>%s</table><h3>General</h3><table cellspacing=6>%s</table>" % (rows, rows2)


class ShortcutsDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("Keyboard Shortcuts")
        self.resize(520, 560)
        view = QTextBrowser()
        view.setHtml(shortcuts_html())
        lay = QVBoxLayout(self)
        lay.addWidget(view)
        lay.addWidget(_buttons(self))
