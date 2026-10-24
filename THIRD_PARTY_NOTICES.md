# Third-party software and models

Paintram is free software under the GNU GPL v3 or later (see `LICENSE`), copyright (C) 2024-2026
pedramkhademi619. Source code: https://github.com/pedramkhademi619/Paint

It is built on the following components. This is a summary for convenience; the authoritative licence
texts are the ones shipped with, or published by, each project.

## Libraries

| Component | Licence | Project |
|---|---|---|
| PyQt5 and Qt 5 | GPL v3 (PyQt5); LGPL v3 / GPL (Qt) | https://www.riverbankcomputing.com/software/pyqt/ , https://www.qt.io |
| Python | PSF License | https://www.python.org |
| NumPy | BSD 3-Clause | https://numpy.org |
| Pillow | HPND | https://python-pillow.org |
| PyTorch | BSD-style | https://pytorch.org |
| diffusers, transformers, accelerate, peft, safetensors, tokenizers, huggingface_hub | Apache 2.0 | https://github.com/huggingface |
| Cython (build time only) | Apache 2.0 | https://cython.org |
| PyInstaller (build time only) | GPL v2+ with a bootloader exception | https://pyinstaller.org |

Because PyQt5 is licensed under the GPL, Paintram as a whole is distributed under the GPL, and its complete
source code is available at the address above.

## AI models (not covered by the GPL; each has its own licence)

| Model | Used for | Licence |
|---|---|---|
| Stable Diffusion v1.5 (`stable-diffusion-v1-5/stable-diffusion-v1-5`) | image generation | CreativeML OpenRAIL-M |
| LCM-LoRA SD1.5 (`latent-consistency/lcm-lora-sdv1-5`) | few-step generation | OpenRAIL++-M |
| ControlNet v1.1 Scribble (`lllyasviel/control_v11p_sd15_scribble`) | redraw a sketch along its lines | CreativeML OpenRAIL-M |
| CLIP ViT-B/32 (`openai/clip-vit-base-patch32`) | recognising what a sketch shows | MIT |

The OpenRAIL licences allow broad use, including commercial use, but contain use-based restrictions
(for example no illegal, harmful or deceptive uses) that must be passed on to people you give the models to.
Read them before redistributing: https://huggingface.co/spaces/CompVis/stable-diffusion-license

Paintram does **not** include a content (NSFW) safety filter.
