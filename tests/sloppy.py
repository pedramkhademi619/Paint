"""Generators of hand-drawn-looking strokes for testing shape recognition (deterministic via a numpy Generator)."""
import math

import numpy as np

from paintapp import shapefit as sf


def _dense(poly, closed=True, n=600):
    return sf.resample(np.asarray(poly, float), n, closed=closed)


def clean_contour(kind, n=600):
    t = np.linspace(0, 2 * np.pi, n, endpoint=False)
    if kind == "circle":
        return np.column_stack([np.cos(t), np.sin(t)])
    if kind == "ellipse":
        return np.column_stack([1.0 * np.cos(t), 0.55 * np.sin(t)])
    if kind == "rect":
        return _dense([(-1, -.6), (1, -.6), (1, .6), (-1, .6)], n=n)
    if kind == "square":
        return _dense([(-1, -1), (1, -1), (1, 1), (-1, 1)], n=n)
    if kind == "triangle":
        return _dense([(0, -1), (1, .8), (-1, .8)], n=n)
    if kind == "diamond":
        return _dense([(0, -1), (.7, 0), (0, 1), (-.7, 0)], n=n)
    if kind == "star":
        return _dense(sf._star() * 1.0, n=n)
    if kind == "heart":
        return _dense(sf._heart() / 16.0, n=n)
    raise KeyError(kind)


def hand_draw(contour, rng, size=None, wobble=0.045, jitter=0.012, tilt=12, stretch=0.2, step=8,
              closed=True, gap=None):
    """Perturb a clean contour like a shaky hand would and sample it like mouse events."""
    size = size or rng.uniform(90, 420)
    n = len(contour)
    pts = contour.copy()
    pts = pts - (pts.min(axis=0) + pts.max(axis=0)) / 2
    pts = pts / np.abs(pts).max() * size / 2
    pts[:, 0] *= 1 + rng.uniform(-stretch, stretch)
    pts[:, 1] *= 1 + rng.uniform(-stretch, stretch)
    a = math.radians(rng.uniform(-tilt, tilt))
    pts = pts @ np.array([[math.cos(a), -math.sin(a)], [math.sin(a), math.cos(a)]]).T
    u = np.linspace(0, 1, n, endpoint=False)
    disp = np.zeros_like(pts)
    for k in (1, 2, 3):                                   # low-frequency wobble = crooked sides
        amp = wobble * size / k
        phase = rng.uniform(0, 2 * np.pi, 2)
        disp[:, 0] += amp * np.sin(2 * np.pi * k * u + phase[0]) * rng.uniform(.3, 1)
        disp[:, 1] += amp * np.sin(2 * np.pi * k * u + phase[1]) * rng.uniform(.3, 1)
    pts = pts + disp
    start = rng.integers(0, n)
    pts = np.roll(pts, -start, axis=0)
    pts = np.vstack([pts, pts[:1]])
    if closed:
        # most people stop short of / run past the start: gap in [-6%, +9%] of the loop
        frac = gap if gap is not None else rng.uniform(-0.06, 0.09)
        keep = int(len(pts) * (1 - frac)) if frac >= 0 else len(pts)
        pts = pts[:max(keep, 8)]
        if frac < 0:
            extra = int(n * -frac)
            pts = np.vstack([pts, pts[1:1 + extra]])
    path = sf.resample(pts, max(8, int(sf.path_length(pts) / step)))
    path = path + rng.normal(0, jitter * size, path.shape)
    return path + rng.uniform(150, 600, 2)


def hand_line(rng, wobble=0.025):
    length = rng.uniform(80, 500)
    t = np.linspace(0, 1, max(8, int(length / 8)))
    ang = rng.uniform(0, 2 * np.pi)
    base = np.column_stack([t * length, np.zeros_like(t)])
    base[:, 1] += wobble * length * (np.sin(2 * np.pi * t * rng.uniform(.5, 1.5) + rng.uniform(0, 6)) * rng.uniform(.3, 1))
    base += rng.normal(0, 0.004 * length, base.shape)
    r = np.array([[math.cos(ang), -math.sin(ang)], [math.sin(ang), math.cos(ang)]])
    return base @ r.T + 300


def scribble(rng):
    pts = np.cumsum(rng.normal(0, 14, (60, 2)), axis=0)
    return pts + 300


def spiral(rng):
    t = np.linspace(0, 5 * np.pi, 120)
    return np.column_stack([t * np.cos(t), t * np.sin(t)]) * rng.uniform(4, 9) + 300


def zigzag(rng):
    xs = np.linspace(0, 300, 14)
    ys = np.where(np.arange(14) % 2 == 0, 0, rng.uniform(60, 120))
    return sf.resample(np.column_stack([xs, ys]), 70) + 200


def s_curve(rng):
    t = np.linspace(0, 1, 60)
    return np.column_stack([120 * np.sin(2 * np.pi * t), 300 * t]) + 200
