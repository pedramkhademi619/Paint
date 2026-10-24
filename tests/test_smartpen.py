"""The Smart pen tool end to end: real mouse events on the canvas, checking the pixels that end up on the layer."""
import math
import unittest

import numpy as np
from PyQt5.QtCore import QPointF, Qt
from PyQt5.QtGui import QColor
from PyQt5.QtTest import QTest

try:
    import sloppy
    from test_paint import EditorCase
except ImportError:
    from tests import sloppy
    from tests.test_paint import EditorCase

from paintapp import shapefit as sf


def into_doc(points, center=(200, 150), size=170):
    """Scale/translate a stroke so it fits the 400x300 test canvas."""
    pts = np.asarray(points, float)
    lo, hi = pts.min(axis=0), pts.max(axis=0)
    scale = size / float(max(hi - lo))
    return [tuple((p - (lo + hi) / 2) * scale + center) for p in pts]


def ink(layer):
    """Boolean mask of the non-white, non-transparent pixels (the Background layer is opaque white)."""
    img = layer.image
    out = np.zeros((img.height(), img.width()), bool)
    for y in range(img.height()):
        for x in range(img.width()):
            c = img.pixelColor(x, y)
            out[y, x] = c.alpha() > 128 and not (c.red() > 240 and c.green() > 240 and c.blue() > 240)
    return out


class TestSmartPen(EditorCase):
    def setUp(self):
        super().setUp()
        self.state.primary = QColor("black")
        self.state.set("size", 8)
        self.win.select_tool("smartpen")
        self.rng = np.random.default_rng(4)

    def sloppy(self, kind, **kw):
        kw.setdefault("tilt", 0)
        return into_doc(sloppy.hand_draw(sloppy.clean_contour(kind), self.rng, **kw))

    def test_wobbly_circle_becomes_a_round_circle(self):
        pts = self.sloppy("circle", wobble=0.07, stretch=0.0)
        self.drag(pts)
        self.assertEqual(self.doc.undo_stack.undoText(), "Smart shape: circle")
        mask = ink(self.doc.layers[0])
        ys, xs = np.nonzero(mask)
        r = np.hypot(xs - xs.mean(), ys - ys.mean())
        self.assertLess(r.std(), 5.0)                         # a ring of constant radius (stroke is 8px thick)
        raw = np.asarray(pts)
        raw_r = np.hypot(*(raw - raw.mean(axis=0)).T)
        self.assertGreater(raw_r.std(), r.std() * 0.9)         # the hand-drawn one was clearly less round

    def test_crooked_heart_becomes_a_symmetric_heart(self):
        self.state.set("fill_mode", "Fill")                    # compare solid areas: thin outlines are too fragile a metric
        pts = self.sloppy("heart", wobble=0.07, jitter=0.02)
        self.drag(pts)
        self.assertEqual(self.doc.undo_stack.undoText(), "Smart shape: heart")
        mask = ink(self.doc.layers[0])
        ys, xs = np.nonzero(mask)
        cx = (xs.min() + xs.max()) / 2.0
        flipped = np.zeros_like(mask)
        for y, x in zip(ys, xs):
            fx = int(round(2 * cx - x))
            if 0 <= fx < mask.shape[1]:
                flipped[y, fx] = True
        iou = (mask & flipped).sum() / float((mask | flipped).sum())
        self.assertGreater(iou, 0.9)

    def test_every_shape_gets_snapped(self):
        for kind, label in (("star", "star"), ("triangle", "triangle"), ("rect", "rect"), ("ellipse", "ellipse"),
                            ("diamond", "diamond")):
            self.drag(self.sloppy(kind))
            self.assertIn(self.doc.undo_stack.undoText().split(": ")[-1], {label, "square", "rect"}, kind)
            self.doc.undo_stack.undo()

    def test_wobbly_line_becomes_straight(self):
        pts = into_doc(sloppy.hand_line(self.rng), size=250)
        self.drag(pts)
        self.assertEqual(self.doc.undo_stack.undoText(), "Smart shape: line")
        ys, xs = np.nonzero(ink(self.doc.layers[0]))
        a = np.polyfit(xs, ys, 1) if np.ptp(xs) > np.ptp(ys) else None
        coords = np.column_stack([xs, ys]).astype(float)
        _u, s, _vt = np.linalg.svd(coords - coords.mean(axis=0), full_matrices=False)
        self.assertLess(s[1] / s[0], 0.06)                     # essentially one-dimensional

    def test_scribble_is_kept_as_drawn(self):
        pts = into_doc(sloppy.scribble(self.rng))
        self.drag(pts)
        self.assertEqual(self.doc.undo_stack.undoText(), "Smart pen stroke")
        self.assertGreater(int(ink(self.doc.layers[0]).sum()), 100)

    def test_alt_on_release_keeps_the_hand_drawn_line(self):
        self.drag(self.sloppy("circle"), mods=Qt.AltModifier)
        self.assertEqual(self.doc.undo_stack.undoText(), "Smart pen stroke")

    def test_undo_removes_the_snapped_shape_in_one_step(self):
        self.drag(self.sloppy("star"))
        self.assertEqual(self.doc.undo_stack.count(), 1)
        self.doc.undo_stack.undo()
        self.assertEqual(int(ink(self.doc.layers[0]).sum()), 0)

    def test_hold_still_previews_the_clean_shape_before_release(self):
        pts = self.sloppy("heart")
        pos = lambda q: self.c.to_screen(QPointF(*q)).toPoint()
        from PyQt5.QtCore import QEvent
        from PyQt5.QtGui import QGuiApplication, QMouseEvent
        QTest.mousePress(self.c, Qt.LeftButton, Qt.NoModifier, pos(pts[0]))
        for q in pts[1:]:
            QGuiApplication.sendEvent(self.c, QMouseEvent(QEvent.MouseMove, QPointF(pos(q)), Qt.NoButton,
                                                          Qt.LeftButton, Qt.NoModifier))
        self.assertIsNone(self.c.tool.snapped)                 # still drawing: no preview yet
        QTest.qWait(700)                                       # rest the pointer
        self.assertIsNotNone(self.c.tool.snapped)
        self.assertEqual(self.c.tool.snapped.kind, "heart")
        QTest.mouseRelease(self.c, Qt.LeftButton, Qt.NoModifier, pos(pts[-1]))
        self.assertEqual(self.doc.undo_stack.undoText(), "Smart shape: heart")

    def test_fill_mode_fills_closed_shapes_with_the_secondary_colour(self):
        self.state.secondary = QColor("red")
        self.state.set("fill_mode", "Outline + Fill")
        self.drag(self.sloppy("circle", stretch=0.0))
        self.assertEqual(self.doc.layers[0].image.pixelColor(200, 150).name(), "#ff0000")

    def test_right_button_swaps_colours(self):
        self.state.primary = QColor("blue")
        self.state.secondary = QColor("green")
        self.drag(self.sloppy("circle", stretch=0.0), button=Qt.RightButton)
        ys, xs = np.nonzero(ink(self.doc.layers[0]))
        img = self.doc.layers[0].image
        darkest = min(zip(xs, ys), key=lambda p: sum(img.pixelColor(int(p[0]), int(p[1])).getRgb()[:3]))
        self.assertEqual(img.pixelColor(int(darkest[0]), int(darkest[1])).name(), "#008000")

    def test_respects_selection_and_locked_layers(self):
        self.doc.set_layer_prop(self.doc.active_layer, "locked", True)
        n = self.doc.undo_stack.count()
        self.drag(self.sloppy("circle"))
        self.assertEqual(self.doc.undo_stack.count(), n)


if __name__ == "__main__":
    unittest.main()
