"""Build the task-15 contact sheet: idle vs the new visible reactions, plus the freshly
re-shot 11-state strip.  Every tile carries its masked pixel difference and the multiple
of the measured baseline noise, so the sheet is both the eyeball evidence and the numbers.
"""
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

RT = Path(__file__).resolve().parent
SWEEP = RT / 'motion-sweep'
SHOW = RT.parent
NOISE = 8

CN = {'idle': '空闲', 'running': '跑命令', 'reading': '查资料', 'writing': '写文件', 'error': '出错了',
      'celebrating': '收工啦', 'listening': '听主人说', 'team': '团队协作', 'stale': '数据过期',
      'offline': '离线', 'thinking': '想事情'}


def load(p):
    return np.asarray(Image.open(p).convert('RGB'), dtype=np.int16)


def mask_of(img):
    mx = img.max(axis=2).astype(np.float32)
    mn = img.min(axis=2).astype(np.float32)
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1), 0)
    return (mx > 60) & (sat > 0.12)


def changed(a, b, m, thr=NOISE):
    d = np.abs(a - b).max(axis=2)
    return float((d[m] > thr).mean()) * 100.0


def font(sz):
    for c in (r'C:\Windows\Fonts\msyh.ttc', r'C:\Windows\Fonts\simhei.ttf'):
        try:
            return ImageFont.truetype(c, sz)
        except Exception:
            pass
    return ImageFont.load_default()


idle_files = sorted(SWEEP.glob('idle-*.png'))
idle = [load(p) for p in idle_files]
ref = np.mean(np.stack(idle), axis=0)
m = mask_of(ref)
noise = float(np.median([changed(a, b, m) for a, b in zip(idle, idle[1:])]))

tiles = [('idle 空闲（基线）', idle[0], f"帧间噪声 {noise:.1f}% 像素改变（人物区）")]
for name, label in [('run-0.3s', 'running 跑命令 + 喷水动作 t+0.3s'),
                    ('run-0.7s', 'running t+0.7s'),
                    ('run-1.2s', 'running t+1.2s'),
                    ('run-1.8s', 'running t+1.8s'),
                    ('run-2.6s', 'running t+2.6s'),
                    ('after-release', '释放后回到生产状态')]:
    p = SWEEP / f'{name}.png'
    if p.exists():
        img = load(p)
        c = changed(ref, img, m)
        tiles.append((label, img, f"与 idle 差 {c:.1f}% 像素 = {c / noise:.2f}× 噪声"))

f_head, f_lab, f_sub = font(22), font(15), font(12)
cols = 4
th, tw = tiles[0][1].shape[0], tiles[0][1].shape[1]
pad, cap, head = 10, 54, 64
rows = (len(tiles) + cols - 1) // cols
W, H = cols * (tw + pad) + pad, head + rows * (th + cap + pad) + pad
sheet = Image.new('RGB', (W, H), (16, 18, 22))
dr = ImageDraw.Draw(sheet)
dr.text((pad, 10), 'task-15 · idle 与「跑命令 + 喷水动作」同一裁剪并排（人物 225x195）', font=f_head, fill=(230, 237, 243))
dr.text((pad, 38), '左边是基线；右边是强制 running 后同一次动作的不同时刻。数字 = 与 idle 的像素差 / 她自身帧间噪声。',
        font=f_sub, fill=(160, 170, 180))
for i, (title, img, sub) in enumerate(tiles):
    r, c = divmod(i, cols)
    x, y = pad + c * (tw + pad), head + r * (th + cap + pad)
    sheet.paste(Image.fromarray(img.astype(np.uint8)), (x, y))
    dr.rectangle([x, y, x + tw - 1, y + th - 1], outline=(90, 190, 255) if i == 0 else (60, 68, 78),
                 width=2 if i == 0 else 1)
    dr.text((x, y + th + 4), title[:42], font=f_lab, fill=(230, 237, 243))
    dr.text((x, y + th + 26), sub[:62], font=f_sub, fill=(240, 180, 90))

# the freshly re-shot 11-state strip
show = sorted(SHOW.glob('state-*.png'))
if show:
    sh = 200
    thumbs = []
    for p in show:
        im = Image.open(p).convert('RGB')
        w = max(1, int(im.width * sh / im.height))
        thumbs.append((p.stem.replace('state-', ''), im.resize((w, sh))))
    sw = sum(t[1].width + 6 for t in thumbs) + pad
    strip = Image.new('RGB', (max(W, sw), H + sh + 60), (16, 18, 22))
    strip.paste(sheet, (0, 0))
    d2 = ImageDraw.Draw(strip)
    y0 = H + 6
    d2.text((pad, y0), '重拍后的 11 档展示图（pet/showcase/state-*.png，含各自的状态动作时刻）',
            font=f_lab, fill=(240, 180, 90))
    d2.text((pad, y0 + 20), 'captured 1.6 s after the state change, i.e. inside the one-shot motion clip',
            font=f_sub, fill=(160, 170, 180))
    x = pad
    for name, im in thumbs:
        strip.paste(im, (x, y0 + 38))
        d2.text((x + 2, y0 + 38 + sh + 2), name, font=f_sub, fill=(230, 237, 243))
        x += im.width + 6
    sheet = strip

out = SHOW / 'reactions-contact-sheet.png'
sheet.save(out)
print('contact sheet ->', out, sheet.size)
print('baseline noise on the character mask: %.2f%%' % noise)
for t, _, s in tiles[1:]:
    print('  %-38s %s' % (t, s))
