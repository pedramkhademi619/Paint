"""Document model: layers, selection, undo history and file I/O."""
import json
import os
import zipfile

from PyQt5.QtCore import QBuffer, QByteArray, QIODevice, QObject, QPointF, QRect, QSize, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QImage, QPainter, QPainterPath, QTransform
from PyQt5.QtWidgets import QUndoCommand, QUndoStack

FMT = QImage.Format_ARGB32_Premultiplied

BLEND_MODES = {
    "Normal": QPainter.CompositionMode_SourceOver,
    "Multiply": QPainter.CompositionMode_Multiply,
    "Screen": QPainter.CompositionMode_Screen,
    "Overlay": QPainter.CompositionMode_Overlay,
    "Darken": QPainter.CompositionMode_Darken,
    "Lighten": QPainter.CompositionMode_Lighten,
    "Color Dodge": QPainter.CompositionMode_ColorDodge,
    "Color Burn": QPainter.CompositionMode_ColorBurn,
    "Hard Light": QPainter.CompositionMode_HardLight,
    "Soft Light": QPainter.CompositionMode_SoftLight,
    "Difference": QPainter.CompositionMode_Difference,
    "Exclusion": QPainter.CompositionMode_Exclusion,
}

PROJECT_EXT = "pnt"
FLAT_EXTS = ("png", "jpg", "jpeg", "bmp", "webp", "tif", "tiff")
OPAQUE_EXTS = ("jpg", "jpeg", "bmp")


def blank_image(size, color=Qt.transparent):
    img = QImage(size, FMT)
    img.fill(color)
    return img


class Layer:
    def __init__(self, name, image, visible=True, opacity=1.0, blend="Normal", locked=False):
        self.name = name
        self.image = image
        self.visible = visible
        self.opacity = opacity
        self.blend = blend
        self.locked = locked


class Overlay:
    """A not-yet-committed stroke/shape drawn on top of one layer."""

    def __init__(self, layer, buf, erase, opacity, clip):
        self.layer = layer
        self.buf = buf
        self.erase = erase
        self.opacity = opacity
        self.clip = clip
        self.dirty = QRect()

    def mode(self):
        return QPainter.CompositionMode_DestinationOut if self.erase else QPainter.CompositionMode_SourceOver

    def paint_onto(self, painter, origin=QPointF(0, 0), rect=None):
        painter.save()
        if self.clip is not None:
            painter.setClipPath(self.clip)
        painter.setOpacity(self.opacity)
        painter.setCompositionMode(self.mode())
        if rect is None:
            painter.drawImage(origin, self.buf)
        else:
            painter.drawImage(rect.topLeft(), self.buf, rect)
        painter.restore()


# ------------------------------------------------------------------ commands

class FuncCommand(QUndoCommand):
    def __init__(self, text, redo, undo, merge_id=-1, merge=None):
        super().__init__(text)
        self._redo, self._undo = redo, undo
        self._merge_id, self._merge = merge_id, merge

    def redo(self):
        self._redo()

    def undo(self):
        self._undo()

    def id(self):
        return self._merge_id

    def mergeWith(self, other):
        if self._merge is None or other.id() != self._merge_id:
            return False
        return self._merge(self, other)


class PixelCommand(QUndoCommand):
    """Replaces a rectangle of one layer; before/after hold only that rectangle."""

    def __init__(self, doc, layer, rect, before, after, text):
        super().__init__(text)
        self.doc, self.layer, self.rect = doc, layer, rect
        self.before, self.after = before, after
        self._first = True

    def _apply(self, img):
        p = QPainter(self.layer.image)
        p.setCompositionMode(QPainter.CompositionMode_Source)
        p.drawImage(self.rect.topLeft(), img)
        p.end()
        self.doc.pixels_changed(self.rect)

    def redo(self):
        if self._first:                       # pixels were already written
            self._first = False
            self.doc.pixels_changed(self.rect)
        else:
            self._apply(self.after)

    def undo(self):
        self._apply(self.before)


class PropCommand(QUndoCommand):
    """Layer property change; consecutive opacity edits collapse into one step."""

    def __init__(self, doc, layer, prop, old, new, text):
        super().__init__(text)
        self.doc, self.layer, self.prop, self.old, self.new = doc, layer, prop, old, new

    def redo(self):
        self.doc.apply_layer_prop(self.layer, self.prop, self.new)

    def undo(self):
        self.doc.apply_layer_prop(self.layer, self.prop, self.old)

    def id(self):
        return 7001 if self.prop == "opacity" else -1

    def mergeWith(self, other):
        if self.prop != "opacity" or other.id() != self.id() or other.layer is not self.layer:
            return False
        self.new = other.new
        return True


class StateCommand(QUndoCommand):
    """Swaps whole-document snapshots (size, layer stack, selection)."""

    def __init__(self, doc, before, after, text):
        super().__init__(text)
        self.doc, self.before, self.after = doc, before, after
        self._first = True

    def redo(self):
        if self._first:
            self._first = False
        else:
            self.doc.restore(self.after)

    def undo(self):
        self.doc.restore(self.before)


class SelectionCommand(QUndoCommand):
    def __init__(self, doc, before, after, text):
        super().__init__(text)
        self.doc, self.before, self.after = doc, before, after
        self._first = True

    def redo(self):
        if self._first:
            self._first = False
        else:
            self.doc._set_selection(self.after)

    def undo(self):
        self.doc._set_selection(self.before)


# ------------------------------------------------------------------ document

class Document(QObject):
    repaintNeeded = pyqtSignal(QRect)       # image-space region that changed on screen
    layersChanged = pyqtSignal()            # stack / properties / active layer
    contentCommitted = pyqtSignal()         # pixels finalised (refresh thumbnails)
    selectionChanged = pyqtSignal()
    sizeChanged = pyqtSignal()
    titleChanged = pyqtSignal()

    def __init__(self, width=800, height=600, background=Qt.white, parent=None):
        super().__init__(parent)
        self.size = QSize(width, height)
        self.layers = [Layer("Background", blank_image(self.size, background))]
        self.active = 0
        self.selection = None
        self.overlay = None
        self.path = None
        self._counter = 1
        self._cache = None
        self._dirty = None
        self.undo_stack = QUndoStack(self)
        self.undo_stack.setUndoLimit(150)
        self.undo_stack.cleanChanged.connect(self.titleChanged)

    # -- construction helpers
    @classmethod
    def from_image(cls, image, path=None):
        doc = cls(image.width(), image.height())
        doc.layers[0].image = image.convertToFormat(FMT)
        doc.path = path
        return doc

    @property
    def rect(self):
        return QRect(0, 0, self.size.width(), self.size.height())

    @property
    def active_layer(self):
        return self.layers[self.active]

    @property
    def name(self):
        return os.path.basename(self.path) if self.path else "Untitled"

    @property
    def modified(self):
        return not self.undo_stack.isClean()

    # -- invalidation
    def invalidate(self, rect=None):
        rect = self.rect if rect is None else rect.intersected(self.rect)
        if rect.isEmpty():
            return
        self._dirty = rect if self._dirty is None else self._dirty.united(rect)
        self.repaintNeeded.emit(rect)

    def pixels_changed(self, rect):
        self.invalidate(rect)
        self.contentCommitted.emit()

    def get_composite(self):
        if self._cache is None or self._cache.size() != self.size:
            self._cache = blank_image(self.size)
            self._dirty = self.rect
        if self._dirty is not None:
            self._render(self._cache, self._dirty, self.overlay)
            self._dirty = None
        return self._cache

    def _render(self, target, rect, overlay=None, background=None):
        p = QPainter(target)
        p.setClipRect(rect)
        p.setCompositionMode(QPainter.CompositionMode_Source)
        p.fillRect(rect, background if background is not None else Qt.transparent)
        for layer in self.layers:
            if not layer.visible:
                continue
            p.setOpacity(layer.opacity)
            p.setCompositionMode(BLEND_MODES.get(layer.blend, QPainter.CompositionMode_SourceOver))
            if overlay is not None and overlay.layer is layer:
                tmp = layer.image.copy(rect)
                q = QPainter(tmp)
                q.translate(-rect.x(), -rect.y())
                overlay.paint_onto(q, rect=rect)
                q.end()
                p.drawImage(rect.topLeft(), tmp)
            else:
                p.drawImage(rect.topLeft(), layer.image, rect)
        p.end()

    def flattened(self, background=None):
        img = blank_image(self.size)
        self._render(img, self.rect, None, background)
        return img

    # -- overlay (live stroke) handling
    def begin_overlay(self, erase=False, opacity=1.0, buf=None):
        if buf is None:
            buf = blank_image(self.size)
        self.overlay = Overlay(self.active_layer, buf, erase, opacity, self.selection)
        return self.overlay

    def commit_overlay(self, text):
        ov, self.overlay = self.overlay, None
        if ov is None:
            return
        rect = ov.dirty.intersected(self.rect)
        if rect.isEmpty():
            self.invalidate()
            return
        before = ov.layer.image.copy(rect)
        p = QPainter(ov.layer.image)
        ov.paint_onto(p, rect=rect)
        p.end()
        self.push_pixels(ov.layer, rect, before, text)

    def cancel_overlay(self):
        ov, self.overlay = self.overlay, None
        if ov is not None:
            self.invalidate(ov.dirty)

    def push_pixels(self, layer, rect, before, text):
        after = layer.image.copy(rect)
        self.undo_stack.push(PixelCommand(self, layer, rect, before, after, text))

    # -- generic edit of the active layer, honouring the selection
    def modify_layer(self, text, make_image, layer=None):
        layer = layer or self.active_layer
        rect = self.rect
        if self.selection is not None:
            rect = self.selection.boundingRect().toAlignedRect().intersected(rect)
        if rect.isEmpty():
            return False
        before = layer.image.copy(rect)
        new = make_image(before.copy())
        p = QPainter(layer.image)
        if self.selection is not None:
            p.setClipPath(self.selection)
        p.setCompositionMode(QPainter.CompositionMode_Source)
        p.drawImage(rect.topLeft(), new)
        p.end()
        self.push_pixels(layer, rect, before, text)
        return True

    def clear_selection_pixels(self):
        return self.modify_layer("Delete", lambda img: blank_image(img.size()))

    def fill_selection(self, color):
        return self.modify_layer("Fill selection", lambda img: blank_image(img.size(), color))

    # -- selection
    def _set_selection(self, path):
        self.selection = path
        self.selectionChanged.emit()

    def set_selection(self, path, text="Select"):
        if path is not None:
            path = path.intersected(self._rect_path())
            if path.isEmpty():
                path = None
        before = self.selection
        if before is None and path is None:
            return
        self._set_selection(path)
        self.undo_stack.push(SelectionCommand(self, before, path, text))

    def _rect_path(self):
        p = QPainterPath()
        p.addRect(self.rect.x(), self.rect.y(), self.rect.width(), self.rect.height())
        return p

    def select_all(self):
        self.set_selection(self._rect_path(), "Select all")

    def invert_selection(self):
        full = self._rect_path()
        self.set_selection(full if self.selection is None else full.subtracted(self.selection), "Invert selection")

    def selection_image(self, layer=None):
        """Selected pixels of a layer as a cropped transparent image (or None)."""
        layer = layer or self.active_layer
        if self.selection is None:
            return layer.image.copy()
        rect = self.selection.boundingRect().toAlignedRect().intersected(self.rect)
        out = blank_image(rect.size())
        p = QPainter(out)
        p.translate(-rect.x(), -rect.y())
        p.setClipPath(self.selection)
        p.drawImage(0, 0, layer.image)
        p.end()
        return out

    # -- layers
    def _new_name(self):
        self._counter += 1
        return "Layer %d" % self._counter

    def set_active(self, index):
        index = max(0, min(index, len(self.layers) - 1))
        if index != self.active:
            self.active = index
            self.layersChanged.emit()

    def _insert(self, index, layer, active):
        self.layers.insert(index, layer)
        self.active = active
        self.invalidate()
        self.layersChanged.emit()
        self.contentCommitted.emit()

    def _remove(self, layer, active):
        self.layers.remove(layer)
        self.active = max(0, min(active, len(self.layers) - 1))
        self.invalidate()
        self.layersChanged.emit()
        self.contentCommitted.emit()

    def add_layer(self, name=None, image=None, text="New layer"):
        layer = Layer(name or self._new_name(), image if image is not None else blank_image(self.size))
        index, prev = self.active + 1, self.active
        self.undo_stack.push(FuncCommand(
            text, lambda: self._insert(index, layer, index), lambda: self._remove(layer, prev)))
        return layer

    def duplicate_layer(self, index=None):
        index = self.active if index is None else index
        src = self.layers[index]
        layer = Layer(src.name + " copy", src.image.copy(), src.visible, src.opacity, src.blend)
        prev = self.active
        self.undo_stack.push(FuncCommand(
            "Duplicate layer", lambda: self._insert(index + 1, layer, index + 1), lambda: self._remove(layer, prev)))

    def delete_layer(self, index=None):
        if len(self.layers) < 2:
            return False
        index = self.active if index is None else index
        layer, prev = self.layers[index], self.active
        self.undo_stack.push(FuncCommand(
            "Delete layer", lambda: self._remove(layer, max(0, index - 1)), lambda: self._insert(index, layer, prev)))
        return True

    def move_layer(self, index, delta):
        new = index + delta
        if not 0 <= new < len(self.layers):
            return

        def swap(a, b):
            self.layers[a], self.layers[b] = self.layers[b], self.layers[a]
            self.active = b
            self.invalidate()
            self.layersChanged.emit()
            self.contentCommitted.emit()

        self.undo_stack.push(FuncCommand("Move layer", lambda: swap(index, new), lambda: swap(new, index)))

    def merge_down(self, index=None):
        index = self.active if index is None else index
        if index < 1:
            return False
        top, below = self.layers[index], self.layers[index - 1]
        before = below.image.copy()
        merged = below.image.copy()
        p = QPainter(merged)
        p.setOpacity(top.opacity if top.visible else 0)
        p.setCompositionMode(BLEND_MODES.get(top.blend, QPainter.CompositionMode_SourceOver))
        p.drawImage(0, 0, top.image)
        p.end()
        prev = self.active

        def redo():
            below.image = merged.copy()
            self._remove(top, index - 1)

        def undo():
            below.image = before.copy()
            self._insert(index, top, prev)

        self.undo_stack.push(FuncCommand("Merge down", redo, undo))
        return True

    def set_layer_prop(self, layer, prop, value, text=None):
        old = getattr(layer, prop)
        if old != value:
            self.undo_stack.push(PropCommand(self, layer, prop, old, value, text or "Layer " + prop))

    def apply_layer_prop(self, layer, prop, value):
        setattr(layer, prop, value)
        self.invalidate()
        self.layersChanged.emit()
        self.contentCommitted.emit()

    # -- whole-document operations (resize, rotate, flatten, ...)
    def snapshot(self):
        return (QSize(self.size), list(self.layers), [l.image.copy() for l in self.layers], self.active,
                QPainterPath(self.selection) if self.selection is not None else None)

    def restore(self, snap):
        size, layers, images, active, selection = snap
        size_changed = size != self.size
        self.size = QSize(size)
        self.layers[:] = layers
        for layer, img in zip(layers, images):
            layer.image = img.copy()
        self.active = active
        self.selection = QPainterPath(selection) if selection is not None else None
        self._cache = None
        self.invalidate()
        if size_changed:
            self.sizeChanged.emit()
        self.selectionChanged.emit()
        self.layersChanged.emit()
        self.contentCommitted.emit()

    def transform_document(self, text, mutate):
        """Run `mutate()` (which edits layers/size in place) as one undoable step."""
        self.cancel_overlay()
        before = self.snapshot()
        mutate()
        self.selection = None
        after = self.snapshot()
        self.restore(after)
        if before[0] != self.size:                 # restore() saw no change: mutate() already resized
            self.sizeChanged.emit()
        self.undo_stack.push(StateCommand(self, before, after, text))

    def _map_images(self, fn, new_size=None):
        for layer in self.layers:
            layer.image = fn(layer.image).convertToFormat(FMT)
        if new_size is not None:
            self.size = QSize(new_size)

    def rotate(self, degrees):
        def mutate():
            t = QTransform().rotate(degrees)
            size = self.size if degrees % 180 == 0 else QSize(self.size.height(), self.size.width())
            self._map_images(lambda im: im.transformed(t), size)
        self.transform_document("Rotate image", mutate)

    def flip(self, horizontal):
        def mutate():
            self._map_images(lambda im: im.mirrored(horizontal, not horizontal))
        self.transform_document("Flip image", mutate)

    def flip_layer(self, horizontal):
        self.modify_layer("Flip layer", lambda im: im.mirrored(horizontal, not horizontal))

    def resize_image(self, width, height, smooth=True):
        def mutate():
            mode = Qt.SmoothTransformation if smooth else Qt.FastTransformation
            self._map_images(lambda im: im.scaled(width, height, Qt.IgnoreAspectRatio, mode), QSize(width, height))
        self.transform_document("Resize image", mutate)

    def resize_canvas(self, width, height, anchor=(0.5, 0.5)):
        dx = int((width - self.size.width()) * anchor[0])
        dy = int((height - self.size.height()) * anchor[1])

        def shift(im):
            out = blank_image(QSize(width, height))
            p = QPainter(out)
            p.drawImage(dx, dy, im)
            p.end()
            return out

        def mutate():
            self._map_images(shift, QSize(width, height))
        self.transform_document("Canvas size", mutate)

    def crop_to_rect(self, rect):
        rect = rect.intersected(self.rect)
        if rect.isEmpty():
            return False

        def mutate():
            self._map_images(lambda im: im.copy(rect), rect.size())
        self.transform_document("Crop", mutate)
        return True

    def flatten(self):
        if len(self.layers) < 2:
            return

        def mutate():
            img = self.flattened()
            self.layers[:] = [Layer("Background", img)]
            self.active = 0
        self.transform_document("Flatten image", mutate)

    # -- file I/O
    def save(self, path, quality=92):
        ext = path.rsplit(".", 1)[-1].lower() if "." in path else PROJECT_EXT
        if ext == PROJECT_EXT:
            self._save_project(path)
        else:
            bg = QColor(Qt.white) if ext in OPAQUE_EXTS else None
            img = self.flattened(bg)
            if ext in OPAQUE_EXTS:
                img = img.convertToFormat(QImage.Format_RGB32)
            if not img.save(path, quality=quality):
                return False
        self.path = path
        self.undo_stack.setClean()
        self.titleChanged.emit()
        return True

    def _save_project(self, path):
        meta = {"version": 1, "width": self.size.width(), "height": self.size.height(),
                "active": self.active, "layers": []}
        with zipfile.ZipFile(path, "w", zipfile.ZIP_STORED) as z:
            for i, layer in enumerate(self.layers):
                ba = QByteArray()
                buf = QBuffer(ba)
                buf.open(QIODevice.WriteOnly)
                layer.image.save(buf, "PNG")
                buf.close()
                fname = "layer%d.png" % i
                z.writestr(fname, bytes(ba))
                meta["layers"].append({"name": layer.name, "visible": layer.visible, "opacity": layer.opacity,
                                       "blend": layer.blend, "locked": layer.locked, "file": fname})
            z.writestr("project.json", json.dumps(meta, indent=1))

    @classmethod
    def open(cls, path):
        ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
        if ext == PROJECT_EXT:
            return cls._open_project(path)
        img = QImage(path)
        if img.isNull():
            raise ValueError("Cannot read image: %s" % path)
        doc = cls.from_image(img, path)
        return doc

    @classmethod
    def _open_project(cls, path):
        with zipfile.ZipFile(path) as z:
            meta = json.loads(z.read("project.json"))
            doc = cls(meta["width"], meta["height"])
            doc.layers = []
            for info in meta["layers"]:
                img = QImage()
                if not img.loadFromData(z.read(info["file"]), "PNG"):
                    raise ValueError("Corrupt layer %s" % info["file"])
                doc.layers.append(Layer(info["name"], img.convertToFormat(FMT), info.get("visible", True),
                                        info.get("opacity", 1.0), info.get("blend", "Normal"), info.get("locked", False)))
        if not doc.layers:
            raise ValueError("Project has no layers")
        doc.active = min(meta.get("active", 0), len(doc.layers) - 1)
        doc._counter = len(doc.layers)
        doc.path = path
        return doc
