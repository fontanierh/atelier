"""Layer-streamed LLM2Vec, retaining both released LoRA adapters in fp32."""

import gc
import json
import time
from pathlib import Path
import torch
from safetensors import safe_open
from transformers import AutoTokenizer, LlamaConfig
from kimodo.model.llm2vec.models.bidirectional_llama import (
    ModifiedLlamaDecoderLayer,
    LlamaRotaryEmbedding,
    LlamaRMSNorm,
)
from kimodo.model.llm2vec.llm2vec import LLM2Vec


class Reader:
    def __init__(self, path):
        self.path = Path(path)
        self.index = json.loads(
            (self.path / "model.safetensors.index.json").read_text()
        )["weight_map"]

    def tensor(self, key):
        with safe_open(self.path / self.index[key], framework="pt", device="cpu") as f:
            return f.get_tensor(key).to(dtype=torch.float32, copy=True)  # release shard mapping

    def rows(self, key, ids):
        with safe_open(self.path / self.index[key], framework="pt", device="cpu") as f:
            sliced = f.get_slice(key)
            return torch.stack([sliced[int(i) : int(i) + 1][0].float() for i in ids])


class Adapter:
    def __init__(self, path):
        self.path = Path(path)
        self.config = json.loads((self.path / "adapter_config.json").read_text())

    def delta(self, key):
        prefix = "base_model.model." + key.removeprefix("model.").removesuffix(
            ".weight"
        )
        with safe_open(
            self.path / "adapter_model.safetensors", framework="pt", device="cpu"
        ) as f:
            akey = prefix + ".lora_A.weight"
            if akey not in f.keys():
                if key.split(".")[-2] in self.config["target_modules"]:
                    raise ValueError("Missing adapter tensor: " + akey)
                return None
            a = f.get_tensor(akey).float()
            b = f.get_tensor(prefix + ".lora_B.weight").float()
            return (b @ a) * (self.config["lora_alpha"] / self.config["r"])


@torch.inference_mode()
def run_layers(config, read_tensor, adapters, hidden, device, progress=print):
    config._attn_implementation = "sdpa"
    ids = torch.arange(hidden.shape[1], device=device).unsqueeze(0)
    rotary = LlamaRotaryEmbedding(config).to(device)
    position_embeddings = rotary(hidden, ids)
    # All prompts are encoded separately and contain no padding; bidirectional attention.
    mask = torch.zeros(
        (1, 1, hidden.shape[1], hidden.shape[1]), device=device, dtype=hidden.dtype
    )
    for i in range(config.num_hidden_layers):
        start = time.monotonic()
        with torch.device("meta"):
            layer = ModifiedLlamaDecoderLayer(config, i)
        state = {}
        for key in layer.state_dict():
            full = "model.layers." + str(i) + "." + key
            value = read_tensor(full).float()
            for adapter in adapters:
                delta = adapter.delta(full)
                if delta is not None:
                    value.add_(delta)
            state[key] = value.to(device)
        layer.load_state_dict(state, assign=True)
        layer.eval()
        del state, value
        hidden = layer(
            hidden,
            attention_mask=mask,
            position_ids=ids,
            position_embeddings=position_embeddings,
            use_cache=False,
        )
        del layer
        gc.collect()
        if device == "mps":
            torch.mps.empty_cache()
        progress(
            f"Encoded layer {i + 1}/{config.num_hidden_layers} ({time.monotonic() - start:.1f}s)"
        )
    norm = LlamaRMSNorm(config.hidden_size, eps=config.rms_norm_eps).to(device)
    norm.weight = torch.nn.Parameter(
        read_tensor("model.norm.weight").to(device), requires_grad=False
    )
    return norm(hidden)


def encode(manifest, prompt, device="mps", progress=print):
    base = Path(manifest["NousResearch/Meta-Llama-3-8B-Instruct"]["path"])
    mntp = Path(manifest["McGill-NLP/LLM2Vec-Meta-Llama-3-8B-Instruct-mntp"]["path"])
    supervised = Path(
        manifest["McGill-NLP/LLM2Vec-Meta-Llama-3-8B-Instruct-mntp-supervised"]["path"]
    )
    config = LlamaConfig.from_pretrained(base)
    tokenizer = AutoTokenizer.from_pretrained(mntp)
    tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "left"

    # Use upstream tokenization, instruction masking and mean pooling unchanged.
    class ConfigHolder(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.config = config

    config._name_or_path = "meta-llama/Meta-Llama-3-8B-Instruct"
    shell = LLM2Vec(
        ConfigHolder(), tokenizer, pooling_mode="mean", skip_instruction=True
    )
    text = shell.prepare_for_tokenization(shell._convert_to_str("", prompt))
    features = shell.tokenize([text])
    reader = Reader(base)
    hidden = (
        reader.rows("model.embed_tokens.weight", features["input_ids"][0])
        .unsqueeze(0)
        .to(device)
    )
    hidden = run_layers(
        config,
        reader.tensor,
        [Adapter(mntp), Adapter(supervised)],
        hidden,
        device,
        progress,
    )
    features = {k: v.to(device) for k, v in features.items()}
    embedding = shell.get_pooling(features, hidden).cpu()
    del hidden, shell
    gc.collect()
    if device == "mps":
        torch.mps.empty_cache()
    return embedding
