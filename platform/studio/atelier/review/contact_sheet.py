"""Contact sheets (Pillow). `sheet` tiles (image, caption) pairs into one JPG; run as a script, it tiles captured frames
into one labelled JPG per view:

    python contact_sheet.py OUT [COLUMNS]     # OUT/captures.json -> OUT/<view>-sheet.jpg
"""
import json, sys
from pathlib import Path


def sheet(items, dest, w, h, cols):
    """A contact sheet of (image path, caption) pairs, each image w x h, cols to a row; missing images are left out.
    Returns dest, or None when no image exists."""
    from PIL import Image, ImageDraw, ImageFont
    items = [(p, c) for p, c in items if Path(p).exists()]
    if not items: return None
    cap = 40 if w > 400 else 30
    canvas = Image.new('RGB', (cols*w, -(-len(items)//cols)*(h+cap)), (244, 241, 234)); d = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype('/System/Library/Fonts/Supplemental/Arial.ttf', 22 if w > 400 else 18)
    except OSError:
        font = ImageFont.load_default()
    for i, (path, caption) in enumerate(items):
        x, y = (i % cols)*w, (i//cols)*(h+cap)
        canvas.paste(Image.open(path).convert('RGB').resize((w, h)), (x, y))
        d.text((x+10, y+h+6), caption, font=font, fill=(30, 30, 30))
    Path(dest).parent.mkdir(parents=True, exist_ok=True); canvas.save(dest, quality=86)
    return dest


def main():
    from PIL import Image, ImageDraw, ImageFont
    out = Path(sys.argv[1]); records = json.loads((out / 'captures.json').read_text())['frames']
    font = ImageFont.truetype('/System/Library/Fonts/Helvetica.ttc', 16)
    columns = int(sys.argv[2]) if len(sys.argv) > 2 else 6
    for view in sorted({r['view'] for r in records}):
        rows = [r for r in records if r['view'] == view]
        first = Image.open(out / rows[0]['file']); w, h = first.size
        scale = min(1, 300 / w); w, h = int(w * scale), int(h * scale)
        canvas = Image.new('RGB', (columns * w, ((len(rows) + columns - 1) // columns) * (h + 22)), '#f5f1e8')
        draw = ImageDraw.Draw(canvas)
        for i, r in enumerate(rows):
            x, y = (i % columns) * w, (i // columns) * (h + 22)
            canvas.paste(Image.open(out / r['file']).convert('RGB').resize((w, h)), (x, y))
            draw.text((x + 6, y + h + 3), f"f{r['frame']} {r['time']:.3f}s", fill='#302c25', font=font)
        canvas.save(out / f'{view}-sheet.jpg', quality=90)
    print('SHEET', out)


if __name__ == '__main__':
    main()
