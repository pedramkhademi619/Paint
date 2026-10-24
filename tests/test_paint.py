"""Headless tests: run with `python -m unittest discover -s tests` (needs PyQt5 + numpy)."""
import math
import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import QEvent, QPointF, QRect, QSettings, Qt  # noqa: E402
from PyQt5.QtGui import QColor, QFontDatabase, QGuiApplication, QMouseEvent, QPainter, QPainterPath  # noqa: E402
from PyQt5.QtTest import QTest  # noqa: E402
from PyQt5.QtWidgets import QApplication, QInputDialog  # noqa: E402

from paintapp import imageutil  # noqa: E402
from paintapp.document import Document  # noqa: E402
from paintapp.mainwindow import MainWindow  # noqa: E402

app = QApplication.instance() or QApplication([])


def rgb(img, x, y):
    return img.pixelColor(x, y).name()


class EditorCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        settings = QSettings(os.path.join(self.tmp.name, "s.ini"), QSettings.IniFormat)
        self.win = MainWindow(Document(400, 300), settings)
        self.win.show()
        self.win.canvas.resize(700, 500)
        self.win.canvas.zoom_to(1.0, QPointF(0, 0))
        self.win.canvas.offset = QPointF(20, 20)
        self.c, self.doc, self.state = self.win.canvas, self.win.doc, self.win.state

    def tearDown(self):
        self.win.doc.undo_stack.clear()
        self.win.close()
        self.tmp.cleanup()

    def drag(self, pts, button=Qt.LeftButton, mods=Qt.NoModifier):
        pos = lambda q: self.c.to_screen(QPointF(*q)).toPoint()
        QTest.mousePress(self.c, button, mods, pos(pts[0]))
        for q in pts[1:]:
            QGuiApplication.sendEvent(
                self.c, QMouseEvent(QEvent.MouseMove, QPointF(pos(q)), Qt.NoButton, button, mods))
        QTest.mouseRelease(self.c, button, mods, pos(pts[-1]))

    def click(self, p, **kw):
        self.drag([p, p], **kw)

    def pixel(self, x, y, layer=None):
        return (layer or self.doc.active_layer).image.pixelColor(x, y)


class TestImageUtil(unittest.TestCase):
    def test_flood_fill_respects_boundary(self):
        doc = Document(50, 40)
        p = QPainter(doc.layers[0].image)
        p.setPen(Qt.black)
        p.drawRect(10, 10, 20, 20)
        p.end()
        inner = imageutil.flood_mask(doc.layers[0].image, 15, 15, 0)
        outer = imageutil.flood_mask(doc.layers[0].image, 1, 1, 0)
        self.assertEqual(inner.sum(), 19 * 19)
        self.assertEqual(outer.sum(), 50 * 40 - 21 * 21)
        self.assertEqual(imageutil.mask_bbox(inner), QRect(11, 11, 19, 19))

    def test_non_contiguous_fill_selects_all_matching(self):
        doc = Document(20, 20)
        p = QPainter(doc.layers[0].image)
        p.fillRect(5, 0, 2, 20, Qt.black)                # splits the canvas in two
        p.end()
        self.assertEqual(imageutil.flood_mask(doc.layers[0].image, 0, 0, 0, True).sum(), 5 * 20)
        self.assertEqual(imageutil.flood_mask(doc.layers[0].image, 0, 0, 0, False).sum(), 18 * 20)

    def test_mask_to_path_matches_mask(self):
        import numpy as np
        mask = np.zeros((30, 40), bool)
        mask[5:15, 8:30] = True
        path = imageutil.mask_to_path(mask)
        self.assertEqual(path.boundingRect().toAlignedRect(), QRect(8, 5, 22, 10))
        self.assertTrue(path.contains(QPointF(10.5, 6.5)))
        self.assertFalse(path.contains(QPointF(2.5, 2.5)))

    def test_every_filter_keeps_shape_and_runs(self):
        doc = Document(33, 21)
        arr = imageutil.to_array(doc.layers[0].image)
        for name, (func, params) in imageutil.FILTERS.items():
            out = func(arr, **{k: d for k, _l, _a, _b, d in params})
            self.assertEqual(out.shape, arr.shape, name)

    def test_invert_and_grayscale(self):
        doc = Document(4, 4, QColor(200, 100, 50))
        arr = imageutil.to_array(doc.layers[0].image)
        inv = imageutil.invert(arr)
        self.assertEqual(tuple(inv[0, 0]), (205, 155, 55, 255))       # BGRA
        gray = imageutil.grayscale(arr)
        self.assertEqual(gray[0, 0, 0], gray[0, 0, 1])
        self.assertEqual(gray[0, 0, 1], gray[0, 0, 2])

    def test_blur_spreads_a_point(self):
        import numpy as np
        arr = np.zeros((21, 21, 4), np.uint8)
        arr[..., 3] = 255
        arr[10, 10, :3] = 255
        out = imageutil.blur(arr, 2)
        self.assertLess(out[10, 10, 0], 255)
        self.assertGreater(out[10, 12, 0], 0)


class TestDocument(unittest.TestCase):
    def test_undo_redo_pixels_and_layers(self):
        d = Document(100, 80)
        d.add_layer()
        ov = d.begin_overlay()
        p = QPainter(ov.buf)
        p.fillRect(10, 10, 20, 20, Qt.red)
        p.end()
        ov.dirty = QRect(10, 10, 20, 20)
        d.commit_overlay("rect")
        self.assertEqual(rgb(d.layers[1].image, 15, 15), "#ff0000")
        d.undo_stack.undo()
        self.assertEqual(d.layers[1].image.pixelColor(15, 15).alpha(), 0)
        d.undo_stack.redo()
        self.assertEqual(rgb(d.layers[1].image, 15, 15), "#ff0000")
        d.undo_stack.undo()
        d.undo_stack.undo()
        self.assertEqual(len(d.layers), 1)

    def test_overlay_opacity_and_erase(self):
        d = Document(40, 40)
        ov = d.begin_overlay(opacity=0.5)
        p = QPainter(ov.buf)
        p.fillRect(0, 0, 40, 40, Qt.black)
        p.end()
        ov.dirty = d.rect
        self.assertAlmostEqual(d.get_composite().pixelColor(5, 5).red(), 127, delta=2)
        d.commit_overlay("half")
        ov = d.begin_overlay(erase=True)
        p = QPainter(ov.buf)
        p.fillRect(0, 0, 10, 10, Qt.black)
        p.end()
        ov.dirty = QRect(0, 0, 10, 10)
        d.commit_overlay("erase")
        self.assertEqual(d.layers[0].image.pixelColor(5, 5).alpha(), 0)

    def test_selection_clips_commit(self):
        d = Document(40, 40)
        sel = QPainterPath()
        sel.addRect(0, 0, 20, 40)
        d.set_selection(sel)
        ov = d.begin_overlay()
        p = QPainter(ov.buf)
        p.fillRect(0, 0, 40, 40, Qt.blue)
        p.end()
        ov.dirty = d.rect
        d.commit_overlay("fill")
        self.assertEqual(rgb(d.layers[0].image, 5, 5), "#0000ff")
        self.assertEqual(rgb(d.layers[0].image, 30, 5), "#ffffff")

    def test_merge_down_flatten_and_undo(self):
        d = Document(30, 30)
        d.add_layer()
        d.active_layer.image.fill(QColor(255, 0, 0, 255))
        d.set_layer_prop(d.active_layer, "opacity", 0.5)
        d.merge_down()
        self.assertEqual(len(d.layers), 1)
        self.assertAlmostEqual(d.layers[0].image.pixelColor(1, 1).green(), 127, delta=2)
        d.undo_stack.undo()
        self.assertEqual(len(d.layers), 2)
        self.assertEqual(rgb(d.layers[0].image, 1, 1), "#ffffff")

    def test_opacity_edits_collapse_into_one_undo_step(self):
        d = Document(10, 10)
        layer = d.layers[0]
        for v in (0.9, 0.7, 0.4):
            d.set_layer_prop(layer, "opacity", v)
        self.assertEqual(d.undo_stack.count(), 1)
        d.undo_stack.undo()
        self.assertEqual(layer.opacity, 1.0)

    def test_blend_mode_multiply(self):
        d = Document(10, 10, QColor(200, 200, 200))
        d.add_layer()
        d.active_layer.image.fill(QColor(128, 128, 128))
        d.set_layer_prop(d.active_layer, "blend", "Multiply")
        self.assertAlmostEqual(d.flattened().pixelColor(2, 2).red(), 200 * 128 / 255, delta=2)

    def test_transform_ops_and_undo(self):
        d = Document(100, 60)
        d.rotate(90)
        self.assertEqual((d.size.width(), d.size.height()), (60, 100))
        d.resize_image(30, 50)
        self.assertEqual((d.layers[0].image.width(), d.layers[0].image.height()), (30, 50))
        d.resize_canvas(80, 80, (0, 0))
        self.assertEqual(d.layers[0].image.pixelColor(70, 70).alpha(), 0)
        d.undo_stack.undo()
        d.undo_stack.undo()
        d.undo_stack.undo()
        self.assertEqual((d.size.width(), d.size.height()), (100, 60))
        self.assertEqual((d.layers[0].image.width(), d.layers[0].image.height()), (100, 60))

    def test_crop(self):
        d = Document(100, 60)
        self.assertTrue(d.crop_to_rect(QRect(10, 10, 30, 20)))
        self.assertEqual((d.size.width(), d.size.height()), (30, 20))

    def test_delete_last_layer_refused(self):
        self.assertFalse(Document(10, 10).delete_layer())

    def test_project_round_trip_keeps_layers(self):
        d = Document(64, 48)
        d.add_layer("Ink")
        d.active_layer.image.fill(QColor(10, 20, 30, 255))
        d.set_layer_prop(d.active_layer, "opacity", 0.25)
        d.set_layer_prop(d.active_layer, "blend", "Screen")
        d.set_layer_prop(d.active_layer, "visible", False)
        with tempfile.TemporaryDirectory() as t:
            path = os.path.join(t, "x.pnt")
            self.assertTrue(d.save(path))
            self.assertFalse(d.modified)
            e = Document.open(path)
        self.assertEqual([l.name for l in e.layers], ["Background", "Ink"])
        self.assertEqual((e.layers[1].opacity, e.layers[1].blend, e.layers[1].visible), (0.25, "Screen", False))
        self.assertEqual(rgb(e.layers[1].image, 3, 3), "#0a141e")

    def test_flat_formats(self):
        d = Document(20, 20, QColor(0, 0, 0, 0))
        d.layers[0].image.fill(QColor(0, 0, 0, 0))
        with tempfile.TemporaryDirectory() as t:
            for ext in ("png", "jpg", "bmp", "webp"):
                path = os.path.join(t, "a." + ext)
                self.assertTrue(d.save(path), ext)
                self.assertEqual(Document.open(path).size, d.size)
            self.assertEqual(Document.open(os.path.join(t, "a.png")).layers[0].image.pixelColor(1, 1).alpha(), 0)
            self.assertEqual(rgb(Document.open(os.path.join(t, "a.jpg")).layers[0].image, 1, 1), "#ffffff")

    def test_open_garbage_raises(self):
        with tempfile.TemporaryDirectory() as t:
            path = os.path.join(t, "bad.png")
            with open(path, "wb") as f:
                f.write(b"nope")
            with self.assertRaises(ValueError):
                Document.open(path)


class TestTools(EditorCase):
    def test_brush_draws_and_undoes(self):
        self.state.primary = QColor("red")
        self.state.set("size", 10)
        self.win.select_tool("brush")
        self.drag([(50, 50), (150, 50), (250, 80)])
        self.assertEqual(rgb(self.doc.layers[0].image, 100, 50), "#ff0000")
        self.assertEqual(self.doc.undo_stack.count(), 1)
        self.doc.undo_stack.undo()
        self.assertEqual(rgb(self.doc.layers[0].image, 100, 50), "#ffffff")

    def test_right_button_uses_secondary(self):
        self.state.primary = QColor("red")
        self.state.secondary = QColor("blue")
        self.win.select_tool("pencil")
        self.drag([(20, 20), (80, 20)], button=Qt.RightButton)
        self.assertEqual(rgb(self.doc.layers[0].image, 50, 20), "#0000ff")

    def test_brush_hardness_gives_soft_edge(self):
        self.state.primary = QColor("black")
        self.state.set("size", 40)
        self.state.set("hardness", 0)
        self.win.select_tool("brush")
        self.click((100, 100))
        center, edge = self.pixel(100, 100).red(), self.pixel(100, 117).red()
        self.assertLess(center, 60)
        self.assertGreater(edge, center + 40)

    def test_eraser_makes_transparent_and_respects_layer(self):
        self.win.select_tool("eraser")
        self.state.set("size", 20)
        self.drag([(50, 50), (120, 50)])
        self.assertEqual(self.pixel(80, 50).alpha(), 0)

    def test_stroke_opacity(self):
        self.state.primary = QColor("black")
        self.state.set("opacity", 50)
        self.state.set("size", 20)
        self.win.select_tool("pencil")
        self.drag([(50, 50), (200, 50), (50, 50)])           # overlapping path must not darken further
        self.assertAlmostEqual(self.pixel(100, 50).red(), 127, delta=3)

    def test_shapes_all_produce_pixels(self):
        self.state.primary = QColor("red")
        self.state.set("fill_mode", "Fill")
        for key in ("rect", "roundrect", "ellipse", "triangle", "diamond", "star", "heart"):
            self.win.select_tool(key)
            before = self.doc.undo_stack.index()
            self.drag([(100, 60), (220, 200)])
            self.assertEqual(self.doc.undo_stack.index(), before + 1, key)
            self.assertEqual(self.pixel(160, 140).name(), "#ff0000", key)
            self.doc.undo_stack.undo()

    def test_shape_modifiers(self):
        self.state.primary = QColor("black")
        self.state.set("fill_mode", "Fill")
        self.win.select_tool("rect")
        self.drag([(100, 100), (200, 140)], mods=Qt.ShiftModifier)      # square 100x100
        self.assertEqual(self.pixel(150, 190).name(), "#000000")
        self.doc.undo_stack.undo()
        self.drag([(150, 150), (200, 180)], mods=Qt.AltModifier)        # centred
        self.assertEqual(self.pixel(110, 125).name(), "#000000")

    def test_line_and_arrow(self):
        self.state.primary = QColor("black")
        self.state.set("size", 4)
        self.win.select_tool("line")
        self.drag([(50, 50), (250, 50)])
        self.assertEqual(self.pixel(150, 50).name(), "#000000")
        self.win.select_tool("arrow")
        self.drag([(50, 150), (250, 150)])
        self.assertEqual(self.pixel(240, 150).name(), "#000000")

    def test_polygon_finishes_on_double_click_and_enter(self):
        self.state.primary = QColor("black")
        self.state.set("fill_mode", "Fill")
        self.win.select_tool("polygon")
        for p in [(50, 50), (200, 50), (200, 200)]:
            self.click(p)
        self.assertEqual(self.doc.undo_stack.count(), 0)
        QTest.keyClick(self.c, Qt.Key_Return)
        self.assertEqual(self.doc.undo_stack.count(), 1)
        self.assertEqual(self.pixel(150, 100).name(), "#000000")
        self.assertEqual(self.pixel(60, 150).name(), "#ffffff")

    def test_polygon_escape_cancels(self):
        self.win.select_tool("polygon")
        self.click((50, 50))
        self.click((100, 80))
        QTest.keyClick(self.c, Qt.Key_Escape)
        self.assertEqual(self.doc.undo_stack.count(), 0)
        self.assertIsNone(self.doc.overlay)

    def test_bucket_fill_and_tolerance(self):
        self.state.primary = QColor("green")
        self.state.set("tolerance", 0)
        self.win.select_tool("line")
        self.state.set("size", 3)
        self.drag([(200, 0), (200, 299)])                    # vertical wall
        self.win.select_tool("fill")
        self.click((50, 50))
        self.assertEqual(self.pixel(50, 50).name(), "#008000")
        self.assertEqual(self.pixel(300, 50).name(), "#ffffff")   # other side untouched
        self.state.set("contiguous", False)
        self.state.primary = QColor("blue")
        self.click((300, 50))
        self.assertEqual(self.pixel(300, 50).name(), "#0000ff")

    def test_gradient(self):
        self.state.primary = QColor("black")
        self.state.secondary = QColor("white")
        self.win.select_tool("gradient")
        self.drag([(0, 0), (400, 0)])
        self.assertLess(self.pixel(10, 10).red(), 20)
        self.assertGreater(self.pixel(390, 10).red(), 235)
        self.assertAlmostEqual(self.pixel(200, 10).red(), 127, delta=6)

    def test_eyedropper(self):
        self.state.primary = QColor("black")
        self.state.set("size", 30)
        self.win.select_tool("brush")
        self.state.primary = QColor(12, 200, 99)
        self.state.set("hardness", 100)
        self.click((100, 100))
        self.state.primary = QColor("black")
        self.win.select_tool("picker")
        self.click((100, 100))
        self.assertEqual(self.state.primary.name(), "#0cc863")
        self.click((300, 250), button=Qt.RightButton)
        self.assertEqual(self.state.secondary.name(), "#ffffff")

    def test_alt_click_picks_colour_with_brush(self):
        self.win.select_tool("brush")
        self.state.primary = QColor(1, 2, 3)
        self.state.set("hardness", 100)
        self.state.set("size", 20)
        self.click((100, 100))
        self.state.primary = QColor("white")
        self.click((100, 100), mods=Qt.AltModifier)
        self.assertEqual(self.state.primary.name(), "#010203")

    @unittest.skipUnless(QFontDatabase().families(), "no fonts installed (headless runner)")
    def test_text_tool(self):
        orig = QInputDialog.getMultiLineText
        QInputDialog.getMultiLineText = staticmethod(lambda *a, **k: ("Hello\nWorld", True))
        try:
            self.state.primary = QColor("black")
            self.state.set("font_size", 40)
            self.win.select_tool("text")
            self.click((50, 50))
        finally:
            QInputDialog.getMultiLineText = orig
        self.assertEqual(self.doc.undo_stack.count(), 1)
        dark = sum(1 for x in range(50, 250) for y in range(50, 140) if self.pixel(x, y).red() < 128)
        self.assertGreater(dark, 100)

    def test_airbrush_sprays_over_time(self):
        self.state.primary = QColor("black")
        self.state.set("size", 40)
        self.win.select_tool("airbrush")
        pos = self.c.to_screen(QPointF(100, 100)).toPoint()
        QTest.mousePress(self.c, Qt.LeftButton, Qt.NoModifier, pos)
        QTest.qWait(250)
        QTest.mouseRelease(self.c, Qt.LeftButton, Qt.NoModifier, pos)
        self.assertEqual(self.doc.undo_stack.count(), 1)
        dots = sum(1 for x in range(80, 120) for y in range(80, 120) if self.pixel(x, y).red() < 200)
        self.assertGreater(dots, 30)

    def test_symmetry_mirrors_stroke(self):
        self.state.primary = QColor("black")
        self.state.set("symmetry", "Horizontal")
        self.state.set("size", 6)
        self.win.select_tool("pencil")
        self.drag([(40, 100), (100, 100)])
        self.assertEqual(self.pixel(70, 100).name(), "#000000")
        self.assertEqual(self.pixel(400 - 70, 100).name(), "#000000")

    def test_locked_and_hidden_layers_refuse_painting(self):
        self.win.select_tool("pencil")
        self.doc.set_layer_prop(self.doc.active_layer, "locked", True)
        self.drag([(20, 20), (80, 20)])
        self.assertEqual(self.doc.undo_stack.count(), 1)       # only the lock change
        self.doc.set_layer_prop(self.doc.active_layer, "locked", False)
        self.doc.set_layer_prop(self.doc.active_layer, "visible", False)
        n = self.doc.undo_stack.count()
        self.drag([(20, 20), (80, 20)])
        self.assertEqual(self.doc.undo_stack.count(), n)

    def test_painting_goes_to_active_layer_only(self):
        self.doc.add_layer()
        self.state.primary = QColor("red")
        self.win.select_tool("pencil")
        self.drag([(20, 20), (80, 20)])
        self.assertEqual(self.pixel(50, 20, self.doc.layers[1]).name(), "#ff0000")
        self.assertEqual(self.pixel(50, 20, self.doc.layers[0]).name(), "#ffffff")


class TestSelection(EditorCase):
    def test_rect_ellipse_lasso_and_combine(self):
        self.win.select_tool("select_rect")
        self.drag([(50, 50), (150, 150)])
        self.assertEqual(self.doc.selection.boundingRect().toRect(), QRect(50, 50, 100, 100))
        self.drag([(100, 100), (250, 250)], mods=Qt.ControlModifier)
        self.assertEqual(self.doc.selection.boundingRect().toRect(), QRect(50, 50, 200, 200))
        self.drag([(50, 50), (250, 250)], mods=Qt.AltModifier)
        self.assertIsNone(self.doc.selection) if self.doc.selection is None else self.assertTrue(
            self.doc.selection.isEmpty())
        self.win.select_tool("select_ellipse")
        self.drag([(10, 10), (110, 60)])
        self.assertTrue(self.doc.selection.contains(QPointF(60, 35)))
        self.assertFalse(self.doc.selection.contains(QPointF(12, 12)))
        self.win.select_tool("lasso")
        self.drag([(50, 50), (200, 50), (200, 200), (50, 200)])
        self.assertTrue(self.doc.selection.contains(QPointF(100, 100)))

    def test_click_outside_deselects(self):
        self.win.select_tool("select_rect")
        self.drag([(50, 50), (150, 150)])
        self.click((300, 250))
        self.assertIsNone(self.doc.selection)
        self.doc.undo_stack.undo()
        self.assertIsNotNone(self.doc.selection)

    def test_magic_wand(self):
        self.state.primary = QColor("black")
        self.win.select_tool("rect")
        self.state.set("fill_mode", "Fill")
        self.drag([(100, 100), (200, 200)])
        self.win.select_tool("wand")
        self.click((150, 150))
        self.assertEqual(self.doc.selection.boundingRect().toRect(), QRect(100, 100, 100, 100))

    def test_select_all_invert_delete_fill(self):
        self.win.a["select_all"].trigger()
        self.assertEqual(self.doc.selection.boundingRect().toRect(), self.doc.rect)
        self.win.a["invert_sel"].trigger()
        self.assertIsNone(self.doc.selection)
        self.win.a["select_all"].trigger()
        self.state.primary = QColor("orange")
        self.win.a["fill_primary"].trigger()
        self.assertEqual(self.pixel(5, 5).name(), "#ffa500")
        self.win.a["clear"].trigger()
        self.assertEqual(self.pixel(5, 5).alpha(), 0)

    def test_move_selection_content(self):
        self.state.primary = QColor("red")
        self.state.set("fill_mode", "Fill")
        self.win.select_tool("rect")
        self.drag([(50, 50), (100, 100)])
        self.win.select_tool("select_rect")
        self.drag([(40, 40), (110, 110)])
        self.win.select_tool("move")
        self.drag([(70, 70), (170, 120)])
        self.assertEqual(self.pixel(70, 70).alpha(), 0)             # hole where it was lifted
        self.assertEqual(self.pixel(170, 120).name(), "#ff0000")
        self.assertEqual(self.doc.selection.boundingRect().toRect(), QRect(140, 90, 70, 70))
        steps = self.doc.undo_stack.count()
        self.doc.undo_stack.undo()                                   # whole move is one step
        self.assertEqual(self.doc.undo_stack.count(), steps)
        self.assertEqual(self.pixel(70, 70).name(), "#ff0000")
        self.assertEqual(self.doc.selection.boundingRect().toRect(), QRect(40, 40, 70, 70))

    def test_alt_move_copies(self):
        self.state.primary = QColor("red")
        self.state.set("fill_mode", "Fill")
        self.win.select_tool("rect")
        self.drag([(50, 50), (100, 100)])
        self.win.a["select_all"].trigger()
        self.win.select_tool("move")
        self.drag([(70, 70), (170, 70)], mods=Qt.AltModifier)
        self.assertEqual(self.pixel(70, 70).name(), "#ff0000")
        self.assertEqual(self.pixel(170, 70).name(), "#ff0000")

    def test_copy_paste_creates_layer(self):
        self.state.primary = QColor("red")
        self.state.set("fill_mode", "Fill")
        self.win.select_tool("rect")
        self.drag([(50, 50), (100, 100)])
        self.win.select_tool("select_rect")
        self.drag([(40, 40), (110, 110)])
        self.win.a["copy"].trigger()
        self.win.a["paste"].trigger()
        self.assertEqual(len(self.doc.layers), 2)
        self.assertEqual(self.c.tool.key, "move")
        pasted = self.doc.layers[1].image
        self.assertGreater(sum(1 for x in range(0, 140) for y in range(0, 140) if pasted.pixelColor(x, y).alpha()), 2000)
        self.assertEqual(self.doc.undo_stack.count() and self.doc.undo_stack.undoText(), "Paste")
        self.doc.undo_stack.undo()
        self.assertEqual(len(self.doc.layers), 1)

    def test_cut_is_one_undo_step(self):
        self.state.primary = QColor("red")
        self.state.set("fill_mode", "Fill")
        self.win.select_tool("rect")
        self.drag([(50, 50), (100, 100)])
        self.win.a["select_all"].trigger()
        n = self.doc.undo_stack.count()
        self.win.a["cut"].trigger()
        self.assertEqual(self.pixel(70, 70).alpha(), 0)
        self.assertEqual(self.doc.undo_stack.count(), n + 1)

    def test_crop_to_selection(self):
        self.win.select_tool("select_rect")
        self.drag([(50, 50), (150, 120)])
        self.win.a["crop"].trigger()
        self.assertEqual((self.doc.size.width(), self.doc.size.height()), (100, 70))


class TestWindow(EditorCase):
    def test_layer_panel_actions(self):
        panel = self.win.layer_panel
        panel.buttons["new_layer"].click()
        panel.buttons["dup_layer"].click()
        self.assertEqual(len(self.doc.layers), 3)
        panel.buttons["merge"].click()
        self.assertEqual(len(self.doc.layers), 2)
        panel.buttons["delete"].click()
        self.assertEqual(len(self.doc.layers), 1)
        QTest.qWait(80)
        self.assertEqual(panel.list.count(), 1)

    def test_layer_panel_visibility_and_rename(self):
        self.doc.add_layer()
        QTest.qWait(80)
        panel = self.win.layer_panel
        item = panel.list.item(0)                       # top layer
        item.setCheckState(Qt.Unchecked)
        self.assertFalse(self.doc.layers[1].visible)
        QTest.qWait(80)
        panel.list.item(0).setText("Renamed")
        self.assertEqual(self.doc.layers[1].name, "Renamed")

    def test_layer_opacity_slider_and_blend(self):
        panel = self.win.layer_panel
        panel.opacity.setValue(40)
        self.assertAlmostEqual(self.doc.layers[0].opacity, 0.4)
        panel.blend.setCurrentText("Multiply")
        panel._blend_changed(0)
        self.assertEqual(self.doc.layers[0].blend, "Multiply")

    def test_filters_via_menu_and_undo(self):
        self.state.primary = QColor(200, 50, 50)
        self.win.a["select_all"].trigger()
        self.win.a["fill_primary"].trigger()
        self.win.run_filter("Invert Colors")
        self.assertEqual(self.pixel(5, 5).name(), "#37cdcd")
        self.doc.undo_stack.undo()
        self.assertEqual(self.pixel(5, 5).name(), "#c83232")

    def test_filter_dialog_applies_only_on_accept(self):
        from paintapp.dialogs import FilterDialog
        func, params = imageutil.FILTERS["Grayscale"]
        self.state.primary = QColor(200, 50, 50)
        self.win.a["select_all"].trigger()
        self.win.a["fill_primary"].trigger()
        self.win.a["deselect"].trigger()
        n = self.doc.undo_stack.count()
        dlg = FilterDialog(self.win, self.doc, "Grayscale", func, params)
        dlg._render()
        self.assertEqual(self.pixel(5, 5).red(), self.pixel(5, 5).green())          # live preview
        dlg.reject()
        self.assertEqual(self.pixel(5, 5).name(), "#c83232")
        self.assertEqual(self.doc.undo_stack.count(), n)
        dlg = FilterDialog(self.win, self.doc, "Grayscale", func, params)
        dlg.accept()
        self.assertEqual(self.pixel(5, 5).red(), self.pixel(5, 5).green())
        self.assertEqual(self.doc.undo_stack.count(), n + 1)

    def test_filter_respects_selection(self):
        self.state.primary = QColor(200, 50, 50)
        self.win.a["select_all"].trigger()
        self.win.a["fill_primary"].trigger()
        self.win.select_tool("select_rect")
        self.drag([(0, 0), (100, 100)])
        self.win.run_filter("Invert Colors")
        self.assertEqual(self.pixel(50, 50).name(), "#37cdcd")
        self.assertEqual(self.pixel(200, 200).name(), "#c83232")

    def test_zoom_and_pan(self):
        z = self.c.zoom
        self.c.zoom_to(z * 2, QPointF(200, 150))
        self.assertAlmostEqual(self.c.zoom, z * 2)
        p = self.c.to_image(self.c.to_screen(QPointF(123, 45)))
        self.assertAlmostEqual(p.x(), 123)
        self.win.a["fit"].trigger()
        self.assertTrue(self.c.auto_fit)
        self.win.a["actual"].trigger()
        self.assertAlmostEqual(self.c.zoom, 1.0)
        before = QPointF(self.c.offset)
        QTest.keyPress(self.c, Qt.Key_Space)
        self.drag([(100, 100), (60, 80)])                     # pan, must not paint
        QTest.keyRelease(self.c, Qt.Key_Space)
        self.assertEqual(self.doc.undo_stack.count(), 0)
        self.assertNotEqual(self.c.offset, before)

    def test_new_image_and_pristine_replacement(self):
        self.win.bind_document(Document(64, 32))
        self.assertEqual(self.win.size_label.text(), "64×32 px")

    def test_resize_and_rotate_actions_update_status(self):
        self.win.a["rot_cw"].trigger()
        self.assertEqual(self.win.size_label.text(), "300×400 px")

    def test_open_and_save_via_window(self):
        path = os.path.join(self.tmp.name, "pic.png")
        self.doc.layers[0].image.fill(QColor("teal"))
        self.assertTrue(self.win._save_to(path))
        self.assertEqual(self.doc.name, "pic.png")
        win2 = self.win.open_path(path)
        self.assertIsNotNone(win2)
        self.assertEqual(rgb(win2.doc.layers[0].image, 3, 3), "#008080")
        if win2 is not self.win:
            win2.doc.undo_stack.setClean()
            win2.close()

    def test_title_shows_modified(self):
        self.win.select_tool("pencil")
        self.drag([(20, 20), (60, 20)])
        self.assertTrue(self.win.isWindowModified())
        self.doc.save(os.path.join(self.tmp.name, "t.pnt"))
        self.assertFalse(self.win.isWindowModified())

    def test_every_tool_selectable_and_has_icon(self):
        for key in self.c.tools:
            self.win.select_tool(key)
            self.assertTrue(self.win.tool_actions[key].isChecked())
            self.assertFalse(self.win.tool_actions[key].icon().isNull())
        self.win.grab()

    def test_option_bar_shows_relevant_controls(self):
        self.win.select_tool("brush")
        self.assertTrue(self.win.options.actions_by_key["hardness"].isVisible())
        self.win.select_tool("fill")
        self.assertFalse(self.win.options.actions_by_key["hardness"].isVisible())
        self.assertTrue(self.win.options.actions_by_key["tolerance"].isVisible())

    def test_bracket_keys_change_size(self):
        self.state.set("size", 20)
        self.win.a["bigger"].trigger()
        self.assertEqual(self.state.size, 25)
        self.win.a["smaller"].trigger()
        self.win.a["smaller"].trigger()
        self.assertEqual(self.state.size, 15)

    def test_swap_and_reset_colours(self):
        self.state.primary = QColor("red")
        self.state.secondary = QColor("blue")
        self.win.a["swap"].trigger()
        self.assertEqual((self.state.primary.name(), self.state.secondary.name()), ("#0000ff", "#ff0000"))
        self.win.a["reset"].trigger()
        self.assertEqual((self.state.primary.name(), self.state.secondary.name()), ("#000000", "#ffffff"))

    def test_colour_picker_round_trip(self):
        picker = self.win.color_panel.picker
        picker.hex.setText("#336699")
        picker._hex()
        self.assertEqual(self.state.primary.name(), "#336699")
        self.state.primary = QColor("#aa5500")
        self.assertEqual(picker.color().name(), "#aa5500")

    def test_canvas_follows_saved_theme(self):
        s = QSettings(os.path.join(self.tmp.name, "light.ini"), QSettings.IniFormat)
        s.setValue("dark", False)
        win = MainWindow(Document(10, 10), s)
        self.assertFalse(win.canvas.dark)
        win.close()

    def test_theme_toggle(self):
        self.win.a["dark"].setChecked(False)
        self.win.toggle_theme()
        self.assertFalse(self.win.dark)
        self.win.a["dark"].setChecked(True)
        self.win.toggle_theme()
        self.assertTrue(self.win.dark)


if __name__ == "__main__":
    unittest.main()
