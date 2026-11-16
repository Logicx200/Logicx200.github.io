"""Visibility analysis for the pet's reaction layer (task-14).

Answers the only question that matters: can a human SEE the reactions?  Method:
  * baseline = consecutive frames captured while the state did not change -> that is
    her inherent breathing/blinking noise;
  * production = frames captured while real tool calls were in flight (the state machine
    stayed in one state, so the signal-level face/prop change is what we compare);
  * forced = the dev channel driving each state on purpose (SUPPLEMENTARY: it proves the
    page can render a state, it does NOT prove production renders it).

Outputs (all under pet/showcase/reactions-test):
  visibility-report.json / .txt
  ../reactions-contact-sheet.png   labelled side-by-side tiles
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
SHOWCASE = HERE.parent
FRAMES = HERE / 'frames'

NOISE_PIXEL = 8          # a channel delta above this counts as "changed"
FACE_BAND = 0.45         # the head is the top 45% of the crop

FORCED_STATE = {
    'f-idle': 'idle', 'f-reading': 'reading', 'f-writing': 'writing', 'f-running': 'running',
    'f-thinking': 'thinking', 'f-error': 'error', 'f-celebrating': 'celebrating',
    'f-listening': 'listening', 'f-team': 'team', 'f-stale': 'stale', 'f-offline': 'offline',
    'f-decor-glasses': 'idle+glassesRound', 'f-decor-phone': 'idle+phone',
    'f-act-love': 'idle+act(love)', 'f-act-selfie': 'idle+act(selfie)',
    'f-released': 'released->production',
}
CN = {
    'idle': '空闲', 'stale': '卡住', 'error': '报错', 'celebrating': '收工庆祝', 'listening': '听主人说',
    'team': '找队友', 'reading': '看书', 'writing': '写代码', 'running': '跑命令', 'thinking': '想事情',
    'offline': '离线',
}


def load_index(tag):
    p = HERE / f'{tag}-index.json'
    if not p.exists():
        return None
    # the capture script writes with Set-Content -Encoding UTF8, which adds a BOM
    return json.loads(p.read_text(encoding='utf-8-sig'))


def load(name):
    return np.asarray(Image.open(FRAMES / name).convert('RGB'), dtype=np.int16)


def diff_stats(a, b, y0=0.0, y1=1.0):
    h = a.shape[0]
    lo, hi = int(h * y0), max(int(h * y0) + 1, int(h * y1))
    d = np.abs(a[lo:hi] - b[lo:hi]).max(axis=2)
    return {
        'meanAbsDiff': round(float(d.mean()), 3),
        'changedPct': round(float((d > NOISE_PIXEL).mean()) * 100.0, 3),
        'maxDiff': int(d.max()),
    }


def read_panel_bottom():
    """screen y of the panel's bottom edge, and the crop's top y (for the clean band)."""
    geo = HERE.parents[1] / 'renderer' / 'panel-geometry.json'
    try:
        doc = json.loads(geo.read_text(encoding='utf-8-sig'))
        page = float(doc.get('panelBottomPage'))
    except Exception:
        return None, None, None
    return page, None, None


def main():
    report = {'noisePixelThreshold': NOISE_PIXEL, 'faceBand': FACE_BAND, 'runs': {}, 'comparisons': []}
    base = load_index('base')
    prod = load_index('prod')
    forced = load_index('forced')

    # ---- geometry: which rows of the crop are the character alone (panel excluded) ----
    panel_bottom_page, _, _ = read_panel_bottom()
    clean0 = 0.0
    panel_band = None
    try:
        meta = (base or prod or forced)[0]
        cx, cy, cw, ch = [int(v) for v in str(meta['crop']).split(',')]
        win = json.loads((HERE.parents[1] / 'host' / 'model.json').read_text(encoding='utf-8-sig'))['window']
        if panel_bottom_page is not None:
            panel_screen_y = float(win['y']) + panel_bottom_page
            clean0 = max(0.0, min(0.99, (panel_screen_y - cy) / float(ch)))
            panel_band = (0.0, clean0)
        report['cleanBand'] = {'startFrac': round(clean0, 3), 'panelBottomScreenY': (float(win['y']) + panel_bottom_page) if panel_bottom_page is not None else None,
                               'cropTopY': cy}
    except Exception as exc:      # noqa: BLE001
        report['cleanBand'] = {'error': repr(exc)}

    # ---------------- baseline noise ----------------
    noise = None
    base_imgs = []
    if base and len(base) >= 3:
        base_imgs = [load(f['file']) for f in base]
        full = [diff_stats(a, b) for a, b in zip(base_imgs, base_imgs[1:])]
        face = [diff_stats(a, b, 0.0, FACE_BAND) for a, b in zip(base_imgs, base_imgs[1:])]
        clean = [diff_stats(a, b, clean0, 1.0) for a, b in zip(base_imgs, base_imgs[1:])]
        panel = [diff_stats(a, b, 0.0, clean0) for a, b in zip(base_imgs, base_imgs[1:])] if clean0 > 0.02 else []
        noise = {
            'frames': len(base_imgs),
            'constantState': sorted({f"{f['state']}/{f['pose']}" for f in base}),
            'wholeFrame': {
                'changedPctMedian': round(float(np.median([p['changedPct'] for p in full])), 3),
                'changedPctMax': round(float(np.max([p['changedPct'] for p in full])), 3),
                'meanAbsDiffMedian': round(float(np.median([p['meanAbsDiff'] for p in full])), 3),
            },
            'faceRegion': {
                'changedPctMedian': round(float(np.median([p['changedPct'] for p in face])), 3),
                'changedPctMax': round(float(np.max([p['changedPct'] for p in face])), 3),
                'meanAbsDiffMedian': round(float(np.median([p['meanAbsDiff'] for p in face])), 3),
            },
            'characterOnlyBand': {
                'rows': f'{clean0:.2f} .. 1.0 of the crop',
                'changedPctMedian': round(float(np.median([p['changedPct'] for p in clean])), 3),
                'changedPctMax': round(float(np.max([p['changedPct'] for p in clean])), 3),
                'meanAbsDiffMedian': round(float(np.median([p['meanAbsDiff'] for p in clean])), 3),
            },
            'panelBandBehindHer': {
                'rows': f'0.00 .. {clean0:.2f} of the crop',
                'changedPctMedian': round(float(np.median([p['changedPct'] for p in panel])), 3) if panel else None,
                'changedPctMax': round(float(np.max([p['changedPct'] for p in panel])), 3) if panel else None,
            } if panel else {},
        }
        report['noise'] = noise
        report['runs']['baseline'] = {'tag': 'base', 'frames': len(base), 'states': noise['constantState']}

    # ---------------- production: group by state/pose AND by tool ----------------
    prod_by_state, prod_by_tool = {}, {}
    if prod:
        for f in prod:
            p = FRAMES / f['file']
            if not p.exists():
                continue
            prod_by_state.setdefault(f"{f['state']}/{f['pose']}", []).append(f)
            prod_by_tool.setdefault(f"{f['tool']}/{f['toolPhase']}", []).append(f)
        report['runs']['production'] = {
            'tag': 'prod', 'frames': len(prod),
            'groups': {k: len(v) for k, v in sorted(prod_by_state.items(), key=lambda kv: -len(kv[1]))},
            'toolGroups': {k: len(v) for k, v in sorted(prod_by_tool.items(), key=lambda kv: -len(kv[1]))},
            'timeline': [{'at': f['at'], 'state': f['state'], 'pose': f['pose'], 'label': f['stateLabel'],
                          'tool': f['tool'], 'toolPhase': f['toolPhase']} for f in prod],
        }

    # ---------------- forced groups ----------------
    forced_by_label = {}
    if forced:
        for f in forced:
            if (FRAMES / f['file']).exists():
                forced_by_label.setdefault(f['label'], []).append(f)
        report['runs']['forced'] = {'tag': 'forced', 'frames': len(forced), 'labels': [f['label'] for f in forced]}

    def add(name, kind, trigger, ref_label, ref_img, img, meta):
        rec = {
            'name': name, 'kind': kind, 'trigger': trigger, 'reference': ref_label, 'frame': meta,
            'wholeFrame': diff_stats(ref_img, img),
            'faceRegion': diff_stats(ref_img, img, 0.0, FACE_BAND),
            'characterOnlyBand': diff_stats(ref_img, img, clean0, 1.0),
        }
        if noise:
            nf = noise['wholeFrame']['changedPctMedian'] or 0.0
            na = noise['faceRegion']['changedPctMedian'] or 0.0
            nc = noise.get('characterOnlyBand', {}).get('changedPctMedian') or 0.0
            rec['xBaselineWhole'] = round(rec['wholeFrame']['changedPct'] / nf, 2) if nf > 0 else None
            rec['xBaselineFace'] = round(rec['faceRegion']['changedPct'] / na, 2) if na > 0 else None
            rec['xBaselineClean'] = round(rec['characterOnlyBand']['changedPct'] / nc, 2) if nc > 0 else None
        report['comparisons'].append(rec)
        return rec

    # baseline self-check: frame 1 vs frame 2 must land at ~1x
    if noise:
        add('baseline self-check (frame1 vs frame2)', 'baseline', 'nothing changed',
            'base frame 1', base_imgs[0], base_imgs[1],
            {'state': base[1]['state'], 'pose': base[1]['pose'], 'label': 'base frame 2'})

    # production: the state never changed, so compare TOOL GROUPS (same state!)
    prod_ref_img = None
    if prod_by_tool:
        top_tool = max(prod_by_tool.items(), key=lambda kv: len(kv[1]))
        prod_ref_img = load(top_tool[1][0]['file'])
        report['productionToolReference'] = {'toolKey': top_tool[0], 'frames': len(top_tool[1]),
                                             'stateKey': f"{top_tool[1][0]['state']}/{top_tool[1][0]['pose']}"}
        for tk, frames in sorted(prod_by_tool.items(), key=lambda kv: -len(kv[1])):
            if tk == top_tool[0]:
                continue
            f = frames[0]
            add(f'production: tool {tk} (state kept constant)', 'production',
                f"real tool call {tk} captured mid-flight",
                f"production reference tool {top_tool[0]} in the same state",
                prod_ref_img, load(f['file']),
                {'state': f['state'], 'pose': f['pose'], 'label': f['label'], 'at': f['at'], 'tool': f['tool']})
        # also: different states inside the production run, if any
        for key, frames in sorted(prod_by_state.items(), key=lambda kv: -len(kv[1])):
            if key == report['productionToolReference']['stateKey']:
                continue
            f = frames[0]
            add(f'production: state {key}', 'production', f"real event -> {key}",
                f"production reference state {report['productionToolReference']['stateKey']}",
                prod_ref_img, load(f['file']),
                {'state': f['state'], 'pose': f['pose'], 'label': f['label'], 'at': f['at'], 'tool': f['tool']})

    # forced comparisons (supplementary)
    if noise and 'f-idle' in forced_by_label:
        idle_img = load(forced_by_label['f-idle'][0]['file'])
        for label, frames in forced_by_label.items():
            if label == 'f-idle':
                continue
            f = frames[0]
            add(f'forced: {label}', 'forced', f['trigger'], 'forced idle (f-idle)', idle_img, load(f['file']),
                {'state': FORCED_STATE.get(label, f['state']), 'pose': f['pose'], 'label': label,
                 'productionStateAtThatMoment': f['state']})

    # ---------------- cross-check: the accepted 11-state showcase images -------------
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

    # ---------------- contact sheet ----------------
    def font(size):
        for cand in (r'C:\Windows\Fonts\msyh.ttc', r'C:\Windows\Fonts\msyhbd.ttc', r'C:\Windows\Fonts\simhei.ttf'):
            try:
                return ImageFont.truetype(cand, size)
            except Exception:
                continue
        return ImageFont.load_default()

    f_head, f_label, f_sub = font(22), font(15), font(12)
    tiles = []   # (title, image, sub, is_reference)
    if base_imgs:
        tiles.append(('基线 baseline（状态不变 19 帧）', base_imgs[0],
                      f"帧间噪声: 整帧 {noise['wholeFrame']['changedPctMedian']}% / 脸区 {noise['faceRegion']['changedPctMedian']}% 像素改变",
                      True))
    for cmp in report['comparisons']:
        if cmp['kind'] == 'baseline':
            continue
        img = None
        if cmp['kind'] == 'production':
            want = cmp['frame'].get('at')
            for f in prod:
                if f['at'] == want:
                    img = load(f['file'])
                    break
        else:
            lbl = cmp['frame'].get('label')
            if lbl in forced_by_label:
                img = load(forced_by_label[lbl][0]['file'])
        if img is None:
            continue
        st = str(cmp['frame'].get('state') or '')
        cn = CN.get(st.split('+')[0], '')
        title = f"{cmp['frame'].get('label')} · {st} {cn}"
        sub = (f"vs {cmp['reference']}: 整帧 {cmp['wholeFrame']['changedPct']}%({cmp['xBaselineWhole']}×)"
               f" 身体带 {cmp['characterOnlyBand']['changedPct']}%({cmp['xBaselineClean']}×)")
        tiles.append((title, img, sub, False))

    if tiles:
        cols = 4
        th, tw = tiles[0][1].shape[0], tiles[0][1].shape[1]
        pad, cap, head = 10, 52, 62
        rows = (len(tiles) + cols - 1) // cols
        sheet = Image.new('RGB', (cols * (tw + pad) + pad, head + rows * (th + cap + pad) + pad), (16, 18, 22))
        dr = ImageDraw.Draw(sheet)
        dr.text((pad, 10), 'reactions visibility sheet · 生产帧 + 强制帧（同一裁剪，人物 225x195）', font=f_head, fill=(230, 237, 243))
        dr.text((pad, 38), '每格：状态 / 触发源 · 与参照帧的像素差（整帧 / 脸区）· 相当于她自身基线噪声的倍数',
                font=f_sub, fill=(160, 170, 180))
        for i, (title, img, sub, is_ref) in enumerate(tiles):
            r, c = divmod(i, cols)
            x = pad + c * (tw + pad)
            y = head + r * (th + cap + pad)
            sheet.paste(Image.fromarray(img.astype(np.uint8)), (x, y))
            dr.rectangle([x, y, x + tw - 1, y + th - 1], outline=(90, 190, 255) if is_ref else (60, 68, 78), width=2 if is_ref else 1)
            dr.text((x, y + th + 4), title[:44], font=f_label, fill=(230, 237, 243))
            dr.text((x, y + th + 24), sub[:64], font=f_sub, fill=(240, 180, 90))
        # ---- strip: the 11 accepted showcase images, same scale, for the naked eye ----
        if show_imgs:
            strip_h = 210
            thumbs = []
            for k, img in sorted(show_imgs.items()):
                im = Image.fromarray(img.astype(np.uint8))
                w = max(1, int(im.width * strip_h / im.height))
                thumbs.append((k, im.resize((w, strip_h))))
            sw = sum(t[1].width + 6 for t in thumbs) + pad
            sh = strip_h + 58
            strip = Image.new('RGB', (max(sheet.width, sw), sheet.height + sh), (16, 18, 22))
            strip.paste(sheet, (0, 0))
            dr2 = ImageDraw.Draw(strip)
            y0 = sheet.height + 6
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
        out = SHOWCASE / 'reactions-contact-sheet.png'
        sheet.save(out)
        report['contactSheet'] = str(out)

    (HERE / 'visibility-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')

    lines = ['=== pet reaction visibility (task-14) ===']
    if noise:
        lines.append(f"baseline: {noise['frames']} frames, state constant {noise['constantState']}")
        lines.append(f"  noise whole frame: {noise['wholeFrame']['changedPctMedian']}% pixels changed (max {noise['wholeFrame']['changedPctMax']}%)")
        lines.append(f"  noise face band  : {noise['faceRegion']['changedPctMedian']}% pixels changed (max {noise['faceRegion']['changedPctMax']}%)")
        lines.append(f"  noise character-only band (rows below the panel): {noise['characterOnlyBand']['changedPctMedian']}% (max {noise['characterOnlyBand']['changedPctMax']}%)")
        if noise.get('panelBandBehindHer'):
            lines.append(f"  noise panel band behind her: {noise['panelBandBehindHer']['changedPctMedian']}% (max {noise['panelBandBehindHer']['changedPctMax']}%)")
    if 'production' in report['runs']:
        lines.append('production frames: ' + json.dumps(report['runs']['production']['groups'], ensure_ascii=False))
        lines.append('production tool groups: ' + json.dumps(report['runs']['production']['toolGroups'], ensure_ascii=False))
    lines.append('')
    lines.append('%-56s %8s %7s %8s %7s %8s %7s' % ('comparison', 'whole%', 'xnoise', 'face%', 'xnoise', 'clean%', 'xnoise'))
    for cmp in report['comparisons']:
        lines.append('%-56s %8.3f %7s %8.3f %7s %8.3f %7s' % (
            cmp['name'][:56], cmp['wholeFrame']['changedPct'], cmp['xBaselineWhole'],
            cmp['faceRegion']['changedPct'], cmp['xBaselineFace'],
            cmp['characterOnlyBand']['changedPct'], cmp['xBaselineClean']))
    if 'contactSheet' in report:
        lines.append('')
        lines.append('contact sheet: ' + report['contactSheet'])
    txt = '\n'.join(lines)
    (HERE / 'visibility-report.txt').write_text(txt, encoding='utf-8')
    print(txt)


if __name__ == '__main__':
    sys.exit(main())
