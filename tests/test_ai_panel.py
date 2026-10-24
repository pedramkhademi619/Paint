"""AI panel tests with a fake engine: no torch, no model, no GPU needed."""
import os
import tempfile
import time
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtCore import QPointF, QRect, QSettings, Qt  # noqa: E402
from PyQt5.QtGui import QColor, QPainterPath  # noqa: E402
from PyQt5.QtWidgets import QApplication, QMessageBox  # noqa: E402

from paintapp.ai import engine as eng  # noqa: E402
from paintapp.ai import models  # noqa: E402
from paintapp.ai.panel import AIPanel  # noqa: E402
from paintapp.document import Document  # noqa: E402
from paintapp.mainwindow import MainWindow  # noqa: E402

app = QApplication.instance() or QApplication([])

try:
    from PIL import Image
except ImportError:                                     # pragma: no cover
    Image = None


class FakeEngine:
    loaded = True
    smart_ready = True

    def __init__(self, delay=0.0, fail=None):
        self.jobs, self.delay, self.fail = [], delay, fail
        self.recognized, self.last_guesses, self.last_label, self.on_info = [], [], "", None

    def recognize(self, pil, top=3):
        self.recognized.append(pil)
        self.last_guesses = [("cat", 0.7), ("dog", 0.2), ("fox", 0.1)]
        return self.last_guesses

    def load(self, status=None):
        pass

    def unload(self):
        self.loaded = False

    def run(self, job, progress=None, cancelled=None):
        self.jobs.append(job)
        for i in range(job.steps):
            time.sleep(self.delay)
            if cancelled and cancelled():
                raise eng.Cancelled()
            if progress:
                progress(i + 1, job.steps)
        if self.fail:
            raise RuntimeError(self.fail)
        if job.mode == "sketch":
            self.last_label = job.subject or self.recognize(job.sketch)[0][0]
            if not job.subject and self.on_info:
                self.on_info("Looks like: cat (70%)")
            return Image.new("RGB", job.control.size, (10, 200, 30)), job.seed
        return Image.new("RGB", (job.width, job.height), (10, 200, 30)), job.seed


@unittest.skipIf(Image is None, "Pillow missing")
class PanelCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        settings = QSettings(os.path.join(self.tmp.name, "s.ini"), QSettings.IniFormat)
        self.win = MainWindow(Document(400, 300), settings)
        self.win.show()
        self.fake = FakeEngine()
        self.win.ai_panel.shutdown()
        self.panel = AIPanel(self.win, engine=self.fake)
        self.doc = self.win.doc

    def tearDown(self):
        self.panel.shutdown()
        self.doc.undo_stack.clear()
        self.win.close()
        self.tmp.cleanup()

    def run_job(self):
        self.panel.generate()
        deadline = time.time() + 20
        while self.panel.thread is not None and time.time() < deadline:
            app.processEvents()
            time.sleep(0.01)
        app.processEvents()
        self.assertIsNone(self.panel.thread, "job did not finish")

    def select(self, x, y, w, h):
        path = QPainterPath()
        path.addRect(x, y, w, h)
        self.doc.set_selection(path)


class TestPanel(PanelCase):
    def test_text_to_image_creates_undoable_layer(self):
        self.panel.prompt.setPlainText("a red fox")
        self.run_job()
        self.assertEqual(len(self.doc.layers), 2)
        self.assertEqual(self.doc.layers[1].name, "AI · a red fox")
        self.assertEqual(self.doc.layers[1].image.pixelColor(200, 150).name(), "#0ac81e")
        job = self.fake.jobs[0]
        self.assertEqual((job.width, job.height), (512, 384))                # canvas aspect, multiples of 8
        self.assertEqual(job.mode, "txt2img")
        self.doc.undo_stack.undo()
        self.assertEqual(len(self.doc.layers), 1)

    def test_empty_prompt_is_rejected_with_message(self):
        self.run_job()
        self.assertEqual(len(self.doc.layers), 1)
        self.assertIn("prompt", self.panel.status.text().lower())
        self.assertEqual(self.fake.jobs, [])

    def test_style_suffix_and_negative_prompt(self):
        self.panel.prompt.setPlainText("castle")
        self.panel.negative.setPlainText("blurry")
        self.panel.style.setCurrentText("Pixel art")
        self.run_job()
        self.assertTrue(self.fake.jobs[0].prompt.startswith("castle, pixel art"))
        self.assertEqual(self.fake.jobs[0].negative, "blurry")

    def test_seed_fixed_vs_random(self):
        self.panel.prompt.setPlainText("x")
        self.panel.random_seed.setChecked(False)
        self.panel.seed.setValue(1234)
        self.run_job()
        self.run_job()
        self.assertEqual([j.seed for j in self.fake.jobs], [1234, 1234])
        self.panel.random_seed.setChecked(True)
        self.run_job()
        self.assertEqual(self.panel.seed.value(), self.fake.jobs[-1].seed)    # shown so it can be reproduced

    def test_fixed_size_is_contained_not_stretched(self):
        self.panel.prompt.setPlainText("tall")
        self.panel.size.setCurrentText("512 × 768")
        self.run_job()
        job = self.fake.jobs[0]
        self.assertEqual((job.width, job.height), (512, 768))
        img = self.doc.layers[1].image
        self.assertEqual(img.pixelColor(200, 150).name(), "#0ac81e")
        self.assertEqual(img.pixelColor(5, 150).alpha(), 0)                  # pillar-box bars stay empty
        self.assertEqual(img.pixelColor(395, 150).alpha(), 0)

    def test_img2img_uses_visible_image_and_strength(self):
        self.doc.layers[0].image.fill(QColor(0, 0, 255))
        self.panel.mode.setCurrentText("Image → Image")
        self.panel.prompt.setPlainText("oil painting")
        self.panel.strength.setValue(40)
        self.run_job()
        job = self.fake.jobs[0]
        self.assertEqual(job.mode, "img2img")
        self.assertAlmostEqual(job.strength, 0.4)
        self.assertEqual(job.image.getpixel((10, 10)), (0, 0, 255))
        self.assertEqual(job.image.size, (job.width, job.height))

    def test_transparency_is_flattened_to_white_for_the_model(self):
        self.doc.layers[0].image.fill(Qt.transparent)
        self.panel.mode.setCurrentText("Image → Image")
        self.panel.prompt.setPlainText("x")
        self.run_job()
        self.assertEqual(self.fake.jobs[0].image.getpixel((5, 5)), (255, 255, 255))

    def test_inpaint_requires_selection(self):
        self.panel.mode.setCurrentText("Inpaint selection")
        self.panel.prompt.setPlainText("a cat")
        self.run_job()
        self.assertEqual(self.fake.jobs, [])
        self.assertIn("selection", self.panel.status.text().lower())

    def test_inpaint_only_touches_selection(self):
        self.select(100, 80, 120, 90)
        self.panel.mode.setCurrentText("Inpaint selection")
        self.panel.prompt.setPlainText("a cat")
        self.run_job()
        job = self.fake.jobs[0]
        self.assertEqual(job.mode, "inpaint")
        self.assertEqual(job.image.size, job.mask.size)
        w, h = job.mask.size
        self.assertEqual(job.mask.getpixel((w // 2, h // 2)), 255)
        self.assertEqual(job.mask.getpixel((0, 0)), 0)
        layer = self.doc.layers[1].image
        self.assertEqual(layer.pixelColor(150, 120).name(), "#0ac81e")
        self.assertEqual(layer.pixelColor(20, 20).alpha(), 0)
        self.assertEqual(layer.pixelColor(300, 250).alpha(), 0)

    def test_img2img_with_selection_works_on_that_region_only(self):
        self.select(0, 0, 200, 150)
        self.panel.mode.setCurrentText("Image → Image")
        self.panel.prompt.setPlainText("x")
        self.run_job()
        layer = self.doc.layers[1].image
        self.assertEqual(layer.pixelColor(100, 70).name(), "#0ac81e")
        self.assertEqual(layer.pixelColor(300, 250).alpha(), 0)

    def test_cancel_stops_job_and_adds_no_layer(self):
        self.fake.delay = 0.05
        self.panel.steps.setValue(12)
        self.panel.prompt.setPlainText("slow")
        self.panel.generate()
        self.assertTrue(self.panel.cancel_btn.isEnabled())
        self.assertFalse(self.panel.generate_btn.isEnabled())
        time.sleep(0.12)
        self.panel.cancel()
        deadline = time.time() + 10
        while self.panel.thread is not None and time.time() < deadline:
            app.processEvents()
            time.sleep(0.01)
        app.processEvents()
        self.assertEqual(len(self.doc.layers), 1)
        self.assertEqual(self.panel.status.text(), "Cancelled.")
        self.assertTrue(self.panel.generate_btn.isEnabled())

    def test_engine_error_is_reported_not_raised(self):
        self.fake.fail = "CUDA out of memory"
        self.panel.prompt.setPlainText("x")
        with mock.patch.object(QMessageBox, "warning") as warn:
            self.run_job()
        self.assertEqual(warn.call_count, 1)
        self.assertIn("out of memory", warn.call_args[0][2])
        self.assertIn("smaller size", warn.call_args[0][2])                  # actionable hint
        self.assertEqual(len(self.doc.layers), 1)
        self.assertTrue(self.panel.generate_btn.isEnabled())

    def test_progress_bar_reports_steps(self):
        seen = []
        self.panel.prompt.setPlainText("x")
        self.panel.steps.setValue(4)
        orig = self.panel._progress
        self.panel._progress = lambda s, t: (seen.append((s, t)), orig(s, t))
        self.panel.generate()
        self.panel.thread.progress.disconnect()
        self.panel.thread.progress.connect(self.panel._progress)
        self.panel.wait()
        app.processEvents()

    def test_strength_slider_only_for_image_modes(self):
        self.assertFalse(self.panel.strength.isEnabled())
        self.panel.mode.setCurrentText("Image → Image")
        self.assertTrue(self.panel.strength.isEnabled())

    def test_result_goes_to_the_document_it_started_from(self):
        other = Document(100, 100)
        self.panel.prompt.setPlainText("x")
        self.fake.delay = 0.02
        self.panel.generate()
        self.win.bind_document(other)                       # user switched document mid-job
        self.panel.wait()
        for _ in range(20):
            app.processEvents()
            time.sleep(0.01)
        self.assertEqual(len(other.layers), 1)
        self.assertEqual(len(self.doc.layers), 2)


class TestSketchToNeat(PanelCase):
    def draw_house(self, layer=None, offset=(0, 0)):
        from PyQt5.QtGui import QPainter, QPen
        layer = layer or self.doc.active_layer
        p = QPainter(layer.image)
        p.setPen(QPen(QColor("black"), 5))
        ox, oy = offset
        p.drawRect(100 + ox, 120 + oy, 120, 90)
        p.drawLine(100 + ox, 120 + oy, 160 + ox, 70 + oy)
        p.drawLine(160 + ox, 70 + oy, 220 + ox, 120 + oy)
        p.end()
        self.doc.invalidate()

    def sketch_mode(self):
        self.panel.mode.setCurrentText("Sketch → Neat")

    def test_mode_shows_its_own_controls(self):
        self.assertFalse(self.panel.sketch_box.isVisibleTo(self.panel))
        self.sketch_mode()
        self.assertTrue(self.panel.sketch_box.isVisibleTo(self.panel))

    def test_recognises_then_redraws_and_hides_the_sketch(self):
        self.doc.add_layer("Sketch")
        self.draw_house()
        self.sketch_mode()
        self.run_job()
        job = self.fake.jobs[0]
        self.assertEqual(job.mode, "sketch")
        self.assertEqual(job.subject, "")                                   # auto-detect
        self.assertEqual(len(self.doc.layers), 3)
        neat = self.doc.layers[2]
        self.assertEqual(neat.name, "AI · neat cat")
        self.assertFalse(self.doc.layers[1].visible)                        # the sketch is hidden
        self.assertEqual(neat.image.pixelColor(160, 160).name(), "#0ac81e")
        self.assertEqual(neat.image.pixelColor(5, 5).alpha(), 0)            # only the sketch's area is replaced
        self.assertIn("drawn as: cat", self.panel.status.text())
        self.assertEqual([self.panel.subject.itemText(i) for i in range(self.panel.subject.count())],
                         ["cat", "dog", "fox"])                              # other guesses offered for a quick fix
        self.doc.undo_stack.undo()                                          # one step undoes layer + hiding
        self.assertEqual(len(self.doc.layers), 2)
        self.assertTrue(self.doc.layers[1].visible)

    def test_control_and_clip_images_have_the_right_polarity_and_size(self):
        self.doc.add_layer("Sketch")
        self.draw_house()
        self.sketch_mode()
        self.run_job()
        job = self.fake.jobs[0]
        self.assertEqual(job.control.size, (job.width, job.height))
        self.assertEqual(job.control.getpixel((0, 0)), (0, 0, 0))            # black background
        self.assertTrue(any(job.control.getpixel((x, y)) == (255, 255, 255)
                            for x in range(0, job.width, 3) for y in range(0, job.height, 3)))   # white lines
        self.assertEqual(job.sketch.size, (224, 224))
        self.assertEqual(job.sketch.getpixel((0, 0)), (255, 255, 255))       # CLIP sees black on white
        self.assertEqual(max(job.width, job.height), 512)
        self.assertEqual((job.width % 8, job.height % 8), (0, 0))

    def test_typed_subject_skips_auto_detection_and_goes_into_the_layer_name(self):
        self.doc.add_layer("Sketch")
        self.draw_house()
        self.sketch_mode()
        self.panel.subject.setEditText("cottage")
        self.run_job()
        self.assertEqual(self.fake.jobs[0].subject, "cottage")
        self.assertEqual(self.fake.recognized, [])
        self.assertEqual(self.doc.layers[2].name, "AI · neat cottage")

    def test_style_extra_prompt_and_follow_strength_reach_the_job(self):
        self.doc.add_layer("Sketch")
        self.draw_house()
        self.sketch_mode()
        self.panel.neat_style.setCurrentText("Flat vector icon")
        self.panel.prompt.setPlainText("blue roof")
        self.panel.negative.setPlainText("people")
        self.panel.follow.setValue(120)
        self.run_job()
        job = self.fake.jobs[0]
        self.assertIn("{subject}", job.prompt)
        self.assertIn("flat vector icon", job.prompt)
        self.assertTrue(job.prompt.endswith(", blue roof"))
        self.assertIn("blurry", job.negative)
        self.assertTrue(job.negative.endswith("people"))
        self.assertAlmostEqual(job.control_scale, 1.2)

    def test_keep_sketch_visible_when_unchecked(self):
        self.doc.add_layer("Sketch")
        self.draw_house()
        self.sketch_mode()
        self.panel.hide_sketch.setChecked(False)
        self.run_job()
        self.assertTrue(self.doc.layers[1].visible)

    def test_works_on_an_opaque_background_layer_too(self):
        self.draw_house()                                                   # black lines on the white Background
        self.sketch_mode()
        self.run_job()
        self.assertEqual(len(self.doc.layers), 2)
        self.assertFalse(self.doc.layers[0].visible)

    def test_empty_drawing_is_reported(self):
        self.doc.add_layer("Empty")
        self.sketch_mode()
        self.run_job()
        self.assertEqual(self.fake.jobs, [])
        self.assertIn("Draw something", self.panel.status.text())

    def test_selection_limits_what_is_recognised(self):
        self.doc.add_layer("Sketch")
        self.draw_house()
        self.draw_house(offset=(-90, 90))
        self.select(80, 60, 160, 170)                                        # only the first house
        self.sketch_mode()
        self.run_job()
        job = self.fake.jobs[0]
        region_h = self.doc.layers[2].image
        covered = [(x, y) for x in range(0, 400, 4) for y in range(0, 300, 4) if region_h.pixelColor(x, y).alpha()]
        self.assertTrue(covered)
        self.assertLess(max(x for x, _y in covered), 270)
        self.assertGreater(min(x for x, _y in covered), 70)
        self.assertEqual(self.doc.layers[1].visible, False)

    def test_what_is_this_button_lists_guesses_without_generating(self):
        self.doc.add_layer("Sketch")
        self.draw_house()
        self.sketch_mode()
        self.panel.recognize()
        deadline = time.time() + 20
        while self.panel.rec_thread is not None and time.time() < deadline:
            app.processEvents()
            time.sleep(0.01)
        app.processEvents()
        self.assertEqual(len(self.fake.recognized), 1)
        self.assertEqual(self.fake.jobs, [])
        self.assertEqual(self.panel.subject.count(), 3)
        self.assertIn("Looks like: cat (70%)", self.panel.status.text())
        self.assertEqual(len(self.doc.layers), 2)

    def test_real_engine_path_asks_for_the_smart_models(self):
        with tempfile.TemporaryDirectory() as t, mock.patch.dict(os.environ, {"PAINTRAM_MODELS_DIR": t}), \
                mock.patch("paintapp.ai.engine.available", return_value=(True, "")):
            TestModels().make_install(t)                                    # base model only
            panel = AIPanel(self.win)
            ok, why = panel.ready("sketch")
            self.assertFalse(ok)
            self.assertIn("sketch recognition models", why)
            self.assertTrue(panel.ready("txt2img")[0])
            panel.shutdown()


class TestSketchHelpers(unittest.TestCase):
    def test_ink_mask_on_transparent_and_opaque_layers(self):
        from PyQt5.QtGui import QImage, QPainter
        from paintapp.ai import sketch
        a = QImage(40, 30, QImage.Format_ARGB32_Premultiplied)
        a.fill(Qt.transparent)
        p = QPainter(a)
        p.fillRect(5, 5, 10, 4, QColor("red"))
        p.end()
        m = sketch.ink_mask(a)
        self.assertEqual((m.shape, int(m.sum())), ((30, 40), 40))
        b = QImage(40, 30, QImage.Format_ARGB32_Premultiplied)
        b.fill(QColor("white"))
        p = QPainter(b)
        p.fillRect(5, 5, 10, 4, QColor("black"))
        p.end()
        self.assertEqual(int(sketch.ink_mask(b).sum()), 40)

    def test_bounding_rect_has_padding_and_empty_is_none(self):
        import numpy as np
        from paintapp.ai import sketch
        m = np.zeros((300, 400), bool)
        self.assertIsNone(sketch.bounding_rect(m))
        m[100:150, 200:300] = True
        r = sketch.bounding_rect(m)
        self.assertTrue(r.contains(QRect(200, 100, 100, 50)))
        self.assertGreater(r.width(), 100)
        self.assertTrue(QRect(0, 0, 400, 300).contains(r))

    def test_thin_lines_are_thickened_and_images_are_well_formed(self):
        import numpy as np
        from paintapp.ai import sketch
        m = np.zeros((200, 300), bool)
        m[100, 20:280] = True                                              # 1px line
        ctl = sketch.control_image(m, 512, 336)
        arr = np.asarray(ctl)
        self.assertEqual(ctl.size, (512, 336))
        self.assertGreaterEqual(int((arr[..., 0] > 128).any(axis=1).sum()), 3)      # at least 3px tall now
        clip = sketch.clip_image(m)
        self.assertEqual(clip.size, (224, 224))
        self.assertEqual(clip.getpixel((0, 0)), (255, 255, 255))


class TestPureHelpers(unittest.TestCase):
    def test_snap_and_fit(self):
        self.assertEqual(eng.snap(501), 504)
        self.assertEqual(eng.snap(499), 496)
        self.assertEqual(eng.snap(10), 256)
        self.assertEqual(eng.snap(5000), 768)
        self.assertEqual(eng.fit_size(1920, 1080, 512), (512, 288))
        self.assertEqual(eng.fit_size(100, 400, 512), (256, 512))
        w, h = eng.fit_size(333, 777, 768)
        self.assertEqual((w % 8, h % 8), (0, 0))

    def test_effective_steps_never_zero(self):
        self.assertGreaterEqual(int(eng.effective_steps(1, 0.2) * 0.2), 1)
        self.assertEqual(eng.effective_steps(8, 0.9), 8)

    def test_availability_message_lists_missing_packages(self):
        with mock.patch("importlib.util.find_spec", return_value=None):
            ok, reason = eng.available()
        self.assertFalse(ok)
        self.assertIn("torch", reason)
        self.assertIn("requirements-ai.txt", reason)


HAS_HF = __import__("importlib.util").util.find_spec("huggingface_hub") is not None


class TestModels(unittest.TestCase):
    def make_install(self, root, fp16=True, lora=True, drop=None):
        base = os.path.join(root, models.BASE_DIR)
        files = list(models.REQUIRED_BASE) + ["tokenizer/vocab.json", "tokenizer/merges.txt"]
        for sub, names in models.WEIGHT_NAMES.items():
            files.append("%s/%s" % (sub, names[0 if fp16 else 1]))
        for f in files:
            if f == drop:
                continue
            path = os.path.join(base, *f.split("/"))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            open(path, "wb").close()
        if lora:
            os.makedirs(os.path.join(root, models.LORA_DIR), exist_ok=True)
            open(os.path.join(root, models.LORA_DIR, models.LORA_FILE), "wb").close()
        return models.ModelPaths(root)

    def test_complete_and_variant_detection(self):
        with tempfile.TemporaryDirectory() as t:
            p = self.make_install(t)
            self.assertTrue(p.complete())
            self.assertEqual(p.variant, "fp16")
            self.assertTrue(p.has_lora())
        with tempfile.TemporaryDirectory() as t:
            p = self.make_install(t, fp16=False, lora=False)
            self.assertTrue(p.complete())
            self.assertIsNone(p.variant)
            self.assertFalse(p.has_lora())

    def test_new_style_tokenizer_json_is_accepted(self):
        with tempfile.TemporaryDirectory() as t:
            p = self.make_install(t, drop="tokenizer/vocab.json")
            self.assertFalse(p.complete())
            open(os.path.join(p.base, "tokenizer", "tokenizer.json"), "wb").close()
            self.assertTrue(p.complete())

    def test_missing_file_is_reported(self):
        with tempfile.TemporaryDirectory() as t:
            p = self.make_install(t, drop="tokenizer/vocab.json")
            self.assertFalse(p.complete())
            self.assertEqual(p.missing(), ["tokenizer/vocab.json"])

    def test_search_order_prefers_env_then_app_then_user(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            self.make_install(b)
            with mock.patch.dict(os.environ, {"PAINTRAM_MODELS_DIR": a}):
                self.assertEqual(models.candidate_dirs()[0], a)
                self.assertIsNone(models.find_models() if not os.path.isdir(models.candidate_dirs()[1]) else None)
            with mock.patch.dict(os.environ, {"PAINTRAM_MODELS_DIR": b}):
                self.assertEqual(models.find_models().root, b)

    def _fake_snapshot(self, calls):
        def fake_snapshot(repo, local_dir, allow_patterns, tqdm_class):
            calls.append((repo, allow_patterns))
            os.makedirs(local_dir, exist_ok=True)
            if repo == models.BASE_REPO:
                self.make_install(os.path.dirname(local_dir), lora=False)
            elif repo == models.LORA_REPO:
                open(os.path.join(local_dir, models.LORA_FILE), "wb").close()
            elif repo == models.CLIP_REPO:
                # like the real openai/clip-vit-base-patch32: small files plus pytorch_model.bin, no safetensors
                for n in ("config.json", "pytorch_model.bin"):
                    if n in allow_patterns or n == "config.json":
                        open(os.path.join(local_dir, n), "wb").close()
            elif repo == models.CONTROL_REPO:
                for n in ("config.json", models.CONTROL_WEIGHTS[0]):
                    open(os.path.join(local_dir, n), "wb").close()
        return fake_snapshot

    @unittest.skipUnless(HAS_HF, "huggingface_hub not installed")
    def test_download_uses_fp16_patterns_and_verifies(self):
        calls = []
        with tempfile.TemporaryDirectory() as t, mock.patch("huggingface_hub.snapshot_download", self._fake_snapshot(calls)):
            paths = models.download(t)
            self.assertTrue(paths.complete() and paths.has_lora() and paths.has_smart())
            self.assertEqual(paths.control_variant, "fp16")
        self.assertEqual([c[0] for c in calls],
                         [models.BASE_REPO, models.LORA_REPO, models.CLIP_REPO, models.CLIP_REPO, models.CONTROL_REPO])
        self.assertIn("unet/diffusion_pytorch_model.fp16.safetensors", calls[0][1])
        self.assertNotIn("*.ckpt", calls[0][1])
        self.assertEqual(calls[1], (models.LORA_REPO, [models.LORA_FILE]))
        self.assertIn("model.safetensors", calls[2][1])
        self.assertEqual(calls[3][1], ["pytorch_model.bin"])                  # fallback when the repo has no safetensors
        self.assertEqual(calls[4][1], models.CONTROL_PATTERNS)

    @unittest.skipUnless(HAS_HF, "huggingface_hub not installed")
    def test_no_smart_download_skips_clip_and_controlnet(self):
        calls = []
        with tempfile.TemporaryDirectory() as t, mock.patch("huggingface_hub.snapshot_download", self._fake_snapshot(calls)):
            paths = models.download(t, smart=False)
            self.assertTrue(paths.complete() and not paths.has_smart())
        self.assertEqual([c[0] for c in calls], [models.BASE_REPO, models.LORA_REPO])

    @unittest.skipUnless(HAS_HF, "huggingface_hub not installed")
    def test_incomplete_smart_download_is_reported(self):
        calls = []
        fake = self._fake_snapshot(calls)

        def skip_clip(repo, local_dir, allow_patterns, tqdm_class):
            if repo != models.CLIP_REPO:
                fake(repo, local_dir, allow_patterns, tqdm_class)

        with tempfile.TemporaryDirectory() as t, mock.patch("huggingface_hub.snapshot_download", skip_clip):
            with self.assertRaises(RuntimeError) as cm:
                models.download(t)
            self.assertIn(models.CLIP_DIR, str(cm.exception))

    @unittest.skipUnless(HAS_HF, "huggingface_hub not installed")
    def test_download_fails_loudly_when_files_missing(self):
        with tempfile.TemporaryDirectory() as t, mock.patch("huggingface_hub.snapshot_download", lambda *a, **k: None):
            with self.assertRaises(RuntimeError):
                models.download(t)


class TestWindowIntegration(unittest.TestCase):
    def test_ai_menu_and_dock(self):
        with tempfile.TemporaryDirectory() as t:
            win = MainWindow(Document(50, 50), QSettings(os.path.join(t, "s.ini"), QSettings.IniFormat))
            win.show()
            self.assertIn("&AI", [a.text() for a in win.menuBar().actions() if a.menu()] or ["&AI"])
            win.a["ai_inpaint"].trigger()
            self.assertEqual(win.ai_panel.mode.currentText(), "Inpaint selection")
            self.assertTrue(win.ai_dock.isVisible())
            win.close()

    def test_missing_dependencies_disable_generate_with_clear_text(self):
        with tempfile.TemporaryDirectory() as t:
            win = MainWindow(Document(50, 50), QSettings(os.path.join(t, "s.ini"), QSettings.IniFormat))
            with mock.patch("paintapp.ai.engine.available", return_value=(False, "Missing Python packages: torch")):
                win.ai_panel.refresh_state()
            self.assertFalse(win.ai_panel.generate_btn.isEnabled())
            self.assertIn("torch", win.ai_panel.status.text())
            win.close()


if __name__ == "__main__":
    unittest.main()
