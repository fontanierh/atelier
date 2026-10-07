#!/usr/bin/env python3
"""Playable character concepts for Yorimichi on Sunburst, steered by Cairo's approved renders.

    YORIMICHI_ARCHIVE=... uv run python games/yorimichi/tools/character_concepts.py [--only slug,slug] [--dry-run]

One character, several takes: a quiet, dark-haired young man in the anime "cool guy" mould (mysterious, nonchalant,
the smartest person in the room), each take tied to a different side of the lore (docs/LORE.md). Every take is a
turnaround model sheet that keeps Cairo's sculpted matte finish, so whichever is chosen can be modelled for the
humanoid bone contract and share Cairo's clips.

Writes <slug>.jpg (the committed copy), <slug>.prompt.txt and <slug>.provenance.json into
games/yorimichi/assets/characters/concepts/, and a contact sheet of every take to build/yorimichi/review/characters/.
The full-size PNG goes to build/yorimichi/characters/concepts/originals/. Model gpt-image-2.5-sunburst, quality high,
1536x1024, through /v1/images/edits. The paid call goes through atelier.ai.ledger: a take that has a provenance file
is never sent again, whatever its status; rename its files to <slug>.rejected-N.* to paint it again.

References: Cairo's final r05 captures from the prototype archive (YORIMICHI_ARCHIVE, not in git; only their names
and hashes are recorded) and the villager's model sheet, for the sheet layout. The key comes from OPENAI_API_KEY (or
the ignored .env).
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[1] / 'world')); import yori  # noqa: E402
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
import argparse, os, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from treehouse_art import MODEL, QUALITY, compact, redact, rel, sha, sheet, sunburst

OUT = yori.ASSETS / 'characters' / 'concepts'
ORIGINALS = yori.OUT / 'characters' / 'concepts' / 'originals'
REVIEW = yori.REVIEW / 'characters'
SIZE = '1536x1024'
CAPTURES = 'output/imagegen/yorimichi-yellow-boy-2026-09-12/outfit-r05/final-captures'


def references():
    archive = os.environ.get('YORIMICHI_ARCHIVE')
    if not archive:
        sys.exit('set YORIMICHI_ARCHIVE to the prototype archive that holds Cairo\'s r05 captures')
    caps = Path(archive).expanduser() / CAPTURES
    return [caps / '01-standing-three-quarter.png', caps / '02-standing-front.png', caps / '03-standing-back.png',
            yori.ASSETS / 'characters' / 'wanderer' / 'references' / 'design-sheet.png']


STYLE = (
    'Production character model sheet for Yorimichi, a stylised 3D Japanese action-exploration game in Unreal. '
    'Images 1, 2 and 3 are renders of Cairo, the approved player character (three-quarter, front and back): they are '
    'the PRIMARY reference for finish, face and proportion language. Match exactly his softly sculpted matte 3D '
    'game-character finish, chunky simplified forms, large clumped hair shapes, warm peach skin, simple face with dark '
    'vertical pill eyes without whites or irises, a barely indicated nose and a small mouth, plain light-grey studio '
    'background and soft even light. Image 4 is the villager\'s model sheet: use it ONLY for the sheet layout '
    '(four labelled views on top, close-ups and colour chips below), not for its flat faceted look.'
)

HERO = (
    'THE CHARACTER: a new playable hero, not Cairo and not a child: a lean young man of about eighteen, clearly taller '
    'and longer-limbed than Cairo (about 5 heads tall, narrow shoulders, long legs), in the mould of the cool, '
    'mysterious anime rival: calm, nonchalant, quietly the smartest person in the room. Near-black hair in a few big '
    'sculpted clumps, a long side-swept fringe that hides one eye. His pill eyes are half-lidded (a flat, heavy upper '
    'lid line cut across the top of each pill), giving a bored, knowing look; a faint lopsided almost-smile. Default '
    'stance: weight on one leg, one hand in a pocket or sleeve, head slightly tilted. Dark, restrained palette with '
    'one accent colour so he reads clearly at game-camera distance and never as a black blob.'
)

LAYOUT = (
    'Composition: landscape model sheet. Top row: equally sized full-body front, exact right profile, back and '
    'three-quarter views of the SAME design in a relaxed A-pose with both hands visible, labelled FRONT, RIGHT '
    'PROFILE, BACK, THREE-QUARTER. Bottom row: a larger face close-up in front and three-quarter (the half-lidded '
    'eyes and the fringe clearly readable), one full-body attitude pose described below, a close-up of his weapon, '
    'and 6 flat colour chips. Consistent height and proportions in every view. Clean modelable shapes suitable for '
    'a game mesh rigged with a standard humanoid skeleton: no tiny straps, laces, embroidery, fine fringe or texture '
    'noise.'
)

AVOID = ('No text other than the short view labels, no logos, no HUD, no borders around the whole sheet, no other '
         'characters, no Cairo, no yellow pullover, no spirits or creatures, no blood, no realistic skin or cloth '
         'shading.')

TAKES = {
    'modori': (
        'TAKE: "the one who came back". He walked into the forest sinkhole with a search party and came out alone '
        'six weeks later, well fed, calm and wrong; he knows what the spirits offered and will not say. One thin '
        'frost-white streak runs through his dark fringe. Long charcoal coat-haori to the knees, worn open, with a '
        'tall stiff collar that hides his chin; slate-grey fitted trousers tucked into dark wrapped shins and simple '
        'black split-toe boots. The hems of the coat and sleeves fade to a pale icy blue, as if frost had crept up '
        'the cloth. Accent: that pale icy blue. Weapon: a length of old knotted rope ending in a heavy dull-gold '
        'bell-metal weight, coiled loosely over one shoulder like a scarf, thrown and pulled back in a fight. '
        'Attitude pose: walking away while glancing back over his shoulder, the rope swinging.'
    ),
    'bell-reader': (
        'TAKE: "the bell-reader". A plateau monastery novice who left before taking vows and is the only person on '
        'the coast who can read the inscription cast into every bell; he worked out the truth before anyone and finds '
        'it tiresome to explain. Dark hair tied in a short low tail, fringe over the right eye, small round thin '
        'wire glasses. Deep indigo wide-sleeved scholar\'s robe-coat over a dark grey high-necked undershirt, a '
        'plain wide sash, slim dark hakama-trousers gathered at the ankle, dark sandals over grey tabi. A long '
        'cylindrical scroll case slung across his back. Accent: muted temple vermilion on the sash and the cord of '
        'the scroll case. Weapon: a slender staff as tall as him, its head a small dull-gold bell-metal bell in an '
        'open cage. Attitude pose: reading a small open book in one hand while holding the staff loosely against '
        'his shoulder with the other, not even looking up.'
    ),
    'guild-defector': (
        'TAKE: "the guild defector". An assayer\'s apprentice of the mining guild who found the ledger that proves '
        'the guild cut the mountain lock, walked out with it, and acts as if nothing happened. Messy dark hair over '
        'one eye, a small dull-gold bell-metal stud in one ear. The guild\'s dark olive-brown work coat, too long '
        'and worn open, the guild badge torn off and leaving a paler patch on the chest; a charcoal roll-neck under '
        'it, dark straight trousers, scuffed dark boots, one canvas satchel on the hip with a folded ledger sticking '
        'out. Accent: dull gold (bell metal) and the paler patch. Weapon: a short single-edged blade of dull-gold '
        'bell metal held in a reverse grip, sheathed horizontally at the small of his back. Attitude pose: leaning '
        'back against nothing with arms crossed, blade hand casually resting, eyes half closed.'
    ),
    'ferry-courier': (
        'TAKE: "the ferry courier". A coastal courier who carries letters and rumours between the fishing villages '
        'and Hidamari by boat and on foot; he hears every theory about the spirits and quietly knows which one is '
        'true. Windswept dark hair, fringe over one eye, a long deep-teal scarf wound high over his chin with two '
        'long tails. Short dark navy jacket with a high collar and wide sleeves pushed to the elbows, dark fitted '
        'trousers with wrapped ankles, light dark-soled shoes, a flat leather letter case on a strap across his '
        'back. Accent: the deep teal scarf and a small red letter seal on the case. Weapon: a closed oil-paper '
        'umbrella of dark plum paper with a dull-gold bell-metal ferrule and tip, used like a sword and opened as a '
        'shield. Attitude pose: the closed umbrella resting on his shoulder, other hand in his pocket, mid-stride.'
    ),
}


def prompt_of(take):
    return '\n\n'.join([STYLE, HERO, TAKES[take], LAYOUT, AVOID])


def run(take, refs):
    from atelier.ai.ledger import run_once
    prompt = prompt_of(take)
    (OUT / f'{take}.prompt.txt').write_text(prompt + '\n')
    metadata = dict(stage='character-concept', concept=take, requested_model=MODEL, quality=QUALITY, size=SIZE,
                    endpoint='/v1/images/edits', execution='games/yorimichi/tools/character_concepts.py',
                    prompt_file=f'{take}.prompt.txt', prompt_sha256=sha(prompt.encode()),
                    reference_files={rel(p): sha(p.read_bytes()) for p in refs},
                    hashes='of the files as the API saw and returned them; the full-size original is kept outside '
                           'the repository')

    def paint():
        t = time.time()
        png, usage = sunburst(prompt, SIZE, refs)
        ORIGINALS.mkdir(parents=True, exist_ok=True); (ORIGINALS / f'{take}.png').write_bytes(png)
        return dict(usage=usage, outputs={f'{take}.png': sha(png)},
                    compact_copy=compact(png, OUT / f'{take}.jpg', 'concepts'),
                    elapsed_seconds=round(time.time() - t, 1))

    return run_once(OUT / f'{take}.provenance.json', metadata, paint)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--only', default='', help='comma-separated takes: ' + ', '.join(TAKES))
    ap.add_argument('--dry-run', action='store_true', help='print the prompts and stop')
    args = ap.parse_args()
    wanted = [t for t in TAKES if not args.only or t in args.only.split(',')]
    if args.dry_run:
        for t in wanted:
            print(f'--- {t}{" (recorded, skipped)" if (OUT / f"{t}.provenance.json").exists() else ""}\n'
                  f'{prompt_of(t)}\n')
        return
    refs = references()
    missing = [rel(p) for p in refs if not p.exists()]
    if missing:
        sys.exit(f'missing references {missing}')
    OUT.mkdir(parents=True, exist_ok=True)
    todo = [t for t in wanted if not (OUT / f'{t}.provenance.json').exists()]
    if todo:
        from atelier.env import require
        require('OPENAI_API_KEY')   # loads the ignored .env; stops with a clear message, never prints the value
    print(f'painting {len(todo)} take(s) in parallel: {", ".join(todo) or "none"}', flush=True)
    failed = []

    def one(take):
        start = time.time()
        try:
            record = run(take, refs)
            print(f'{take}: done ({record["elapsed_seconds"]} s)', flush=True)
        except Exception as e:  # noqa: BLE001 - recorded by the ledger, never retried
            failed.append(take)
            print(f'{take}: failed after {round(time.time() - start)} s: {redact(e)[:300]}', flush=True)

    with ThreadPoolExecutor(len(todo) or 1) as pool:
        futures = [pool.submit(one, t) for t in todo]
        start = time.time()
        while not all(f.done() for f in futures):
            time.sleep(1)
            if int(time.time() - start) % 30 == 0:
                waiting = [t for t, f in zip(todo, futures) if not f.done()]
                print(f'{round(time.time() - start)} s: waiting on Sunburst for {", ".join(waiting)}', flush=True)
                time.sleep(1)
    sheet([(OUT / f'{t}.jpg', t) for t in TAKES], REVIEW / 'character-concepts.jpg', 768, 512, 2)
    if failed:
        sys.exit(f'stopped: {", ".join(failed)} failed and are not retried')


if __name__ == '__main__':
    main()
