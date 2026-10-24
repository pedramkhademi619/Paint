"""UI building blocks: vector icons, colour picker, layer panel, option bar."""
import math

from PyQt5 import sip
from PyQt5.QtCore import QPointF, QRectF, QSize, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import (QBrush, QColor, QFont, QIcon, QImage, QLinearGradient, QPainter, QPainterPath, QPen,
                         QPixmap, QPolygonF)
from PyQt5.QtWidgets import (QCheckBox, QComboBox, QFontComboBox, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                             QListWidget, QListWidgetItem, QSizePolicy, QSlider, QSpinBox, QToolBar, QToolButton,
                             QVBoxLayout, QWidget)

from .document import BLEND_MODES

# ------------------------------------------------------------------ icons
# Each function draws into a 24x24 box with the given colour.


def _stroke(p, c, w=1.8):
    p.setPen(QPen(c, w, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(Qt.NoBrush)


def _fill(p, c):
    p.setPen(Qt.NoPen)
    p.setBrush(c)


def _poly(*pts):
    return QPolygonF([QPointF(x, y) for x, y in pts])


def _shape_icon(draw):
    def f(p, c):
        _stroke(p, c)
        draw(p, c)
    return f


def i_brush(p, c):
    _stroke(p, c, 2.2)
    p.drawLine(QPointF(19, 4), QPointF(10.5, 12.5))
    _fill(p, c)
    p.drawEllipse(QPointF(8, 16), 4.2, 4.2)


def i_pencil(p, c):
    _stroke(p, c, 1.6)
    p.drawPolygon(_poly((16, 3.5), (20.5, 8), (9, 19.5), (4, 20.5), (4.5, 15.5)))
    p.drawLine(QPointF(13.5, 6), QPointF(18, 10.5))


def i_eraser(p, c):
    _stroke(p, c, 1.6)
    p.drawPolygon(_poly((9, 19), (3.5, 13.5), (14, 3.5), (20.5, 10), (12, 19)))
    p.drawLine(QPointF(7, 8.2), QPointF(16, 17))
    p.drawLine(QPointF(9, 20), QPointF(21, 20))


def i_airbrush(p, c):
    _fill(p, c)
    for x, y, r in [(6, 7, 1.3), (11, 5, 1), (15, 8, 1.4), (9, 11, 1.2), (14, 13, 1), (18, 12, 1),
                    (6, 15, 1), (11, 17, 1.4), (16, 18, 1.1), (19, 6, 0.9), (4, 11, 0.9), (20, 16, 0.9)]:
        p.drawEllipse(QPointF(x, y), r, r)


def i_smartpen(p, c):
    _stroke(p, c, 1.7)
    h = QPainterPath()                                   # a tidy heart plus a sparkle = "it cleans up your shapes"
    h.moveTo(9, 20)
    h.cubicTo(1.5, 14.5, 2.5, 8, 7, 7.5)
    h.cubicTo(8.7, 7.4, 9, 8.6, 9, 9.5)
    h.cubicTo(9, 8.6, 9.4, 7.4, 11, 7.5)
    h.cubicTo(15.5, 8, 16.5, 14.5, 9, 20)
    p.drawPath(h)
    _stroke(p, c, 1.4)
    for x, y, r in ((18.5, 5.5, 3.2), (21, 12, 1.8)):
        p.drawLine(QPointF(x - r, y), QPointF(x + r, y))
        p.drawLine(QPointF(x, y - r), QPointF(x, y + r))


def i_line(p, c):
    _stroke(p, c, 2)
    p.drawLine(QPointF(5, 19), QPointF(19, 5))


def i_arrow(p, c):
    _stroke(p, c, 2)
    p.drawLine(QPointF(5, 19), QPointF(18, 6))
    _fill(p, c)
    p.drawPolygon(_poly((20, 4), (11.5, 6.5), (17.5, 12.5)))


def i_rect(p, c):
    _stroke(p, c)
    p.drawRect(QRectF(4.5, 6.5, 15, 11))


def i_roundrect(p, c):
    _stroke(p, c)
    p.drawRoundedRect(QRectF(4.5, 6.5, 15, 11), 4, 4)


def i_ellipse(p, c):
    _stroke(p, c)
    p.drawEllipse(QRectF(4.5, 6, 15, 12))


def i_triangle(p, c):
    _stroke(p, c)
    p.drawPolygon(_poly((12, 4.5), (20, 19), (4, 19)))


def i_diamond(p, c):
    _stroke(p, c)
    p.drawPolygon(_poly((12, 3.5), (20.5, 12), (12, 20.5), (3.5, 12)))


def i_star(p, c):
    _stroke(p, c, 1.6)
    pts = []
    for i in range(10):
        a = -math.pi / 2 + i * math.pi / 5
        k = 8.5 if i % 2 == 0 else 3.6
        pts.append((12 + k * math.cos(a), 12.5 + k * math.sin(a)))
    p.drawPolygon(_poly(*pts))


def i_heart(p, c):
    _stroke(p, c, 1.8)
    h = QPainterPath()
    h.moveTo(12, 20)
    h.cubicTo(2, 13, 2.5, 5.5, 8, 5)
    h.cubicTo(10.5, 4.8, 12, 6.5, 12, 8)
    h.cubicTo(12, 6.5, 13.5, 4.8, 16, 5)
    h.cubicTo(21.5, 5.5, 22, 13, 12, 20)
    p.drawPath(h)


def i_polygon(p, c):
    _stroke(p, c)
    p.drawPolygon(_poly((5, 8), (13, 4), (20, 11), (16, 19), (6, 17)))


def i_fill(p, c):
    _stroke(p, c, 1.7)
    p.drawPolygon(_poly((4, 12), (11, 5), (18, 12), (11, 19)))
    p.drawLine(QPointF(7.5, 8.5), QPointF(14.5, 15.5))
    _fill(p, c)
    d = QPainterPath()
    d.moveTo(20, 14)
    d.cubicTo(18.5, 16.5, 18, 17.5, 18, 18.5)
    d.cubicTo(18, 21, 22, 21, 22, 18.5)
    d.cubicTo(22, 17.5, 21.5, 16.5, 20, 14)
    p.drawPath(d)


def i_gradient(p, c):
    g = QLinearGradient(4, 0, 20, 0)
    g.setColorAt(0, c)
    g.setColorAt(1, QColor(c.red(), c.green(), c.blue(), 20))
    p.setPen(QPen(c, 1.5))
    p.setBrush(QBrush(g))
    p.drawRoundedRect(QRectF(3.5, 5.5, 17, 13), 2, 2)


def i_picker(p, c):
    _stroke(p, c, 1.8)
    p.drawLine(QPointF(5, 19), QPointF(13, 11))
    p.drawLine(QPointF(8, 20), QPointF(4, 16))
    _fill(p, c)
    p.drawPolygon(_poly((13.5, 5.5), (18.5, 10.5), (16, 13), (11, 8)))
    p.drawEllipse(QPointF(18.5, 5.5), 2.5, 2.5)


def i_text(p, c):
    p.setPen(c)
    f = QFont("Sans Serif")
    f.setPixelSize(20)
    f.setBold(True)
    p.setFont(f)
    p.drawText(QRectF(0, 0, 24, 24), Qt.AlignCenter, "T")


def _dashed(p, c, w=1.6):
    pen = QPen(c, w, Qt.DashLine, Qt.RoundCap)
    pen.setDashPattern([2.2, 1.8])
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)


def i_select_rect(p, c):
    _dashed(p, c)
    p.drawRect(QRectF(4.5, 5.5, 15, 13))


def i_select_ellipse(p, c):
    _dashed(p, c)
    p.drawEllipse(QRectF(4.5, 5, 15, 14))


def i_lasso(p, c):
    _dashed(p, c)
    path = QPainterPath()
    path.moveTo(5, 10)
    path.cubicTo(5, 3, 20, 3, 20, 9)
    path.cubicTo(20, 15, 11, 15, 10, 13)
    path.cubicTo(8, 17, 9, 20, 6, 21)
    p.drawPath(path)


def i_wand(p, c):
    _stroke(p, c, 2.2)
    p.drawLine(QPointF(5, 20), QPointF(15, 10))
    _stroke(p, c, 1.4)
    for x, y in [(17.5, 4), (20.5, 8), (13.5, 5.5)]:
        p.drawLine(QPointF(x - 1.5, y), QPointF(x + 1.5, y))
        p.drawLine(QPointF(x, y - 1.5), QPointF(x, y + 1.5))


def i_move(p, c):
    _stroke(p, c, 1.8)
    p.drawLine(QPointF(12, 3.5), QPointF(12, 20.5))
    p.drawLine(QPointF(3.5, 12), QPointF(20.5, 12))
    _fill(p, c)
    for pts in [((12, 2), (9.5, 5.5), (14.5, 5.5)), ((12, 22), (9.5, 18.5), (14.5, 18.5)),
                ((2, 12), (5.5, 9.5), (5.5, 14.5)), ((22, 12), (18.5, 9.5), (18.5, 14.5))]:
        p.drawPolygon(_poly(*pts))


def i_hand(p, c):
    _stroke(p, c, 1.6)
    path = QPainterPath()
    path.moveTo(7, 12)
    path.lineTo(7, 6.5)
    path.moveTo(10, 11)
    path.lineTo(10, 4.5)
    path.moveTo(13, 11)
    path.lineTo(13, 5)
    path.moveTo(16, 12)
    path.lineTo(16, 7.5)
    p.drawPath(path)
    body = QPainterPath()
    body.moveTo(7, 12)
    body.lineTo(7, 14)
    body.cubicTo(4, 12, 3, 14, 5.5, 17)
    body.cubicTo(7.5, 20, 9, 21, 12.5, 21)
    body.cubicTo(17, 21, 19, 18, 19, 14)
    body.lineTo(19, 10)
    p.drawPath(body)


def i_zoom(p, c):
    _stroke(p, c, 2)
    p.drawEllipse(QPointF(10.5, 10.5), 6, 6)
    p.drawLine(QPointF(15, 15), QPointF(20.5, 20.5))


def i_new_layer(p, c):
    _stroke(p, c, 1.7)
    p.drawPolygon(_poly((12, 4), (21, 9), (12, 14), (3, 9)))
    p.drawLine(QPointF(12, 17), QPointF(12, 22))
    p.drawLine(QPointF(9.5, 19.5), QPointF(14.5, 19.5))


def i_dup_layer(p, c):
    _stroke(p, c, 1.7)
    p.drawRect(QRectF(4.5, 8.5, 11, 11))
    p.drawPolyline(_poly((8.5, 8.5), (8.5, 4.5), (19.5, 4.5), (19.5, 15.5), (15.5, 15.5)))


def i_delete(p, c):
    _stroke(p, c, 1.7)
    p.drawLine(QPointF(5, 7), QPointF(19, 7))
    p.drawPolyline(_poly((9, 7), (9, 4.5), (15, 4.5), (15, 7)))
    p.drawPolyline(_poly((6.5, 7), (7.5, 20), (16.5, 20), (17.5, 7)))


def i_merge(p, c):
    _stroke(p, c, 1.8)
    p.drawLine(QPointF(12, 3), QPointF(12, 14))
    p.drawPolyline(_poly((7.5, 10), (12, 14.5), (16.5, 10)))
    p.drawLine(QPointF(5, 19), QPointF(19, 19))


def i_up(p, c):
    _stroke(p, c, 2)
    p.drawPolyline(_poly((6, 15), (12, 8), (18, 15)))


def i_down(p, c):
    _stroke(p, c, 2)
    p.drawPolyline(_poly((6, 9), (12, 16), (18, 9)))


def i_swap(p, c):
    _stroke(p, c, 1.7)
    p.drawPolyline(_poly((5, 9), (19, 9), (16, 6)))
    p.drawPolyline(_poly((19, 15), (5, 15), (8, 18)))


ICONS = {
    "brush": i_brush, "smartpen": i_smartpen, "pencil": i_pencil, "eraser": i_eraser, "airbrush": i_airbrush, "line": i_line,
    "arrow": i_arrow, "rect": i_rect, "roundrect": i_roundrect, "ellipse": i_ellipse, "triangle": i_triangle,
    "diamond": i_diamond, "star": i_star, "heart": i_heart, "polygon": i_polygon, "fill": i_fill,
    "gradient": i_gradient, "picker": i_picker, "text": i_text, "select_rect": i_select_rect,
    "select_ellipse": i_select_ellipse, "lasso": i_lasso, "wand": i_wand, "move": i_move, "hand": i_hand,
    "zoom": i_zoom, "new_layer": i_new_layer, "dup_layer": i_dup_layer, "delete": i_delete, "merge": i_merge,
    "up": i_up, "down": i_down, "swap": i_swap,
}


def make_icon(name, color, size=24):
    icon = QIcon()
    for scale in (1, 2):
        px = QPixmap(size * scale, size * scale)
        px.setDevicePixelRatio(scale)
        px.fill(Qt.transparent)
        p = QPainter(px)
        p.setRenderHint(QPainter.Antialiasing)
        p.scale(size / 24.0, size / 24.0)
        ICONS[name](p, QColor(color))
        p.end()
        icon.addPixmap(px)
    return icon


# ------------------------------------------------------------------ colour picker

class GradientSlider(QWidget):
    valueChanged = pyqtSignal(float)

    def __init__(self, kind, parent=None):
        super().__init__(parent)
        self.kind = kind                    # "hue" | "alpha"
        self.value = 0.0
        self.base = QColor(0, 0, 0)
        self.setFixedHeight(16)
        self.setMinimumWidth(80)

    def set_value(self, v):
        self.value = max(0.0, min(1.0, v))
        self.update()

    def _pick(self, e):
        w = max(1, self.width() - 10)
        self.value = max(0.0, min(1.0, (e.x() - 5) / w))
        self.update()
        self.valueChanged.emit(self.value)

    def mousePressEvent(self, e):
        self._pick(e)

    def mouseMoveEvent(self, e):
        if e.buttons() & Qt.LeftButton:
            self._pick(e)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(5, 3, self.width() - 10, self.height() - 6)
        if self.kind == "hue":
            g = QLinearGradient(r.left(), 0, r.right(), 0)
            for i in range(7):
                g.setColorAt(i / 6.0, QColor.fromHsvF(i / 6.0 if i < 6 else 0.999, 1, 1))
            p.setBrush(QBrush(g))
        else:
            p.setBrush(QColor(200, 200, 200))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(r, 3, 3)
            p.setBrush(QColor(140, 140, 140))
            sz = r.height() / 2
            x = r.left()
            col = 0
            while x < r.right():
                for row in range(2):
                    if (col + row) % 2:
                        p.drawRect(QRectF(x, r.top() + row * sz, min(sz, r.right() - x), sz))
                x += sz
                col += 1
            g = QLinearGradient(r.left(), 0, r.right(), 0)
            c0 = QColor(self.base)
            c0.setAlpha(0)
            g.setColorAt(0, c0)
            g.setColorAt(1, QColor(self.base.red(), self.base.green(), self.base.blue()))
            p.setBrush(QBrush(g))
        p.setPen(QPen(QColor(0, 0, 0, 90), 1))
        p.drawRoundedRect(r, 3, 3)
        x = 5 + self.value * (self.width() - 10)
        p.setPen(QPen(Qt.white, 2))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(QRectF(x - 3, 1.5, 6, self.height() - 3), 2, 2)
        p.setPen(QPen(Qt.black, 1))
        p.drawRoundedRect(QRectF(x - 4, 0.5, 8, self.height() - 1), 2.5, 2.5)


class SVSquare(QWidget):
    changed = pyqtSignal(float, float)      # saturation, value

    def __init__(self, parent=None):
        super().__init__(parent)
        self.h, self.s, self.v = 0.0, 0.0, 0.0
        self._cache = None
        self.setMinimumSize(120, 100)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_hsv(self, h, s, v):
        if h != self.h:
            self._cache = None
        self.h, self.s, self.v = h, s, v
        self.update()

    def resizeEvent(self, e):
        self._cache = None

    def _pick(self, e):
        self.s = max(0.0, min(1.0, e.x() / max(1, self.width() - 1)))
        self.v = max(0.0, min(1.0, 1 - e.y() / max(1, self.height() - 1)))
        self.update()
        self.changed.emit(self.s, self.v)

    def mousePressEvent(self, e):
        self._pick(e)

    def mouseMoveEvent(self, e):
        if e.buttons() & Qt.LeftButton:
            self._pick(e)

    def paintEvent(self, _):
        if self._cache is None or self._cache.size() != self.size():
            img = QImage(self.size(), QImage.Format_RGB32)
            q = QPainter(img)
            q.fillRect(img.rect(), QColor.fromHsvF(self.h, 1, 1))
            gw = QLinearGradient(0, 0, img.width(), 0)
            gw.setColorAt(0, Qt.white)
            gw.setColorAt(1, QColor(255, 255, 255, 0))
            q.fillRect(img.rect(), QBrush(gw))
            gb = QLinearGradient(0, 0, 0, img.height())
            gb.setColorAt(0, QColor(0, 0, 0, 0))
            gb.setColorAt(1, Qt.black)
            q.fillRect(img.rect(), QBrush(gb))
            q.end()
            self._cache = img
        p = QPainter(self)
        p.drawImage(0, 0, self._cache)
        x, y = self.s * (self.width() - 1), (1 - self.v) * (self.height() - 1)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(Qt.black, 2))
        p.drawEllipse(QPointF(x, y), 6, 6)
        p.setPen(QPen(Qt.white, 1.2))
        p.drawEllipse(QPointF(x, y), 6, 6)


class ColorPicker(QWidget):
    colorChanged = pyqtSignal(QColor)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.h, self.s, self.v, self.a = 0.0, 0.0, 0.0, 1.0
        self.square = SVSquare()
        self.hue = GradientSlider("hue")
        self.alpha = GradientSlider("alpha")
        self.hex = QLineEdit()
        self.hex.setMaxLength(9)
        self.hex.setFixedWidth(88)
        self.hex.setPlaceholderText("#rrggbb")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        lay.addWidget(self.square, 1)
        lay.addWidget(self.hue)
        lay.addWidget(self.alpha)
        row = QHBoxLayout()
        row.addWidget(QLabel("Hex"))
        row.addWidget(self.hex)
        row.addStretch(1)
        lay.addLayout(row)
        self.square.changed.connect(self._sv)
        self.hue.valueChanged.connect(self._hue)
        self.alpha.valueChanged.connect(self._alpha)
        self.hex.editingFinished.connect(self._hex)

    def color(self):
        c = QColor.fromHsvF(self.h, self.s, self.v)
        c.setAlphaF(self.a)
        return c

    def set_color(self, color):
        h, s, v, a = color.getHsvF()
        if h < 0:
            h = self.h
        elif s == 0:
            h = self.h
        self.h, self.s, self.v, self.a = h, s, v, a
        self._sync()

    def _sync(self):
        self.square.set_hsv(self.h, self.s, self.v)
        self.hue.set_value(self.h)
        self.alpha.base = QColor.fromHsvF(self.h, self.s, self.v)
        self.alpha.set_value(self.a)
        if not self.hex.hasFocus():
            c = self.color()
            self.hex.setText(c.name() if c.alpha() == 255 else c.name(QColor.HexArgb))

    def _emit(self):
        self._sync()
        self.colorChanged.emit(self.color())

    def _sv(self, s, v):
        self.s, self.v = s, v
        self._emit()

    def _hue(self, h):
        self.h = min(h, 0.999)
        self._emit()

    def _alpha(self, a):
        self.a = a
        self._emit()

    def _hex(self):
        c = QColor(self.hex.text().strip())
        if c.isValid():
            self.set_color(c)
            self.colorChanged.emit(self.color())
        else:
            self._sync()


PALETTE = [
    "#000000", "#3c3c3c", "#7f7f7f", "#b4b4b4", "#dcdcdc", "#ffffff", "#5a3825", "#8b5a2b",
    "#c0392b", "#e74c3c", "#e67e22", "#f39c12", "#f1c40f", "#f7e08b", "#d4e157", "#8bc34a",
    "#27ae60", "#16a085", "#1abc9c", "#4dd0e1", "#3498db", "#2962ff", "#1a237e", "#5e35b1",
    "#8e44ad", "#ab47bc", "#e91e63", "#ff80ab", "#ffccbc", "#d7ccc8", "#90a4ae", "#455a64",
]


class SwatchButton(QToolButton):
    picked = pyqtSignal(QColor, bool)       # colour, secondary?

    def __init__(self, color, parent=None):
        super().__init__(parent)
        self.color = QColor(color)
        self.setFixedSize(18, 18)
        self.setToolTip(self.color.name())
        self.setCursor(Qt.PointingHandCursor)

    def mousePressEvent(self, e):
        if e.button() in (Qt.LeftButton, Qt.RightButton):
            self.picked.emit(self.color, e.button() == Qt.RightButton)

    def paintEvent(self, _):
        p = QPainter(self)
        r = self.rect().adjusted(1, 1, -1, -1)
        p.fillRect(r, self.color)
        p.setPen(QPen(QColor(0, 0, 0, 110)))
        p.drawRect(r)


class PrimarySecondary(QWidget):
    """Overlapping primary/secondary swatches; click selects which one the picker edits."""
    targetChanged = pyqtSignal(bool)        # True = secondary

    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self.secondary_active = False
        self.setFixedSize(54, 48)
        self.setToolTip("Primary (front) and secondary (back) colour. Click to edit.")

    def paintEvent(self, _):
        p = QPainter(self)
        for rect, color, active in ((QRectF(18, 16, 30, 28), self.state.secondary, self.secondary_active),
                                    (QRectF(3, 3, 30, 28), self.state.primary, not self.secondary_active)):
            p.fillRect(rect, QColor(255, 255, 255))
            p.fillRect(rect, QBrush(Qt.Dense6Pattern if color.alpha() < 255 else Qt.NoBrush))
            p.fillRect(rect, color)
            p.setPen(QPen(self.palette().highlight().color() if active else QColor(0, 0, 0, 140), 2 if active else 1))
            p.drawRect(rect)

    def mousePressEvent(self, e):
        if QRectF(3, 3, 30, 28).contains(QPointF(e.pos())):
            self.secondary_active = False
        elif QRectF(18, 16, 30, 28).contains(QPointF(e.pos())):
            self.secondary_active = True
        else:
            return
        self.update()
        self.targetChanged.emit(self.secondary_active)


class ColorPanel(QWidget):
    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self._recent_shown = None
        self.picker = ColorPicker()
        self.indicator = PrimarySecondary(state)
        self.swap = QToolButton()
        self.swap.setToolTip("Swap colours (X)")
        self.swap.setAutoRaise(True)
        self.reset = QToolButton()
        self.reset.setText("◐")
        self.reset.setToolTip("Default colours (D)")
        self.reset.setAutoRaise(True)
        top = QHBoxLayout()
        top.addWidget(self.indicator)
        col = QVBoxLayout()
        col.addWidget(self.swap)
        col.addWidget(self.reset)
        top.addLayout(col)
        top.addStretch(1)
        self.palette_grid = QGridLayout()
        self.palette_grid.setSpacing(2)
        self.recent_row = QHBoxLayout()
        self.recent_row.setSpacing(2)
        for i, name in enumerate(PALETTE):
            b = SwatchButton(name)
            b.picked.connect(self._apply)
            self.palette_grid.addWidget(b, i // 8, i % 8)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.addLayout(top)
        lay.addWidget(self.picker, 1)
        lay.addLayout(self.palette_grid)
        lay.addWidget(QLabel("Recent"))
        lay.addLayout(self.recent_row)
        self.swap.clicked.connect(state.swap_colors)
        self.reset.clicked.connect(state.reset_colors)
        self.indicator.targetChanged.connect(lambda _s: self.sync())
        self.picker.colorChanged.connect(self._from_picker)
        state.colorsChanged.connect(self.sync)
        self.sync()

    def _target_secondary(self):
        return self.indicator.secondary_active

    def _apply(self, color, secondary):
        if secondary:
            self.state.secondary = color
        else:
            self.state.primary = color

    def _from_picker(self, color):
        if self._target_secondary():
            self.state.secondary = color
        else:
            self.state.primary = color

    def sync(self):
        color = self.state.secondary if self._target_secondary() else self.state.primary
        if color.rgba() != self.picker.color().rgba():
            self.picker.blockSignals(True)
            self.picker.set_color(color)
            self.picker.blockSignals(False)
        self.indicator.update()
        recent = [c.rgba() for c in self.state.recent[:8]]
        if recent == self._recent_shown:
            return
        self._recent_shown = recent
        while self.recent_row.count():
            item = self.recent_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for c in self.state.recent[:8]:
            b = SwatchButton(c)
            b.picked.connect(self._apply)
            self.recent_row.addWidget(b)
        self.recent_row.addStretch(1)


# ------------------------------------------------------------------ layers

class LayerPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.doc = None
        self._thumbs = {}
        self.list = QListWidget()
        self.list.setIconSize(QSize(44, 32))
        self.list.setSpacing(1)
        self.opacity = QSlider(Qt.Horizontal)
        self.opacity.setRange(0, 100)
        self.opacity_label = QLabel("100%")
        self.opacity_label.setMinimumWidth(36)
        self.blend = QComboBox()
        self.blend.addItems(list(BLEND_MODES))
        self.buttons = {}
        bar = QHBoxLayout()
        bar.setSpacing(2)
        for key, tip in (("new_layer", "New layer"), ("dup_layer", "Duplicate layer"), ("delete", "Delete layer"),
                         ("merge", "Merge down"), ("up", "Move up"), ("down", "Move down")):
            b = QToolButton()
            b.setToolTip(tip)
            b.setAutoRaise(True)
            self.buttons[key] = b
            bar.addWidget(b)
        bar.addStretch(1)
        row = QHBoxLayout()
        row.addWidget(QLabel("Opacity"))
        row.addWidget(self.opacity, 1)
        row.addWidget(self.opacity_label)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.addWidget(self.blend)
        lay.addLayout(row)
        lay.addWidget(self.list, 1)
        lay.addLayout(bar)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(40)
        self._timer.timeout.connect(self.rebuild)
        self.list.currentRowChanged.connect(self._row_changed)
        self.list.itemChanged.connect(self._item_changed)
        self.opacity.valueChanged.connect(self._opacity_changed)
        self.blend.activated.connect(self._blend_changed)
        self.list.setContextMenuPolicy(Qt.ActionsContextMenu)
        b = self.buttons
        b["new_layer"].clicked.connect(lambda: self.doc.add_layer())
        b["dup_layer"].clicked.connect(lambda: self.doc.duplicate_layer())
        b["delete"].clicked.connect(lambda: self.doc.delete_layer())
        b["merge"].clicked.connect(lambda: self.doc.merge_down())
        b["up"].clicked.connect(lambda: self.doc.move_layer(self.doc.active, 1))
        b["down"].clicked.connect(lambda: self.doc.move_layer(self.doc.active, -1))

    def set_document(self, doc):
        if self.doc is not None:
            self.doc.layersChanged.disconnect(self.schedule)
            self.doc.contentCommitted.disconnect(self.schedule)
        self.doc = doc
        doc.layersChanged.connect(self.schedule)
        doc.contentCommitted.connect(self.schedule)
        self.rebuild()

    def set_icons(self, make):
        for key, b in self.buttons.items():
            b.setIcon(make(key))

    def schedule(self):
        if not sip.isdeleted(self) and not sip.isdeleted(self._timer):
            self._timer.start()

    def _thumb(self, layer):
        key = layer.image.cacheKey()
        cached = self._thumbs.get(id(layer))
        if cached is not None and cached[0] == key:
            return cached[1]
        icon = self._make_thumb(layer)
        self._thumbs[id(layer)] = (key, icon)
        return icon

    def _make_thumb(self, layer):
        w, h = 44, 32
        px = QPixmap(w, h)
        px.fill(QColor(255, 255, 255))
        p = QPainter(px)
        p.fillRect(0, 0, w, h, QColor(204, 204, 204))
        for y in range(0, h, 8):
            for x in range(0, w, 8):
                if (x // 8 + y // 8) % 2:
                    p.fillRect(x, y, 8, 8, QColor(255, 255, 255))
        img = layer.image
        if img.width() > w * 8:                       # cheap pre-shrink keeps huge layers responsive
            img = img.scaled(w * 4, h * 4, Qt.KeepAspectRatio, Qt.FastTransformation)
        img = img.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        p.drawImage((w - img.width()) // 2, (h - img.height()) // 2, img)
        p.end()
        return QIcon(px)

    def rebuild(self):
        """Refresh the list. Runs from a coalescing timer, so it can fire while the window is being torn down."""
        try:
            self._rebuild()
        except RuntimeError:
            if not (sip.isdeleted(self) or sip.isdeleted(self.list)):
                raise                               # a real bug, not a dying widget

    def _rebuild(self):
        doc = self.doc
        if doc is None or sip.isdeleted(self) or sip.isdeleted(self.list):      # the window may already be closing
            return
        self.list.blockSignals(True)
        self.list.clear()
        live = {id(l) for l in doc.layers}
        self._thumbs = {k: v for k, v in self._thumbs.items() if k in live}
        for i in reversed(range(len(doc.layers))):
            layer = doc.layers[i]
            item = QListWidgetItem(self._thumb(layer), layer.name + ("  🔒" if layer.locked else ""))
            item.setData(Qt.UserRole, i)
            item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsUserCheckable | Qt.ItemIsEditable)
            item.setCheckState(Qt.Checked if layer.visible else Qt.Unchecked)
            self.list.addItem(item)
            if i == doc.active:
                self.list.setCurrentItem(item)
        self.list.blockSignals(False)
        layer = doc.active_layer
        self.opacity.blockSignals(True)
        self.opacity.setValue(round(layer.opacity * 100))
        self.opacity.blockSignals(False)
        self.opacity_label.setText("%d%%" % round(layer.opacity * 100))
        self.blend.setCurrentText(layer.blend)

    def _index(self, item):
        return item.data(Qt.UserRole)

    def _row_changed(self, row):
        item = self.list.item(row)
        if item is not None and self.doc is not None:
            self.doc.set_active(self._index(item))

    def _item_changed(self, item):
        doc, i = self.doc, self._index(item)
        layer = doc.layers[i]
        visible = item.checkState() == Qt.Checked
        if visible != layer.visible:
            doc.set_layer_prop(layer, "visible", visible, "Toggle visibility")
            return
        name = item.text().replace("  🔒", "").strip()
        if name and name != layer.name:
            doc.set_layer_prop(layer, "name", name, "Rename layer")

    def _opacity_changed(self, value):
        self.opacity_label.setText("%d%%" % value)
        if self.doc is not None:
            self.doc.set_layer_prop(self.doc.active_layer, "opacity", value / 100.0, "Layer opacity")

    def _blend_changed(self, _i):
        self.doc.set_layer_prop(self.doc.active_layer, "blend", self.blend.currentText(), "Blend mode")


# ------------------------------------------------------------------ option bar

OPTION_DEFS = {
    "size": ("slider", "Size", 1, 300),
    "opacity": ("slider", "Opacity", 1, 100),
    "hardness": ("slider", "Hardness", 0, 100),
    "smoothing": ("slider", "Smoothing", 0, 100),
    "tolerance": ("slider", "Tolerance", 0, 255),
    "radius": ("slider", "Corner", 0, 200),
    "fill_mode": ("combo", "Style", ["Outline", "Fill", "Outline + Fill"]),
    "dash": ("combo", "Line", ["Solid", "Dash", "Dot", "Dash-Dot"]),
    "symmetry": ("combo", "Mirror", ["Off", "Horizontal", "Vertical", "Both", "Radial ×6"]),
    "gradient": ("combo", "Gradient", ["Linear", "Radial"]),
    "gradient_end": ("combo", "To", ["Secondary", "Transparent"]),
    "sample": ("combo", "Sample", ["Layer", "Merged"]),
    "contiguous": ("check", "Contiguous"),
    "antialias": ("check", "Anti-alias"),
    "bold": ("check", "Bold"),
    "italic": ("check", "Italic"),
    "font": ("font", "Font"),
    "font_size": ("spin", "Size", 6, 600),
    "star_points": ("spin", "Points", 3, 16),
}


class OptionBar(QToolBar):
    def __init__(self, state, parent=None):
        super().__init__("Tool options", parent)
        self.state = state
        self.setMovable(False)
        self.actions_by_key = {}
        self.syncers = {}
        for key, spec in OPTION_DEFS.items():
            widget = self._make(key, spec)
            self.actions_by_key[key] = self.addWidget(widget)
        state.changed.connect(self._external_change)
        self.hint = QLabel()
        self.hint.setStyleSheet("color: gray; padding-left: 12px")
        self.addWidget(self.hint)

    def _make(self, key, spec):
        kind, label = spec[0], spec[1]
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(6, 0, 6, 0)
        lay.setSpacing(4)
        s = self.state
        if kind == "slider":
            lay.addWidget(QLabel(label))
            sl = QSlider(Qt.Horizontal)
            sl.setRange(spec[2], spec[3])
            sl.setFixedWidth(90)
            val = QLabel()
            val.setMinimumWidth(28)
            val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            lay.addWidget(sl)
            lay.addWidget(val)

            def sync(v=None, sl=sl, val=val, key=key):
                v = getattr(s, key)
                sl.blockSignals(True)
                sl.setValue(v)
                sl.blockSignals(False)
                val.setText(str(v))
            sl.valueChanged.connect(lambda v, key=key: s.set(key, v))
        elif kind == "combo":
            lay.addWidget(QLabel(label))
            cb = QComboBox()
            cb.addItems(spec[2])
            lay.addWidget(cb)

            def sync(cb=cb, key=key):
                cb.blockSignals(True)
                cb.setCurrentText(getattr(s, key) if getattr(s, key) in spec[2] else spec[2][0])
                cb.blockSignals(False)
            cb.currentTextChanged.connect(lambda t, key=key: s.set(key, t))
        elif kind == "check":
            cb = QCheckBox(label)
            lay.addWidget(cb)

            def sync(cb=cb, key=key):
                cb.blockSignals(True)
                cb.setChecked(getattr(s, key))
                cb.blockSignals(False)
            cb.toggled.connect(lambda v, key=key: s.set(key, v))
        elif kind == "font":
            fc = QFontComboBox()
            fc.setMaximumWidth(170)
            lay.addWidget(fc)

            def sync(fc=fc, key=key):
                fc.blockSignals(True)
                fc.setCurrentFont(QFont(getattr(s, key)))
                fc.blockSignals(False)
            fc.currentFontChanged.connect(lambda f, key=key: s.set(key, f.family()))
        else:  # spin
            lay.addWidget(QLabel(label))
            sp = QSpinBox()
            sp.setRange(spec[2], spec[3])
            lay.addWidget(sp)

            def sync(sp=sp, key=key):
                sp.blockSignals(True)
                sp.setValue(getattr(s, key))
                sp.blockSignals(False)
            sp.valueChanged.connect(lambda v, key=key: s.set(key, v))
        self.syncers[key] = sync
        sync()
        return w

    def _external_change(self, key):
        if key in self.syncers:
            self.syncers[key]()

    def show_for(self, keys, hint=""):
        for key, action in self.actions_by_key.items():
            action.setVisible(key in keys)
        self.hint.setText(hint)
