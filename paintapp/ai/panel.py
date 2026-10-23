"""Dock panel for AI generation: prompt, mode, options, progress, and placing the result as a layer."""
from PyQt5.QtCore import QRect, QRectF, QSize, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QImage, QPainter, QPen
from PyQt5.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel, QMessageBox,
                             QPlainTextEdit, QProgressBar, QPushButton, QScrollArea, QSlider, QSpinBox,
                             QVBoxLayout, QWidget)

from . import engine as eng
from . import models
from .worker import DownloadThread, JobThread

MODES = ["Text → Image", "Image → Image", "Inpaint selection"]
MODE_KEYS = ["txt2img", "img2img", "inpaint"]
SIZES = ["Match canvas (512)", "Match canvas (768)", "512 × 512", "512 × 768", "768 × 512"]
STYLES = {
    "None": "",
    "Photo": ", photograph, natural light, sharp focus, high detail",
    "Digital painting": ", digital painting, detailed, concept art, trending on artstation",
    "Anime": ", anime style, clean line art, vibrant colors",
    "Pixel art": ", pixel art, 16-bit, limited color palette",
    "Watercolor": ", watercolor painting, soft washes, paper texture",
    "Pencil sketch": ", pencil sketch, graphite, hatching, monochrome",
}


class AIPanel(QWidget):
    layerCreated = pyqtSignal(str)

    def __init__(self, window, engine=None, parent=None):
        super().__init__(parent)
        self.window = window
        self.engine = engine                 # injected in tests; otherwise built from the installed model
        self._injected = engine is not None
        self.thread = None
        self.dl_thread = None
        self._build()
        self.refresh_state()

    # ------------------------------------------------------------ UI
    def _build(self):
        self.mode = QComboBox()
        self.mode.addItems(MODES)
        self.prompt = QPlainTextEdit()
        self.prompt.setPlaceholderText("Describe what you want, e.g. “a lighthouse on a cliff at sunset”")
        self.prompt.setFixedHeight(70)
        self.negative = QPlainTextEdit()
        self.negative.setPlaceholderText("Negative prompt (things to avoid)")
        self.negative.setFixedHeight(40)
        self.style = QComboBox()
        self.style.addItems(list(STYLES))
        self.size = QComboBox()
        self.size.addItems(SIZES)
        self.steps = QSpinBox()
        self.steps.setRange(1, 12)
        self.steps.setValue(5)
        self.guidance = QDoubleSpinBox()
        self.guidance.setRange(1.0, 4.0)
        self.guidance.setSingleStep(0.1)
        self.guidance.setValue(1.5)
        self.strength = QSlider(Qt.Horizontal)
        self.strength.setRange(10, 100)
        self.strength.setValue(65)
        self.strength_label = QLabel("0.65")
        self.strength.valueChanged.connect(lambda v: self.strength_label.setText("%.2f" % (v / 100.0)))
        self.seed = QSpinBox()
        self.seed.setRange(0, 2 ** 31 - 1)
        self.random_seed = QCheckBox("Random")
        self.random_seed.setChecked(True)
        self.generate_btn = QPushButton("Generate")
        self.generate_btn.setDefault(True)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setEnabled(False)
        self.download_btn = QPushButton("Download model (~2.2 GB)")
        self.bar = QProgressBar()
        self.bar.setTextVisible(True)
        self.bar.setFormat("")
        self.status = QLabel()
        self.status.setWordWrap(True)

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.addRow("Mode", self.mode)
        form.addRow("Style", self.style)
        form.addRow("Size", self.size)
        form.addRow("Steps", self.steps)
        form.addRow("Guidance", self.guidance)
        strength_row = QHBoxLayout()
        strength_row.addWidget(self.strength, 1)
        strength_row.addWidget(self.strength_label)
        form.addRow("Strength", strength_row)
        seed_row = QHBoxLayout()
        seed_row.addWidget(self.seed, 1)
        seed_row.addWidget(self.random_seed)
        form.addRow("Seed", seed_row)

        buttons = QHBoxLayout()
        buttons.addWidget(self.generate_btn, 1)
        buttons.addWidget(self.cancel_btn)
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.addWidget(QLabel("Prompt"))
        lay.addWidget(self.prompt)
        lay.addWidget(self.negative)
        lay.addLayout(form)
        lay.addLayout(buttons)
        lay.addWidget(self.download_btn)
        lay.addWidget(self.bar)
        lay.addWidget(self.status)
        lay.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setWidget(inner)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        self.mode.currentIndexChanged.connect(self._mode_changed)
        self.generate_btn.clicked.connect(self.generate)
        self.cancel_btn.clicked.connect(self.cancel)
        self.download_btn.clicked.connect(self.download)
        self._mode_changed()

    def _mode_changed(self):
        img2 = self.mode.currentIndex() != 0
        self.strength.setEnabled(img2)
        self.strength_label.setEnabled(img2)

    def focus_prompt(self):
        self.prompt.setFocus()

    # ------------------------------------------------------------ readiness
    def ready(self):
        if self._injected:
            return True, ""
        ok, reason = eng.available()
        if not ok:
            return False, reason
        if models.find_models() is None:
            return False, "The AI model is not installed yet."
        return True, ""

    def refresh_state(self, keep_text=False):
        ok, reason = self.ready()
        libs_ok = self._injected or eng.available()[0]
        self.generate_btn.setEnabled(ok and self.thread is None)
        self.download_btn.setVisible(libs_ok and not ok and self.dl_thread is None)
        if keep_text:
            return
        if ok:
            where = "" if self._injected else " (%s)" % models.find_models().root
            self.status.setText("Ready%s." % where)
        else:
            self.status.setText(reason)

    def _busy(self, busy):
        for w in (self.mode, self.prompt, self.negative, self.style, self.size, self.steps, self.guidance,
                  self.seed, self.random_seed, self.generate_btn):
            w.setEnabled(not busy)
        self.cancel_btn.setEnabled(busy and self.thread is not None)
        if not busy:
            self._mode_changed()

    # ------------------------------------------------------------ job building
    def _longest(self):
        text = self.size.currentText()
        return 768 if "768)" in text else 512

    def _gen_size(self, region):
        text = self.size.currentText()
        if text.startswith("Match"):
            return eng.fit_size(region.width(), region.height(), self._longest())
        a, b = text.replace("×", "x").split("x")
        return int(a), int(b)

    def build_job(self):
        """Returns (Job, context) or raises ValueError with a message for the user."""
        doc = self.window.doc
        mode = MODE_KEYS[self.mode.currentIndex()]
        prompt = self.prompt.toPlainText().strip()
        if not prompt:
            raise ValueError("Write a prompt first.")
        prompt += STYLES[self.style.currentText()]
        seed = eng.random_seed() if self.random_seed.isChecked() else self.seed.value()
        job = eng.Job(mode=mode, prompt=prompt, negative=self.negative.toPlainText().strip(),
                      steps=self.steps.value(), guidance=self.guidance.value(),
                      strength=self.strength.value() / 100.0, seed=seed)
        sel = doc.selection
        ctx = {"doc": doc, "clip": sel, "name": "AI · " + self.prompt.toPlainText().strip()[:28],
               "prompt": job.prompt}
        if mode == "txt2img":
            region = doc.rect
            job.width, job.height = self._gen_size(region)
            if not self.size.currentText().startswith("Match"):
                ctx["fit"] = True                 # fixed aspect: contain inside the canvas
            ctx["region"] = region
            return job, ctx
        flat = doc.flattened(QColor("white"))
        if mode == "img2img":
            region = sel.boundingRect().toAlignedRect().intersected(doc.rect) if sel is not None else doc.rect
        else:
            if sel is None:
                raise ValueError("Make a selection first: the AI repaints inside it.")
            box = sel.boundingRect().toAlignedRect()
            pad = max(32, int(max(box.width(), box.height()) * 0.15))
            region = box.adjusted(-pad, -pad, pad, pad).intersected(doc.rect)
        if region.isEmpty():
            raise ValueError("Nothing to work on.")
        w, h = eng.fit_size(region.width(), region.height(), self._longest())
        job.width, job.height = w, h
        crop = flat.copy(region).scaled(w, h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        job.image = eng.qimage_to_pil(crop)
        if mode == "inpaint":
            mask = QImage(region.size(), QImage.Format_Grayscale8)
            mask.fill(0)
            p = QPainter(mask)
            p.setRenderHint(QPainter.Antialiasing)
            p.translate(-region.x(), -region.y())
            p.setPen(QPen(QColor(255, 255, 255), 6))      # grow a few px so edges blend
            p.setBrush(QColor(255, 255, 255))
            p.drawPath(sel)
            p.end()
            job.mask = eng.mask_to_pil(mask.scaled(w, h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation))
        ctx["region"] = region
        return job, ctx

    # ------------------------------------------------------------ running
    def generate(self):
        if self.thread is not None:
            return
        try:
            job, ctx = self.build_job()
        except ValueError as exc:
            self.status.setText(str(exc))
            return
        ok, reason = self.ready()
        if not ok:
            self.status.setText(reason)
            return
        if self.engine is None:
            self.engine = eng.Engine(models.find_models())
        self.ctx = ctx
        self.thread = JobThread(self.engine, job, self)
        t = self.thread
        t.status.connect(self.status.setText)
        t.progress.connect(self._progress)
        t.done.connect(self._done)
        t.failed.connect(self._failed)
        t.cancelled.connect(self._cancelled)
        t.finished.connect(self._thread_finished)
        self.bar.setRange(0, 0)               # busy until the first step arrives
        self._busy(True)
        t.start()

    def cancel(self):
        if self.thread is not None:
            self.thread.cancel()
            self.status.setText("Cancelling…")

    def _progress(self, step, total):
        self.bar.setRange(0, total)
        self.bar.setValue(step)
        self.bar.setFormat("step %d / %d" % (step, total))

    def _done(self, pil, seed):
        if self.random_seed.isChecked():
            self.seed.setValue(seed)
        self.apply_result(eng.pil_to_qimage(pil), self.ctx)
        self.status.setText("Done · seed %d" % seed)

    def _failed(self, message):
        self.status.setText("Failed.")
        QMessageBox.warning(self, "AI generation failed", message)

    def _cancelled(self):
        self.status.setText("Cancelled.")

    def _thread_finished(self):
        self.thread.deleteLater()
        self.thread = None
        self.bar.setRange(0, 1)
        self.bar.setValue(0)
        self.bar.setFormat("")
        self._busy(False)
        self.refresh_state(keep_text=True)

    def wait(self, ms=60000):
        """Block until the running job ends (used by tests)."""
        t = self.thread
        if t is not None:
            t.wait(ms)

    # ------------------------------------------------------------ result placement
    def apply_result(self, img, ctx):
        doc = ctx["doc"]
        region = ctx["region"]
        layer_img = QImage(doc.size, QImage.Format_ARGB32_Premultiplied)
        layer_img.fill(Qt.transparent)
        p = QPainter(layer_img)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        if ctx.get("clip") is not None:
            p.setClipPath(ctx["clip"])
        target = QRect(region)
        if ctx.get("fit"):
            scaled = img.size().scaled(region.size(), Qt.KeepAspectRatio)
            target = QRect(region.x() + (region.width() - scaled.width()) // 2,
                           region.y() + (region.height() - scaled.height()) // 2, scaled.width(), scaled.height())
        p.drawImage(target, img)
        p.end()
        doc.add_layer(ctx["name"], layer_img, "AI generate")
        self.layerCreated.emit(ctx["name"])

    # ------------------------------------------------------------ model download
    def download(self):
        if self.dl_thread is not None:
            return
        self.dl_thread = DownloadThread(parent=self)
        t = self.dl_thread
        t.progress.connect(self._dl_progress)
        t.done.connect(lambda paths: self.status.setText("Model installed in %s" % paths.root))
        t.failed.connect(lambda m: (self.status.setText("Download failed."),
                                    QMessageBox.warning(self, "Download failed", m)))
        t.finished.connect(self._dl_finished)
        self.download_btn.setVisible(False)
        self.bar.setRange(0, 0)
        self.status.setText("Downloading the model…")
        t.start()

    def _dl_progress(self, desc, done, total):
        if total:
            self.bar.setRange(0, 1000)
            self.bar.setValue(int(1000.0 * done / total))
            self.bar.setFormat("%.0f / %.0f MB" % (done / 1e6, total / 1e6))
            self.status.setText("Downloading %s" % desc[:40])

    def _dl_finished(self):
        self.dl_thread.deleteLater()
        self.dl_thread = None
        self.bar.setRange(0, 1)
        self.bar.setValue(0)
        self.bar.setFormat("")
        self.refresh_state(keep_text=True)

    def shutdown(self):
        if self.thread is not None:
            self.thread.cancel()
            self.thread.wait(5000)
        if self.engine is not None and self.engine.loaded:
            self.engine.unload()
