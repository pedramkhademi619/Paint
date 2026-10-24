"""Turn a wobbly hand-drawn stroke into a clean geometric shape ("smart pen").

Qt-free: input is a list of (x, y) points, output is a `Shape` describing the tidy version, or None
when the stroke does not look like anything we know (then the caller keeps the user's drawing).

How it works
  * open strokes: straight line, or a polyline with a few straight segments
  * closed strokes: the outline is compared with clean templates (ellipse, rectangle, diamond, triangle,
    star, heart) using a chamfer distance, after normalising position/size and trying small rotations;
    leftovers are tried as a straight-edged polygon
"""
import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

N = 96                       # points used for matching
MIN_LENGTH = 24.0            # shorter strokes are dots/ticks, never shapes
CLOSE_RATIO = 0.22           # end-to-start gap relative to path length that still counts as "closed"
LINE_DEVIATION = 0.075       # max sideways wobble of a straight line, relative to its length


@dataclass
class Shape:
    kind: str                                   # line polyline ellipse circle rect square diamond triangle star heart polygon
    closed: bool
    points: np.ndarray = field(default_factory=lambda: np.zeros((0, 2)))   # polygon / polyline vertices
    center: tuple = (0.0, 0.0)                  # ellipse only
    radii: tuple = (0.0, 0.0)
    angle: float = 0.0                          # degrees, ellipse rotation
    score: float = 0.0                          # lower = closer match

    @property
    def label(self):
        return {"polyline": "polyline", "polygon": "polygon"}.get(self.kind, self.kind)


# ------------------------------------------------------------------ geometry helpers

def _dedupe(pts):
    pts = np.asarray(pts, float)
    if len(pts) < 2:
        return pts
    keep = np.r_[True, np.hypot(*np.diff(pts, axis=0).T) > 1e-9]
    return pts[keep]


def path_length(pts):
    return float(np.hypot(*np.diff(pts, axis=0).T).sum()) if len(pts) > 1 else 0.0


def resample(pts, n=N, closed=False):
    """n points evenly spaced along the path (optionally treating it as a closed loop)."""
    pts = _dedupe(pts)
    if closed:
        pts = np.vstack([pts, pts[:1]])
    seg = np.hypot(*np.diff(pts, axis=0).T)
    total = seg.sum()
    if total <= 0:
        return np.repeat(pts[:1], n, axis=0)
    t = np.r_[0, np.cumsum(seg)] / total
    u = np.linspace(0, 1, n, endpoint=not closed)
    return np.column_stack([np.interp(u, t, pts[:, 0]), np.interp(u, t, pts[:, 1])])


def _rot(deg):
    a = math.radians(deg)
    return np.array([[math.cos(a), -math.sin(a)], [math.sin(a), math.cos(a)]])


def _chamfer(a, b):
    d = np.sqrt(((a[:, None, :] - b[None, :, :]) ** 2).sum(-1))
    d1, d2 = d.min(axis=1), d.min(axis=0)
    return 0.5 * (d1.mean() + d2.mean()) + 0.25 * max(d1.max(), d2.max())


# ------------------------------------------------------------------ templates (unit square, y down)

def _outline(poly, n=N):
    return resample(np.asarray(poly, float), n, closed=True)


def _normalised(pts):
    pts = np.asarray(pts, float)
    lo, hi = pts.min(axis=0), pts.max(axis=0)
    return (pts - lo) / np.maximum(hi - lo, 1e-9)


def _star(points=5, ratio=0.382):
    pts = []
    for i in range(points * 2):
        a = -math.pi / 2 + i * math.pi / points
        r = 1.0 if i % 2 == 0 else ratio
        pts.append((r * math.cos(a), r * math.sin(a)))
    return np.array(pts)


def _heart(n=400):
    t = np.linspace(0, 2 * math.pi, n, endpoint=False)
    x = 16 * np.sin(t) ** 3
    y = -(13 * np.cos(t) - 5 * np.cos(2 * t) - 2 * np.cos(3 * t) - np.cos(4 * t))     # y down
    return np.column_stack([x, y])


def _build_templates():
    circle = np.column_stack([0.5 + 0.5 * np.cos(np.linspace(0, 2 * np.pi, N, endpoint=False)),
                              0.5 + 0.5 * np.sin(np.linspace(0, 2 * np.pi, N, endpoint=False))])
    star, heart = _star(), _heart()
    raw = {
        "ellipse": (circle, range(-90, 91, 15), None),
        "rect": (_outline([(0, 0), (1, 0), (1, 1), (0, 1)]), range(-45, 46, 5), None),
        "diamond": (_outline([(.5, 0), (1, .5), (.5, 1), (0, .5)]), range(-10, 11, 5), None),
        "triangle": (_outline([(.5, 0), (1, 1), (0, 1)]), list(range(-30, 31, 10)) + list(range(150, 211, 10)), None),
        "star": (_outline(star), range(-36, 37, 6), _aspect(star)),
        "heart": (_outline(heart), range(-30, 31, 6), _aspect(heart)),
    }
    out = {}
    for name, (poly, thetas, aspect) in raw.items():
        pts = resample(np.asarray(poly, float), N, closed=True) if name != "ellipse" else poly
        out[name] = (_normalised(pts), list(thetas), aspect)
    return out


def _aspect(poly):
    w, h = np.ptp(poly[:, 0]), np.ptp(poly[:, 1])
    return float(w / h)


TEMPLATES = _build_templates()
# (kind -> accept if chamfer score below)
THRESHOLD = {"ellipse": 0.105, "rect": 0.105, "diamond": 0.105, "triangle": 0.105, "star": 0.115, "heart": 0.115}
# a heart/star must beat the "simpler" shapes by this margin, otherwise a sloppy blob would become a heart
PREFER_SIMPLE = {"heart": 0.85, "star": 0.85}


def _place(template_unit, lo, hi, theta, center, aspect=None):
    """Map a unit-square template into the drawn bounding box (in the rotated frame) and rotate back."""
    size = hi - lo
    t = template_unit
    if aspect is not None and 0.7 < (size[0] / size[1]) / aspect < 1.43:   # keep a star/heart in proportion
        w = min(size[0], size[1] * aspect)
        h = w / aspect
        offset = lo + (size - np.array([w, h])) / 2
        q = offset + t * np.array([w, h])
    else:
        q = lo + t * size
    return q @ _rot(theta).T + center


# ------------------------------------------------------------------ open strokes

def _line_fit(pts):
    c = pts.mean(axis=0)
    _u, _s, vt = np.linalg.svd(pts - c, full_matrices=False)
    axis = vt[0]
    proj = (pts - c) @ axis
    side = (pts - c) @ vt[1]
    return c, axis, proj, side


def _rdp(pts, eps):
    """Ramer-Douglas-Peucker on an open polyline; returns indices of kept vertices."""
    keep = np.zeros(len(pts), bool)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        if b <= a + 1:
            continue
        p, q = pts[a], pts[b]
        d = q - p
        norm = np.hypot(*d)
        seg = pts[a + 1:b]
        dist = np.hypot(*(seg - p).T) if norm < 1e-9 else np.abs(d[0] * (seg[:, 1] - p[1]) - d[1] * (seg[:, 0] - p[0])) / norm
        i = int(dist.argmax())
        if dist[i] > eps:
            m = a + 1 + i
            keep[m] = True
            stack += [(a, m), (m, b)]
    return np.flatnonzero(keep)


def _polyline_residual(pts, verts, closed):
    v = np.vstack([verts, verts[:1]]) if closed else verts
    best = np.full(len(pts), np.inf)
    for a, b in zip(v[:-1], v[1:]):
        ab = b - a
        denom = max(float(ab @ ab), 1e-12)
        t = np.clip(((pts - a) @ ab) / denom, 0, 1)
        best = np.minimum(best, np.hypot(*(pts - (a + t[:, None] * ab)).T))
    return best


def _turn(a, b, c):
    """Direction change in degrees at b along a -> b -> c."""
    ab, bc = b - a, c - b
    return abs(math.degrees(math.atan2(ab[0] * bc[1] - ab[1] * bc[0], ab @ bc)))


def _merge_close(verts, tol, closed):
    """Drop vertices that sit almost on the line between their neighbours or too close to each other."""
    verts = [np.asarray(v, float) for v in verts]
    changed = True
    while changed and len(verts) > 2:
        changed = False
        n = len(verts)
        for i in range(n):
            if not closed and i in (0, n - 1):
                continue
            a, b, c = verts[i - 1], verts[i], verts[(i + 1) % n]
            if np.hypot(*(b - a)) < tol or (np.hypot(*(c - b)) < tol and (closed or i < n - 1)):
                del verts[i]
                changed = True
                break
            if _turn(a, b, c) < 12:
                del verts[i]
                changed = True
                break
    return np.array(verts)


def _open_shape(raw):
    pts = resample(raw, 64)
    length = path_length(pts)
    c, axis, proj, side = _line_fit(pts)
    extent = float(np.ptp(proj))
    if extent > 0 and np.abs(side).max() / extent < LINE_DEVIATION and extent / length > 0.9:
        p0 = c + axis * ((raw[0] - c) @ axis)
        p1 = c + axis * ((raw[-1] - c) @ axis)
        return Shape("line", False, np.array([p0, p1]), score=float(np.abs(side).max() / extent))
    diag = math.hypot(*np.ptp(pts, axis=0))
    idx = _rdp(pts, 0.05 * diag)
    verts = _merge_close(pts[idx], 0.08 * diag, closed=False)
    if 3 <= len(verts) <= 6:
        res = _polyline_residual(pts, verts, closed=False)
        sharp = all(_turn(verts[i - 1], verts[i], verts[i + 1]) >= 50 for i in range(1, len(verts) - 1))
        if sharp and res.mean() < 0.02 * diag and res.max() < 0.06 * diag:
            return Shape("polyline", False, verts, score=float(res.mean() / diag))
    return None


# ------------------------------------------------------------------ closed strokes

def _snap_triangle(v):
    """Tidy a 3-vertex shape: equilateral / isosceles when the drawing was close to it."""
    sides = [np.hypot(*(v[(i + 1) % 3] - v[i])) for i in range(3)]
    if max(sides) / max(min(sides), 1e-9) < 1.18:                       # near equilateral
        c = v.mean(axis=0)
        r = np.mean([np.hypot(*(p - c)) for p in v])
        a0 = math.atan2(*(v[0] - c)[::-1])
        return np.array([c + r * np.array([math.cos(a0 + k * 2 * math.pi / 3), math.sin(a0 + k * 2 * math.pi / 3)])
                         for k in range(3)])
    return v


def _closed_polygon(pts):
    diag = math.hypot(*np.ptp(pts, axis=0))
    # cut the loop at the point farthest from the start so RDP has two anchor points
    k = int(np.hypot(*(pts - pts[0]).T).argmax())
    loop = np.vstack([pts[k:], pts[:k + 1]])
    idx = _rdp(loop, 0.045 * diag)
    verts = _merge_close(loop[idx][:-1], 0.09 * diag, closed=True)
    if not 3 <= len(verts) <= 8:
        return None
    res = _polyline_residual(pts, verts, closed=True)
    if res.mean() > 0.022 * diag or res.max() > 0.065 * diag:
        return None
    if len(verts) == 3:
        verts = _snap_triangle(verts)
        return Shape("triangle", True, verts, score=float(res.mean() / diag))
    return Shape("polygon", True, verts, score=float(res.mean() / diag))


def corner_count(pts, min_turn=50.0):
    """Number of sharp corners on a closed outline (turning measured over ~1/10 of the perimeter)."""
    n = len(pts)
    k = max(3, n // 10)
    a, b, c = np.roll(pts, k, axis=0), pts, np.roll(pts, -k, axis=0)
    ab, bc = b - a, c - b
    turn = np.abs(np.degrees(np.arctan2(ab[:, 0] * bc[:, 1] - ab[:, 1] * bc[:, 0], (ab * bc).sum(axis=1))))
    corners, i = 0, 0
    above = turn > min_turn
    if above.all():
        return n
    i0 = int(np.argmin(above))                 # start in a gap so we never split a corner across the seam
    for j in range(n):
        idx = (i0 + j) % n
        prev = (i0 + j - 1) % n
        if above[idx] and not above[prev]:
            corners += 1
    return corners


def _closed_shape(raw):
    pts = resample(raw, N, closed=True)
    center = pts.mean(axis=0)
    scores = []
    for name, (unit, thetas, aspect) in TEMPLATES.items():
        best = (9e9, 0.0, None, None)
        for th in thetas:
            q = (pts - center) @ _rot(-th).T
            lo, hi = q.min(axis=0), q.max(axis=0)
            if min(hi - lo) < 1e-6:
                continue
            s = _chamfer((q - lo) / (hi - lo), unit)
            if s < best[0]:
                best = (s, th, lo, hi)
        scores.append((best[0], name, best))
    corners = corner_count(pts)
    # crooked "round" outlines with four clear corners are rectangles, with three clear corners triangles
    boost = {"rect": 0.8 if corners == 4 else 1.0, "triangle": 0.85 if corners == 3 else 1.0,
             "ellipse": 1.25 if corners in (3, 4) else 1.0}
    scores = [(s * boost.get(n, 1.0), n, b) for s, n, b in scores]
    scores.sort(key=lambda t: t[0])
    by_name = {n: s for s, n, _b in scores}
    for s, name, (_s, th, lo, hi) in scores:
        if s > THRESHOLD[name]:
            break
        simple = min((by_name[n] for n in ("ellipse", "rect", "diamond", "triangle")), default=9e9)
        if name in PREFER_SIMPLE and s > simple * PREFER_SIMPLE[name]:
            continue                                          # a plain shape fits about as well: do not guess "heart"
        return _shape_from_template(name, s, th, lo, hi, center, pts)
    return _closed_polygon(pts)


SNAP_DEG = 8.0                # a shape drawn this close to upright is made exactly upright


def _shape_from_template(name, score, theta, lo, hi, center, pts_drawn):
    if name != "ellipse":
        target = 180.0 if abs(abs(theta) - 180) <= SNAP_DEG else 0.0
        if target != theta and abs(theta - target) <= SNAP_DEG:
            theta = target
            q = (pts_drawn - center) @ _rot(-theta).T
            lo, hi = q.min(axis=0), q.max(axis=0)
    size = hi - lo
    mid = (lo + hi) / 2
    c = center + _rot(theta) @ mid
    if name == "ellipse":
        rx, ry = size[0] / 2, size[1] / 2
        if abs(rx - ry) / max(rx, ry) < 0.12:
            rx = ry = (rx + ry) / 2
            return Shape("circle", True, center=tuple(c), radii=(rx, ry), angle=0.0, score=score)
        return Shape("ellipse", True, center=tuple(c), radii=(rx, ry), angle=float(theta), score=score)
    unit, _th, aspect = TEMPLATES[name]
    if name in ("rect", "diamond", "triangle"):
        corners = {"rect": [(0, 0), (1, 0), (1, 1), (0, 1)], "diamond": [(.5, 0), (1, .5), (.5, 1), (0, .5)],
                   "triangle": [(.5, 0), (1, 1), (0, 1)]}[name]
        unit = np.array(corners, float)
        if name == "rect" and abs(size[0] - size[1]) / max(size) < 0.1:
            side = size.mean()
            lo, hi = mid - side / 2, mid + side / 2
        pts = _place(unit, lo, hi, theta, center)
        kind = "square" if name == "rect" and abs(size[0] - size[1]) / max(size) < 0.1 else name
        if name == "triangle":
            sides = [np.hypot(*(pts[(i + 1) % 3] - pts[i])) for i in range(3)]
            if max(sides) / min(sides) < 1.12:
                pts = _snap_triangle(pts)
        return Shape(kind, True, pts, score=score)
    if name == "star":
        pts = _place(_normalised(_star()), lo, hi, theta, center, aspect)
        return Shape("star", True, pts, score=score)
    pts = _place(_normalised(_heart()), lo, hi, theta, center, aspect)           # smooth 400-point curve
    return Shape("heart", True, pts, score=score)


# ------------------------------------------------------------------ public API

def recognize(points) -> Optional[Shape]:
    """Best clean shape for a stroke, or None if it should be left alone."""
    raw = _dedupe(points)
    if len(raw) < 4 or path_length(raw) < MIN_LENGTH:
        return None
    length = path_length(raw)
    gap = float(np.hypot(*(raw[0] - raw[-1])))
    if gap < CLOSE_RATIO * length:
        diag = math.hypot(*np.ptp(raw, axis=0))
        if diag < 12:
            return None
        return _closed_shape(raw)
    return _open_shape(raw)
