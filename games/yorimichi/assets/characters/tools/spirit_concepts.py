#!/usr/bin/env python3
"""Spirit lore concepts for Yorimichi, painted by gpt-image-2.5-sunburst from recent game stills.

    set -a; source .env; set +a
    uv run python games/yorimichi/assets/characters/tools/spirit_concepts.py [--only slug,slug] [--n 1]

Writes PNGs, prompt files and provenance into output/imagegen/yorimichi-spirits-2026-09-13/ (r01)
or a revision subfolder: r02 (threatening designs after the r01 review), r03 (per-type low-poly
biped model sheets with turnaround and variants).
Reference stills are the 11 September trailer location scouts (current world look) and the
13 September Cairo outfit-r04 capture (current player character).
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[3] / 'world')); import yori  # noqa: E402
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parent))  # Blender's --python does not add the script's folder
from _archive import ROOT, TOOLS  # noqa: E402  (ROOT: the prototype archive holding the revision history)
import argparse, hashlib, os, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# ROOT (the archive) comes from _archive
BASE = ROOT / 'output/imagegen/yorimichi-spirits-2026-09-13'
OUT = BASE  # set per revision in main()
MODEL = 'gpt-image-2.5-sunburst'
QUALITY = 'high'
SIZE = '1536x1024'

SCOUTS = yori.OUT / 'trailer/2026-09-11-location-scouts-1080'
CHAR = ROOT / 'output/imagegen/yorimichi-yellow-boy-2026-09-12/outfit-r04/final-captures'
WORLD_STILLS = [SCOUTS / 'hamlet.png', SCOUTS / 'main-plaza.png', SCOUTS / 'fishing-village.png']
CHAR_STILLS = [CHAR / '01-standing-three-quarter.png', CHAR / '06-running-three-quarter.png']

STYLE = (
    "The attached images are screenshots of our low-poly Unreal game Yorimichi, plus renders of its player "
    "character: painted flat-shaded polygons, chunky timber, cream plaster, slate-blue tiled roofs, an autumn "
    "palette of rust, ochre and pine green, soft daylight, no outlines, no photoreal texture. Paint the concept "
    "in exactly that style, with the same geometric simplicity, as if it were a screenshot of the same game. "
    "Spirits must look like they belong next to that player character: same faceted construction, same scale "
    "language, simple faces with dark rectangular eyes, no gore, nothing frightening. No text, no labels. "
)

CONCEPTS = {
    'lineup': dict(
        stills=WORLD_STILLS[:1] + CHAR_STILLS,
        prompt=STYLE + (
            "A character design sheet on a plain warm cream background: six spirits of the coast standing in a "
            "row at the same scale as the player character, who stands at the left end for scale. From left to "
            "right: a fox spirit wearing a short haori and a white paper mask pushed up on its forehead; a large "
            "crow with a small paper lantern tied to its back; a walking paper umbrella with one eye and a "
            "wooden leg; a small rain spirit shaped like a cloud with two thin legs and a dripping fringe; a "
            "glass fishing float spirit wrapped in rope netting with stubby arms; a leaf-pile spirit, a mound of "
            "autumn leaves with two eyes and twig fingers. Three-quarter view, even lighting, clean readable "
            "silhouettes, each one buildable from simple polygon primitives."
        ),
    ),
    'arrival': dict(
        stills=[SCOUTS / 'fishing-village.png', SCOUTS / 'hamlet.png'] + CHAR_STILLS[:1],
        prompt=STYLE + (
            "Scene: dusk at the fishing village. A long procession of spirits walks in from the sea across the "
            "surface of the water toward the dock, carrying paper lanterns: fox spirits, crows, umbrella spirits, "
            "small cloud spirits, float spirits, a few tall ones at the back. The island with its summit temple "
            "is behind them against an orange sky. The player character and two villagers stand on the dock "
            "watching calmly; this is a yearly event, not an attack. Wide three-quarter view from the shore."
        ),
    ),
    'festival': dict(
        stills=[SCOUTS / 'fishing-village.png', SCOUTS / 'main-plaza.png'] + CHAR_STILLS[:1],
        prompt=STYLE + (
            "Scene: the sending-off festival at night on the island temple terrace. A great bronze bell in a "
            "timber bell house, ribbons, paper lanterns on strings, a big drum, a small fire in a stone bowl. "
            "Below, hundreds of small lanterns float on the dark sea. Spirits drift away from the terrace and "
            "out over the water toward the horizon like leaves blown by the wind, glowing faintly. Several "
            "player characters and villagers stand on the terrace, one about to strike the bell with a log. "
            "Warm lantern light against deep blue night, three-quarter view from the terrace edge."
        ),
    ),
    'havoc': dict(
        stills=[SCOUTS / 'hamlet.png'] + CHAR_STILLS,
        prompt=STYLE + (
            "Scene: the same forest hamlet clearing as the attached screenshot, same camera and daylight, but "
            "the spirits have overstayed and are making trouble. A leaf-pile spirit with eyes rolls after a "
            "resident, crows sit on a roof with stolen laundry and a shoe, a walking umbrella hops across the "
            "path, a fox spirit in a paper mask leans against the well with an armful of vegetables, a cloud "
            "spirit rains on one flower bed only. The player character stands in the middle of the clearing "
            "holding a bamboo pole. Mischief, not horror. Keep the buildings, paths and trees of the screenshot."
        ),
    ),
    'stayed': dict(
        stills=[SCOUTS / 'hamlet.png', SCOUTS / 'main-plaza.png'] + CHAR_STILLS[:1],
        prompt=STYLE + (
            "Character concept: the spirit who refused to go home, the game's main antagonist. A tall, slender, "
            "elegant figure about twice the player character's height, wearing a long coat made of overlapping "
            "autumn leaves in rust and ochre, a wide flat hat, and a calm mask-like face with dark rectangular "
            "eyes. In one hand he holds the broken clapper of a great bell. Leaves drift off his coat and never "
            "reach the ground. He stands on a mountain path among pine trees, the player character small in the "
            "foreground looking up. Dignified and sad rather than menacing. Three-quarter view."
        ),
    ),
}


STYLE_R02 = (
    "The attached images are screenshots of our low-poly Unreal game Yorimichi, plus renders of its player "
    "character: painted flat-shaded polygons, chunky timber, cream plaster, slate-blue tiled roofs, an autumn "
    "palette of rust, ochre and pine green, no outlines, no photoreal texture. Paint the concept in exactly that "
    "style, with the same geometric simplicity, as if it were a screenshot of the same game. The spirits are "
    "enemies in an action game and must read as dangerous: tall, gaunt or heavy, masked or hollow-faced, "
    "antlers, rope, bone-white wood, torn cloth, fog and dead leaves. Not cute, not mascots, not friendly "
    "animals, no big round eyes, no smiles. Menacing and strange, but no blood or gore. No text, no labels. "
)

CONCEPTS_R02 = {
    'lineup': dict(
        stills=WORLD_STILLS[:1] + CHAR_STILLS,
        prompt=STYLE_R02 + (
            "A character design sheet on a plain dark slate background: the player character at the left for "
            "scale, then six enemy spirits in a row, each taller than him. A fox-masked hunter with a long thin "
            "body, a tattered coat and clawed hands; a crow spirit the size of a man with a beaked wooden mask "
            "and a cloak of black feathers; a rope-bound drowned sailor spirit dripping water, face hidden under "
            "a straw hat; a stag-antlered figure made of bone-white driftwood with a hollow chest; a frost "
            "spirit, a jagged pale figure with icicle fingers and no face; a leaf-wraith, a swirling column of "
            "dead leaves around a dark mask. Three-quarter view, even lighting, clean readable silhouettes, "
            "each buildable from simple polygon primitives."
        ),
    ),
    'chasm': dict(
        stills=[SCOUTS / 'hamlet.png', SCOUTS / 'fishing-village.png'] + CHAR_STILLS[:1],
        prompt=STYLE_R02 + (
            "Scene: a remote mountain valley in autumn, pine trees and grey rock. The ground has split open into "
            "a long black chasm, and cold fog pours out of it and spills downhill. Out of the fog climb spirits: "
            "masked, antlered, tall and thin, some carrying dim lanterns, a crow spirit perched on the rim, a "
            "frost spirit at the front leaving white ground behind it. Three player characters stand on a ridge "
            "in the foreground looking down, one holding a bamboo pole, one a lantern on a staff. Late "
            "afternoon light on the ridge, the chasm in shadow. Wide three-quarter view."
        ),
    ),
    'bell_siege': dict(
        stills=[SCOUTS / 'main-plaza.png', SCOUTS / 'hamlet.png'] + CHAR_STILLS,
        prompt=STYLE_R02 + (
            "Scene: night in the city square from the attached screenshot, same buildings and ginkgo trees. A "
            "timber bell tower with a great bronze bell stands in the square. A dozen player characters in "
            "different outfits defend the tower steps with poles, fans, nets and lanterns while spirits press "
            "in from the dark streets: fox-masked hunters, a huge antlered driftwood figure, crow spirits on "
            "the rooftops, leaf-wraiths swirling between the tables. Lanterns knocked over, leaves everywhere, "
            "one warden climbing the tower toward the bell rope. Tense, dramatic, still the same game style."
        ),
    ),
    'frost_town': dict(
        stills=[SCOUTS / 'fishing-village.png', SCOUTS / 'hamlet.png'] + CHAR_STILLS[:1],
        prompt=STYLE_R02 + (
            "Scene: a small mountain town that was lost to the spirits. Slate-blue roofs and timber houses "
            "under a thin crust of frost, dead leaves frozen mid-air, lanterns dark, doors open, a cart tipped "
            "over. Pale frost spirits stand motionless in the street like statues, a tall masked figure sits on "
            "the shrine steps watching. Grey fog, low cold light. The player character enters from the near "
            "end of the street, small, cautious, lantern raised. Three-quarter view down the main street."
        ),
    ),
}


STYLE_R03 = (
    "The attached images are our low-poly game's approved enemy lineup, its player character, and a game "
    "screenshot: painted flat-shaded polygons, no outlines, no photoreal texture, rust, ochre, slate and "
    "bone-white. Paint in exactly that style. This is a production model sheet for a LOW-POLY BIPED enemy: "
    "an ordinary two-arms two-legs humanoid body plan so it can share one skeleton and be auto-rigged; no "
    "extra limbs, no floating parts, no thin strands, no fine detail, no ribbons thinner than a finger. Cloaks, "
    "hair and rope are solid faceted shapes. Fog, leaves or frost effects are drawn separately, not as part "
    "of the body. Under three thousand triangles. Menacing, not cute: masked or hollow-faced, no big round "
    "eyes, no smiles, no blood or gore. Plain flat dark-slate background, even studio lighting, no text. "
    "Layout: top row a turnaround of the base design (front, side, back) standing in a relaxed A-pose; "
    "bottom row two variants of the same type (a common one and a stronger one) plus one attack pose. "
    "The player character stands at the far left of the top row for scale. "
)

CONCEPTS_R03 = {
    'fox_hunter': dict(prompt=STYLE_R03 + (
        "Type: the fox-masked hunter, the fast common raider. Slightly taller than the player, long thin "
        "limbs, hunched, clawed hands, white fox mask with a dark slit, tattered short coat, rope belt, "
        "wooden sandals. Common variant: bare and ragged. Strong variant: layered coat pieces and a second "
        "mask on the back of the head. Attack pose: lunging with claws.")),
    'crow_mask': dict(prompt=STYLE_R03 + (
        "Type: the crow spirit as a humanoid, the scout and thief. Human height, thin, with a long beaked "
        "wooden mask, a solid faceted cloak of black feathers over the shoulders and arms, bird-like "
        "digitigrade legs but only two, clawed feet. Common variant: short cloak. Strong variant: a "
        "longer cloak, bone charms, a hooked pole. Attack pose: swooping strike with the cloak flared.")),
    'drowned': dict(prompt=STYLE_R03 + (
        "Type: the drowned one, a slow heavy bruiser from the sea openings. Broad and stooped, a head and a "
        "half taller than the player, body wrapped in thick rope and rotten net, a wide straw hat hiding the "
        "face, a glass fishing float and an anchor chain as solid props. Common variant: rope only. Strong "
        "variant: barnacle plates and a boat-hook. Attack pose: overhead two-handed swing.")),
    'antlered': dict(prompt=STYLE_R03 + (
        "Type: the antlered warden, the elite of the forest and mountain openings. Twice the player's "
        "height, long straight legs, narrow body of bone-white driftwood under a hooded shroud, a deer skull "
        "mask with solid faceted antlers, a thick rope collar with hanging paper tags as solid slabs. Common "
        "variant: small antlers, plain shroud. Strong variant: wide antlers, a chest cage of driftwood and "
        "a lantern hung inside. Attack pose: one long arm reaching down to grab.")),
    'frost': dict(prompt=STYLE_R03 + (
        "Type: the frost spirit, the slow area-denial enemy from the cold plateau. Human height, jagged "
        "pale blue-white body made of stacked ice facets, no face at all, icicle fingers as solid wedges, "
        "a cracked mantle of frost on the shoulders. Common variant: narrow. Strong variant: broad, with a "
        "frozen mask fragment and frost spreading from its feet. Attack pose: slamming both hands into the "
        "ground.")),
    'lantern_hood': dict(prompt=STYLE_R03 + (
        "Type: the lantern carrier, the support caster that strengthens other spirits. Human height, "
        "fully hooded in a long solid faceted robe of dead-leaf brown with a rope of large wooden beads, a "
        "white box mask with a vertical slit, a paper lantern on a short pole held in one hand. Common "
        "variant: one lantern. Strong variant: two lanterns on a yoke and a taller hood. Attack pose: "
        "lifting the lantern high while the robe flares.")),
    'roster': dict(prompt=(
        "The attached images are our low-poly game's approved enemy lineup, its player character, and a game "
        "screenshot: painted flat-shaded polygons, no outlines, rust, ochre, slate and bone-white. Paint in "
        "exactly that style. A single size-class roster sheet on a plain dark-slate background, no text: the "
        "player character at the far left, then all enemy spirits standing in one row sorted by height. Small: "
        "a fox-masked hunter and a crow-masked scout with a feather cloak. Medium: a hooded lantern carrier "
        "with a box mask and a faceless frost spirit made of ice facets. Large: a drowned one wrapped in rope "
        "and net under a straw hat, and an antlered warden with a deer skull mask twice the player's height. "
        "Boss at the far right: a tall one, four times the player's height, a gaunt hooded giant of bone-white "
        "wood with a wide flat mask and a broken ring of the same metal as a bell hanging from its neck. All "
        "are simple two-legged humanoid bodies buildable at low polygon counts; menacing, no gore, no cute faces."
    )),
}
for _c in CONCEPTS_R03.values():
    _c['stills'] = [BASE / 'r02/lineup.png', CHAR / '01-standing-three-quarter.png', SCOUTS / 'hamlet.png']
# Second pass: the r02 lineup reference pulled every sheet toward fox masks and antlers. These four use the
# r03 roster (all types distinct) as the reference and say explicitly what the type is not.
_ISOLATE = {
    'crow_mask': "This type is the SECOND figure in the attached roster: the crow-masked scout. It has a long "
                 "beaked wooden mask and a feather cloak. It has NO fox mask and NO antlers. ",
    'drowned': "This type is the FIFTH figure in the attached roster: the drowned one under a wide straw hat, "
               "wrapped in rope and net. It has NO fox mask and NO antlers. ",
    'frost': "This type is the FOURTH figure in the attached roster: the frost spirit, made of pale blue-white "
             "ice facets with no face. It has NO fox mask, NO antlers and NO cloth. ",
    'lantern_hood': "This type is the THIRD figure in the attached roster: the hooded lantern carrier with a "
                    "white box mask and a bead rope. It has NO fox mask and NO antlers. ",
}
for _k, _clause in _ISOLATE.items():
    CONCEPTS_R03[_k]['prompt'] = _clause + CONCEPTS_R03[_k]['prompt']
    CONCEPTS_R03[_k]['stills'] = [BASE / 'r03/roster.png', CHAR / '01-standing-three-quarter.png']


def key():
    k = os.environ.get('OPENAI_API_KEY', '')
    if not k:
        sys.exit('OPENAI_API_KEY is not set; source .env first')
    return k


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def gpt_edit(prompt, images, n):
    """n Sunburst edits of the context images (atelier.ai.images). Returns (PNG bytes list, seconds)."""
    from atelier.ai import images as client
    blobs, _, seconds = client.sunburst(prompt, SIZE, images, n, model=MODEL, quality=QUALITY, key=key())
    return blobs, seconds


def run(slug, n):
    c = CONCEPTS[slug]
    stills = [s for s in c['stills'] if s.exists()]
    missing = [str(s) for s in c['stills'] if not s.exists()]
    if missing:
        raise RuntimeError(f'{slug}: missing stills {missing}')
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f'{slug}.prompt.txt').write_text(c['prompt'] + '\n')
    from atelier.ai import ledger

    def paint():
        outs = []
        blobs, secs = gpt_edit(c['prompt'], stills, n)
        for i, b in enumerate(blobs):
            p = OUT / (f'{slug}.png' if n == 1 else f'{slug}-{i + 1}.png')
            p.write_bytes(b)
            outs.append(p.name)
        return dict(elapsed_seconds=secs, outputs={o: sha(OUT / o) for o in outs}, approval='pending')
    # The record is written before the paid call; a failed or uncertain one is never sent again by itself.
    prov, err = ledger.try_once(OUT / f'{slug}.provenance.json', dict(
        stage='lore-concept', concept=slug, requested_model=MODEL, quality=QUALITY, size=SIZE, n=n,
        endpoint='/v1/images/edits', execution='games/yorimichi/assets/characters/tools/spirit_concepts.py',
        prompt_file=f'{slug}.prompt.txt', prompt_sha256=hashlib.sha256(c['prompt'].encode()).hexdigest(),
        reference_files={str(s.relative_to(ROOT)): sha(s) for s in stills}), paint)
    if not prov:   # images of a failed call are not reported as outputs
        return slug, [], None, err
    return slug, list(prov['outputs']), prov['elapsed_seconds'], None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--only', default='')
    ap.add_argument('--n', type=int, default=1)
    ap.add_argument('--rev', default='r01', choices=['r01', 'r02', 'r03'])
    a = ap.parse_args()
    global OUT, CONCEPTS
    if a.rev != 'r01':
        OUT = BASE / a.rev
        CONCEPTS = {'r02': CONCEPTS_R02, 'r03': CONCEPTS_R03}[a.rev]
    slugs = [s for s in a.only.split(',') if s] or list(CONCEPTS)
    key()
    with ThreadPoolExecutor(max_workers=len(slugs)) as ex:
        for slug, outs, secs, err in ex.map(lambda s: run(s, a.n), slugs):
            print(f'{slug}: {"ERROR " + err if err else ", ".join(outs)} ({secs}s)')


if __name__ == '__main__':
    main()
