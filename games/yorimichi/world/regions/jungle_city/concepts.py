"""Create the ledgered Sunburst reference set for the unplaced Jungle City proposal."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from atelier.ai.images import MODEL, QUALITY, compact, paint


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
OUT = HERE / "assets" / "concepts"
ORIGINALS = REPO / "build" / "yorimichi" / "jungle-city" / "concepts" / "originals"
STYLE_REFS = [
    REPO / "games/yorimichi/world/map/painted/world_map.png",
    REPO / "games/yorimichi/assets/southwest/concepts/aerial.jpg",
]
SIZE = "1536x1024"

STYLE = """Use the visual language of Image 1 and the aerial character of Image 2:
hand-painted stylised game concept art, warm clear light, readable silhouettes,
rich but restrained colour, subtle paper/canvas texture, cinematic depth, and
architecture that feels inhabitable rather than archaeological display.

The place is Jungle City in Yorimichi: a complete city about 650 by 520 metres,
in the middle of dense tropical jungle, inspired by Angkor in Cambodia without
copying a specific monument. Warm sandstone, red laterite, mossy steps, dark
teal-green roofs, broad lotus reservoirs, monumental axial causeways, naga
balustrades, stepped temple-mountain silhouettes, carved gates, stilt houses,
market roofs, stone bridges, kapok and fig trees, palms, vines, and roots
spilling over old walls. The city must read as a coherent urban landscape with
clear districts, circulation, water management, and jungle pressure at its
edges. No modern buildings, vehicles, signage, text, labels, pins, frames,
copyrighted characters, or photoreal people."""

VIEWS = {
    "master-aerial": """A complete north-up aerial master view. Show the whole city and enough surrounding jungle to understand its boundary: central five-tier temple mountain, rectangular moat and axial gates, inner ceremonial precinct, eastern market terraces, western baray reservoir, canals, bridges, smaller shrine courts, dense forest wall, distant hazy mountains. The composition must clearly match a Belmonte-scale district and read as a navigable map area.""",
    "dusk-aerial": """The same complete city and layout at humid golden dusk. Keep the geography and landmarks recognisably identical to a master plan: temple mountain at centre, long east-west causeway, moat, baray, market district, gates and forest boundary. Warm lantern points gather along processional routes while the jungle falls into cool green shadow.""",
    "east-causeway": """Eye-level approach along the east causeway toward the main gate and temple mountain. A wide sandstone road crosses water on multiple shallow bridges, with naga balustrades, worn guardian figures, market roofs glimpsed behind trees, and the stepped sanctuary rising above the canopy. Strong foreground, middle-distance gate, landmark silhouette in the distance.""",
    "main-gate": """Three-quarter view of the eastern city gate from outside the moat. A massive laterite wall, carved sandstone gatehouse with three deep passages, stepped Khmer-inspired roof profile, lotus finials, watch galleries, naga stair rails, flowering trees and roots. People-scale lanterns and small shrines make the monumental size clear.""",
    "temple-mountain": """Close architectural view of the central temple mountain from its southwest corner. Five broad stepped terraces, steep central stair, galleries, corner towers, lotus-bud spires, worn sandstone, moss and vines, banners and small lanterns. The geometry must be crisp enough to model from: massing, stairs, roof profiles, tower rhythm and terrace proportions must be unmistakable.""",
    "market-terraces": """A lively eastern market district between the inner wall and the gate. Long open timber-and-thatch roofs, stone terraces, stilt houses over a canal, shaded courtyards, cloth awnings, baskets, lanterns, bridges, and temple towers visible above the roofs. Keep architecture modular and readable, with no modern retail language.""",
    "baray-reservoir": """The western baray and garden district: a large rectangular reservoir with stepped stone ghats, lotus beds, small island shrines, sluice channels, shaded promenades, palms and enormous fig trees. Show how water connects to the city moat and supports the urban fabric.""",
    "jungle-neighborhood": """A residential and shrine neighborhood inside the jungle edge. Smaller sandstone and timber pavilions, tiled courtyards, footpaths, carved boundary stones, footbridges over canals, dense kapok, fig, palm and bamboo, roots over ruins. This view should show the city is lived-in beyond the monumental centre.""",
    "stone-bridges": """A modelling reference for a major stone bridge and canal crossing. Show the arch/span construction, stepped approaches, carved parapets, naga terminals, worn paving, sluice gates, lotus water, and relationship to walls and market roofs. Orthographic-feeling three-quarter composition with strong dimension clarity.""",
    "material-studies": """A clean concept sheet-like scene containing large readable examples of the proposal materials in use: warm carved sandstone, red laterite blockwork, mossy stair stone, dark green roof tile, aged timber, woven thatch, teal reservoir water, jungle ground, flowering canopy, and orange lantern light. Keep a single coherent environment and avoid text callouts.""",
    "night-processional": """The central east-west ceremonial axis at night. Hundreds of small warm lanterns trace the causeways and terraces, the temple mountain is a calm dark silhouette with selective warm windows and braziers, reservoirs reflect the sky, and blue-green jungle frames the route. Same city layout and landmarks; cinematic but still readable for exploration.""",
    "play-scale-check": """A wide human-scale view from a raised market terrace looking toward the temple mountain. Show ordinary doors, stairs, railings, bridge widths, market stalls and tree trunks at believable walking scale, then the monumental gate and sanctuary beyond. This image is specifically for checking that the full city feels like a game area similar in extent and density to Belmonte.""",
}


def existing_record(slug: str) -> dict | None:
    path = OUT / f"{slug}.provenance.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())


def make(slug: str, prompt: str) -> None:
    target = ORIGINALS / f"{slug}.png"
    record = OUT / f"{slug}.provenance.json"
    prior = existing_record(slug)
    if prior is not None:
        print(f"SKIP {slug}: ledger record exists with status {prior.get('status')}", flush=True)
        return
    full_prompt = f"{STYLE}\n\nVIEW: {prompt}\n\nNo text or labels anywhere in the image."
    print(f"SUBMIT {slug}: {MODEL} {QUALITY} {SIZE}", flush=True)
    paint(
        target,
        full_prompt,
        SIZE,
        STYLE_REFS,
        record=record,
        metadata={
            "stage": "jungle-city-concept",
            "view": slug,
            "prompt": full_prompt,
            "reference_files": [str(p.relative_to(REPO)) for p in STYLE_REFS],
            "execution": str(Path(__file__).resolve().relative_to(REPO)),
        },
    )
    compact(target, OUT / f"{slug}.jpg", 1536, 90, "4:2:0")
    print(f"DONE {slug}: {target.name}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("views", nargs="*", help="only these view slugs")
    args = parser.parse_args()
    selected = list(VIEWS) if not args.views else args.views
    unknown = [name for name in selected if name not in VIEWS]
    if unknown:
        parser.error("unknown views: " + ", ".join(unknown))
    OUT.mkdir(parents=True, exist_ok=True)
    ORIGINALS.mkdir(parents=True, exist_ok=True)
    for ref in STYLE_REFS:
        if not ref.is_file():
            raise SystemExit(f"missing style reference: {ref}")
    print(f"Jungle City concepts: {len(selected)} ledgered Sunburst calls", flush=True)
    for slug in selected:
        make(slug, VIEWS[slug])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
