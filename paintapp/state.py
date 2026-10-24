"""Shared tool/colour state observed by the canvas, option bar and panels."""
from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtGui import QColor

DEFAULTS = dict(
    size=12, opacity=100, hardness=70, smoothing=0,
    fill_mode="Outline", dash="Solid", antialias=True,
    tolerance=24, contiguous=True, sample="Layer",
    gradient="Linear", gradient_end="Secondary",
    font="Sans Serif", font_size=32, bold=False, italic=False,
    symmetry="Off", radius=18, star_points=5,
)

MAX_RECENT = 16


class AppState(QObject):
    changed = pyqtSignal(str)          # name of the option that changed
    colorsChanged = pyqtSignal()
    toolChanged = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        for key, value in DEFAULTS.items():
            setattr(self, key, value)
        self._primary = QColor(0, 0, 0)
        self._secondary = QColor(255, 255, 255)
        self.recent = []
        self.tool = "brush"

    def set(self, key, value):
        if getattr(self, key) != value:
            setattr(self, key, value)
            self.changed.emit(key)

    @property
    def primary(self):
        return QColor(self._primary)

    @primary.setter
    def primary(self, color):
        self._primary = QColor(color)
        self.colorsChanged.emit()

    @property
    def secondary(self):
        return QColor(self._secondary)

    @secondary.setter
    def secondary(self, color):
        self._secondary = QColor(color)
        self.colorsChanged.emit()

    def swap_colors(self, *_):
        self._primary, self._secondary = self._secondary, self._primary
        self.colorsChanged.emit()

    def reset_colors(self, *_):
        self._primary, self._secondary = QColor(0, 0, 0), QColor(255, 255, 255)
        self.colorsChanged.emit()

    def remember_color(self, color):
        color = QColor(color)
        self.recent = [c for c in self.recent if c.rgba() != color.rgba()]
        self.recent.insert(0, color)
        del self.recent[MAX_RECENT:]
        self.colorsChanged.emit()
