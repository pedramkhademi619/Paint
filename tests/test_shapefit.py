"""Recognition accuracy of the smart-pen shape fitter on synthetic sloppy strokes (fixed seed, deterministic)."""
import collections
import math
import unittest

import numpy as np

try:
    import sloppy
except ImportError:                                        # run as `python -m unittest tests.test_shapefit`
    from tests import sloppy

from paintapp import shapefit as sf

ACCEPT = {
    "circle": {"circle", "ellipse"}, "ellipse": {"ellipse", "circle"}, "rect": {"rect", "square", "polygon"},
    "square": {"square", "rect"}, "triangle": {"triangle"}, "diamond": {"diamond", "rect", "square"},
    "star": {"star"}, "heart": {"heart"},
}
TRIALS = 40
MIN_RATE = 0.9


class TestRecognition(unittest.TestCase):
    def rate(self, kind, level=1.0, seed=7):
        rng = np.random.default_rng(seed)
        got = collections.Counter()
        for _ in range(TRIALS):
            pts = sloppy.hand_draw(sloppy.clean_contour(kind), rng, wobble=0.045 * level, jitter=0.012 * level)
            shape = sf.recognize(pts)
            got[shape.kind if shape else None] += 1
        return sum(v for k, v in got.items() if k in ACCEPT[kind]) / float(TRIALS), got

    def test_each_closed_shape_is_recognised_when_drawn_sloppily(self):
        for kind in ACCEPT:
            rate, got = self.rate(kind)
            self.assertGreaterEqual(rate, MIN_RATE, "%s -> %s" % (kind, dict(got)))

    def test_a_crooked_heart_is_a_heart(self):
        for seed in range(5):
            rng = np.random.default_rng(seed)
            pts = sloppy.hand_draw(sloppy.clean_contour("heart"), rng, wobble=0.07, jitter=0.02, tilt=20, stretch=0.3)
            self.assertEqual(sf.recognize(pts).kind, "heart", seed)

    def test_lines_and_corners(self):
        rng = np.random.default_rng(3)
        kinds = collections.Counter(sf.recognize(sloppy.hand_line(rng)).kind for _ in range(TRIALS))
        self.assertEqual(kinds["line"], TRIALS)
        check = np.array([(0, 0), (40, 60), (140, -40)], float) + 100        # a tick mark / "V"
        shape = sf.recognize(sf.resample(check, 60) + np.random.default_rng(1).normal(0, 1.2, (60, 2)))
        self.assertEqual(shape.kind, "polyline")
        self.assertEqual(len(shape.points), 3)

    def test_things_that_are_not_shapes_are_left_alone(self):
        rng = np.random.default_rng(11)
        for name, gen in (("scribble", sloppy.scribble), ("spiral", sloppy.spiral), ("zigzag", sloppy.zigzag),
                          ("s_curve", sloppy.s_curve)):
            hits = sum(1 for _ in range(TRIALS) if sf.recognize(gen(rng)) is not None)
            self.assertLessEqual(hits, TRIALS * 0.1, name)

    def test_dots_and_tiny_strokes_are_ignored(self):
        self.assertIsNone(sf.recognize([(10, 10), (11, 10), (11, 11), (10, 11)]))
        self.assertIsNone(sf.recognize([(5, 5)]))
        self.assertIsNone(sf.recognize([]))

    def test_output_geometry_is_clean(self):
        rng = np.random.default_rng(5)
        circle = sf.recognize(sloppy.hand_draw(sloppy.clean_contour("circle"), rng, stretch=0.0))
        self.assertEqual(circle.kind, "circle")
        self.assertEqual(circle.radii[0], circle.radii[1])
        square = sf.recognize(sloppy.hand_draw(sloppy.clean_contour("square"), rng, stretch=0.0, tilt=3))
        self.assertEqual(square.kind, "square")
        d = [np.hypot(*(square.points[(i + 1) % 4] - square.points[i])) for i in range(4)]
        self.assertLess(max(d) - min(d), 1e-6)                       # four equal sides
        xs = sorted(set(np.round(square.points[:, 0], 6)))
        self.assertEqual(len(xs), 2)                                 # snapped upright: only two distinct x values
        heart = sf.recognize(sloppy.hand_draw(sloppy.clean_contour("heart"), rng, tilt=0))
        left, right = heart.points[:, 0].min(), heart.points[:, 0].max()
        self.assertAlmostEqual(heart.points[:, 0].mean(), (left + right) / 2, delta=(right - left) * 0.03)  # symmetric

    def test_equilateral_triangle_is_snapped(self):
        v = np.array([(0, 0), (100, 4), (52, 90)], float)
        shape = sf.recognize(np.vstack([sf.resample(v, 90, closed=True), v[:1]]))
        self.assertEqual(shape.kind, "triangle")
        s = [np.hypot(*(shape.points[(i + 1) % 3] - shape.points[i])) for i in range(3)]
        self.assertLess(max(s) / min(s), 1.01)

    def test_speed(self):
        import time
        rng = np.random.default_rng(2)
        strokes = [sloppy.hand_draw(sloppy.clean_contour(k), rng) for k in ACCEPT for _ in range(3)]
        t = time.time()
        for s in strokes:
            sf.recognize(s)
        self.assertLess((time.time() - t) / len(strokes), 0.25)      # fast enough to run on every pen release


if __name__ == "__main__":
    unittest.main()
