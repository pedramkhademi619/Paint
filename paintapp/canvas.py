"""The editing surface: view transform, rendering, input dispatch."""
import math

from PyQt5.QtCore import QPointF, QRect, QRectF, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QBrush, QColor, QPainter, QPen, QPixmap
from PyQt5.QtWidgets import QWidget

from .tools import TOOL_CLASSES

MIN_ZOOM, MAX_ZOOM = 0.05, 64.0


def _checker(dark):
    a, b = (QColor(70, 70, 74), QColor(88, 88, 92)) if dark else (QColor(255, 255, 255), QColor(214, 214, 214))
    pm = QPixmap(16, 16)
    pm.fill(a)
    p = QPainter(pm)
    p.fillRect(0, 0, 8, 8, b)
    p.fillRect(8, 8, 8, 8, b)
    p.end()
    return pm


class Canvas(QWidget):
    mouseMoved = pyqtSignal(object)       # QPointF in image space, or None
    zoomChanged = pyqtSignal(float)
    message = pyqtSignal(str)
    toolHint = pyqtSignal(str)

    def __init__(self, doc, state, parent=None):
        super().__init__(parent)
        self.state = state
        self.zoom = 1.0
        self.offset = QPointF(0, 0)
        self.auto_fit = True
        self.show_grid = False
        self.grid_size = 16
        self.dark = True
        self.sel_preview = None
        self.hover = None
        self._space = False
        self._pan = None
        self._grab = None
        self._ants = 0
        self._doc = None
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMinimumSize(240, 200)
        self.tools = {cls.key: cls(self) for cls in TOOL_CLASSES}
        self.tool = self.tools[state.tool]
        self._checker = _checker(self.dark)
        self.ants_timer = QTimer(self)
        self.ants_timer.setInterval(120)
        self.ants_timer.timeout.connect(self._tick)
        self.ants_timer.start()
        state.changed.connect(lambda _k: self._refresh_cursor())
        self.set_document(doc)

    # ------------------------------------------------------------ document
    @property
    def doc(self):
        return self._doc

    def set_document(self, doc):
        if self._doc is not None:
            self._doc.repaintNeeded.disconnect(self._on_repaint)
            self._doc.selectionChanged.disconnect(self.update)
            self._doc.sizeChanged.disconnect(self._on_size)
        self._doc = doc
        doc.repaintNeeded.connect(self._on_repaint)
        doc.selectionChanged.connect(self.update)
        doc.sizeChanged.connect(self._on_size)
        self.auto_fit = True
        self.fit()
        self.update()

    def _on_size(self):
        if self.auto_fit:
            self.fit()
        self.update()

    def _on_repaint(self, rect):
        tl = self.to_screen(QPointF(rect.left(), rect.top()))
        br = self.to_screen(QPointF(rect.right() + 1, rect.bottom() + 1))
        self.update(QRectF(tl, br).toAlignedRect().adjusted(-2, -2, 2, 2))

    def _tick(self):
        if self.doc.selection is not None or self.sel_preview is not None:
            self._ants = (self._ants + 1) % 16
            self.update()

    # ------------------------------------------------------------ tools
    def set_tool(self, key):
        if key == self.tool.key:
            return
        self.tool.deactivate()
        self.tool = self.tools[key]
        self.state.tool = key
        self.tool.activate()
        self.sel_preview = None
        self._refresh_cursor()
        self.toolHint.emit(self.tool.hint)
        self.state.toolChanged.emit(key)
        self.update()

    def _refresh_cursor(self):
        if self._pan is not None:
            self.setCursor(Qt.ClosedHandCursor)
        elif self._space or self.tool.key == "hand":
            self.setCursor(Qt.OpenHandCursor)
        elif self.tool.brush_cursor and self.state.size * self.zoom >= 6:
            self.setCursor(Qt.BlankCursor)
        else:
            self.setCursor(self.tool.cursor)
        self.update()

    def can_paint(self):
        layer = self.doc.active_layer
        if not layer.visible:
            self.message.emit("The active layer is hidden.")
            return False
        if layer.locked:
            self.message.emit("The active layer is locked.")
            return False
        return True

    def symmetry_transforms(self):
        w, h = self.doc.size.width(), self.doc.size.height()
        cx, cy = w / 2.0, h / 2.0
        ident = lambda p: QPointF(p)
        mode = self.state.symmetry
        if mode == "Horizontal":
            return [ident, lambda p: QPointF(w - p.x(), p.y())]
        if mode == "Vertical":
            return [ident, lambda p: QPointF(p.x(), h - p.y())]
        if mode == "Both":
            return [ident, lambda p: QPointF(w - p.x(), p.y()), lambda p: QPointF(p.x(), h - p.y()),
                    lambda p: QPointF(w - p.x(), h - p.y())]
        if mode.startswith("Radial"):
            n = 6

            def rot(k):
                a = 2 * math.pi * k / n
                ca, sa = math.cos(a), math.sin(a)
                return lambda p: QPointF(cx + (p.x() - cx) * ca - (p.y() - cy) * sa,
                                         cy + (p.x() - cx) * sa + (p.y() - cy) * ca)
            return [rot(k) for k in range(n)]
        return [ident]

    # ------------------------------------------------------------ stroke buffer API
    def begin_stroke(self, erase=False, opacity=1.0, buf=None):
        self.doc.cancel_overlay()
        return self.doc.begin_overlay(erase, opacity, buf)

    def stroke_painter(self, aa=None):
        p = QPainter(self.doc.overlay.buf)
        if aa is None:
            aa = self.state.antialias
        p.setRenderHint(QPainter.Antialiasing, aa)
        return p

    def touch(self, rect):
        ov = self.doc.overlay
        if ov is None:
            return
        rect = rect.intersected(self.doc.rect)
        if rect.isEmpty():
            return
        ov.dirty = ov.dirty.united(rect)
        self.doc.invalidate(rect)

    def clear_stroke(self):
        ov = self.doc.overlay
        if ov is None or ov.dirty.isEmpty():
            return
        p = QPainter(ov.buf)
        p.setCompositionMode(QPainter.CompositionMode_Source)
        p.fillRect(ov.dirty, Qt.transparent)
        p.end()
        self.doc.invalidate(ov.dirty)
        ov.dirty = QRect()

    def commit_stroke(self, text):
        self.doc.commit_overlay(text)

    def cancel_stroke(self):
        self.doc.cancel_overlay()

    def sample_color(self, p):
        x, y = int(math.floor(p.x())), int(math.floor(p.y()))
        if not self.doc.rect.contains(x, y):
            return None
        return self.doc.get_composite().pixelColor(x, y)

    # ------------------------------------------------------------ view transform
    def to_image(self, sp):
        return QPointF((sp.x() - self.offset.x()) / self.zoom, (sp.y() - self.offset.y()) / self.zoom)

    def to_screen(self, ip):
        return QPointF(ip.x() * self.zoom + self.offset.x(), ip.y() * self.zoom + self.offset.y())

    def fit(self):
        iw, ih = self.doc.size.width(), self.doc.size.height()
        z = min((self.width() - 40) / max(1, iw), (self.height() - 40) / max(1, ih))
        self.zoom = max(MIN_ZOOM, min(z, 16.0))
        self.offset = QPointF((self.width() - iw * self.zoom) / 2, (self.height() - ih * self.zoom) / 2)
        self.auto_fit = True
        self.zoomChanged.emit(self.zoom)
        self._refresh_cursor()

    def zoom_to(self, z, image_anchor=None):
        z = max(MIN_ZOOM, min(MAX_ZOOM, z))
        if image_anchor is None:
            anchor_screen = QPointF(self.width() / 2, self.height() / 2)
            image_anchor = self.to_image(anchor_screen)
        else:
            anchor_screen = self.to_screen(image_anchor)
        self.zoom = z
        self.offset = QPointF(anchor_screen.x() - image_anchor.x() * z, anchor_screen.y() - image_anchor.y() * z)
        self.auto_fit = False
        self._clamp_offset()
        self.zoomChanged.emit(self.zoom)
        self._refresh_cursor()

    def actual_size(self):
        self.zoom_to(1.0)

    def _clamp_offset(self):
        iw, ih = self.doc.size.width() * self.zoom, self.doc.size.height() * self.zoom
        keep = 60
        x = min(max(self.offset.x(), keep - iw), self.width() - keep)
        y = min(max(self.offset.y(), keep - ih), self.height() - keep)
        self.offset = QPointF(x, y)

    def set_dark(self, dark):
        self.dark = dark
        self._checker = _checker(dark)
        self.update()

    def resizeEvent(self, e):
        if self.auto_fit:
            self.fit()
        super().resizeEvent(e)

    # ------------------------------------------------------------ painting
    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(38, 38, 40) if self.dark else QColor(170, 170, 174))
        iw, ih = self.doc.size.width(), self.doc.size.height()
        z = self.zoom
        frame = QRectF(self.offset.x(), self.offset.y(), iw * z, ih * z)
        p.fillRect(frame.translated(3, 3), QColor(0, 0, 0, 70))
        p.save()
        p.setClipRect(frame.toAlignedRect().intersected(event.rect()))
        p.setBrushOrigin(frame.topLeft())
        p.fillRect(frame, QBrush(self._checker))
        p.restore()

        comp = self.doc.get_composite()
        vis = QRectF(self.to_image(QPointF(0, 0)), self.to_image(QPointF(self.width(), self.height())))
        src = vis.intersected(QRectF(0, 0, iw, ih))
        if not src.isEmpty():
            src = QRectF(math.floor(src.left()), math.floor(src.top()),
                         math.ceil(src.right()) - math.floor(src.left()), math.ceil(src.bottom()) - math.floor(src.top()))
            src = src.intersected(QRectF(0, 0, iw, ih))
            target = QRectF(self.to_screen(src.topLeft()), self.to_screen(src.bottomRight()))
            p.setRenderHint(QPainter.SmoothPixmapTransform, z < 2.0)
            p.drawImage(target, comp, src)
            self._draw_grid(p, src)

        # selection and previews (image space)
        p.save()
        p.translate(self.offset)
        p.scale(z, z)
        p.setRenderHint(QPainter.Antialiasing, False)
        if self.doc.selection is not None:
            self._ants_path(p, self.doc.selection)
        if self.sel_preview is not None:
            self._ants_path(p, self.sel_preview, tint=True)
        p.restore()

        self._draw_brush_ring(p)
        p.setPen(QPen(QColor(0, 0, 0, 120) if not self.dark else QColor(255, 255, 255, 40), 1))
        p.drawRect(frame.adjusted(-0.5, -0.5, 0.5, 0.5))
        p.end()

    def _ants_path(self, p, path, tint=False):
        pen = QPen(Qt.black, 1)
        pen.setCosmetic(True)
        p.setPen(pen)
        p.setBrush(QColor(80, 140, 255, 40) if tint else Qt.NoBrush)
        p.drawPath(path)
        pen = QPen(Qt.white, 1, Qt.CustomDashLine)
        pen.setCosmetic(True)
        pen.setDashPattern([4, 4])
        pen.setDashOffset(self._ants / 2.0)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)

    def _draw_grid(self, p, src):
        z = self.zoom
        step = None
        if self.show_grid:
            step = self.grid_size
        elif z >= 8:
            step = 1
        if step is None or step * z < 4:
            return
        p.setRenderHint(QPainter.Antialiasing, False)
        p.setPen(QPen(QColor(128, 128, 128, 90), 1))
        x0 = int(math.ceil(src.left() / step) * step)
        x = x0
        while x <= src.right():
            sx = self.to_screen(QPointF(x, 0)).x()
            p.drawLine(QPointF(sx, self.to_screen(src.topLeft()).y()), QPointF(sx, self.to_screen(src.bottomLeft()).y()))
            x += step
        y = int(math.ceil(src.top() / step) * step)
        while y <= src.bottom():
            sy = self.to_screen(QPointF(0, y)).y()
            p.drawLine(QPointF(self.to_screen(src.topLeft()).x(), sy), QPointF(self.to_screen(src.topRight()).x(), sy))
            y += step

    def _draw_brush_ring(self, p):
        if self.hover is None or not self.tool.brush_cursor or self._space or self._pan is not None:
            return
        r = self.state.size * self.zoom / 2.0
        if r < 3:
            return
        c = self.to_screen(self.hover)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(0, 0, 0, 200), 1.4))
        p.drawEllipse(c, r, r)
        p.setPen(QPen(QColor(255, 255, 255, 220), 0.8))
        p.drawEllipse(c, r + 1, r + 1)
        p.drawLine(QPointF(c.x() - 3, c.y()), QPointF(c.x() + 3, c.y()))
        p.drawLine(QPointF(c.x(), c.y() - 3), QPointF(c.x(), c.y() + 3))

    # ------------------------------------------------------------ input
    def mousePressEvent(self, e):
        self.setFocus()
        if e.button() == Qt.MiddleButton or (e.button() == Qt.LeftButton and (self._space or self.tool.key == "hand")):
            self._pan = (e.pos(), QPointF(self.offset))
            self._refresh_cursor()
            return
        if e.button() not in (Qt.LeftButton, Qt.RightButton):
            return
        tool = self.tool
        if tool.alt_eyedrop and e.modifiers() & Qt.AltModifier:
            tool = self.tools["picker"]
        self._grab = tool
        tool.press(self.to_image(e.pos()), e.button(), e.modifiers())

    def mouseMoveEvent(self, e):
        ip = self.to_image(e.pos())
        self.hover = ip
        self.mouseMoved.emit(ip)
        if self._pan is not None:
            start, off = self._pan
            self.offset = QPointF(off.x() + e.x() - start.x(), off.y() + e.y() - start.y())
            self.auto_fit = False
            self._clamp_offset()
            self.update()
        elif self._grab is not None:
            self._grab.move(ip, e.modifiers())
            if self.tool.brush_cursor:
                self.update()
        else:
            if self.tool.brush_cursor:
                self.update()

    def mouseReleaseEvent(self, e):
        if self._pan is not None and e.button() in (Qt.MiddleButton, Qt.LeftButton):
            self._pan = None
            self._refresh_cursor()
            return
        if self._grab is not None and e.button() in (Qt.LeftButton, Qt.RightButton):
            grab, self._grab = self._grab, None
            grab.release(self.to_image(e.pos()), e.modifiers())

    def mouseDoubleClickEvent(self, e):
        if e.button() in (Qt.LeftButton, Qt.RightButton):
            self.tool.double_click(self.to_image(e.pos()), e.button(), e.modifiers())

    def leaveEvent(self, e):
        self.hover = None
        self.mouseMoved.emit(None)
        self.update()

    def wheelEvent(self, e):
        steps = e.angleDelta().y() / 120.0
        if steps == 0:
            return
        anchor = self.to_image(QPointF(e.pos()))
        self.zoom_to(self.zoom * (1.2 ** steps), anchor)
        self.update()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Space and not e.isAutoRepeat():
            self._space = True
            self._refresh_cursor()
            return
        if self.tool.key_press(e):
            return
        super().keyPressEvent(e)

    def keyReleaseEvent(self, e):
        if e.key() == Qt.Key_Space and not e.isAutoRepeat():
            self._space = False
            self._refresh_cursor()
            return
        super().keyReleaseEvent(e)
