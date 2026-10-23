"""Stable Diffusion 1.5 + LCM-LoRA wrapper. torch/diffusers are imported lazily so the editor
runs fine without them; use `available()` to find out."""
import math
import random
from dataclasses import dataclass
from typing import Any, Optional

import numpy as np

MAX_SIDE = 768
MIN_SIDE = 256


class Cancelled(Exception):
    pass


def available():
    """(ok, reason). Checks the libraries without importing torch's heavy parts twice."""
    import importlib.util
    missing = [m for m in ("torch", "diffusers", "transformers", "accelerate", "safetensors", "peft")
               if importlib.util.find_spec(m) is None]
    if missing:
        return False, "Missing Python packages: %s. Run: pip install -r requirements-ai.txt" % ", ".join(missing)
    return True, ""


def snap(value, lo=MIN_SIDE, hi=MAX_SIDE):
    """Round to a multiple of 8 inside [lo, hi] (what the VAE needs)."""
    return int(min(hi, max(lo, round(value / 8.0) * 8)))


def fit_size(width, height, longest=512):
    """Size with the aspect of width x height whose longest side is ~`longest`, multiples of 8."""
    scale = longest / float(max(width, height))
    return snap(width * scale), snap(height * scale)


@dataclass
class Job:
    mode: str                       # "txt2img" | "img2img" | "inpaint"
    prompt: str
    negative: str = ""
    width: int = 512
    height: int = 512
    steps: int = 5
    guidance: float = 1.5
    strength: float = 0.65
    seed: Optional[int] = None
    image: Any = None               # PIL RGB, for img2img / inpaint
    mask: Any = None                # PIL L, 255 = repaint, for inpaint


def random_seed():
    return random.randrange(0, 2 ** 31)


def effective_steps(steps, strength):
    """img2img/inpaint run only int(steps*strength) steps; make sure that is at least 1."""
    return max(steps, int(math.ceil(1.0 / max(strength, 0.05))))


class Engine:
    def __init__(self, paths, device=None):
        self.paths = paths
        self.device = device
        self._pipes = None
        self.info = ""

    @property
    def loaded(self):
        return self._pipes is not None

    def load(self, status=None):
        if self.loaded:
            return
        say = status or (lambda _t: None)
        import torch
        from diffusers import (LCMScheduler, StableDiffusionImg2ImgPipeline, StableDiffusionInpaintPipeline,
                               StableDiffusionPipeline)

        if self.device is None:
            if torch.cuda.is_available():
                self.device = "cuda"
            elif getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
                self.device = "mps"
            else:
                self.device = "cpu"
        half = self.device == "cuda"
        dtype = torch.float16 if half else torch.float32
        say("Loading model onto %s…" % self.device)
        pipe = StableDiffusionPipeline.from_pretrained(
            self.paths.base, torch_dtype=dtype, variant=self.paths.variant,
            safety_checker=None, requires_safety_checker=False)
        pipe.scheduler = LCMScheduler.from_config(pipe.scheduler.config)
        if self.paths.has_lora():
            say("Applying LCM-LoRA…")
            pipe.load_lora_weights(self.paths.lora_dir, weight_name=self._lora_name())
            pipe.fuse_lora()
        pipe.set_progress_bar_config(disable=True)
        self.info = self.device
        if self.device == "cuda":
            vram = torch.cuda.get_device_properties(0).total_memory / 2 ** 30
            if vram < 5.5:                      # small cards: stream sub-models through the GPU
                pipe.enable_model_cpu_offload()
                pipe.enable_attention_slicing()
                self.info += " (low-VRAM mode, %.1f GB)" % vram
            else:
                pipe.to("cuda")
                self.info += " (%.0f GB)" % vram
            pipe.vae.enable_tiling()
        else:
            pipe.to(self.device)
            pipe.enable_attention_slicing()
        comps = pipe.components
        self._pipes = {
            "txt2img": pipe,
            "img2img": StableDiffusionImg2ImgPipeline(**comps),
            "inpaint": StableDiffusionInpaintPipeline(**comps),
        }
        for p in self._pipes.values():
            p.set_progress_bar_config(disable=True)
        say("Model ready (%s)" % self.info)

    def _lora_name(self):
        from .models import LORA_FILE
        return LORA_FILE

    def unload(self):
        self._pipes = None
        try:
            import gc
            import torch
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:                      # best effort: torch may be missing or half torn down
            pass

    def run(self, job, progress=None, cancelled=None):
        """Generate one PIL image. `progress(step, total)`; `cancelled()` aborts between steps."""
        import torch
        if not self.loaded:
            self.load()
        pipe = self._pipes[job.mode]
        seed = job.seed if job.seed is not None else random_seed()
        gen_device = "cpu" if self.device in ("mps",) else self.device
        generator = torch.Generator(gen_device).manual_seed(int(seed))
        steps = job.steps if job.mode == "txt2img" else effective_steps(job.steps, job.strength)
        done_steps = [0]

        def on_step(_pipe, step, _t, kwargs):
            if cancelled and cancelled():
                raise Cancelled()
            done_steps[0] = step + 1
            if progress:
                progress(step + 1, steps if job.mode == "txt2img" else max(1, int(steps * job.strength)))
            return kwargs

        common = dict(prompt=job.prompt, negative_prompt=job.negative or None, num_inference_steps=steps,
                      guidance_scale=job.guidance, generator=generator, callback_on_step_end=on_step)
        if job.mode == "txt2img":
            out = pipe(width=job.width, height=job.height, **common)
        elif job.mode == "img2img":
            out = pipe(image=job.image, strength=job.strength, **common)
        elif job.mode == "inpaint":
            out = pipe(image=job.image, mask_image=job.mask, strength=max(job.strength, 0.8),
                       width=job.image.width, height=job.image.height, **common)
        else:
            raise ValueError("unknown mode %r" % job.mode)
        return out.images[0], int(seed)


# ------------------------------------------------------------------ QImage <-> PIL

def qimage_to_pil(img):
    from PIL import Image
    from PyQt5.QtGui import QImage
    from .. import imageutil
    arr = imageutil.to_array(img.convertToFormat(QImage.Format_ARGB32))
    rgb = np.ascontiguousarray(arr[..., 2::-1])
    # flatten transparency onto white so empty areas do not become black
    alpha = arr[..., 3:4].astype(np.float32) / 255.0
    rgb = (rgb * alpha + 255 * (1 - alpha)).astype(np.uint8)
    return Image.fromarray(rgb, "RGB")


def pil_to_qimage(pil):
    from PyQt5.QtGui import QImage
    rgba = np.ascontiguousarray(np.asarray(pil.convert("RGBA")))
    h, w = rgba.shape[:2]
    return QImage(rgba.data, w, h, w * 4, QImage.Format_RGBA8888).convertToFormat(
        QImage.Format_ARGB32_Premultiplied)


def mask_to_pil(qimg):
    """Alpha8/grayscale QImage -> PIL 'L'."""
    from PIL import Image
    from PyQt5.QtGui import QImage
    g = qimg.convertToFormat(QImage.Format_Grayscale8)
    w, h = g.width(), g.height()
    ptr = g.constBits()
    ptr.setsize(g.sizeInBytes())
    arr = np.frombuffer(ptr, np.uint8).reshape(h, g.bytesPerLine())[:, :w].copy()
    return Image.fromarray(arr, "L")
