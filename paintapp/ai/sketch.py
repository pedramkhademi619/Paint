"""Turn the user's rough drawing into the images the recogniser and ControlNet expect."""
import numpy as np
from PIL import Image
from PyQt5.QtCore import QRect

from .. import imageutil


def ink_mask(qimage, threshold=40):
    """Boolean (h, w) mask of the strokes: opaque pixels on transparent layers, dark pixels on opaque ones."""
    arr = imageutil.to_array(qimage)                       # B, G, R, A straight alpha
    alpha = arr[..., 3]
    if (alpha < 250).any():
        return alpha > threshold
    lum = 0.114 * arr[..., 0] + 0.587 * arr[..., 1] + 0.299 * arr[..., 2]
    return lum < 200


def bounding_rect(mask, pad=0.12, min_side=64):
    """QRect around the ink with some breathing room, or None when the layer is empty."""
    rows, cols = np.flatnonzero(mask.any(axis=1)), np.flatnonzero(mask.any(axis=0))
    if rows.size == 0:
        return None
    h, w = mask.shape
    x0, x1, y0, y1 = cols[0], cols[-1] + 1, rows[0], rows[-1] + 1
    px, py = max(int((x1 - x0) * pad), 8), max(int((y1 - y0) * pad), 8)
    rect = QRect(int(x0 - px), int(y0 - py), int(x1 - x0 + 2 * px), int(y1 - y0 + 2 * py))
    if rect.width() < min_side:
        rect.adjust(-(min_side - rect.width()) // 2, 0, (min_side - rect.width() + 1) // 2, 0)
    if rect.height() < min_side:
        rect.adjust(0, -(min_side - rect.height()) // 2, 0, (min_side - rect.height() + 1) // 2)
    return rect.intersected(QRect(0, 0, w, h))


def dilate(mask, radius):
    """Grow the strokes by `radius` pixels (square structuring element, pure numpy)."""
    if radius <= 0:
        return mask
    out = mask.copy()
    for _ in range(radius):
        grown = out.copy()
        grown[1:] |= out[:-1]
        grown[:-1] |= out[1:]
        grown[:, 1:] |= out[:, :-1]
        grown[:, :-1] |= out[:, 1:]
        out = grown
    return out


def _resize_mask(mask, size):
    """Resize keeping hairlines alive (any trace of ink counts), then thicken at the small size where it is cheap."""
    img = Image.fromarray((mask * 255).astype(np.uint8), "L").resize(size, Image.BOX if max(mask.shape) > max(size) else Image.BILINEAR)
    return np.asarray(img) > 20


def erode(mask, radius=1):
    out = mask.copy()
    for _ in range(radius):
        shrunk = out.copy()
        shrunk[1:] &= out[:-1]
        shrunk[:-1] &= out[1:]
        shrunk[:, 1:] &= out[:, :-1]
        shrunk[:, :-1] &= out[:, 1:]
        shrunk[0] = shrunk[-1] = False
        shrunk[:, 0] = shrunk[:, -1] = False
        out = shrunk
    return out


def _thick_enough(mask, target_width):
    """Grow thin strokes until they survive erosion, i.e. are roughly `target_width` px wide, so both models see them."""
    if not mask.any():
        return mask
    k = max(1, (int(target_width) + 1) // 2 - 1)
    grown = mask
    for step in range(target_width + 1):
        grown = dilate(mask, step)
        if erode(grown, k).sum() >= 0.25 * grown.sum():
            return grown
    return grown


def clip_image(mask, side=224):
    """Black strokes on white, square, as CLIP sees doodles best."""
    h, w = mask.shape
    s = max(h, w)
    canvas = np.zeros((s, s), bool)
    canvas[(s - h) // 2:(s - h) // 2 + h, (s - w) // 2:(s - w) // 2 + w] = mask
    canvas = _thick_enough(_resize_mask(canvas, (side, side)), 3)
    return Image.fromarray(np.where(canvas, 0, 255).astype(np.uint8), "L").convert("RGB")


def control_image(mask, width, height):
    """White strokes on black at the generation size: the ControlNet-Scribble input."""
    m = _thick_enough(_resize_mask(mask, (width, height)), 3)
    return Image.fromarray(np.where(m, 255, 0).astype(np.uint8), "L").convert("RGB")
