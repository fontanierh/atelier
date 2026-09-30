"""Headless diffusion with a memory-bounded, cached LLM2Vec encoder."""

import hashlib
import json
import random
import sys
import time
from pathlib import Path


class Engine:
    def __init__(self, root, device="cpu", text_device=None):
        import numpy as np
        import torch

        self.root = Path(root).resolve()
        sys.path.insert(0, str(self.root / "upstream"))
        from kimodo.model.loading import instantiate_from_dict
        from omegaconf import OmegaConf

        self.np, self.torch = np, torch
        self.device = device
        self.text_device = text_device or (
            "mps" if torch.backends.mps.is_available() else "cpu"
        )
        torch.set_num_threads(4)
        manifest = json.loads((self.root / "downloads.json").read_text())
        # Installation records portable paths relative to this isolated build root.
        self.manifest = {
            key: {**entry, "path": str(self.root / entry["path"])}
            for key, entry in manifest.items()
        }
        modelpath = Path(self.manifest["nvidia/Kimodo-SOMA-RP-v1.1"]["path"])
        config = OmegaConf.load(modelpath / "config.yaml")
        config.checkpoint_dir = str(modelpath)
        modelcfg = OmegaConf.to_container(config, resolve=True)
        modelcfg.pop("checkpoint_dir")
        modelcfg["text_encoder"] = None
        self.model = instantiate_from_dict(
            modelcfg, overrides={"device": device}
        ).eval()
        self.model.text_encoder = self.encode
        (self.root / "embeddings").mkdir(exist_ok=True)

    def encode(self, texts):
        from .streamed_text import encode

        torch = self.torch
        values = []
        identity = {key: entry["revision"] for key, entry in self.manifest.items()}
        for text in texts:
            key = hashlib.sha256(
                json.dumps(
                    [text, identity, "llm2vec-stream-fp32-bidirectional-v1"],
                    sort_keys=True,
                ).encode()
            ).hexdigest()
            path = self.root / "embeddings" / (key + ".pt")
            if path.exists():
                embedding = torch.load(path, weights_only=True)
            else:
                embedding = encode(
                    self.manifest, text, self.text_device, self.text_progress
                )
                torch.save(embedding, path)
            if embedding.shape != (1, 4096) or not torch.isfinite(embedding).all():
                raise ValueError("Invalid text embedding")
            values.append(embedding)
        return torch.cat(values).unsqueeze(1), [1] * len(values)

    def generate(self, prompt, seed, guidance=2.0, steps=100, frames=90, progress=None):
        from kimodo.sanitize import sanitize_text

        torch, np = self.torch, self.np
        prompt = sanitize_text(prompt)
        start = time.monotonic()
        layer = 0

        def text_progress(message):
            nonlocal layer
            layer += 1
            print(message, flush=True)
            if progress:
                progress(layer, 32 + steps)

        self.text_progress = text_progress

        def denoising(items):
            for i, item in enumerate(items):
                if progress:
                    progress(32 + i, 32 + steps)
                yield item

        random.seed(seed)
        np.random.seed(seed)
        torch.manual_seed(seed)
        with torch.inference_mode():
            output = self.model(
                prompt,
                frames,
                steps,
                cfg_weight=[guidance, guidance],
                return_numpy=True,
                post_processing=False,
                progress_bar=denoising,
            )
        provenance = {
            "generator": "Kimodo",
            "model": "nvidia/Kimodo-SOMA-RP-v1.1",
            "upstream_revision": "58e781898b3d7e328a676a75d3e338c45dce3ad9",
            "weights": {key: entry["revision"] for key, entry in self.manifest.items()},
            "prompt": prompt,
            "seed": seed,
            "steps": steps,
            "guidance": [guidance, guidance],
            "frames": frames,
            "fps": 30,
            "device": self.device,
            "text_device": self.text_device,
            "text_encoder": "LLM2Vec with MNTP + supervised adapters, streamed fp32, bidirectional attention",
            "post_processing": False,
            "reference_usage": "none",
            "seconds": round(time.monotonic() - start, 3),
        }
        return output, provenance
