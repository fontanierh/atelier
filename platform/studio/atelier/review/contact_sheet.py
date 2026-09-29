"""Tile captured frames into one labelled JPG per view (Pillow)."""
import json, sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
out = Path(sys.argv[1]); records = json.loads((out / 'captures.json').read_text())['frames']
font = ImageFont.truetype('/System/Library/Fonts/Helvetica.ttc', 16)
columns = int(sys.argv[2]) if len(sys.argv) > 2 else 6
for view in sorted({r['view'] for r in records}):
    rows = [r for r in records if r['view'] == view]
    first = Image.open(out / rows[0]['file']); w, h = first.size
    scale = min(1, 300 / w); w, h = int(w * scale), int(h * scale)
    sheet = Image.new('RGB', (columns * w, ((len(rows) + columns - 1) // columns) * (h + 22)), '#f5f1e8')
    draw = ImageDraw.Draw(sheet)
    for i, r in enumerate(rows):
        x, y = (i % columns) * w, (i // columns) * (h + 22)
        sheet.paste(Image.open(out / r['file']).convert('RGB').resize((w, h)), (x, y))
        draw.text((x + 6, y + h + 3), f"f{r['frame']} {r['time']:.3f}s", fill='#302c25', font=font)
    sheet.save(out / f'{view}-sheet.jpg', quality=90)
print('SHEET', out)
