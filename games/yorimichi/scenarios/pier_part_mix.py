"""Assemble approved Pier takes, make an original beat, mix board sounds, encode.

    uv run python games/yorimichi/scenarios/pier_part_mix.py TAKE_DIR ... --out PART_DIR

Only complete, bail-free filmed takes are accepted. Source captures remain in
place; the assembly uses hard links. The soundtrack is an original procedural
composition (no sampled music) with a muted piano, bass and brushed drums.
"""
import argparse
import csv
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import wave

import numpy as np

from pier_part_check import assess

RATE = 48000


def beat(path, seconds):
    rng = np.random.default_rng(8128)
    result = np.zeros(round((seconds + 2) * RATE), np.float32)
    bpm = 92
    step = 60 / bpm
    chords = [(53, 56, 60, 63), (49, 53, 56, 60), (51, 55, 58, 62), (48, 51, 55, 58)]
    def add(at, signal, level):
        start = round(at * RATE); end = min(len(result), start + len(signal))
        if end > start: result[start:end] += signal[:end-start] * level
    def note(midi, duration, mellow=True):
        t = np.arange(round(duration*RATE)) / RATE
        hz = 440 * 2**((midi-69)/12)
        signal = sum(np.sin(math.tau*hz*(i+1)*t) * (1/(i+1)**2 if mellow else 1/(i+1))
                     for i in range(4 if mellow else 2))
        return (signal * (1-np.exp(-t*120)) * np.exp(-t*(2.2 if mellow else 4.8))).astype(np.float32)
    for bar in range(math.ceil(seconds/(4*step))):
        chord = chords[bar % len(chords)]
        at = bar*4*step
        for j, midi in enumerate(chord): add(at+j*.017, note(midi+12, 2.5), .065)
        for pulse in range(4):
            t = np.arange(round(.32*RATE))/RATE
            hz = 43+100*np.exp(-t*35)
            kick = np.sin(math.tau*np.cumsum(hz)/RATE)*np.exp(-t*20)
            if pulse in (0, 2): add(at+pulse*step, kick, .18)
            if pulse in (1, 3):
                noise = rng.normal(0, 1, len(t)); brush = np.convolve(noise, np.ones(7)/7, 'same')
                add(at+pulse*step, brush*np.exp(-t*24), .065)
            add(at+pulse*step, note(chord[0]-12, .52, False), .11)
        for half in range(8):
            at_hat=at+half*step/2+(step*.055 if half%2 else 0)
            t=np.arange(round(.075*RATE))/RATE
            noise=rng.normal(0, 1, len(t)); high=noise-np.convolve(noise, np.ones(21)/21, 'same')
            add(at_hat, high*np.exp(-t*65), .015 if half%2 else .023)
        if bar%2:
            for offset, index in [(1.5, 3), (2.5, 2), (3.5, 1)]:
                add(at+offset*step, note(chord[index]+24, .8), .035)
    result=np.tanh(result*1.4)
    with wave.open(str(path), 'wb') as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(RATE)
        f.writeframes((np.clip(result, -1, 1)*32767).astype('<i2').tobytes())
    path.with_suffix('.json').write_text(json.dumps(dict(title='Salt Air / Sunset Pier',
        author='Original procedural composition in pier_part_mix.py', bpm=bpm, seed=8128,
        instruments=['additive muted piano', 'sine bass', 'synthesised brushed drums'],
        samples='none', chords=chords), indent=2)+'\n')


def assemble(takes, out):
    out.mkdir(parents=True, exist_ok=False)
    film=sim=0; cams=[]; loops=[]; sounds=[]; marks=[]; states=[]
    for take in takes:
        report=assess(take)
        if not report['ok']: raise RuntimeError('Unapproved take: '+str(take))
        done=json.loads((take/'done.json').read_text())
        if not done['filmed']: raise RuntimeError('Rehearsal has no frames: '+str(take))
        for i in range(done['film_frames']):
            os.link(take/('frame_%05d.png'%i), out/('frame_%05d.png'%(film+i)))
        for row in csv.DictReader((take/'camera.csv').open()):
            cams.append(','.join([str(int(row['frame'])+film), row['x'], row['y'], row['z'], row['yaw']]))
        loops.extend((take/'loops.csv').read_text().splitlines())
        for sound in json.loads((take/'audio.json').read_text()):
            if sound['frame']>=0: sounds.append({**sound, 'frame':sound['frame']+sim})
        marks.extend({**mark, 'film_frame':mark['film_frame']+film, 'sim_frame':mark['sim_frame']+sim} for mark in done['shots'])
        states.extend({**row, 'frame':row['frame']+sim} for row in json.loads((take/'states.json').read_text()))
        film+=done['film_frames']; sim+=done['sim_frames']
    (out/'camera.csv').write_text('frame,x,y,z,yaw\n'+'\n'.join(cams)+'\n')
    (out/'loops.csv').write_text('\n'.join(loops)+'\n')
    (out/'audio.json').write_text(json.dumps(sounds))
    (out/'states.json').write_text(json.dumps(states))
    (out/'done.json').write_text(json.dumps(dict(film_frames=film, sim_frames=sim,
        fps_sim=60, fps_film=30, filmed=True, frame_extension='png', shots=marks), indent=2)+'\n')
    beat(out/'salt-air.wav', film/30)
    subprocess.run([sys.executable, str(Path(__file__).with_name('skate_mix_showreel.py')),
                    str(out), '--out', 'sunset-pier', '--music', str(out/'salt-air.wav'),
                    '--title', 'SUNSET PIER'], check=True)
    print('SUNSET PIER PART', out/'sunset-pier.mp4')


if __name__ == '__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('takes',type=Path,nargs='+')
    ap.add_argument('--out',type=Path,required=True);args=ap.parse_args()
    assemble(args.takes,args.out)
