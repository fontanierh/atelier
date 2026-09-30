"""Install headless Kimodo and pinned text weights in an ignored build root."""

import argparse
import json
import os
from pathlib import Path
import subprocess

REVISION = "58e781898b3d7e328a676a75d3e338c45dce3ad9"
MODELS = {
    "NousResearch/Meta-Llama-3-8B-Instruct": "53346005fb0ef11d3b6a83b12c895cca40156b6c",
    "McGill-NLP/LLM2Vec-Meta-Llama-3-8B-Instruct-mntp": "31474e395ada192e8ed1586db6be79fb3b70c9c0",
    "McGill-NLP/LLM2Vec-Meta-Llama-3-8B-Instruct-mntp-supervised": "baa8ebf04a1c2500e61288e7dad65e8ae42601a7",
    "nvidia/Kimodo-SOMA-RP-v1.1": "6c9233af1180b8151e3c4703477104af5dce9dd5",
}


def command(*args, env=None):
    subprocess.run([str(arg) for arg in args], env=env, check=True)


def download_weights(root):
    from huggingface_hub import snapshot_download

    root = Path(root).resolve()
    manifest = {}
    for repo, revision in MODELS.items():
        print(f"Downloading {repo} at {revision}", flush=True)
        path = Path(
            snapshot_download(
                repo,
                revision=revision,
                cache_dir=root / "hub",
                max_workers=2,
                allow_patterns=[
                    "*.safetensors",
                    "*.json",
                    "*.txt",
                    "*.yaml",
                    "*.npy",
                    "LICENSE*",
                    "USE_POLICY*",
                ],
            )
        )
        manifest[repo] = {"revision": revision, "path": str(path.relative_to(root))}
        (root / "downloads.json").write_text(json.dumps(manifest, indent=2) + "\n")


def install(root, atelier_source=None):
    root = Path(root).resolve()
    source = Path(atelier_source or Path(__file__).resolve().parents[5])
    root.mkdir(parents=True, exist_ok=True)
    upstream = root / "upstream"
    if not upstream.exists():
        command("git", "clone", "https://github.com/nv-tlabs/kimodo.git", upstream)
    command("git", "-C", upstream, "checkout", "--detach", REVISION)
    if not (root / "venv").exists():
        command("uv", "venv", root / "venv", "--python", "3.11")
    python = root / "venv/bin/python"
    command(
        "uv",
        "pip",
        "install",
        "--python",
        python,
        "-r",
        Path(__file__).with_name("requirements.txt"),
    )
    # Native MotionCorrection assumes x86 SIMD and does not build on this ARM
    # rig. Sampling works without it; expose that omission in provenance.
    env = {**os.environ, "SKIP_MOTION_CORRECTION_IN_SETUP": "1"}
    command("uv", "pip", "install", "--python", python, "-e", upstream, env=env)
    command("uv", "pip", "install", "--python", python, "--no-deps", "-e", source)
    command(python, "-m", "atelier.ai.kimodo.install", "--root", root, "--weights-only")
    return python


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--weights-only", action="store_true")
    args = parser.parse_args()
    if args.weights_only:
        download_weights(args.root)
    else:
        print(install(args.root))


if __name__ == "__main__":
    main()
