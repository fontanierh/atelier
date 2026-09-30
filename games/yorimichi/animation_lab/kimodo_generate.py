"""Generate and save a fox take headlessly, with no browser or HTTP server."""

import argparse
from pathlib import Path
import time
from server import Lab, REPO


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPO / "build/yorimichi/kimodo")
    parser.add_argument("--prompt", default="A person does a backflip.")
    parser.add_argument("--title", default="Backflip")
    parser.add_argument("--seed", type=int, default=99)
    parser.add_argument("--steps", type=int, default=100)
    parser.add_argument("--guidance", type=float, default=2.0)
    parser.add_argument("--duration", type=float, default=3.0)
    parser.add_argument("--device", choices=["cpu", "cuda"], default="cpu")
    args = parser.parse_args()
    lab = Lab(args.root, warm=False, generator="kimodo")
    lab.load(args.device)
    job = lab.create(
        {
            "prompt": args.prompt,
            "title": args.title,
            "seed": args.seed,
            "steps": args.steps,
            "guidance": args.guidance,
            "duration": args.duration,
            "guided_sprint": False,
            "reference_clip": None,
            "category": "Movement",
        }
    )
    while lab.active:
        time.sleep(1)
    result = lab.jobs[job["id"]]
    if result["status"] != "complete":
        raise SystemExit("Kimodo generation failed; see the guarded log")
    print(f"Saved {args.root / 'results' / job['id']}", flush=True)


if __name__ == "__main__":
    main()
