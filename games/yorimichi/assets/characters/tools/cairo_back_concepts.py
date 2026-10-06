#!/usr/bin/env python3
"""Back-view improvement studies for the accepted Cairo (r05) character, painted by Sunburst.

    set +x; set -a; source ./.env; set +a
    uv run python games/yorimichi/assets/characters/tools/cairo_back_concepts.py [--only slug,slug] [--n 1]

Inputs are Cycles captures of the accepted r05 dressed character (no generative source). Each study keeps the
character identical and changes only what the variation says, shown as a two-view panel: true back view on
the left, back three-quarter on the right. Outputs, prompt files and provenance go to
output/imagegen/yorimichi-yellow-boy-2026-09-12/back-concepts-r01/. The API key is read from the environment
inside this process only; it is never placed on a command line. Raw provider replies (without image bytes)
are kept in the ignored api-private/ subfolder.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[3] / 'world')); import yori  # noqa: E402
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parent))  # Blender's --python does not add the script's folder
from _archive import ROOT, TOOLS  # noqa: E402  (ROOT: the prototype archive holding the revision history)
import argparse, hashlib, json, os, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# ROOT (the archive) comes from _archive
CHAR = ROOT / 'output/imagegen/yorimichi-yellow-boy-2026-09-12'
OUT = CHAR / 'back-concepts-r01'
CAPS = CHAR / 'outfit-r05/final-captures'
MODEL = 'gpt-image-2.5-sunburst'
QUALITY = 'high'
SIZE = '1536x1024'
STILLS = [CAPS / '03-standing-back.png', CAPS / '01-standing-three-quarter.png', CAPS / '08-running-back.png']

BASE = (
    "The attached images are renders of our approved game character: image 1 is his current back view, image 2 "
    "his front three-quarter view, image 3 his back while running. This is the exact character; keep his identity "
    "completely: same oversized head, dark chocolate layered hair with the small upward tuft, compact four-head "
    "proportions, warm peach skin, mustard-yellow short-sleeve pullover with the small cream neckline worn over "
    "white long sleeves, deep desaturated blue shorts, cream ankle socks, simple brown slip-on shoes. Same softly "
    "sculpted matte 3D game-character finish, same plain light-gray studio background, same soft even light and "
    "faint contact shadow. The character is seen from behind during most of the game and his back currently "
    "reads as plain, so this is a design study of the back only. "
    "Composition: ONE panel with exactly two full-body figures of him at the same scale, standing relaxed with arms "
    "hanging along the thighs: on the left a true back view (camera directly behind, no face visible), on the right "
    "a back three-quarter view turned so a little of the right cheek shows. Generous margins, nothing cropped, no "
    "text, no labels, no props on the floor, no other characters. "
    "Change ONLY what the following variation says; do not alter the face, hair colour, body, colours of the "
    "existing clothes or the shoes. "
)

CONCEPTS = {
    'rucksack': (
        "Variation: add a small worn canvas rucksack in olive-khaki with a rolled-top flap, one cream leather "
        "buckle strap down the middle, two simple padded shoulder straps in the same olive, and a small brown "
        "leather patch. It sits high between the shoulder blades, compact so it does not hide the shorts, with "
        "chunky simplified forms suitable for a low-poly game model. Nothing else changes."
    ),
    'hooded': (
        "Variation: the yellow pullover becomes a hooded pullover. A generous soft hood in the same mustard "
        "yellow, lined in cream, lies folded down on the upper back and shoulders, with two short cream drawstrings "
        "hanging at the front of the neck. The hood's fold creates a clear shape between the shoulder blades and "
        "breaks the plain back. Keep the short sleeves and the white long sleeves. Nothing else changes."
    ),
    'back-print': (
        "Variation: graphic on the shirt only. Across the upper back of the yellow pullover add a wide cream "
        "horizontal band that runs shoulder to shoulder just below the neckline, edged with a thin rust-red stripe, "
        "and centred on the band a simple flat rust-red circle emblem, like a rising sun crest, about a hand wide. "
        "Flat colour, no texture, readable at distance. Add a small stitched rust rectangle on the back pocket of the "
        "shorts. Nothing else changes."
    ),
    'waist-jacket': (
        "Variation: a light rust-orange windbreaker jacket is tied around his waist by its sleeves, knotted at the "
        "front, so from behind the jacket body hangs over the top of the blue shorts down to mid-thigh with soft "
        "broad folds and its cream collar showing at the top. It breaks the straight line between shirt and shorts "
        "and gives the hips a readable silhouette from the back. Nothing else changes."
    ),
    'satchel': (
        "Variation: a small flat cross-body satchel in warm brown leather with a cream flap, hung on a wide cream "
        "webbing strap that runs diagonally across his back from the left shoulder to the right hip. The bag rests "
        "against the right hip at the level of the shorts' hem, slightly behind him. The strap reads as one clean "
        "diagonal from behind. Nothing else changes."
    ),
    'scarf-tuft': (
        "Variation: small touches only. A short cream cotton scarf is knotted loosely at the back of the neck with "
        "two tails, one rust-red and one cream, resting between the shoulder blades. The hair gets a slightly "
        "taller, more distinct tuft with two spikes, and a broad extra hair clump sweeps down over the nape. Add two "
        "cream patch pockets on the back of the blue shorts with visible stitching. Nothing else changes."
    ),
}


BASE_R02 = (
    "The attached images are renders of our approved game character: image 1 is his current back view, image 2 "
    "his front three-quarter view, image 3 his back while running. Keep his identity: same oversized head, face "
    "with small dark rectangular eyes, dark chocolate hair, compact four-head proportions, warm peach skin, and "
    "mustard yellow as his signature colour. Same softly sculpted matte 3D game-character finish, same plain "
    "light-gray studio background, same soft even light and faint contact shadow. "
    "The user finds the current look too plain and too much like a schoolboy, especially from behind. Redesign "
    "his outfit and hair so he looks COOLER: a confident, quick young adventurer in a warm Japanese countryside "
    "brawler game, with attitude, asymmetry and a strong silhouette that reads from the back at gameplay "
    "distance. Keep him a kid, keep it wearable and buildable as a low-poly game model with a few garment pieces, "
    "no weapons, no photoreal texture, no glossy plastic. "
    "Composition: ONE panel with exactly two full-body figures of him at the same scale in a relaxed, slightly "
    "cocky standing pose with arms hanging naturally, palms toward the thighs: on the left a true back view, on "
    "the right a front three-quarter view. Generous margins, nothing cropped, no text, no labels, no props on the "
    "floor, no other characters. Direction: "
)

CONCEPTS_R02 = {
    'haori': (
        "a short open indigo haori jacket worn over the yellow shirt, its hem cut at the hips and its back carrying "
        "one big cream circular crest with a bell mark; sleeves pushed up showing cream forearm wraps; the hair "
        "swept into taller windblown spikes leaning to one side; blue shorts with a knotted rope belt and a small "
        "bronze bell hanging at the back of the hip; cream tabi-style socks and dark high-top sneakers with tan soles."
    ),
    'streamer': (
        "a long rust-red headband tied at the back of the head with two tails that stream down between the "
        "shoulder blades; the yellow shirt now sleeveless over long white sleeves, with a dark-navy diagonal chest "
        "strap holding a small pouch on the lower back; fingerless dark gloves; one navy knee pad; hair bigger and "
        "spikier with the tuft turned into a bold swept crest; shorts slightly longer with a contrast cream stripe "
        "down the side; running shoes with a rust stripe."
    ),
    'half-cape': (
        "a short rust-orange half cape clasped over the left shoulder with a wooden toggle, hanging to the waist "
        "and covering half the back, its inner side cream; the yellow shirt with a high rolled collar; a wide dark "
        "leather belt over the shorts with a hanging bell charm; wrapped shins in cream cloth above the shoes; the "
        "hair more angular with three big forward spikes and a longer back clump over the nape."
    ),
    'hooded-vest': (
        "a sleeveless deep-indigo hooded vest worn open over the yellow shirt, hood down with a large pointed hood "
        "in cream lining lying on the upper back; two cream drawstrings; navy forearm sleeves with the white ones "
        "gone; dark shorts with a yellow stripe; hair pushed up into a taller messy crest; a small wooden bell "
        "charm tied to the vest at the back of the neck; chunky dark sneakers."
    ),
    'festival': (
        "a short happi coat in deep indigo with bold cream geometric shoulder bands and a big cream circle crest on "
        "the back, worn open over the yellow shirt; a twisted cream-and-rust headband; the white long sleeves "
        "rolled to the elbow with cream wrist wraps; a rope belt; the blue shorts replaced by dark cropped pants "
        "wrapped tight below the knee; straw-coloured sandal-sneakers; hair spikier with a longer tuft."
    ),
    'ranger': (
        "a fitted olive-green sleeveless jacket with a high collar over the yellow shirt, a wide cream strap "
        "across the back holding a small rolled cream blanket low on the back; a dark bandana around the neck "
        "hanging at the back in a triangle; the hair much bigger and more dramatic, a full windswept mane with the "
        "tuft as a sharp crest; wrapped forearms; the shorts with big cargo pockets on the back; sturdy brown boots "
        "with cream socks folded over."
    ),
}


BASE_R03 = (
    "Image 1 is the approved direction for our game character: a boy with an oversized head, dark chocolate spiky "
    "hair, small dark rectangular eyes, warm peach skin, a mustard-yellow shirt, blue shorts with a rope belt and a "
    "small bronze bell at the back of the hip, cream forearm wraps, cream socks and dark high-top sneakers, wearing "
    "an open short indigo haori jacket with a bell-in-circle crest on the back. Image 2 is his original back render "
    "for identity. Keep EVERYTHING from image 1 exactly: face, hair, body, pose, yellow shirt, shorts, belt, bell, "
    "wraps, socks, sneakers, the softly sculpted matte 3D finish, the plain light-gray studio background, the soft "
    "even light and faint contact shadow. "
    "Composition identical to image 1: ONE panel with two full-body figures at the same scale, true back view on "
    "the left, front three-quarter view on the right, arms hanging naturally with palms toward the thighs. Generous "
    "margins, nothing cropped, no text, no labels, no props, no other characters. "
    "Change ONLY the jacket layer worn over the yellow shirt, as follows: "
)

CONCEPTS_R03 = {
    'vest-indigo': (
        "the same indigo haori but SLEEVELESS: a short open vest with wide armholes so the yellow short sleeves "
        "and white long sleeves show fully; same bell-in-circle cream crest on the back; a cream binding along the "
        "front edges and armholes."
    ),
    'vest-rust': (
        "a sleeveless open vest in rust red-orange with a deep-indigo binding along the front edges and armholes, "
        "the back crest becoming a big indigo circle with a cream bell inside; the vest cut a little longer, hem "
        "just below the belt with two short side slits."
    ),
    'haori-long': (
        "the indigo haori made LONGER, its hem falling to mid-thigh and split at the back so it hangs in two "
        "panels over the shorts; sleeves kept short and rolled; the bell crest moved up between the shoulder blades "
        "and made larger, with a thin cream stripe running down each back panel to the hem."
    ),
    'haori-charcoal-stripes': (
        "the haori in charcoal black with three bold cream horizontal stripes across the upper back and around "
        "each sleeve; no circle crest, instead a small cream bell mark high at the nape; the jacket slightly boxier "
        "with a stand-up collar."
    ),
    'haori-hooded': (
        "the indigo haori with a large cream-lined hood folded down on the upper back, the crest on the hood's "
        "outer side so it still reads from behind; the sleeves cut off at the shoulder like a hooded vest; one "
        "rust toggle closing at the chest."
    ),
    'haori-olive-asym': (
        "an asymmetric jacket in deep olive green: the left side long-sleeved and rolled, the right side "
        "sleeveless, closed diagonally across the chest with a rust cord; on the back a cream crescent moon and "
        "bell crest; the hem cut diagonally, longer on the sleeveless side."
    ),
}


BASE_R04 = (
    "The attached images are renders of our approved game character: image 1 is his current back view, image 2 "
    "his front three-quarter view, image 3 his back while running. Keep his identity exactly: same oversized head, "
    "face with small dark rectangular eyes, dark chocolate spiky hair with the small upward tuft, compact four-head "
    "kid proportions, warm peach skin. Same softly sculpted matte 3D game-character finish, same plain light-gray "
    "studio background, same soft even light and faint contact shadow. "
    "Replace his ENTIRE outfit with a new one in the spirit of baggy Japanese street skateboarding clothes: "
    "oversized, loose, layered, wide silhouettes, dropped shoulders, stacked or cropped trousers, chunky skate "
    "shoes, the kind of look seen on young skaters in Tokyo. He is a quick, confident young adventurer in a warm "
    "Japanese countryside brawler game, so it must still read as a game hero with a strong silhouette from the "
    "back at gameplay distance, and stay wearable and buildable as a low-poly game model with a few garment pieces. "
    "STRICT RULE ON SURFACES: every garment is a flat solid colour. No printed graphics, no logos, no text, no "
    "stripes, no patterns, no camouflage, no embroidery, no visible fabric texture; those will be designed by hand "
    "later. All the interest must come from the cut, the layering, the volume and the colour blocking, using at "
    "most four colours in the whole outfit. Mustard yellow may stay as one accent colour but does not have to. "
    "No weapons, no props, no skateboard, no glossy plastic, no photoreal cloth. "
    "Composition: ONE panel with exactly two full-body figures of him at the same scale in a relaxed, slightly "
    "cocky standing pose with arms hanging naturally, palms toward the thighs: on the left a true back view, on "
    "the right a front three-quarter view. Generous margins, nothing cropped, no text, no labels, no other "
    "characters. Direction: "
)

CONCEPTS_R04 = {
    'boxy-tee-cargo': (
        "a huge boxy mustard-yellow short-sleeve tee that hangs to mid-thigh over a white long-sleeve layer, "
        "extra-wide olive-drab cargo work trousers with big flap pockets on the thighs, stacked in folds over "
        "chunky cream-and-black skate shoes, and a small black beanie pushed back so the hair tuft still shows."
    ),
    'boxy-tee-cargo-nohat': (
        "a huge boxy mustard-yellow short-sleeve tee that hangs to mid-thigh over a white long-sleeve layer, "
        "extra-wide olive-drab cargo work trousers with big flap pockets on the thighs, stacked in folds over "
        "chunky cream-and-black skate shoes. NO hat of any kind: the hair is fully visible exactly as in the "
        "reference renders, spiky with the small upward tuft. Pay special attention to the hands: each hand has "
        "exactly five simple rounded fingers, relaxed and slightly curled, thumbs toward the front, palms facing the "
        "thighs, no extra or fused fingers, matching the reference renders."
    ),
    'coach-jacket': (
        "a boxy navy nylon coach jacket with a flat collar and snap front worn open over a plain cream tee, "
        "baggy cropped khaki chinos that stop above the ankle, tall white tube socks, suede rust-brown skate shoes "
        "with fat laces, and a black cap worn backwards under the hair."
    ),
    'chore-jacket-pleats': (
        "an oversized indigo denim chore jacket with dropped shoulders and big patch pockets, sleeves rolled once, "
        "over a mustard tee, extremely wide dark-charcoal pleated trousers cuffed high above cream split-toe "
        "sneakers, and a thin white headband; a Japanese workwear feel made baggy."
    ),
    'cropped-hoodie-jorts': (
        "a wide cropped hoodie in dusty sage green with a big hood lying on the back, the hem of a longer mustard "
        "tee showing beneath it, sagging wide dark-denim shorts that end below the knee, high white socks with one "
        "black band, and thick-soled black skate shoes."
    ),
    'work-vest-double-knee': (
        "a loose warm-brown canvas work vest with big chest pockets worn over an oversized white long-sleeve shirt "
        "with very wide sleeves, baggy black double-knee work trousers rolled at the ankle over grey socks, cream "
        "skate shoes, and a soft cream bucket hat that keeps the hair tuft visible."
    ),
    'nylon-shorts-layers': (
        "an oversized mustard tee half tucked into extra-baggy knee-length black nylon shorts with a wide "
        "drawcord waist, long white sleeves showing below the tee, a slim navy zip vest worn open, shin-high navy "
        "socks, chunky white skate shoes, and a rolled navy bandana around the neck."
    ),
}

SWORD_STILLS = [CHAR / 'body-swap-r02-headless/captures/standing--front-left.png',
                CHAR / 'body-swap-r02-headless/captures/standing--back.png',
                CHAR / 'back-concepts-r04/boxy-tee-cargo-nohat-1.png']
BASE_SWORD = (
    "The attached images are renders of our approved game character in his final outfit: image 1 is his front "
    "three-quarter view, image 2 his back view, image 3 the painted concept the outfit was built from. Keep him "
    "exactly as he is: same oversized head, face with small dark rectangular eyes, dark chocolate spiky hair with "
    "the small upward tuft, compact four-head kid proportions, warm peach skin, and the SAME outfit unchanged: a "
    "huge boxy mustard-yellow short-sleeve tee to mid-thigh over white long sleeves, extra-wide olive-drab cargo "
    "trousers stacked over chunky cream-and-black skate shoes. Same softly sculpted matte 3D game-character "
    "finish, same plain light-gray studio background, same soft even light and faint contact shadow. "
    "He is the hero of a warm Japanese countryside action game where angry spirits pour out of openings in the "
    "ground; the only thing they cannot stand is an old cast bell metal, dull grey-green bronze with a faint cold "
    "glow. His weapon is a short one-handed sword that he improves through the game. This study shows ONE stage of "
    "that sword. The blade must be short for his size, a wakizashi length or less, so it reads as a kid's sword, "
    "and simple enough to build as a low-poly game prop with a flat-colour material and at most one glow. "
    "Composition: ONE panel with two things at generous scale, nothing cropped, no text, no labels, no other "
    "characters, no effects except the glow described. On the left, a full-body figure of him standing in a "
    "relaxed, slightly cocky low ready stance, holding the sword in his RIGHT hand with the point down and a bit "
    "forward so the whole blade and grip are clearly visible, left arm loose; each hand has exactly five simple "
    "rounded fingers. On the right, the same sword alone, large, upright, at the same painted finish, so every part "
    "of it can be read: blade, guard, grip, and anything hanging from it. The sword at this stage: "
)
CONCEPTS_SWORD = {
    'stage1-bokken': (
        "STAGE 1, the wooden practice sword. A plain kid-sized bokken taken from a village dojo storeroom: pale "
        "worn oak, a simple oval wooden guard, a grip wrapped in a faded cotton cord, a small chip out of the edge, "
        "and a short frayed red loop at the pommel. No metal at all, no glow. It should look humble, borrowed and "
        "a little too big for him."
    ),
    'stage3-bell-shard': (
        "STAGE 3, the bell-shard edge. A short single-edged steel sword a coast fisherman once owned, dark grey "
        "steel with a slightly worn look, a plain round iron guard and a grip wrapped in dark navy cord; a village "
        "smith has folded a fragment of an old town bell into the cutting edge, so a band of dull grey-green "
        "bronze runs along the edge only, with a faint cold blue-white glow just at that edge, and a small cast "
        "bell fragment with part of an inscription hangs from the pommel on a cord. It should look repaired and "
        "hopeful, half ordinary and half something else."
    ),
    'stage5-lock-blade': (
        "STAGE 5, the lock blade. The whole short sword recast from a piece of a broken seal-lock: the blade, guard "
        "and pommel are one piece of dull grey-green bell bronze with the raised cast inscription of the old locks "
        "running down the flat of the blade, the guard shaped like a bell mouth, the grip wrapped in mustard-yellow "
        "cord to match his tee, and a steady cold blue-white glow along the inscription and the edge. Still short, "
        "still one-handed, still simple in silhouette; the power shows in the material and the glow, not in size or "
        "ornament."
    ),
}


def key():
    k = os.environ.get('OPENAI_API_KEY', '')
    if not k:
        sys.exit('OPENAI_API_KEY is not set; run: set +x; set -a; source ./.env; set +a')
    return k


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def gpt_edit(prompt, images, n):
    """n Sunburst edits of the context images (atelier.ai.images). Returns (PNG bytes list, response, seconds)."""
    from atelier.ai import images as client
    return client.sunburst(prompt, SIZE, images, n, model=MODEL, quality=QUALITY, key=key())


def run(slug, n):
    prompt = BASE + CONCEPTS[slug]
    OUT.mkdir(parents=True, exist_ok=True)
    priv = OUT / 'api-private'
    priv.mkdir(exist_ok=True, mode=0o700)
    (priv / '.gitignore').write_text('*\n')
    (OUT / f'{slug}.prompt.txt').write_text(prompt + '\n')
    from atelier.ai import ledger

    def paint():
        outs = []
        blobs, raw, secs = gpt_edit(prompt, STILLS, n)
        p = priv / f'{slug}.response.json'
        p.write_text(json.dumps(raw, indent=1))
        p.chmod(0o600)
        for i, b in enumerate(blobs):
            p = OUT / (f'{slug}.png' if n == 1 else f'{slug}-{i + 1}.png')
            p.write_bytes(b)
            outs.append(p.name)
        return dict(elapsed_seconds=secs, outputs={o: sha(OUT / o) for o in outs}, approval='pending')
    # The record is written before the paid call; a failed or uncertain one is never sent again by itself.
    prov, err = ledger.try_once(OUT / f'{slug}.provenance.json', dict(
        stage={'r01': 'back-view-concept', 'r04': 'skate-outfit-concept'}.get(OUT.name[-3:], 'sword-stage-concept' if 'sword' in OUT.name else 'cooler-look-concept'), concept=slug, requested_model=MODEL, quality=QUALITY, size=SIZE, n=n,
        endpoint='/v1/images/edits', execution='games/yorimichi/assets/characters/tools/cairo_back_concepts.py',
        prompt_file=f'{slug}.prompt.txt', prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),
        reference_files={str(s.relative_to(ROOT)): sha(s) for s in STILLS},
        reference_source='body-swap-r02-headless captures (game-r11 outfit) + back-concepts-r04 study' if STILLS is SWORD_STILLS else 'outfit-r05/WarmOriginal-Outfit-r05.blend (accepted r05; Cycles captures, unchanged)',
    ), paint)
    if not prov:   # images of a failed call are not reported as outputs
        return slug, [], None, err
    return slug, list(prov['outputs']), prov['elapsed_seconds'], None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--only', default='')
    ap.add_argument('--n', type=int, default=1)
    ap.add_argument('--rev', default='r01', choices=['r01', 'r02', 'r03', 'r04', 'sword'])
    a = ap.parse_args()
    global OUT, BASE, CONCEPTS
    if a.rev == 'r02':
        OUT, BASE, CONCEPTS = CHAR / 'back-concepts-r02', BASE_R02, CONCEPTS_R02
    if a.rev == 'r03':
        global STILLS
        OUT, BASE, CONCEPTS = CHAR / 'back-concepts-r03', BASE_R03, CONCEPTS_R03
        STILLS = [CHAR / 'back-concepts-r02/haori.png', CAPS / '03-standing-back.png']
    if a.rev == 'r04':
        OUT, BASE, CONCEPTS = CHAR / 'back-concepts-r04', BASE_R04, CONCEPTS_R04
    if a.rev == 'sword':
        OUT, BASE, CONCEPTS, STILLS = CHAR / 'sword-concepts-r01', BASE_SWORD, CONCEPTS_SWORD, SWORD_STILLS
    slugs = [s for s in a.only.split(',') if s] or list(CONCEPTS)
    key()
    for s in STILLS:
        if not s.exists():
            sys.exit(f'missing capture {s}')
    with ThreadPoolExecutor(max_workers=len(slugs)) as ex:
        for slug, outs, secs, err in ex.map(lambda s: run(s, a.n), slugs):
            print(f'{slug}: {"ERROR " + err if err else ", ".join(outs)} ({secs}s)')


if __name__ == '__main__':
    main()
