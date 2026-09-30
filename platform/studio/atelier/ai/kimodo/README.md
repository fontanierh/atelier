# Headless Kimodo

This adapter runs the pinned [NVIDIA Kimodo](https://github.com/nv-tlabs/kimodo) SOMA RP v1.1 checkpoint locally.
It needs no browser, hosted inference endpoint, API key, or CUDA device. Installation downloads about 17 GB of
weights into a caller-selected ignored build directory. Upstream code and weights retain their respective licences;
none are redistributed in this repository.

The released LLM2Vec encoder is an 8B Llama model with MNTP and supervised LoRA adapters. Loading it whole would
exceed Atelier's 10 GiB memory guard. `streamed_text.py` reads only the requested token-embedding rows, then loads
and releases one decoder layer at a time. Both adapters are applied in fp32, with explicit bidirectional attention;
upstream tokenization and mean pooling are reused. This is a different runtime/precision from the default bf16
CUDA encoder, not a quantized or smaller substitute. A tiny complete PEFT model tests the streamed result and the
published adapter naming convention. Missing expected adapter weights fail loudly.

The pinned base weights come from `NousResearch/Meta-Llama-3-8B-Instruct`, a public distribution of the required
Llama 3 base; the two adapters come from McGill NLP. This avoids requiring an authenticated download from Meta's
Hugging Face repository. The Llama licence still applies. All four weight revisions and the upstream revision are
recorded in provenance. Embeddings are cached by sanitized prompt, weight revisions and encoder format.

Install from an Atelier checkout into an ignored build directory:

```sh
uv run python -m atelier.ai.kimodo.install --root build/motion-experiment
```

Run the following with the installed environment's Python, inside a memory-guarded process:

```python
from atelier.ai.kimodo import Engine

engine = Engine("build/motion-experiment", device="cpu")
output, provenance = engine.generate(
    "A person does a backflip.", seed=99, guidance=2, steps=100, frames=90,
)
# output: raw SOMA joint rotations, positions, contacts and root trajectory.
```

Run inference under `atelier.safety.guarded`, including the layer-streamed encoder. On the tested M3 Pro,
text encoding uses MPS and diffusion uses CPU: the upstream diffusion buffers include float64, which PyTorch MPS
cannot hold. CUDA can be selected for diffusion on another host; the streamed text encoder also works on CPU.
Native MotionCorrection is omitted because its x86 SIMD build fails on ARM. Every take records
`post_processing: false`; no hidden contact cleanup occurs.

`retarget_motion` takes an explicit target hierarchy, anatomical map, feet and axis transform. It folds omitted
source joints, scales root travel by leg height and applies one constant floor placement offset. It transfers
canonical SOMA rotation deltas, preserving a complete hip rotation. SOMA's BVH bone-axis offsets are a different
convention and are deliberately excluded. Target-specific mappings belong to the game adapter.

Callers own character export, anatomical mappings, the headless command, the UI and acceptance decisions.
`rig` supplies `names`, root-first `parents` and Y-up canonical world rest `positions`; `joint_map` names the
corresponding SOMA joints. `foot_names` controls leg-height scaling and floor placement; `canonical_to_gltf`
is an explicit xyzw axis quaternion for the shared [browser retargeter](../../../../web/motion/README.md).
Raw output, per-take provenance and captures belong in the caller's ignored build directory.

The retarget tests run without loading model weights. Streamed/full PEFT parity tests require the isolated
environment installed above:

```sh
build/motion-experiment/venv/bin/python -m unittest discover -s platform/studio/tests -p 'test_kimodo.py'
```
