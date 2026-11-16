"""Zoomed pose comparison: is the POSE (not the label) visible at all?

Takes the forced frames captured back-to-back (so the panel behind her barely moved),
diffs them against each other and lays the crops out at 2x so the eye can judge the
thing the numbers cannot: whether a human notices.
"""
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
FRAMES = HERE / 'frames'
idx = json.loads((HERE / 'forced-index.json').read_text(encoding='utf-8-sig'))
by_label = {f['label']: f['file'] for f in idx}
order = [('f-idle', 'idle 空闲'), ('f-stale', 'sleepy 瞌睡'), ('f-thinking', 'thinking 想事情'),
         ('f-offline', 'offline 离线'), ('f-error', 'gloomy 沮丧/报错'), ('f-celebrating', 'happy 高兴/庆祝'),
         ('f-reading', 'reading 看书'), ('f-writing', 'scribble 写字'), ('f-running', 'sleeves 挽袖子')]

imgs = {}
for label, _ in order:
    if label in by_label:
        imgs[label] = np.asarray(Image.open(FRAMES / by_label[label]).convert('RGB'), dtype=np.int16)

ref = imgs['f-idle']
lines = []
lines.append('pairwise pixel difference against f-idle (forced back-to-back, ~2.6 s apart):')
for label, name in order:
    if label not in imgs or label == 'f-idle':
        continue
    d = np.abs(imgs[label] - ref).max(axis=2)
    lines.append('  %-16s changed %6.3f%%   mean %6.3f   max %3d' % (name, (d > 8).mean() * 100, d.mean(), d.max()))
# and between two clearly different poses
for a, b in (('f-stale', 'f-celebrating'), ('f-error', 'f-running'), ('f-offline', 'f-reading')):
    if a in imgs and b in imgs:
        d = np.abs(imgs[a] - imgs[b]).max(axis=2)
        lines.append('  %-16s vs %-16s changed %6.3f%%   mean %6.3f' % (a, b, (d > 8).mean() * 100, d.mean()))
txt = '\n'.join(lines)
(HERE / 'pose-zoom.txt').write_text(txt, encoding='utf-8')
print(txt)

scale = 2
tiles = [(name, Image.fromarray(imgs[label].astype(np.uint8)).resize(
    (imgs[label].shape[1] * scale, imgs[label].shape[0] * scale), Image.NEAREST)) for label, name in order if label in imgs]
cols = 3
tw, th = tiles[0][1].size
pad, cap, head = 10, 30, 70
rows = (len(tiles) + cols - 1) // cols
sheet = Image.new('RGB', (cols * (tw + pad) + pad, head + rows * (th + cap + pad)), (16, 18, 22))
dr = ImageDraw.Draw(sheet)
font_path = r'C:\Windows\Fonts\msyh.ttc'
try:
    f_head = ImageFont.truetype(font_path, 22)
    f_lab = ImageFont.truetype(font_path, 16)
    f_sub = ImageFont.truetype(font_path, 13)
except Exception:
    f_head = f_lab = f_sub = ImageFont.load_default()
dr.text((pad, 10), '强制姿势 2x 放大：同一裁剪，先看能不能一眼看出差别', font=f_head, fill=(230, 237, 243))
dr.text((pad, 40), txt.split('\n')[0], font=f_sub, fill=(160, 170, 180))
for i, (name, im) in enumerate(tiles):
    r, c = divmod(i, cols)
    x, y = pad + c * (tw + pad), head + r * (th + cap + pad)
    sheet.paste(im, (x, y))
    dr.rectangle([x, y, x + tw - 1, y + th - 1], outline=(60, 68, 78))
    dr.text((x, y + th + 4), name, font=f_lab, fill=(230, 237, 243))
sheet.save(HERE / 'pose-zoom.png')
print('saved', HERE / 'pose-zoom.png')
