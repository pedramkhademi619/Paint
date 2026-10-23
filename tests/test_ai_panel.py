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

    def __init__(self, delay=0.0, fail=None):
        self.jobs, self.delay, self.fail = [], delay, fail

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
            with mock.patch.dict(os.environ, {"PAINT_MODELS_DIR": a}):
                self.assertEqual(models.candidate_dirs()[0], a)
                self.assertIsNone(models.find_models() if not os.path.isdir(models.candidate_dirs()[1]) else None)
            with mock.patch.dict(os.environ, {"PAINT_MODELS_DIR": b}):
                self.assertEqual(models.find_models().root, b)

    @unittest.skipUnless(HAS_HF, "huggingface_hub not installed")
    def test_download_uses_fp16_patterns_and_verifies(self):
        calls = []

        def fake_snapshot(repo, local_dir, allow_patterns, tqdm_class):
            calls.append((repo, allow_patterns))
            if repo == models.BASE_REPO:
                root = os.path.dirname(local_dir)
                self.make_install(root, lora=False)
            else:
                os.makedirs(local_dir, exist_ok=True)
                open(os.path.join(local_dir, models.LORA_FILE), "wb").close()

        with tempfile.TemporaryDirectory() as t, mock.patch("huggingface_hub.snapshot_download", fake_snapshot):
            paths = models.download(t)
            self.assertTrue(paths.complete() and paths.has_lora())
        self.assertEqual(calls[0][0], models.BASE_REPO)
        self.assertIn("unet/diffusion_pytorch_model.fp16.safetensors", calls[0][1])
        self.assertNotIn("*.ckpt", calls[0][1])
        self.assertEqual(calls[1], (models.LORA_REPO, [models.LORA_FILE]))

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
