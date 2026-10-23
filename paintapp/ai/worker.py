"""Background threads so generation and downloads never block the UI."""
from PyQt5.QtCore import QThread, pyqtSignal

from .engine import Cancelled


class JobThread(QThread):
    status = pyqtSignal(str)
    progress = pyqtSignal(int, int)
    done = pyqtSignal(object, int)          # PIL image, seed used
    failed = pyqtSignal(str)
    cancelled = pyqtSignal()

    def __init__(self, engine, job, parent=None):
        super().__init__(parent)
        self.engine, self.job = engine, job
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        try:
            if not self.engine.loaded:
                self.engine.load(self.status.emit)
            self.status.emit("Generating…")
            image, seed = self.engine.run(self.job, self.progress.emit, lambda: self._cancel)
        except Cancelled:
            self.cancelled.emit()
        except Exception as exc:               # surfaced to the user, includes CUDA out-of-memory
            self.failed.emit(self._explain(exc))
        else:
            self.done.emit(image, seed)

    @staticmethod
    def _explain(exc):
        text = "%s: %s" % (type(exc).__name__, exc)
        if "out of memory" in text.lower():
            text += "\n\nThe GPU ran out of memory. Try a smaller size (512) or close other GPU programs."
        return text


class DownloadThread(QThread):
    progress = pyqtSignal(str, int, int)
    done = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, dest=None, parent=None):
        super().__init__(parent)
        self.dest = dest

    def run(self):
        from . import models
        try:
            paths = models.download(self.dest, self.progress.emit)
        except Exception as exc:
            self.failed.emit("%s: %s" % (type(exc).__name__, exc))
        else:
            self.done.emit(paths)
