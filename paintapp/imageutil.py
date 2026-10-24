"""NumPy-backed pixel helpers: QImage <-> ndarray, flood fill and filters.

Arrays are (height, width, 4) uint8 in B, G, R, A order with *straight*
(non-premultiplied) alpha, which is what QImage.Format_ARGB32 uses on
little-endian machines.
"""
from collections import OrderedDict

import numpy as np
from PyQt5.QtCore import QRect
from PyQt5.QtGui import QBitmap, QImage, QPainterPath, QRegion


def to_array(img):
    img = img.convertToFormat(QImage.Format_ARGB32)
    w, h = img.width(), img.height()
    ptr = img.constBits()
    ptr.setsize(img.sizeInBytes())
    arr = np.frombuffer(ptr, dtype=np.uint8).reshape(h, img.bytesPerLine())
    return arr[:, : w * 4].reshape(h, w, 4).copy()


def from_array(arr):
    arr = np.ascontiguousarray(arr, dtype=np.uint8)
    h, w = arr.shape[:2]
    img = QImage(arr.data, w, h, w * 4, QImage.Format_ARGB32)
    return img.convertToFormat(QImage.Format_ARGB32_Premultiplied)


# ---------------------------------------------------------------- selection masks

def _premultiplied_view(img):
    """Zero-copy (h, w, 4) BGRA view of a premultiplied image; keep `img` alive while using it."""
    w, h = img.width(), img.height()
    ptr = img.constBits()
    ptr.setsize(img.sizeInBytes())
    return np.frombuffer(ptr, dtype=np.uint8).reshape(h, img.bytesPerLine())[:, : w * 4].reshape(h, w, 4)


def flood_mask(img, x, y, tolerance=0, contiguous=True):
    """Boolean mask of pixels similar to the one at (x, y), or None if outside."""
    img = img.convertToFormat(QImage.Format_ARGB32_Premultiplied)
    arr = _premultiplied_view(img)
    h, w = arr.shape[:2]
    if not (0 <= x < w and 0 <= y < h):
        return None
    if tolerance <= 0:
        a32 = arr.view(np.uint32).reshape(h, w)
        match = a32 == a32[y, x]
    else:
        match = np.ones((h, w), bool)
        for ch in range(4):
            plane = arr[..., ch]
            t = plane[y, x]
            match &= (np.maximum(plane, t) - np.minimum(plane, t)) <= tolerance
    return _connected(match, x, y) if contiguous else match


def _connected(match, x, y):
    """Scanline flood fill over a boolean array, seeded at (x, y)."""
    h, w = match.shape
    out = np.zeros_like(match)
    if not match[y, x]:
        return out
    stack = [(x, y)]
    while stack:
        sx, sy = stack.pop()
        if out[sy, sx] or not match[sy, sx]:
            continue
        blocked = np.flatnonzero(~match[sy])
        i = np.searchsorted(blocked, sx)
        left = blocked[i - 1] + 1 if i > 0 else 0
        right = blocked[i] - 1 if i < len(blocked) else w - 1
        out[sy, left:right + 1] = True
        for ny in (sy - 1, sy + 1):
            if 0 <= ny < h:
                seg = match[ny, left:right + 1] & ~out[ny, left:right + 1]
                if seg.any():
                    edges = np.diff(np.concatenate(([0], seg.view(np.int8), [0])))
                    for s in np.flatnonzero(edges == 1):
                        stack.append((left + int(s), ny))
    return out


def mask_bbox(mask):
    """Bounding QRect of the True cells, or an empty QRect."""
    rows = np.flatnonzero(mask.any(axis=1))
    if rows.size == 0:
        return QRect()
    cols = np.flatnonzero(mask.any(axis=0))
    return QRect(int(cols[0]), int(rows[0]), int(cols[-1] - cols[0] + 1), int(rows[-1] - rows[0] + 1))


def mask_to_image(mask, color):
    """Transparent premultiplied image with `color` wherever mask is True."""
    h, w = mask.shape
    a = color.alpha()
    value = (a << 24) | (round(color.red() * a / 255) << 16) | (round(color.green() * a / 255) << 8) \
        | round(color.blue() * a / 255)
    pixels = np.multiply(mask, np.uint32(value), dtype=np.uint32)
    return QImage(pixels.data, w, h, w * 4, QImage.Format_ARGB32_Premultiplied).copy()


def mask_to_path(mask):
    """Convert a boolean mask to a QPainterPath (via a 1-bit QBitmap region)."""
    h, w = mask.shape
    packed = np.packbits(mask, axis=1)
    stride = (packed.shape[1] + 3) // 4 * 4
    padded = np.zeros((h, stride), np.uint8)
    padded[:, : packed.shape[1]] = packed
    img = QImage(padded.data, w, h, stride, QImage.Format_Mono)
    bitmap = QBitmap.fromImage(img.copy())
    path = QPainterPath()
    path.addRegion(QRegion(bitmap))
    return path.simplified()


# ---------------------------------------------------------------- filters

def _u8(a):
    return np.clip(a, 0, 255).astype(np.uint8)


def _rgb_view(a):
    return a[..., :3]


def invert(arr):
    out = arr.copy()
    out[..., :3] = 255 - out[..., :3]
    return out


def grayscale(arr, amount=100):
    a = arr.astype(np.float32)
    lum = 0.114 * a[..., 0] + 0.587 * a[..., 1] + 0.299 * a[..., 2]
    t = amount / 100.0
    for c in range(3):
        a[..., c] = a[..., c] * (1 - t) + lum * t
    return _u8(a)


def sepia(arr, amount=100):
    a = arr.astype(np.float32)
    b, g, r = a[..., 0], a[..., 1], a[..., 2]
    sr = 0.393 * r + 0.769 * g + 0.189 * b
    sg = 0.349 * r + 0.686 * g + 0.168 * b
    sb = 0.272 * r + 0.534 * g + 0.131 * b
    t = amount / 100.0
    a[..., 2] = r * (1 - t) + sr * t
    a[..., 1] = g * (1 - t) + sg * t
    a[..., 0] = b * (1 - t) + sb * t
    return _u8(a)


def brightness_contrast(arr, brightness=0, contrast=0):
    a = arr.astype(np.float32)
    c = contrast * 2.55
    factor = (259 * (c + 255)) / (255 * (259 - c))
    rgb = (a[..., :3] - 128) * factor + 128 + brightness * 2.55
    a[..., :3] = rgb
    return _u8(a)


_YIQ = np.array([[0.299, 0.587, 0.114], [0.596, -0.274, -0.322], [0.211, -0.523, 0.312]], np.float32)


def hue_saturation(arr, hue=0, saturation=0, lightness=0):
    a = arr.astype(np.float32)
    th = np.deg2rad(hue)
    s = 1 + saturation / 100.0
    rot = np.array([[1, 0, 0],
                    [0, np.cos(th) * s, -np.sin(th) * s],
                    [0, np.sin(th) * s, np.cos(th) * s]], np.float32)
    m = np.linalg.inv(_YIQ) @ rot @ _YIQ                 # acts on (r, g, b)
    rgb = a[..., 2::-1] @ m.T + lightness * 2.55         # BGR -> RGB
    a[..., :3] = rgb[..., ::-1]
    return _u8(a)


def _box_blur(a, r, axis):
    if r <= 0:
        return a
    n = a.shape[axis]
    pad = [(0, 0)] * a.ndim
    pad[axis] = (r + 1, r)
    c = np.cumsum(np.pad(a, pad, mode="edge"), axis=axis, dtype=np.float64)
    hi = [slice(None)] * a.ndim
    lo = [slice(None)] * a.ndim
    hi[axis] = slice(2 * r + 1, 2 * r + 1 + n)
    lo[axis] = slice(0, n)
    return ((c[tuple(hi)] - c[tuple(lo)]) / (2 * r + 1)).astype(np.float32)


def _blur_f32(arr, radius):
    a = arr.astype(np.float32)
    a[..., :3] *= a[..., 3:4] / 255.0                    # premultiply
    for _ in range(3):                                   # 3 box passes ~ gaussian
        for axis in (0, 1):
            a = _box_blur(a, int(radius), axis)
    alpha = a[..., 3:4] / 255.0
    a[..., :3] = np.where(alpha > 1e-4, a[..., :3] / np.maximum(alpha, 1e-4), 0)
    return a


def blur(arr, radius=4):
    return _u8(_blur_f32(arr, radius))


def sharpen(arr, amount=100, radius=2):
    a = arr.astype(np.float32)
    soft = _blur_f32(arr, radius)
    a[..., :3] += (a[..., :3] - soft[..., :3]) * (amount / 100.0)
    return _u8(a)


def pixelate(arr, size=8):
    size = max(1, int(size))
    h, w = arr.shape[:2]
    ph, pw = -h % size, -w % size
    a = np.pad(arr.astype(np.float32), ((0, ph), (0, pw), (0, 0)), mode="edge")
    H, W = a.shape[:2]
    small = a.reshape(H // size, size, W // size, size, 4).mean(axis=(1, 3))
    big = np.repeat(np.repeat(small, size, axis=0), size, axis=1)
    return _u8(big[:h, :w])


def posterize(arr, levels=4):
    a = arr.astype(np.float32)
    levels = max(2, int(levels))
    a[..., :3] = np.round(a[..., :3] / 255.0 * (levels - 1)) * (255.0 / (levels - 1))
    return _u8(a)


def add_noise(arr, amount=20):
    a = arr.astype(np.float32)
    noise = np.random.normal(0, amount, a.shape[:2] + (1,)).astype(np.float32)
    a[..., :3] += noise
    return _u8(a)


def edge_detect(arr, strength=100):
    a = arr.astype(np.float32)
    lum = 0.114 * a[..., 0] + 0.587 * a[..., 1] + 0.299 * a[..., 2]
    p = np.pad(lum, 1, mode="edge")
    gx = (p[:-2, 2:] + 2 * p[1:-1, 2:] + p[2:, 2:]) - (p[:-2, :-2] + 2 * p[1:-1, :-2] + p[2:, :-2])
    gy = (p[2:, :-2] + 2 * p[2:, 1:-1] + p[2:, 2:]) - (p[:-2, :-2] + 2 * p[:-2, 1:-1] + p[:-2, 2:])
    mag = np.sqrt(gx * gx + gy * gy) * (strength / 100.0)
    a[..., :3] = mag[..., None]
    return _u8(a)


# name -> (function, [(param, label, min, max, default), ...])
FILTERS = OrderedDict([
    ("Brightness / Contrast", (brightness_contrast, [("brightness", "Brightness", -100, 100, 0),
                                                     ("contrast", "Contrast", -100, 100, 0)])),
    ("Hue / Saturation", (hue_saturation, [("hue", "Hue", -180, 180, 0),
                                           ("saturation", "Saturation", -100, 100, 0),
                                           ("lightness", "Lightness", -100, 100, 0)])),
    ("Grayscale", (grayscale, [("amount", "Amount", 0, 100, 100)])),
    ("Sepia", (sepia, [("amount", "Amount", 0, 100, 100)])),
    ("Invert Colors", (invert, [])),
    ("Blur", (blur, [("radius", "Radius", 1, 40, 4)])),
    ("Sharpen", (sharpen, [("amount", "Amount", 10, 300, 100)])),
    ("Pixelate", (pixelate, [("size", "Block size", 2, 64, 8)])),
    ("Posterize", (posterize, [("levels", "Levels", 2, 16, 4)])),
    ("Add Noise", (add_noise, [("amount", "Amount", 1, 100, 20)])),
    ("Edge Detect", (edge_detect, [("strength", "Strength", 10, 400, 100)])),
])
