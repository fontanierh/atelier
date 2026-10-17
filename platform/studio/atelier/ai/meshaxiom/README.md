# MeshAxiom on Apple Silicon

Experimental inference adapter for the released MeshAxiom-Base image-to-mesh model. It uses the upstream
architecture and EMA tensors with PyTorch MPS. Vertex and topology models run in separate processes; the
unused point-cloud encoder is omitted from image inference. Model weights and upstream source remain in
an ignored build directory. Ordinary Atelier installation does not install PyTorch or download weights.

The adapter uses BF16 Linear layers, FP32 normalization, CPU FP64 rotary-position tables, query-tiled
attention over all keys, and one CPU nearest-neighbour/PCA calculation per topology request. It preserves
the 20-step DPM++2M sampler, eight coarse vertex candidates, per-level guidance and topology self-conditioning.
Random streams differ from NVIDIA CUDA, so output hashes are not expected to match CUDA Exact.

Install from an Atelier checkout with Python 3.12 and `uv`:

```sh
uv run python -m atelier.ai.meshaxiom.install --root build/meshaxiom
```

Installation downloads approximately 19.66 GiB of checkpoint files and needs at least 30 GiB free disk.
The installer pins source and model revisions and verifies all three SHA256 identities. The isolated
runtime is `build/meshaxiom/venv/bin/python`; base Atelier dependencies stay unchanged. Unreal Engine
and Blender are not needed for inference; Blender is optional for later material authoring. The upstream
code/weight licence assignment is pending; installation retains the DINOv3 licence and upstream notices.
No upstream source or pretrained weights are bundled with this adapter.

Run through the existing machine memory guard, using a fresh report directory and an explicit deadline:

```sh
ATELIER_AGENT=YOUR_BOARD_OWNER nice -n 10 uv run python -m atelier.safety.guarded \
  --report build/meshaxiom/run-01.guard --timeout 1800 --purpose "MeshAxiom image-to-mesh" -- \
  build/meshaxiom/venv/bin/python -u -m atelier.ai.meshaxiom \
  --root build/meshaxiom --image reference.png --output build/meshaxiom/object --face-budget 2000
```

Use one centered object against a black background. The model receives a 512 by 512 RGB image.
Sunburst references must use Atelier's paid-call ledger and include the exact prompt, model and quality.
The model generates geometry; materials and UVs belong to subsequent asset authoring.

The default 8,192-node safety bound fails rather than truncating an oversized result. Higher face budgets
need measured capacity and attention/runtime validation. The published architecture accepts up to 26,000
vertices; this is not a claim that the maximum size has been validated on a 32 GiB laptop. Keep the normal
machine guards. Do not disable memory watermarks or let the operating system swap indiscriminately.

`--stage vertex` and `--stage topology` allow a completed vertex result to be reused in the same output
folder. Each stage writes its own report. A successful geometry run produces `mesh.glb`, `mesh.obj`,
`mesh.json`, `vertices.npz` and `topology.npz`. Face count is a condition, not an enforced output count.
Inspect the prop and report measured memory/runtime before accepting it as a game source asset.

For small CPU equivalence checks after installation, run:

```sh
build/meshaxiom/venv/bin/python -m atelier.ai.meshaxiom.verify
```

This compares tiled masked attention, FP64 rotary tables and the guided DPM++2M sampler against the
pinned upstream definitions. It does not load the pretrained weights or claim image-level CUDA identity.

For a larger experiment **explicitly authorized by the machine owner**, select up to a 16 GiB session
ceiling. This command uses the same actual-child and aggregate guards, normal broker admission and host
headroom, with a matching explicit memory/GPU reservation. It never edits shared capacity profiles.
Run the two stages separately and inspect the first guard receipt before submitting the second:

```sh
ATELIER_AGENT=YOUR_BOARD_OWNER nice -n 10 uv run python -m atelier.ai.meshaxiom.guarded \
  --root build/meshaxiom --image reference.png --output build/meshaxiom/object-16k \
  --stage vertex --face-budget 16000 --max-nodes 12000 --memory-gib 16 --timeout 3600 \
  --report build/meshaxiom/vertex-16k-01.guard
```

After successful vertex completion, repeat with `--stage topology` and a fresh report path. The 16,000-face
condition is approximate: inspect the realized triangle count instead of treating the request as a guarantee.
The released model consumes one image per object; it has no native multiview conditioning interface.

After topology completes, inspect it without loading model weights:

```sh
build/meshaxiom/venv/bin/python -m atelier.ai.meshaxiom.audit \
  --root build/meshaxiom --output build/meshaxiom/object-16k --minimum-faces 15000
```

The report includes raw and canonical usable face counts, boundary/nonmanifold edges, components,
degenerates and slivers. A missed minimum returns exit code 2. Passing the count does not approve
the visual result or facial edge flow; inspect both solid and wireframe views.
