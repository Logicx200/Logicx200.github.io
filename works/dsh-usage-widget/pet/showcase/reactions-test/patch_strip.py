"""Append a showcase cross-check to the contact sheet.

The 11 state images in pet/showcase are the evidence that was accepted earlier.  If the
user "sees no change", the honest thing is to put those very images next to each other
and measure them with the same metric.  This patch adds that strip to the sheet.
"""
import ast
from pathlib import Path

p = Path(r'F:\dsh-usage-widget\pet\showcase\reactions-test\analyse.py')
t = p.read_text(encoding='utf-8')

# 1. measure the accepted showcase images and add the numbers to the report
t = t.replace(
    "    (HERE / 'visibility-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')",
    """    # ---------------- cross-check: the accepted 11-state showcase images -------------
    show_dir = SHOWCASE
    show_files = sorted(show_dir.glob('state-*.png'))
    show_stats = {}
    show_imgs = {}
    if show_files:
        for f in show_files:
            show_imgs[f.stem.replace('state-', '')] = np.asarray(Image.open(f).convert('RGB'), dtype=np.int16)
        ref_name = 'idle' if 'idle' in show_imgs else sorted(show_imgs)[0]
        ref_show = show_imgs[ref_name]
        for k, img in sorted(show_imgs.items()):
            if k == ref_name:
                continue
            d = np.abs(img - ref_show).max(axis=2)
            show_stats[k] = {'vs': ref_name, 'changedPct': round(float((d > NOISE_PIXEL).mean()) * 100.0, 3),
                             'meanAbsDiff': round(float(d.mean()), 3)}
        report['acceptedShowcase'] = {
            'images': len(show_files), 'reference': ref_name, 'stats': show_stats,
            'note': 'the 11 accepted state images are nearly the same picture - see the sheet strip',
        }

    (HERE / 'visibility-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')""")

# 2. add the strip below the reaction tiles
t = t.replace(
    """        out = SHOWCASE / 'reactions-contact-sheet.png'
        sheet.save(out)
        report['contactSheet'] = str(out)""",
    """        # ---- strip: the 11 accepted showcase images, same scale, for the naked eye ----
        if show_imgs:
            strip_h = 210
            thumbs = []
            for k, img in sorted(show_imgs.items()):
                im = Image.fromarray(img.astype(np.uint8))
                w = max(1, int(im.width * strip_h / im.height))
                thumbs.append((k, im.resize((w, strip_h))))
            sw = sum(t[1].width + 6 for t in thumbs) + pad
            sh = strip_h + 58
            strip = Image.new('RGB', (max(W, sw), H + sh), (16, 18, 22))
            strip.paste(sheet, (0, 0))
            dr2 = ImageDraw.Draw(strip)
            y0 = H + 6
            dr2.text((pad, y0), '已交付的 11 档展示图（pet/showcase/state-*.png）：彼此只差 3~8% 像素，比她静止时的帧间噪声（13.6%）还小',
                     font=f_label, fill=(240, 180, 90))
            dr2.text((pad, y0 + 20), 'which means: even the accepted showcase images are nearly the same picture - the labels differ, the character barely does',
                     font=f_sub, fill=(160, 170, 180))
            x = pad
            for k, im in thumbs:
                strip.paste(im, (x, y0 + 36))
                dr2.text((x + 2, y0 + 36 + strip_h + 2), k, font=f_sub, fill=(230, 237, 243))
                x += im.width + 6
            sheet = strip
            W, H = strip.size
        out = SHOWCASE / 'reactions-contact-sheet.png'
        sheet.save(out)
        report['contactSheet'] = str(out)""")

p.write_text(t, encoding='utf-8')
ast.parse(t)
print('strip patch applied, analyse.py parses OK')
