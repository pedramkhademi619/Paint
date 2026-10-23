"""Engine tests against a tiny randomly-initialised Stable Diffusion pipeline built on the fly.

No download needed. Skipped automatically when torch/diffusers/transformers/peft are not installed.
"""
import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from paintapp.ai import engine as eng  # noqa: E402
from paintapp.ai import models  # noqa: E402

OK, WHY = eng.available()


def bytes_to_unicode():
    """GPT-2/CLIP byte -> printable unicode map (same as the tokenizer's own; it moved between releases)."""
    bs = list(range(ord("!"), ord("~") + 1)) + list(range(ord("¡"), ord("¬") + 1)) + list(range(ord("®"), ord("ÿ") + 1))
    cs, n = bs[:], 0
    for b in range(256):
        if b not in bs:
            bs.append(b)
            cs.append(256 + n)
            n += 1
    return dict(zip(bs, map(chr, cs)))


def build_tiny_install(root, with_lora=False):
    """Write a miniature but structurally real SD1.5 install (and optionally a real LoRA file) under root."""
    import json
    import torch
    from diffusers import AutoencoderKL, DDIMScheduler, StableDiffusionPipeline, UNet2DConditionModel
    from transformers import CLIPTextConfig, CLIPTextModel, CLIPTokenizer

    torch.manual_seed(0)
    chars = list(bytes_to_unicode().values())
    vocab = {"<|startoftext|>": 0, "<|endoftext|>": 1}
    for tok in chars + [c + "</w>" for c in chars]:
        vocab.setdefault(tok, len(vocab))
    tokdir = os.path.join(root, "_tok")
    os.makedirs(tokdir)
    with open(os.path.join(tokdir, "vocab.json"), "w") as f:
        json.dump(vocab, f)
    with open(os.path.join(tokdir, "merges.txt"), "w") as f:
        f.write("#version: 0.2\n")
    tokenizer = CLIPTokenizer(os.path.join(tokdir, "vocab.json"), os.path.join(tokdir, "merges.txt"),
                              model_max_length=77)
    text_encoder = CLIPTextModel(CLIPTextConfig(
        hidden_size=16, intermediate_size=32, num_attention_heads=2, num_hidden_layers=1,
        vocab_size=len(vocab), max_position_embeddings=77, projection_dim=16, bos_token_id=0, eos_token_id=1))
    unet = UNet2DConditionModel(
        block_out_channels=(8, 16), layers_per_block=1, sample_size=32, in_channels=4, out_channels=4,
        down_block_types=("DownBlock2D", "CrossAttnDownBlock2D"), up_block_types=("CrossAttnUpBlock2D", "UpBlock2D"),
        cross_attention_dim=16, attention_head_dim=2, norm_num_groups=4)
    vae = AutoencoderKL(
        block_out_channels=[8, 8, 8, 8], in_channels=3, out_channels=3, latent_channels=4, norm_num_groups=4,
        down_block_types=["DownEncoderBlock2D"] * 4, up_block_types=["UpDecoderBlock2D"] * 4)
    pipe = StableDiffusionPipeline(
        vae=vae, text_encoder=text_encoder, tokenizer=tokenizer, unet=unet, scheduler=DDIMScheduler(),
        safety_checker=None, feature_extractor=None, requires_safety_checker=False)
    paths = models.ModelPaths(root)
    pipe.save_pretrained(paths.base)
    if with_lora:
        from diffusers.utils import convert_state_dict_to_diffusers
        from peft import LoraConfig
        from peft.utils import get_peft_model_state_dict
        lora_unet = UNet2DConditionModel.from_pretrained(os.path.join(paths.base, "unet"))
        lora_unet.add_adapter(LoraConfig(r=2, lora_alpha=2, init_lora_weights="gaussian",
                                         target_modules=["to_q", "to_k", "to_v", "to_out.0"]))
        os.makedirs(paths.lora_dir)
        StableDiffusionPipeline.save_lora_weights(
            paths.lora_dir, unet_lora_layers=convert_state_dict_to_diffusers(get_peft_model_state_dict(lora_unet)), weight_name=models.LORA_FILE)
    return paths


def img(size=(256, 256), color=(120, 40, 200)):
    from PIL import Image
    return Image.new("RGB", size, color)


@unittest.skipUnless(OK, WHY)
class TestEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.paths = build_tiny_install(cls.tmp.name)
        cls.engine = eng.Engine(cls.paths, device="cpu")
        cls.engine.load()

    @classmethod
    def tearDownClass(cls):
        cls.engine.unload()
        cls.tmp.cleanup()

    def test_tiny_install_matches_our_layout_check(self):
        self.assertTrue(self.paths.complete(), self.paths.missing())
        self.assertIsNone(self.paths.variant)
        self.assertFalse(self.paths.has_lora())

    def test_txt2img_size_seed_and_determinism(self):
        import numpy as np
        job = eng.Job("txt2img", "a cat", width=256, height=256, steps=2, guidance=1.0, seed=7)
        a, seed = self.engine.run(job)
        b, _ = self.engine.run(job)
        c, _ = self.engine.run(eng.Job("txt2img", "a cat", width=256, height=256, steps=2, guidance=1.0, seed=8))
        self.assertEqual(a.size, (256, 256))
        self.assertEqual(seed, 7)
        self.assertEqual(np.asarray(a).tolist(), np.asarray(b).tolist())
        self.assertNotEqual(np.asarray(a).tolist(), np.asarray(c).tolist())

    def test_non_square_output(self):
        out, _ = self.engine.run(eng.Job("txt2img", "x", width=320, height=256, steps=1, guidance=1.0, seed=1))
        self.assertEqual(out.size, (320, 256))

    def test_guidance_above_one_uses_negative_prompt_path(self):
        out, _ = self.engine.run(eng.Job("txt2img", "x", negative="blurry", width=256, height=256, steps=2,
                                         guidance=2.0, seed=1))
        self.assertEqual(out.size, (256, 256))

    def test_progress_reports_every_step(self):
        seen = []
        self.engine.run(eng.Job("txt2img", "x", width=256, height=256, steps=3, guidance=1.0, seed=1),
                        progress=lambda s, t: seen.append((s, t)))
        self.assertEqual(seen, [(1, 3), (2, 3), (3, 3)])

    def test_cancel_between_steps(self):
        calls = []

        def cancelled():
            calls.append(1)
            return len(calls) >= 2

        with self.assertRaises(eng.Cancelled):
            self.engine.run(eng.Job("txt2img", "x", width=256, height=256, steps=6, guidance=1.0, seed=1),
                            cancelled=cancelled)
        out, _ = self.engine.run(eng.Job("txt2img", "x", width=256, height=256, steps=1, guidance=1.0, seed=1))
        self.assertEqual(out.size, (256, 256))                       # engine still usable afterwards

    def test_img2img_runs_at_least_one_step_even_for_low_strength(self):
        seen = []
        out, _ = self.engine.run(
            eng.Job("img2img", "x", width=256, height=256, steps=1, guidance=1.0, strength=0.2, seed=3, image=img()),
            progress=lambda s, t: seen.append((s, t)))
        self.assertEqual(out.size, (256, 256))
        self.assertTrue(seen)

    def test_img2img_strength_controls_how_many_steps_run(self):
        totals = {}
        for strength in (0.25, 1.0):
            seen = []
            self.engine.run(eng.Job("img2img", "x", steps=8, guidance=1.0, strength=strength, seed=3, image=img()),
                            progress=lambda s, t: seen.append(t))
            totals[strength] = seen[-1]
        self.assertEqual(totals, {0.25: 2, 1.0: 8})

    def test_inpaint_returns_same_size_and_keeps_unmasked_area_close(self):
        import numpy as np
        from PIL import Image
        src = img(color=(10, 200, 10))
        mask = Image.new("L", src.size, 0)
        mask.paste(255, (96, 96, 192, 192))
        out, _ = self.engine.run(eng.Job("inpaint", "x", steps=3, guidance=1.0, strength=1.0, seed=2,
                                         image=src, mask=mask))
        self.assertEqual(out.size, src.size)
        outside = np.abs(np.asarray(out, float)[:64, :64] - np.asarray(src, float)[:64, :64]).mean()
        inside = np.abs(np.asarray(out, float)[110:180, 110:180] - np.asarray(src, float)[110:180, 110:180]).mean()
        self.assertLess(outside, inside)

    def test_unknown_mode(self):
        with self.assertRaises(KeyError):
            self.engine.run(eng.Job("nope", "x"))

    def test_unload_then_reload(self):
        e = eng.Engine(self.paths, device="cpu")
        e.load()
        self.assertTrue(e.loaded)
        e.unload()
        self.assertFalse(e.loaded)
        out, _ = e.run(eng.Job("txt2img", "x", width=256, height=256, steps=1, guidance=1.0, seed=1))
        self.assertTrue(e.loaded)
        self.assertEqual(out.size, (256, 256))
        e.unload()


@unittest.skipUnless(OK, WHY)
class TestLora(unittest.TestCase):
    def test_lora_is_loaded_and_fused(self):
        with tempfile.TemporaryDirectory() as t:
            paths = build_tiny_install(t, with_lora=True)
            self.assertTrue(paths.has_lora())
            e = eng.Engine(paths, device="cpu")
            e.load()
            out, _ = e.run(eng.Job("txt2img", "x", width=256, height=256, steps=2, guidance=1.0, seed=5))
            self.assertEqual(out.size, (256, 256))
            e.unload()


@unittest.skipUnless(OK, WHY)
class TestEndToEnd(unittest.TestCase):
    """Real panel -> thread -> real engine (tiny model on CPU) -> new layer. Nothing mocked except the folder."""

    def test_generate_from_the_ui_with_a_real_engine(self):
        import time
        from unittest import mock
        from PyQt5.QtCore import QSettings, QTimer
        from PyQt5.QtGui import QPainterPath
        from PyQt5.QtWidgets import QApplication
        from paintapp.document import Document
        from paintapp.mainwindow import MainWindow
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as t, mock.patch.dict(os.environ, {"PAINT_MODELS_DIR": os.path.join(t, "m")}):
            build_tiny_install(os.path.join(t, "m"), with_lora=True)
            win = MainWindow(Document(300, 200), QSettings(os.path.join(t, "s.ini"), QSettings.IniFormat))
            win.show()
            panel = win.ai_panel
            panel.refresh_state()
            self.assertTrue(panel.generate_btn.isEnabled(), panel.status.text())
            panel.steps.setValue(2)
            panel.guidance.setValue(1.0)

            def run():
                panel.generate()
                end = time.time() + 120
                while panel.thread is not None and time.time() < end:
                    app.processEvents()
                    time.sleep(0.02)
                app.processEvents()
                self.assertIsNone(panel.thread, "timed out: " + panel.status.text())

            panel.prompt.setPlainText("a boat")
            run()
            self.assertEqual(len(win.doc.layers), 2, panel.status.text())
            self.assertGreater(win.doc.layers[1].image.pixelColor(150, 100).alpha(), 0)
            self.assertTrue(panel.engine.loaded)
            panel.mode.setCurrentText("Image → Image")
            run()
            self.assertEqual(len(win.doc.layers), 3)
            sel = QPainterPath()
            sel.addRect(60, 40, 100, 80)
            win.doc.set_selection(sel)
            panel.mode.setCurrentText("Inpaint selection")
            run()
            self.assertEqual(len(win.doc.layers), 4)
            self.assertEqual(win.doc.layers[3].image.pixelColor(10, 10).alpha(), 0)      # outside selection
            self.assertGreater(win.doc.layers[3].image.pixelColor(100, 80).alpha(), 0)   # inside
            win.doc.undo_stack.undo()
            self.assertEqual(len(win.doc.layers), 3)
            win.doc.undo_stack.setClean()               # otherwise close() waits on the "save changes?" dialog
            win.close()


@unittest.skipUnless(OK, WHY)
class TestConversions(unittest.TestCase):
    def test_qimage_pil_roundtrip_and_white_flattening(self):
        from PyQt5.QtGui import QColor, QImage
        from PyQt5.QtWidgets import QApplication
        QApplication.instance() or QApplication([])
        q = QImage(4, 4, QImage.Format_ARGB32_Premultiplied)
        q.fill(QColor(0, 0, 0, 0))
        self.assertEqual(eng.qimage_to_pil(q).getpixel((1, 1)), (255, 255, 255))
        q.fill(QColor(10, 20, 30))
        self.assertEqual(eng.qimage_to_pil(q).getpixel((1, 1)), (10, 20, 30))
        back = eng.pil_to_qimage(img((3, 2), (1, 2, 3)))
        self.assertEqual((back.width(), back.height(), back.pixelColor(1, 1).name()), (3, 2, "#010203"))


if __name__ == "__main__":
    unittest.main()
