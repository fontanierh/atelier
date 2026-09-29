"""Probe a generated MP4 and build timestamped overview/stride review sheets.

Run with the revision directory. Requires ffmpeg, ffprobe and Pillow.
The original video is preserved; intermediate frames stay outside the server.
"""
import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import subprocess

from PIL import Image, ImageDraw, ImageFont

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('revision', type=Path)
args = parser.parse_args()
root = args.revision.resolve()
video = root / 'reference.mp4'
metadata = json.loads(subprocess.check_output([
    'ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(video)]))
stream = next(s for s in metadata['streams'] if s['codec_type'] == 'video')
fps = float(Fraction(stream['avg_frame_rate']))
if fps <= 0 or Fraction(stream['avg_frame_rate']) != Fraction(stream['r_frame_rate']):
    raise SystemExit('Frame sheets require a constant-frame-rate reference; inspect the source first.')
duration = float(stream.get('duration', metadata['format']['duration']))
frames = int(stream.get('nb_frames', round(duration * fps)))
report = {'duration_seconds': duration, 'fps': fps, 'frames': frames,
          'width': stream['width'], 'height': stream['height'],
          'codec': stream['codec_name'], 'pixel_format': stream['pix_fmt'],
          'audio_streams': sum(s['codec_type'] == 'audio' for s in metadata['streams']),
          'source': 'reference.mp4', 'sha256': hashlib.sha256(video.read_bytes()).hexdigest()}
job_path = root / 'job.json'
job = json.loads(job_path.read_text())
if job.get('video_sha256') != report['sha256']:
    raise SystemExit('Video does not match the recorded generation; do not publish it.')
private_frames = root / 'analysis-frames'
private_frames.mkdir(exist_ok=True)
font = ImageFont.truetype('/System/Library/Fonts/Helvetica.ttc', 18)

for name, step, count in [('overview', max(1, frames // 12), 12),
                          ('stride', max(1, round(fps / 12)), min(24, frames))]:
    count = min(count, (frames - 1) // step + 1)
    folder = private_frames / name
    folder.mkdir(exist_ok=True)
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(video),
                    '-vf', f'select=not(mod(n\\,{step})),scale=320:-1',
                    '-fps_mode', 'vfr', '-frames:v', str(count),
                    str(folder / '%03d.png')], check=True)
    samples = []
    first = Image.open(folder / '001.png').convert('RGB')
    width, height = first.size
    columns = 4
    sheet = Image.new('RGB', (columns * width, ((count + 3) // 4) * (height + 32)), '#f5f1e8')
    draw = ImageDraw.Draw(sheet)
    for index in range(count):
        frame = index * step
        x, y = (index % columns) * width, (index // columns) * (height + 32)
        sheet.paste(Image.open(folder / f'{index+1:03d}.png').convert('RGB'), (x, y))
        draw.text((x + 8, y + height + 5), f'{frame / fps:.3f}s  ·  frame {frame+1}', fill='#302c25', font=font)
        samples.append({'frame_zero_based': frame, 'time_seconds': frame / fps})
    sheet.save(root / f'{name}.jpg', quality=94)
    report[name + '_samples'] = samples
subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(video),
                '-frames:v', '1', str(root / 'poster.png')], check=True)
(root / 'video-metadata.json').write_text(json.dumps(report, indent=2) + '\n')
job.update(framespersecond=fps, duration=duration, width=stream['width'], height=stream['height'])
job_path.write_text(json.dumps(job, indent=2) + '\n')
print(f'{duration:g}s, {fps:g} fps, {stream["width"]}×{stream["height"]}; overview and stride sheets saved.')
