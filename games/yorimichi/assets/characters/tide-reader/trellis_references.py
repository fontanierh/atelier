#!/usr/bin/env python3
"""Paint Kiyo's single-object head and body references for local TRELLIS generation.

    uv run python games/yorimichi/assets/characters/tide-reader/trellis_references.py head
    uv run python games/yorimichi/assets/characters/tide-reader/trellis_references.py body

The approved Sunburst turnaround and construction sheet are edit sources only. Each
paid call produces one isolated front view on pure black, which the TRELLIS wrapper
can matte without confusing multiple views. Calls use gpt-image-2.5-sunburst at high
quality through atelier.ai.ledger and are never retried automatically.
"""
import argparse
import hashlib
import io
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
sys.path.insert(0, str(REPO / "games" / "yorimichi" / "tools"))
sys.path.insert(0, str(REPO / "games" / "yorimichi" / "world"))
import yori  # noqa: E402
from treehouse_art import MODEL, QUALITY, rel, sha, sunburst  # noqa: E402

from atelier.ai.ledger import run_once  # noqa: E402
from atelier.env import require  # noqa: E402

SIZE = "1024x1024"
SOURCE = HERE / "references"
TARGET = HERE / "trellis" / "references"
WORK = yori.OUT / "characters" / "tide-reader" / "trellis" / "references"
ORIGINALS = WORK / "originals"
INPUTS = WORK / "inputs"

HEAD = """The attached images are the approved Sunburst turnaround sheet, construction-detail sheet and face-close crop for Kiyo, the elderly tide-reader of the stylised Japanese game Yorimichi. They are the authority for her identity, age, face, hair, palette and faceted game-model language. Paint one production reference for a separately generated 3D head. This is not a redesign and not a character sheet.

ONE ISOLATED COMPLETE HEAD ONLY, orthographic front view, looking straight at the camera, neutral patient expression. No neck, shoulders, torso, clothing, hat, staff, tide-board, satchel or body. The whole skull and every grey hair silhouette must fit with clear margin. The wide indigo weather hat is intentionally excluded because it remains a separately authored procedural accessory.

IDENTITY: an elderly coastal fisherwoman, about seventy years old, broad angular face with a strong jaw, full weathered cheeks, broad rounded nose, warm sun-browned skin and simple faceted shell earrings. Two dark vertical pill eyes with no whites and no irises, under heavy level lids; a few short crow's-feet creases, relaxed level brows, a small calm closed mouth and two short smile creases. Do not rejuvenate her, change her ethnicity or copy a young skater.

HAIR: silver-grey, thick and sculptural, in a low bun at the nape plus a few broad angular side locks and a short swept fringe. Keep the eyes, brows and mouth fully readable. No thin strands. The bun and locks may extend beyond the skull, but no hair may touch the image edge.

STYLE: soft matte, smoothly modelled low-poly game character from the approved design: large readable facial planes, restrained facet detail, no pores, no individual hair fibres, no photographic texture, no painterly brushwork. Even neutral studio lighting that reveals the face shape.

REGISTRATION: exactly one head, centred on a 1024-square canvas. Crown near y=55, chin near y=900, nose on the vertical centre line, symmetric ears, front of both earrings visible. Clear margin at every side.

BACKGROUND: uniform pure black (#000000), connected to all four borders, with no gradient, vignette, cast shadow or halo. The head and hair are fully opaque and have crisp clean edges. No text, labels, border, multiple views, inset or alternate expression.
"""

BODY = """The attached images are the approved Sunburst turnaround sheet, construction-detail sheet and full-front crop for Kiyo, the elderly tide-reader of the stylised Japanese game Yorimichi. They are the authority for her identity, clothing design, palette and faceted game-model language. Paint one production reference for a separately generated 3D body. This is not a redesign and not a character sheet.

ONE ISOLATED HEADLESS BODY, orthographic front view, symmetric T-pose. No head, hair, face, hat, earrings or neck above the base of the throat. End the bare warm-skin neck in a clean horizontal plug. Both arms are fully straight and horizontal at shoulder height, elbows straight, palms down, fingers relaxed and straight. Both legs are straight with a small natural gap, feet forward, the broad straw soles level on one baseline.

PROPORTIONS: short and broad, about 4.4 heads tall if the missing head were shown, mature elderly fisherwoman. Do not make a slim tall youth.

CLOTHING: deep-indigo layered fisherman's coat reaching mid-thigh, with a short broad shoulder cape over it, an asymmetric crossed front, a cream inner collar and wide sleeves pushed up to the forearms with broad cream cuffs. A muted rust sash wraps the waist twice. Dark blue-grey cropped trousers, cream shin wraps and broad flat straw sandals with simple straps. Keep the garment planes broad and readable. No embroidery, lace, tiny seams, thin cords, wicker microgeometry or texture noise.

REMOVE ALL HELD AND DANGLING PROPS: no tide staff, wooden tide-board, shell counters, satchel, diagonal bag strap, bamboo case, rolled chart, jewellery or other accessory. The coat and body beneath the removed satchel remain plain and complete. Bare warm-brown hands and forearms, five fingers on each hand.

STYLE: soft matte, smoothly modelled low-poly game character in the approved design: clean sculptural planes, restrained facets, no photographic fabric texture and no painterly brushwork. Even neutral studio lighting.

REGISTRATION: exactly one body, centred on a 1024-square canvas. Neck top near y=55, straight hand axes near y=245, crotch near y=520, soles near y=955. Clear margin around every fingertip, elbow, sleeve and sandal.

BACKGROUND: uniform pure black (#000000), connected to all four borders, with no gradient, vignette, floor, cast shadow or halo. The body is fully opaque and has crisp clean edges. No text, labels, border, multiple views, inset or alternate pose.
"""

PROMPTS = {"head": HEAD, "body": BODY}


def crop_inputs():
    """Make single-figure edit inputs; these crops never become inference images."""
    from PIL import Image

    INPUTS.mkdir(parents=True, exist_ok=True)
    sheet = Image.open(SOURCE / "sheet.jpg").convert("RGB")
    face = sheet.crop((8, 555, 320, 950))
    body = sheet.crop((8, 18, 396, 558))
    face.save(INPUTS / "kiyo-face-close.png")
    body.save(INPUTS / "kiyo-body-front.png")
    return {
        "head": [SOURCE / "sheet.jpg", SOURCE / "details.jpg", INPUTS / "kiyo-face-close.png"],
        "body": [SOURCE / "sheet.jpg", SOURCE / "details.jpg", INPUTS / "kiyo-body-front.png"],
    }


def image_facts(png):
    from PIL import Image

    image = Image.open(io.BytesIO(png))
    facts = {
        "dimensions": list(image.size),
        "mode": image.mode,
        "genuine_alpha": False,
    }
    if "A" in image.getbands():
        alpha = image.getchannel("A")
        transparent = sum(1 for value in alpha.getdata() if value < 255)
        facts.update(
            genuine_alpha=transparent > 0,
            transparent_fraction=round(transparent / (image.width * image.height), 4),
        )
    return facts


def paint(name, refs):
    prompt = PROMPTS[name]
    missing = [rel(path) for path in refs if not path.exists()]
    if missing:
        raise SystemExit(f"missing references for {name}: {missing}")

    TARGET.mkdir(parents=True, exist_ok=True)
    ORIGINALS.mkdir(parents=True, exist_ok=True)
    prompt_file = TARGET / f"{name}.prompt.txt"
    prompt_file.write_text(prompt + "\n")
    metadata = dict(
        asset="tide-reader",
        stage="trellis-reference",
        part=name,
        provider="openai",
        requested_model=MODEL,
        quality=QUALITY,
        size=SIZE,
        endpoint="/v1/images/edits",
        execution="games/yorimichi/assets/characters/tide-reader/trellis_references.py",
        prompt_file=f"trellis/references/{name}.prompt.txt",
        prompt_sha256=sha(prompt.encode()),
        reference_files={rel(path): sha(path.read_bytes()) for path in refs},
        crops="Single-figure crops from the approved sheet are edit inputs only; the output is one isolated object.",
        background="pure black for the wrapper's border-connected matte",
        hashes="of the files as the API saw and returned them; the full-size original is kept outside the repository",
    )

    def call():
        started = time.time()
        png, usage = sunburst(prompt, SIZE, refs)
        output = TARGET / f"{name}.png"
        (ORIGINALS / f"{name}.png").write_bytes(png)
        output.write_bytes(png)
        return dict(
            usage=usage,
            outputs={output.name: sha(png)},
            image=image_facts(png),
            elapsed_seconds=round(time.time() - started, 1),
        )

    record = run_once(TARGET / f"{name}.provenance.json", metadata, call)
    print(f'{name}: {record["status"]} ({record.get("elapsed_seconds", "?")} s)', flush=True)
    print(outputs_line(record), flush=True)


def outputs_line(record):
    output = next(iter(record.get("outputs", {"?": "?"})))
    return f"output: {TARGET / output} sha256={record.get('outputs', {}).get(output, '?')}"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("parts", nargs="+", choices=["head", "body", "all"])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    wanted = list(PROMPTS) if "all" in args.parts else args.parts
    refs = crop_inputs()
    for name in wanted:
        if args.dry_run:
            print(f"--- {name}\n{PROMPTS[name]}\n")
            continue
        record = TARGET / f"{name}.provenance.json"
        if record.exists():
            print(f"{name}: already recorded; left untouched", flush=True)
            continue
        require("OPENAI_API_KEY")
        paint(name, refs[name])


if __name__ == "__main__":
    main()
