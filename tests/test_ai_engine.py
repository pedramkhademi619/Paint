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


def build_tiny_install(root, with_lora=False):
    """Write a miniature but structurally real SD1.5 install (and optionally a real LoRA file) under root."""
    import json
    import torch
    from diffusers import AutoencoderKL, DDIMScheduler, StableDiffusionPipeline, UNet2DConditionModel
    from transformers import CLIPTextConfig, CLIPTextModel, CLIPTokenizer
    from transformers.models.clip.tokenization_clip import bytes_to_unicode

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
    tokenizer = CLIPTokenizer(os.path.join(tokdir, "vocab.json"), os.path.join(tokdir, "merges.txt"))
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
        from diffusers.utils import get_peft_model_state_dict
        from peft import LoraConfig
        lora_unet = UNet2DConditionModel.from_pretrained(os.path.join(paths.base, "unet"))
        lora_unet.add_adapter(LoraConfig(r=2, lora_alpha=2, init_lora_weights="gaussian",
                                         target_modules=["to_q", "to_k", "to_v", "to_out.0"]))
        os.makedirs(paths.lora_dir)
        StableDiffusionPipeline.save_lora_weights(
            paths.lora_dir, unet_lora_layers=get_peft_model_state_dict(lora_unet), weight_name=models.LORA_FILE)
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
        job = eng.Job("txt2img", "a cat", width=256, height=256, steps=2, guidance=1.0, seed=7)
        a, seed = self.engine.run(job)
        b, _ = self.engine.run(job)
        c, _ = self.engine.run(eng.Job("txt2img", "a cat", width=256, height=256, steps=2, guidance=1.0, seed=8))
        self.assertEqual(a.size, (256, 256))
        self.assertEqual(seed, 7)
        self.assertEqual(list(a.getdata())[:50], list(b.getdata())[:50])
        self.assertNotEqual(list(a.getdata()), list(c.getdata()))

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

    def test_img2img_low_strength_stays_close_to_input(self):
        import numpy as np
        src = img(color=(200, 30, 30))
        low, _ = self.engine.run(eng.Job("img2img", "x", steps=4, guidance=1.0, strength=0.15, seed=3, image=src))
        high, _ = self.engine.run(eng.Job("img2img", "x", steps=4, guidance=1.0, strength=1.0, seed=3, image=src))
        d_low = np.abs(np.asarray(low, float) - np.asarray(src, float)).mean()
        d_high = np.abs(np.asarray(high, float) - np.asarray(src, float)).mean()
        self.assertLess(d_low, d_high)

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
