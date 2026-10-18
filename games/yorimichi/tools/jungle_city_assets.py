"""Create ledgered Sunburst sources for the unplaced Jungle City asset library.

Object references are isolated for TRELLIS reconstruction. Textures are flat, seamless
surface plates for Blender and the proposal viewer. Every paid call is recorded by
``atelier.ai.images.paint`` before submission and is never retried by this script.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from atelier.ai.images import MODEL, QUALITY, compact, paint
from atelier.review.contact_sheet import sheet


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
LIBRARY = REPO / "games/yorimichi/assets/jungle_city"
REFERENCES = LIBRARY / "references"
TEXTURES = LIBRARY / "textures"
WORK = REPO / "build/yorimichi/jungle-city/asset-sources"
CONCEPTS = REPO / "games/yorimichi/world/regions/jungle_city/assets/concepts"
STYLE_REFS = [
    CONCEPTS / "material-studies.jpg",
    CONCEPTS / "temple-mountain.jpg",
]
SIZE = "1024x1024"


OBJECT_STYLE = """Paint exactly one complete architectural object or plant for 3D reconstruction.
Show the whole silhouette with a clear margin, three-quarter front view from slightly above,
centred and orthographic-feeling, on a completely flat pure black background. Use soft even
light with no cast shadow and no ground plane. Every visible component must be solid and
connected; no floating trim, detached pieces, holes in the main silhouette, people, tools,
text, labels, watermark, frame or surrounding scenery. Keep the hand-painted stylisation of
Images 1 and 2: warm readable colours, matte surfaces, crisp chunky forms, subtle weathering,
moss in creases, and believable Cambodian jungle-city proportions. The object is a reusable
module, not a ruin fragment. Object: """


OBJECTS = {
    "hero_prang": """a monumental Khmer-inspired sandstone temple tower, about 38 metres tall,
with a broad stepped base, steep central stair, colonnaded gallery, three receding carved tiers,
deep false-door porches, repeated pilasters and lotus-bud spire; mossy warm sandstone with a few
flowering vines, but the architecture remains intact and usable""",
    "monumental_gate": """a monumental laterite city gatehouse, about 32 metres wide and 28 metres
tall, with three deep arched passages, battered red block walls, carved sandstone lintels, two
flanking watch galleries, a stepped dark teal roof, lotus finials and small naga stair rails;
the complete gate is symmetrical and structurally clear""",
    "naga_bridge": """a complete short Khmer stone bridge module, about 28 metres long, with a wide
worn sandstone deck, four shallow steps at both ends, heavy carved parapets, and a large seven-head
naga balustrade terminal at each end; the bridge deck and supports form one solid connected object""",
    "reservoir_pavilion": """a square waterside pavilion, about 15 metres wide and 13 metres tall,
with a stepped sandstone ghat base, four corner columns, open timber gallery, deep hipped dark teal
tile roof, upturned finials and a small lotus spire; a complete pavilion suitable beside a reservoir""",
    "market_hall": """a long open Khmer market hall, about 28 metres long and 10 metres tall, with
low stone terraces, two rows of timber posts, deep layered hipped tile roof, carved bargeboards,
small hanging lanterns and open shaded sides; one complete modular hall without counters or people""",
    "guardian_statue": """a monumental standing Khmer guardian warrior statue on a carved sandstone
pedestal, about 9 metres tall, holding a long stone staff with both hands, square serene face, broad
shouldered ceremonial skirt and tall tiered headdress; weathered warm sandstone with moss and small vines""",
    "great_fig_tree": """an enormous tropical fig tree, about 28 metres tall, with a broad buttressed
trunk, twisting aerial roots, spreading asymmetrical branches and several layered dark green canopy
clusters with a few orange-red blossoms; the trunk, roots and canopy are connected into one solid object""",
    "stilt_house": """a Southeast Asian timber stilt house, about 14 metres long and 11 metres tall,
with a low stone footing, twelve timber posts, enclosed plank walls, shaded veranda, two stair flights,
steep dark teal tiled roof and small finials; one complete modular house without furniture or people""",
}


TEXTURE_STYLE = """Create one seamless tileable material texture for a stylised game environment.
Flat straight-on orthographic view, evenly lit, no perspective, no object silhouette, no vignette,
no cast shadow, no highlights, no text, no label, no border, no frame. The pattern must repeat
cleanly when the left edge meets the right and the top meets the bottom. Keep the warm hand-painted
look of Images 1 and 2: restrained colour variation, matte surface, broad readable detail and subtle
wear. Material: """


TEXTURE_OBJECTS = {
    "warm_carved_sandstone": """large warm honey-grey sandstone blocks with shallow Khmer carved bands,
fine chisel marks, chipped corners, pale dust and sparse moss in the joints""",
    "red_laterite_blocks": """irregular deep red-brown laterite masonry blocks with dark pores, warm clay
dust, damp green moss in recesses and softly rounded worn corners""",
    "mossy_stair_stone": """worn pale sandstone paving slabs and stair stone, uneven joints, dark foot polish,
hairline cracks, scattered moss and tiny grass shoots""",
    "dark_teal_roof_tile": """small overlapping Khmer roof tiles in dark blue-green and charcoal, softly
uneven rows, warm edge wear, tiny chips and restrained moss near the lower tile edges""",
    "aged_tropical_timber": """aged tropical timber plains and beams, warm umber grain, dark seams, subtle
adze marks, sun bleaching, small cracks and a little green dampness near the edges""",
    "jungle_canopy": """layered stylised tropical leaves seen from above, deep green, olive and teal foliage,
small pale undersides, scattered orange-red blossoms and no visible branches or sky""",
}


def record_path(folder: Path, slug: str) -> Path:
    return folder / f"{slug}.provenance.json"


def make_object(slug: str, description: str) -> None:
    target = WORK / "references" / f"{slug}.png"
    record = record_path(REFERENCES, slug)
    if record.exists():
        print(f"SKIP {slug}: record exists", flush=True)
        return
    prompt = OBJECT_STYLE + description + "."
    print(f"SUBMIT reference {slug}: {MODEL} {QUALITY} {SIZE}", flush=True)
    paint(
        target,
        prompt,
        SIZE,
        STYLE_REFS,
        record=record,
        metadata={
            "stage": "jungle-city-trellis-reference",
            "asset": slug,
            "prompt": prompt,
            "references": [str(path.relative_to(REPO)) for path in STYLE_REFS],
            "execution": "games/yorimichi/tools/jungle_city_assets.py",
        },
    )
    compact(target, REFERENCES / f"{slug}.jpg", 1024, 92, "4:4:4")
    print(f"DONE reference {slug}", flush=True)


def make_texture(slug: str, description: str) -> None:
    target = WORK / "textures" / f"{slug}.png"
    record = record_path(TEXTURES, slug)
    if record.exists():
        compact_path = TEXTURES / f"{slug}.jpg"
        if target.is_file() and not compact_path.exists():
            compact(target, compact_path, 1024, 94, "4:4:4")
            print(f"COMPACTED {slug}: record exists", flush=True)
        else:
            print(f"SKIP {slug}: record exists", flush=True)
        return
    prompt = TEXTURE_STYLE + description + "."
    print(f"SUBMIT texture {slug}: {MODEL} {QUALITY} {SIZE}", flush=True)
    paint(
        target,
        prompt,
        SIZE,
        STYLE_REFS,
        record=record,
        metadata={
            "stage": "jungle-city-texture",
            "material": slug,
            "prompt": prompt,
            "references": [str(path.relative_to(REPO)) for path in STYLE_REFS],
            "execution": "games/yorimichi/tools/jungle_city_assets.py",
        },
    )
    compact(target, TEXTURES / f"{slug}.jpg", 1024, 94, "4:4:4")
    print(f"DONE texture {slug}", flush=True)


def make_sheet() -> None:
    REFERENCES.mkdir(parents=True, exist_ok=True)
    TEXTURES.mkdir(parents=True, exist_ok=True)
    sheet(
        [(REFERENCES / f"{slug}.jpg", slug) for slug in OBJECTS]
        + [(TEXTURES / f"{slug}.jpg", slug) for slug in TEXTURE_OBJECTS],
        WORK / "jungle-city-asset-sources.jpg",
        384,
        384,
        4,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("references", "textures", "sheet"))
    parser.add_argument("--only", help="comma-separated slugs within the selected stage")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.stage == "sheet":
        make_sheet()
        return 0

    items = OBJECTS if args.stage == "references" else TEXTURE_OBJECTS
    selected = [slug for slug in items if not args.only or slug in args.only.split(",")]
    unknown = set(args.only.split(",")) - set(items) if args.only else set()
    if unknown:
        parser.error("unknown slugs: " + ", ".join(sorted(unknown)))

    if args.dry_run:
        for slug in selected:
            print(f"{slug}: recorded={record_path(REFERENCES if args.stage == 'references' else TEXTURES, slug).exists()}")
        return 0

    for path in (*STYLE_REFS,):
        if not path.is_file():
            raise SystemExit(f"missing style reference: {path}")
    make = make_object if args.stage == "references" else make_texture
    for slug in selected:
        make(slug, items[slug])
    make_sheet()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
