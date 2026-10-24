"""Drawing, selection and navigation tools.

Every tool talks to the Canvas through a small API (begin_stroke / touch /
commit_stroke / ...) and never touches layer pixels directly, except the Move
tool which edits the layer live and records one undo step on release.
"""
import math
import random

from PyQt5.QtCore import QPoint, QPointF, QRect, QRectF, QSize, Qt, QTimer
from PyQt5.QtGui import (QBrush, QColor, QFont, QFontDatabase, QFontInfo, QFontMetricsF, QLinearGradient, QPainter, QPainterPath,
                         QPen, QPolygonF, QRadialGradient, QTransform)
from PyQt5.QtWidgets import QInputDialog

from . import imageutil, shapefit
from .document import blank_image

DASH_STYLES = {"Solid": Qt.SolidLine, "Dash": Qt.DashLine, "Dot": Qt.DotLine, "Dash-Dot": Qt.DashDotLine}


def dist(a, b):
    return math.hypot(a.x() - b.x(), a.y() - b.y())


class Tool:
    key = ""
    label = ""
    shortcut = ""
    options = ()               # AppState keys shown in the option bar
    cursor = Qt.CrossCursor
    brush_cursor = False       # draw a size ring under the pointer
    alt_eyedrop = False        # Alt+click temporarily becomes the colour picker
    hint = ""

    def __init__(self, canvas):
        self.c = canvas

    def activate(self):
        pass

    def deactivate(self):
        pass

    def press(self, p, button, mods):
        pass

    def move(self, p, mods):
        pass

    def release(self, p, mods):
        pass

    def double_click(self, p, button, mods):
        pass

    def key_press(self, event):
        return False


# ------------------------------------------------------------------ freehand

class FreehandTool(Tool):
    erase = False
    pixel = False              # aliased 1:1 pixels
    options = ("size", "opacity", "hardness", "smoothing", "symmetry")
    brush_cursor = True
    alt_eyedrop = True
    undo_text = "Brush stroke"

    def __init__(self, canvas):
        super().__init__(canvas)
        self.active = False
        self._tips = {}

    # -- stroke life-cycle
    def press(self, p, button, mods):
        c = self.c
        if not c.can_paint():
            return
        s = c.state
        self.color = QColor(0, 0, 0) if self.erase else QColor(s.primary if button == Qt.LeftButton else s.secondary)
        c.begin_stroke(erase=self.erase, opacity=s.opacity / 100.0)
        self.xf = c.symmetry_transforms()
        self.carry = [0.0] * len(self.xf)
        self.last = self.smoothed = p
        self.active = True
        self.dab(p)

    def move(self, p, mods):
        if not self.active:
            return
        k = self.c.state.smoothing / 100.0 * 0.93
        self.smoothed = QPointF(self.smoothed.x() + (p.x() - self.smoothed.x()) * (1 - k),
                                self.smoothed.y() + (p.y() - self.smoothed.y()) * (1 - k))
        self.segment(self.last, self.smoothed)
        self.last = self.smoothed

    def release(self, p, mods):
        if not self.active:
            return
        self.active = False
        self.segment(self.last, p)
        self.finish()
        self.c.commit_stroke(self.undo_text)
        if not self.erase:
            self.c.state.remember_color(self.color)

    def finish(self):
        pass

    def deactivate(self):
        if self.active:
            self.active = False
            self.c.commit_stroke(self.undo_text)

    # -- geometry
    def segment(self, a, b):
        dirty = QRect()
        for i, f in enumerate(self.xf):
            dirty = dirty.united(self._line(f(a), f(b), i))
        self.c.touch(dirty)

    def dab(self, p):
        dirty = QRect()
        for i, f in enumerate(self.xf):
            dirty = dirty.united(self._line(f(p), f(p), i, dab=True))
        self.c.touch(dirty)

    def _pen_width(self):
        return max(1.0, float(self.c.state.size))

    def _line(self, a, b, i, dab=False):
        """Stamp the brush from a to b; returns the dirty QRect."""
        w = self._pen_width()
        painter = self.c.stroke_painter(aa=not self.pixel)
        pad = int(math.ceil(w)) + 3
        rect = QRectF(a, b).normalized().adjusted(-pad, -pad, pad, pad).toAlignedRect()
        if self.pixel:
            pen = QPen(self.color, w, Qt.SolidLine, Qt.SquareCap if w <= 1 else Qt.RoundCap, Qt.RoundJoin)
            pen.setCosmetic(False)
            painter.setPen(pen)
            painter.drawLine(a, b) if not dab else painter.drawPoint(a)
            painter.end()
            return rect
        tip = self._tip()
        n = tip.width()
        step = max(1.0, w * 0.1)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        if dab:
            painter.drawImage(QPointF(a.x() - n / 2, a.y() - n / 2), tip)
        else:
            d = dist(a, b)
            if d > 0:
                pos = step - self.carry[i]
                while pos <= d:
                    t = pos / d
                    painter.drawImage(QPointF(a.x() + (b.x() - a.x()) * t - n / 2,
                                              a.y() + (b.y() - a.y()) * t - n / 2), tip)
                    pos += step
                self.carry[i] = d - (pos - step)
        painter.end()
        return rect

    def _tip(self):
        s = self.c.state
        d = max(1.0, float(s.size))
        key = (round(d * 2), s.hardness, self.color.rgba())
        tip = self._tips.get(key)
        if tip is None:
            if len(self._tips) > 48:
                self._tips.clear()
            n = int(math.ceil(d)) + 2
            tip = blank_image(QSize(n, n))
            p = QPainter(tip)
            p.setRenderHint(QPainter.Antialiasing)
            p.setPen(Qt.NoPen)
            ctr, r = n / 2.0, d / 2.0
            if s.hardness >= 99:
                p.setBrush(self.color)
            else:
                g = QRadialGradient(ctr, ctr, r)
                transparent = QColor(self.color)
                transparent.setAlpha(0)
                mid = QColor(self.color)
                mid.setAlpha(int(self.color.alpha() * 0.5))
                inner = max(s.hardness / 100.0, 0.001)
                g.setColorAt(0, self.color)
                g.setColorAt(inner, self.color)
                g.setColorAt(inner + (1 - inner) * 0.5, mid)
                g.setColorAt(1, transparent)
                p.setBrush(QBrush(g))
            p.drawEllipse(QPointF(ctr, ctr), r, r)
            p.end()
            self._tips[key] = tip
        return tip


class BrushTool(FreehandTool):
    key, label, shortcut = "brush", "Brush", "B"
    hint = "Drag to paint. Right button uses the secondary colour. Alt+click picks a colour."


class PencilTool(FreehandTool):
    key, label, shortcut = "pencil", "Pencil", "N"
    pixel = True
    options = ("size", "opacity", "smoothing", "symmetry")
    undo_text = "Pencil stroke"
    hint = "Hard, aliased pixels."


class EraserTool(FreehandTool):
    key, label, shortcut = "eraser", "Eraser", "E"
    erase = True
    alt_eyedrop = False
    undo_text = "Erase"
    hint = "Erases to transparency on the active layer."


class AirbrushTool(FreehandTool):
    key, label, shortcut = "airbrush", "Airbrush", "A"
    options = ("size", "opacity", "symmetry")
    undo_text = "Airbrush"
    hint = "Hold the button to build up soft spray."

    def __init__(self, canvas):
        super().__init__(canvas)
        self.timer = QTimer(canvas)
        self.timer.setInterval(25)
        self.timer.timeout.connect(self.spray)
        self.cur = QPointF()

    def press(self, p, button, mods):
        super().press(p, button, mods)
        if self.active:
            self.cur = p
            self.timer.start()

    def move(self, p, mods):
        self.cur = p

    def finish(self):
        self.timer.stop()

    def deactivate(self):
        self.timer.stop()
        super().deactivate()

    def dab(self, p):
        pass

    def segment(self, a, b):
        pass

    def spray(self):
        if not self.active:
            return
        r = max(1.0, self.c.state.size / 2.0)
        n = int(r * r * 0.12) + 4
        dirty = QRect()
        for f in self.xf:
            center = f(self.cur)
            painter = self.c.stroke_painter(aa=True)
            col = QColor(self.color)
            col.setAlpha(70)
            painter.setPen(QPen(col, 1.2))
            for _ in range(n):
                ang = random.random() * 2 * math.pi
                rad = r * math.sqrt(random.random())
                painter.drawPoint(QPointF(center.x() + rad * math.cos(ang), center.y() + rad * math.sin(ang)))
            painter.end()
            dirty = dirty.united(QRectF(center.x() - r - 2, center.y() - r - 2, 2 * r + 4, 2 * r + 4).toAlignedRect())
        self.c.touch(dirty)


# ------------------------------------------------------------------ shapes

class ShapeTool(Tool):
    kind = "rect"
    options = ("size", "opacity", "fill_mode", "dash", "antialias")
    hint = "Drag to draw. Shift = constrain, Alt = from centre. Right button swaps colours."

    def __init__(self, canvas):
        super().__init__(canvas)
        self.drag = False

    def press(self, p, button, mods):
        if not self.c.can_paint():
            return
        self.drag = True
        self.start = self.cur = p
        self.button = button
        self.c.begin_stroke(opacity=self.c.state.opacity / 100.0)
        self.render(mods)

    def move(self, p, mods):
        if self.drag:
            self.cur = p
            self.render(mods)

    def release(self, p, mods):
        if not self.drag:
            return
        self.drag = False
        self.cur = p
        self.render(mods)
        self.c.commit_stroke(self.label)
        self.c.state.remember_color(self.colors()[0])

    def deactivate(self):
        if self.drag:
            self.drag = False
            self.c.cancel_stroke()

    def colors(self):
        s = self.c.state
        a, b = (s.primary, s.secondary) if self.button == Qt.LeftButton else (s.secondary, s.primary)
        return a, b

    def box(self, mods):
        a, b = self.start, self.cur
        dx, dy = b.x() - a.x(), b.y() - a.y()
        if mods & Qt.ShiftModifier:
            m = max(abs(dx), abs(dy))
            dx, dy = math.copysign(m, dx or 1), math.copysign(m, dy or 1)
        if mods & Qt.AltModifier:
            return QRectF(a.x() - dx, a.y() - dy, 2 * dx, 2 * dy).normalized()
        return QRectF(a.x(), a.y(), dx, dy).normalized()

    def build_path(self, r):
        path = QPainterPath()
        s = self.c.state
        if self.kind == "rect":
            path.addRect(r)
        elif self.kind == "roundrect":
            rad = min(s.radius, r.width() / 2, r.height() / 2)
            path.addRoundedRect(r, rad, rad)
        elif self.kind == "ellipse":
            path.addEllipse(r)
        elif self.kind == "triangle":
            path.addPolygon(QPolygonF([QPointF(r.center().x(), r.top()), r.bottomRight(), r.bottomLeft()]))
            path.closeSubpath()
        elif self.kind == "diamond":
            path.addPolygon(QPolygonF([QPointF(r.center().x(), r.top()), QPointF(r.right(), r.center().y()),
                                       QPointF(r.center().x(), r.bottom()), QPointF(r.left(), r.center().y())]))
            path.closeSubpath()
        elif self.kind == "star":
            n = max(3, s.star_points)
            cx, cy, rx, ry = r.center().x(), r.center().y(), r.width() / 2, r.height() / 2
            pts = []
            for i in range(n * 2):
                ang = -math.pi / 2 + i * math.pi / n
                k = 1.0 if i % 2 == 0 else 0.42
                pts.append(QPointF(cx + rx * k * math.cos(ang), cy + ry * k * math.sin(ang)))
            path.addPolygon(QPolygonF(pts))
            path.closeSubpath()
        elif self.kind == "heart":
            h = QPainterPath()
            h.moveTo(.5, .92)
            h.cubicTo(.08, .62, -.02, .28, .25, .12)
            h.cubicTo(.40, .04, .50, .18, .50, .28)
            h.cubicTo(.50, .18, .60, .04, .75, .12)
            h.cubicTo(1.02, .28, .92, .62, .5, .92)
            h.closeSubpath()
            path = QTransform().translate(r.x(), r.y()).scale(r.width(), r.height()).map(h)
        return path

    def make_pen_brush(self):
        s = self.c.state
        main, other = self.colors()
        pen = QPen(main, max(1, s.size), DASH_STYLES.get(s.dash, Qt.SolidLine), Qt.RoundCap, Qt.RoundJoin)
        brush = Qt.NoBrush
        if s.fill_mode == "Fill":
            pen, brush = Qt.NoPen, QBrush(main)
        elif s.fill_mode == "Outline + Fill":
            brush = QBrush(other)
        return pen, brush

    def render(self, mods):
        c = self.c
        c.clear_stroke()
        painter = c.stroke_painter()
        pen, brush = self.make_pen_brush()
        painter.setPen(pen)
        painter.setBrush(brush)
        path = self.build_path(self.box(mods))
        painter.drawPath(path)
        painter.end()
        w = max(1, c.state.size) + 3
        c.touch(path.boundingRect().adjusted(-w, -w, w, w).toAlignedRect())


class RectTool(ShapeTool):
    key, label, shortcut, kind = "rect", "Rectangle", "R", "rect"


class RoundRectTool(ShapeTool):
    key, label, shortcut, kind = "roundrect", "Rounded rectangle", "Shift+R", "roundrect"
    options = ShapeTool.options + ("radius",)


class EllipseTool(ShapeTool):
    key, label, shortcut, kind = "ellipse", "Ellipse", "O", "ellipse"


class TriangleTool(ShapeTool):
    key, label, shortcut, kind = "triangle", "Triangle", "", "triangle"


class DiamondTool(ShapeTool):
    key, label, shortcut, kind = "diamond", "Diamond", "", "diamond"


class StarTool(ShapeTool):
    key, label, shortcut, kind = "star", "Star", "", "star"
    options = ShapeTool.options + ("star_points",)


class HeartTool(ShapeTool):
    key, label, shortcut, kind = "heart", "Heart", "", "heart"


class LineTool(ShapeTool):
    key, label, shortcut = "line", "Line", "L"
    options = ("size", "opacity", "dash", "antialias")
    arrow = False
    hint = "Drag to draw. Shift snaps to 45°. Alt = from centre."

    def endpoints(self, mods):
        a, b = self.start, self.cur
        if mods & Qt.ShiftModifier:
            ang = round(math.atan2(b.y() - a.y(), b.x() - a.x()) / (math.pi / 4)) * (math.pi / 4)
            d = dist(a, b)
            b = QPointF(a.x() + d * math.cos(ang), a.y() + d * math.sin(ang))
        if mods & Qt.AltModifier:
            a = QPointF(2 * a.x() - b.x(), 2 * a.y() - b.y())
        return a, b

    def render(self, mods):
        c = self.c
        c.clear_stroke()
        painter = c.stroke_painter()
        s = c.state
        main = self.colors()[0]
        pen = QPen(main, max(1, s.size), DASH_STYLES.get(s.dash, Qt.SolidLine), Qt.RoundCap, Qt.RoundJoin)
        painter.setPen(pen)
        a, b = self.endpoints(mods)
        bounds = QRectF(a, b).normalized()
        if self.arrow and dist(a, b) > 1:
            ang = math.atan2(b.y() - a.y(), b.x() - a.x())
            size = max(12.0, s.size * 4.0)
            base = QPointF(b.x() - math.cos(ang) * size * 0.8, b.y() - math.sin(ang) * size * 0.8)
            painter.drawLine(a, base)
            head = QPolygonF([b, QPointF(b.x() - size * math.cos(ang - 0.42), b.y() - size * math.sin(ang - 0.42)),
                              QPointF(b.x() - size * math.cos(ang + 0.42), b.y() - size * math.sin(ang + 0.42))])
            painter.setPen(Qt.NoPen)
            painter.setBrush(main)
            painter.drawPolygon(head)
            bounds = bounds.united(head.boundingRect())
        else:
            painter.drawLine(a, b)
        painter.end()
        w = max(1, s.size) + 4
        c.touch(bounds.adjusted(-w, -w, w, w).toAlignedRect())


class ArrowTool(LineTool):
    key, label, shortcut = "arrow", "Arrow", "Shift+L"
    arrow = True


class PolygonTool(ShapeTool):
    key, label, shortcut, kind = "polygon", "Polygon", "P", "polygon"
    hint = "Click to add points; double-click, Enter or click the first point to finish. Esc cancels."

    def __init__(self, canvas):
        super().__init__(canvas)
        self.points = []

    def press(self, p, button, mods):
        c = self.c
        if not self.points:
            if not c.can_paint():
                return
            self.button = button
            c.begin_stroke(opacity=c.state.opacity / 100.0)
            self.points = [p]
        else:
            if len(self.points) >= 3 and dist(p, self.points[0]) * c.zoom < 8:
                self.finish_polygon()
                return
            self.points.append(p)
        self.cur = p
        self.drag = True
        self.draw_polygon(closed=False)

    def move(self, p, mods):
        if self.points:
            self.cur = p
            self.draw_polygon(closed=False)

    def release(self, p, mods):
        pass

    def double_click(self, p, button, mods):
        self.finish_polygon()

    def key_press(self, event):
        if not self.points:
            return False
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.finish_polygon()
        elif event.key() == Qt.Key_Escape:
            self.reset()
            self.c.cancel_stroke()
        elif event.key() == Qt.Key_Backspace:
            self.points.pop()
            if self.points:
                self.draw_polygon(closed=False)
            else:
                self.reset()
                self.c.cancel_stroke()
        else:
            return False
        return True

    def reset(self):
        self.points = []
        self.drag = False

    def deactivate(self):
        if len(self.points) >= 2:
            self.finish_polygon()
        elif self.points:
            self.reset()
            self.c.cancel_stroke()

    def finish_polygon(self):
        if len(self.points) < 2:
            self.reset()
            self.c.cancel_stroke()
            return
        self.draw_polygon(closed=True)
        self.c.commit_stroke(self.label)
        self.c.state.remember_color(self.colors()[0])
        self.reset()

    def draw_polygon(self, closed):
        c = self.c
        c.clear_stroke()
        painter = c.stroke_painter()
        pen, brush = self.make_pen_brush()
        painter.setPen(pen)
        pts = list(self.points) if closed else list(self.points) + [self.cur]
        poly = QPolygonF(pts)
        if closed:
            painter.setBrush(brush)
            painter.drawPolygon(poly)
        else:
            painter.setBrush(Qt.NoBrush)
            if pen == Qt.NoPen:
                painter.setPen(QPen(self.colors()[0], 1))
            painter.drawPolyline(poly)
        painter.end()
        w = max(1, c.state.size) + 4
        c.touch(poly.boundingRect().adjusted(-w, -w, w, w).toAlignedRect())


# ------------------------------------------------------------------ fills & picking

class FillTool(Tool):
    key, label, shortcut = "fill", "Paint bucket", "G"
    options = ("opacity", "tolerance", "contiguous", "sample")
    alt_eyedrop = True
    hint = "Click to fill similar pixels. Right button uses the secondary colour."

    def press(self, p, button, mods):
        c = self.c
        if not c.can_paint():
            return
        s = c.state
        src = c.doc.flattened() if s.sample == "Merged" else c.doc.active_layer.image
        mask = imageutil.flood_mask(src, int(p.x()), int(p.y()), s.tolerance, s.contiguous)
        if mask is None or not mask.any():
            return
        color = QColor(s.primary if button == Qt.LeftButton else s.secondary)
        ov = c.begin_stroke(opacity=s.opacity / 100.0, buf=imageutil.mask_to_image(mask, color))
        ov.dirty = imageutil.mask_bbox(mask)
        c.doc.invalidate(ov.dirty)
        c.commit_stroke("Fill")
        s.remember_color(color)


class GradientTool(Tool):
    key, label, shortcut = "gradient", "Gradient", "Shift+G"
    options = ("opacity", "gradient", "gradient_end")
    hint = "Drag from the start to the end of the gradient."

    def __init__(self, canvas):
        super().__init__(canvas)
        self.drag = False

    def press(self, p, button, mods):
        if not self.c.can_paint():
            return
        self.drag = True
        self.start = self.cur = p
        self.button = button
        self.c.begin_stroke(opacity=self.c.state.opacity / 100.0)
        self.render()

    def move(self, p, mods):
        if self.drag:
            self.cur = p
            self.render()

    def release(self, p, mods):
        if self.drag:
            self.drag = False
            self.cur = p
            self.render()
            self.c.commit_stroke("Gradient")

    def deactivate(self):
        if self.drag:
            self.drag = False
            self.c.cancel_stroke()

    def render(self):
        c, s = self.c, self.c.state
        a, b = (s.primary, s.secondary) if self.button == Qt.LeftButton else (s.secondary, s.primary)
        if s.gradient_end == "Transparent":
            b = QColor(a)
            b.setAlpha(0)
        if s.gradient == "Radial":
            g = QRadialGradient(self.start, max(1.0, dist(self.start, self.cur)))
        else:
            g = QLinearGradient(self.start, self.cur)
        g.setColorAt(0, a)
        g.setColorAt(1, b)
        c.clear_stroke()
        painter = c.stroke_painter(aa=False)
        painter.fillRect(c.doc.rect, QBrush(g))
        painter.end()
        c.touch(c.doc.rect)


class PickerTool(Tool):
    key, label, shortcut = "picker", "Colour picker", "I"
    options = ()
    cursor = Qt.PointingHandCursor
    hint = "Click to pick the primary colour, right-click for secondary."

    def press(self, p, button, mods):
        self.button = button
        self.pick(p)

    def move(self, p, mods):
        self.pick(p)

    def pick(self, p):
        color = self.c.sample_color(p)
        if color is None or color.alpha() == 0:
            return
        if self.button == Qt.LeftButton:
            self.c.state.primary = color
        else:
            self.c.state.secondary = color


class TextTool(Tool):
    key, label, shortcut = "text", "Text", "T"
    options = ("opacity", "font", "font_size", "bold", "italic", "antialias")
    cursor = Qt.IBeamCursor
    hint = "Click where the text should start."

    def press(self, p, button, mods):
        c = self.c
        if not c.can_paint():
            return
        text, ok = QInputDialog.getMultiLineText(c, "Text", "Enter text:")
        if not ok or not text.strip():
            return
        s = c.state
        font = QFont(s.font)
        if not QFontInfo(font).exactMatch():              # e.g. "Sans Serif" does not exist on Windows
            font = QFontDatabase.systemFont(QFontDatabase.GeneralFont)
        font.setPixelSize(max(4, s.font_size))
        font.setBold(s.bold)
        font.setItalic(s.italic)
        color = QColor(s.primary if button == Qt.LeftButton else s.secondary)
        c.begin_stroke(opacity=s.opacity / 100.0)
        painter = c.stroke_painter()
        painter.setFont(font)
        painter.setPen(color)
        fm = QFontMetricsF(font)
        dirty = QRectF()
        for i, line in enumerate(text.split("\n")):
            origin = QPointF(p.x(), p.y() + fm.ascent() + i * fm.lineSpacing())
            painter.drawText(origin, line)
            dirty = dirty.united(QRectF(origin.x(), origin.y() - fm.ascent(), fm.horizontalAdvance(line), fm.height()))
        painter.end()
        c.touch(dirty.adjusted(-4, -4, 4, 4).toAlignedRect())
        c.commit_stroke("Text")
        s.remember_color(color)


# ------------------------------------------------------------------ selection

def combine_selection(old, new, mods):
    """Ctrl adds, Alt subtracts, Ctrl+Alt intersects; otherwise replace."""
    if old is None:
        return new
    ctrl, alt = bool(mods & Qt.ControlModifier), bool(mods & Qt.AltModifier)
    if ctrl and alt:
        return old.intersected(new)
    if alt:
        return old.subtracted(new)
    if ctrl:
        return old.united(new)
    return new


class SelectionTool(Tool):
    options = ()
    hint = "Drag to select. Ctrl adds, Alt subtracts, Shift constrains."

    def __init__(self, canvas):
        super().__init__(canvas)
        self.drag = False

    def press(self, p, button, mods):
        if button != Qt.LeftButton:
            return
        self.drag = True
        self.start = self.cur = QPointF(round(p.x()), round(p.y()))
        self.points = [self.start]
        self.update_preview(mods)

    def move(self, p, mods):
        if self.drag:
            self.cur = QPointF(round(p.x()), round(p.y()))
            self.points.append(self.cur)
            self.update_preview(mods)

    def release(self, p, mods):
        if not self.drag:
            return
        self.drag = False
        self.cur = QPointF(round(p.x()), round(p.y()))
        path = self.shape(mods)
        self.c.sel_preview = None
        doc = self.c.doc
        if path.boundingRect().width() < 1.5 and path.boundingRect().height() < 1.5:
            if not (mods & (Qt.ControlModifier | Qt.AltModifier)):
                doc.set_selection(None, "Deselect")
        else:
            doc.set_selection(combine_selection(doc.selection, path, mods), "Select")
        self.c.update()

    def deactivate(self):
        self.drag = False
        self.c.sel_preview = None

    def update_preview(self, mods):
        self.c.sel_preview = self.shape(mods)
        self.c.update()

    def box(self, mods):
        a, b = self.start, self.cur
        dx, dy = b.x() - a.x(), b.y() - a.y()
        if mods & Qt.ShiftModifier:
            m = max(abs(dx), abs(dy))
            dx, dy = math.copysign(m, dx or 1), math.copysign(m, dy or 1)
        return QRectF(a.x(), a.y(), dx, dy).normalized()

    def shape(self, mods):
        return QPainterPath()


class RectSelectTool(SelectionTool):
    key, label, shortcut = "select_rect", "Rectangle select", "M"

    def shape(self, mods):
        path = QPainterPath()
        path.addRect(self.box(mods))
        return path


class EllipseSelectTool(SelectionTool):
    key, label, shortcut = "select_ellipse", "Ellipse select", "Shift+M"

    def shape(self, mods):
        path = QPainterPath()
        path.addEllipse(self.box(mods))
        return path


class LassoTool(SelectionTool):
    key, label, shortcut = "lasso", "Lasso select", "Q"
    hint = "Draw freehand around the area. Ctrl adds, Alt subtracts."

    def shape(self, mods):
        path = QPainterPath()
        if len(self.points) > 2:
            path.addPolygon(QPolygonF(self.points))
            path.closeSubpath()
        return path


class WandTool(Tool):
    key, label, shortcut = "wand", "Magic wand", "W"
    options = ("tolerance", "contiguous", "sample")
    hint = "Click to select similar pixels. Ctrl adds, Alt subtracts."

    def press(self, p, button, mods):
        c, s = self.c, self.c.state
        src = c.doc.flattened() if s.sample == "Merged" else c.doc.active_layer.image
        mask = imageutil.flood_mask(src, int(p.x()), int(p.y()), s.tolerance, s.contiguous)
        if mask is None:
            return
        path = imageutil.mask_to_path(mask)
        c.doc.set_selection(combine_selection(c.doc.selection, path, mods), "Magic wand")


# ------------------------------------------------------------------ move / navigation

class MoveTool(Tool):
    key, label, shortcut = "move", "Move", "V"
    options = ()
    cursor = Qt.SizeAllCursor
    hint = "Drag to move the selection (or the whole layer). Alt-drag copies."

    def __init__(self, canvas):
        super().__init__(canvas)
        self.drag = False

    def press(self, p, button, mods):
        c = self.c
        if button != Qt.LeftButton or not c.can_paint():
            return
        doc = c.doc
        self.layer = doc.active_layer
        self.original = self.layer.image.copy()
        if doc.selection is not None:
            self.bounds = doc.selection.boundingRect().toAlignedRect().intersected(doc.rect)
            self.floating = doc.selection_image(self.layer)
            self.base = self.original.copy()
            if not (mods & Qt.AltModifier):
                q = QPainter(self.base)
                q.setClipPath(doc.selection)
                q.setCompositionMode(QPainter.CompositionMode_Clear)
                q.fillRect(doc.rect, Qt.transparent)
                q.end()
        else:
            self.bounds = doc.rect
            self.floating = self.original.copy()
            self.base = blank_image(self.original.size()) if not (mods & Qt.AltModifier) else self.original.copy()
        if self.bounds.isEmpty():
            return
        self.start, self.offset, self.drag = p, QPoint(0, 0), True

    def move(self, p, mods):
        if not self.drag:
            return
        self.offset = QPoint(int(round(p.x() - self.start.x())), int(round(p.y() - self.start.y())))
        self.layer.image = self.base.copy()
        q = QPainter(self.layer.image)
        q.drawImage(self.bounds.topLeft() + self.offset, self.floating)
        q.end()
        self.c.doc.invalidate()

    def release(self, p, mods):
        if not self.drag:
            return
        self.drag = False
        doc = self.c.doc
        if self.offset == QPoint(0, 0):
            self.layer.image = self.original
            doc.invalidate()
            return
        rect = self.bounds.united(self.bounds.translated(self.offset)).intersected(doc.rect)
        before = self.original.copy(rect)
        doc.undo_stack.beginMacro("Move")
        doc.push_pixels(self.layer, rect, before, "Move pixels")
        if doc.selection is not None:
            moved = doc.selection.translated(self.offset.x(), self.offset.y())
            doc.set_selection(moved, "Move selection")
        doc.undo_stack.endMacro()

    def deactivate(self):
        if self.drag:
            self.drag = False
            self.layer.image = self.original
            self.c.doc.invalidate()


class HandTool(Tool):
    key, label, shortcut = "hand", "Pan", "H"
    cursor = Qt.OpenHandCursor
    hint = "Drag to pan. Space also pans with any tool."


class ZoomTool(Tool):
    key, label, shortcut = "zoom", "Zoom", "Z"
    cursor = Qt.PointingHandCursor
    hint = "Click to zoom in, right-click (or Alt) to zoom out."

    def press(self, p, button, mods):
        out = button == Qt.RightButton or bool(mods & Qt.AltModifier)
        self.c.zoom_to(self.c.zoom * (0.5 if out else 2.0), p)


class SmartPenTool(Tool):
    """Draw roughly; line, circle, ellipse, rectangle, triangle, diamond, star and heart snap to a clean shape."""
    key, label, shortcut = "smartpen", "Smart pen", "S"
    options = ("size", "opacity", "fill_mode", "dash", "antialias")
    brush_cursor = True
    HOLD_MS = 450
    hint = ("Draw any shape roughly (circle, heart, star, rectangle, triangle, line…): it snaps to a clean one. "
            "Hold still to preview, hold Alt when releasing to keep your own line.")

    def __init__(self, canvas):
        super().__init__(canvas)
        self.drag = False
        self.snapped = None
        self.timer = QTimer(canvas)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._hold)

    # -- stroke life-cycle
    def press(self, p, button, mods):
        c = self.c
        if not c.can_paint():
            return
        self.button = button
        self.points = [(p.x(), p.y())]
        self.snapped = None
        self.drag = True
        c.begin_stroke(opacity=c.state.opacity / 100.0)
        main = self.colors()[0]
        painter = c.stroke_painter()
        painter.setPen(self._pen(main))
        painter.drawPoint(p)
        painter.end()
        w = c.state.size + 3
        c.touch(QRectF(p.x() - w, p.y() - w, 2 * w, 2 * w).toAlignedRect())
        self.last = p
        self.timer.start(self.HOLD_MS)

    def move(self, p, mods):
        if not self.drag or self.snapped is not None:
            return                                          # a previewed shape stays put until release
        self.points.append((p.x(), p.y()))
        c = self.c
        painter = c.stroke_painter()
        painter.setPen(self._pen(self.colors()[0]))
        painter.drawLine(self.last, p)
        painter.end()
        w = c.state.size + 3
        c.touch(QRectF(self.last, p).normalized().adjusted(-w, -w, w, w).toAlignedRect())
        self.last = p
        self.timer.start(self.HOLD_MS)

    def release(self, p, mods):
        if not self.drag:
            return
        self.timer.stop()
        self.drag = False
        keep_raw = bool(mods & Qt.AltModifier)
        if self.snapped is None and not keep_raw:
            if (p.x(), p.y()) != self.points[-1]:
                self.points.append((p.x(), p.y()))
            shape = shapefit.recognize(self.points)
            if shape is not None:
                self.snapped = shape
                self._render(shape)
        text = "Smart shape: %s" % self.snapped.label if self.snapped is not None and not keep_raw else "Smart pen stroke"
        if self.snapped is not None and keep_raw:
            text = "Smart pen stroke"
        self.c.commit_stroke(text)
        self.c.state.remember_color(self.colors()[0])
        self.snapped = None

    def deactivate(self):
        self.timer.stop()
        if self.drag:
            self.drag = False
            self.c.cancel_stroke()

    # -- helpers
    def colors(self):
        s = self.c.state
        return (s.primary, s.secondary) if self.button == Qt.LeftButton else (s.secondary, s.primary)

    def _pen(self, color, dash=Qt.SolidLine):
        return QPen(color, max(1, self.c.state.size), dash, Qt.RoundCap, Qt.RoundJoin)

    def _hold(self):
        """Pointer rested: show what the stroke will become (release to accept, keep drawing is ignored)."""
        if not self.drag or self.snapped is not None or len(self.points) < 4:
            return
        shape = shapefit.recognize(self.points)
        if shape is not None:
            self.snapped = shape
            self._render(shape)
            self.c.message.emit("Recognised: %s. Release to keep it, or press Alt while releasing to undo the snap." % shape.label)

    def _render(self, shape):
        c, s = self.c, self.c.state
        c.clear_stroke()
        painter = c.stroke_painter()
        main, other = self.colors()
        pen = self._pen(main, DASH_STYLES.get(s.dash, Qt.SolidLine))
        brush = Qt.NoBrush
        if shape.closed:
            if s.fill_mode == "Fill":
                pen, brush = Qt.NoPen, QBrush(main)
            elif s.fill_mode == "Outline + Fill":
                brush = QBrush(other)
        painter.setPen(pen)
        painter.setBrush(brush)
        if shape.kind in ("ellipse", "circle"):
            cx, cy = shape.center
            painter.translate(cx, cy)
            painter.rotate(shape.angle)
            painter.drawEllipse(QPointF(0, 0), shape.radii[0], shape.radii[1])
            reach = max(shape.radii) + 2
            bounds = QRectF(cx - reach, cy - reach, 2 * reach, 2 * reach)
        else:
            poly = QPolygonF([QPointF(x, y) for x, y in shape.points])
            painter.drawPolygon(poly) if shape.closed else painter.drawPolyline(poly)
            bounds = poly.boundingRect()
        painter.end()
        w = max(1, s.size) + 4
        c.touch(bounds.adjusted(-w, -w, w, w).toAlignedRect())


TOOL_CLASSES = [
    BrushTool, PencilTool, EraserTool, AirbrushTool, SmartPenTool,
    LineTool, ArrowTool, RectTool, RoundRectTool, EllipseTool, TriangleTool, DiamondTool, StarTool, HeartTool,
    PolygonTool, FillTool, GradientTool, PickerTool, TextTool,
    RectSelectTool, EllipseSelectTool, LassoTool, WandTool, MoveTool, HandTool, ZoomTool,
]
