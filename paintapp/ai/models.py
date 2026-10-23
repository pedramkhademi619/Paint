"""Where the AI model lives on disk and how to fetch it. Qt-free and torch-free."""
import os
import sys

BASE_REPO = "stable-diffusion-v1-5/stable-diffusion-v1-5"
LORA_REPO = "latent-consistency/lcm-lora-sdv1-5"
BASE_DIR = "sd15"
LORA_DIR = "lcm-lora-sdv1-5"
LORA_FILE = "pytorch_lora_weights.safetensors"

# fp16 weights only (~2.1 GB); the repo also carries fp32 copies, a safety checker and .ckpt files we skip
BASE_PATTERNS = [
    "model_index.json", "scheduler/*.json", "tokenizer/*",
    "text_encoder/config.json", "text_encoder/model.fp16.safetensors",
    "unet/config.json", "unet/diffusion_pytorch_model.fp16.safetensors",
    "vae/config.json", "vae/diffusion_pytorch_model.fp16.safetensors",
]
REQUIRED_BASE = [
    "model_index.json", "scheduler/scheduler_config.json", "tokenizer/vocab.json", "tokenizer/merges.txt",
    "text_encoder/config.json", "unet/config.json", "vae/config.json",
]
WEIGHT_NAMES = {
    "text_encoder": ("model.fp16.safetensors", "model.safetensors"),
    "unet": ("diffusion_pytorch_model.fp16.safetensors", "diffusion_pytorch_model.safetensors"),
    "vae": ("diffusion_pytorch_model.fp16.safetensors", "diffusion_pytorch_model.safetensors"),
}


class ModelPaths:
    def __init__(self, root):
        self.root = root
        self.base = os.path.join(root, BASE_DIR)
        self.lora_dir = os.path.join(root, LORA_DIR)
        self.lora_file = os.path.join(self.lora_dir, LORA_FILE)

    @property
    def variant(self):
        """'fp16' when the UNet ships as an fp16 file, else None (plain names)."""
        fp16 = os.path.join(self.base, "unet", WEIGHT_NAMES["unet"][0])
        return "fp16" if os.path.isfile(fp16) else None

    def has_lora(self):
        return os.path.isfile(self.lora_file)

    def missing(self):
        """Relative names of required files that are not on disk (empty list = complete)."""
        gone = [p for p in REQUIRED_BASE if not os.path.isfile(os.path.join(self.base, *p.split("/")))]
        for sub, names in WEIGHT_NAMES.items():
            if not any(os.path.isfile(os.path.join(self.base, sub, n)) for n in names):
                gone.append("%s/%s" % (sub, names[0]))
        return gone

    def complete(self):
        return not self.missing()


def app_root():
    """Folder holding the program: the install dir when frozen, the repo checkout otherwise."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def user_models_dir():
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~\\AppData\\Local")
        return os.path.join(base, "Paint", "models")
    base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(base, "paint", "models")


def candidate_dirs():
    """Search order: $PAINT_MODELS_DIR, models/ next to the program (installer), then the per-user folder."""
    dirs = []
    if os.environ.get("PAINT_MODELS_DIR"):
        dirs.append(os.environ["PAINT_MODELS_DIR"])
    dirs += [os.path.join(app_root(), "models"), user_models_dir()]
    return dirs


def find_models():
    """ModelPaths of the first complete install, or None."""
    for d in candidate_dirs():
        paths = ModelPaths(d)
        if paths.complete():
            return paths
    return None


def download(dest=None, progress=None):
    """Download the model into `dest` (default: per-user folder). `progress(text, done, total)` is optional.

    Needs `huggingface_hub` and network access to huggingface.co. Returns the ModelPaths.
    """
    from huggingface_hub import snapshot_download
    from tqdm.auto import tqdm

    dest = dest or os.environ.get("PAINT_MODELS_DIR") or user_models_dir()
    paths = ModelPaths(dest)

    class Bar(tqdm):
        def update(self, n=1):
            r = super().update(n)
            if progress:
                progress(self.desc or "", self.n, self.total or 0)
            return r

    os.makedirs(paths.base, exist_ok=True)
    snapshot_download(BASE_REPO, local_dir=paths.base, allow_patterns=BASE_PATTERNS, tqdm_class=Bar)
    snapshot_download(LORA_REPO, local_dir=paths.lora_dir, allow_patterns=[LORA_FILE], tqdm_class=Bar)
    gone = paths.missing()
    if gone or not paths.has_lora():
        raise RuntimeError("Download finished but files are missing: %s" % ", ".join(gone or [LORA_FILE]))
    return paths


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(prog="python -m paintapp.ai.models", description="Install the local AI model")
    ap.add_argument("action", choices=["download", "status"])
    ap.add_argument("--dest", help="target folder (default: %s)" % user_models_dir())
    args = ap.parse_args(argv)
    if args.action == "status":
        found = find_models()
        print("installed at %s" % found.root if found else "not installed")
        return 0 if found else 1

    def show(desc, done, total):
        if total:
            print("\r%-40s %6.1f / %6.1f MB" % (desc[:40], done / 1e6, total / 1e6), end="", flush=True)

    paths = download(args.dest, show)
    print("\nInstalled to", paths.root)
    return 0


if __name__ == "__main__":
    sys.exit(main())
