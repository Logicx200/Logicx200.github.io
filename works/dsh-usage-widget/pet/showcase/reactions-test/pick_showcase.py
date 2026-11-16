"""Pick each state's most distinctive frame from the task16 burst and report the numbers.

For every state the shooter captured a burst around the motion clip's peak.  This script
  * measures the baseline from the idle burst (frame-to-frame jitter: pixel + silhouette),
  * picks, per state, the burst frame whose SILHOUETTE is farthest from the idle reference
    (that is the state's most visible moment - no runtime change, no frozen pose),
  * writes it to pet/showcase/state-<state>.png (the deliverable the docs embed),
  * then reports the pairwise differences of the final 11 images against the baseline,
    with BOTH metrics: raw pixels (the lead's metric) and silhouette (the gate's metric).
"""
import json
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
BURSTS = HERE / 'shoot-bursts'
SHOW = HERE.parent
STATES = SHOW / 'states.json'


def load(p):
    return np.asarray(Image.open(p).convert('RGB'), dtype=np.int16)


def sil(img):
    mx = img.max(axis=2).astype(np.float32)
    mn = img.min(axis=2).astype(np.float32)
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1), 0)
    return (mx > 60) & (sat > 0.12)


def shape(img):
    m = sil(img)
    ys, xs = np.nonzero(m)
    if len(xs) == 0:
        return {'w': 0, 'h': 0, 'area': 0, 'cx': 0.0, 'cy': 0.0, 'mask': m}
    return {'w': int(xs.max() - xs.min() + 1), 'h': int(ys.max() - ys.min() + 1), 'area': int(m.sum()),
            'cx': float(xs.mean()), 'cy': float(ys.mean()), 'mask': m}


def sdist(a, b):
    return float(abs(a['w'] - b['w']) + abs(a['h'] - b['h']) + abs(a['area'] - b['area']) / 50.0
                 + abs(a['cx'] - b['cx']) + abs(a['cy'] - b['cy']))


def pix_changed(a, b, mask, thr=8):
    d = np.abs(a - b).max(axis=2)
    return float((d[mask] > thr).mean()) * 100.0


def main():
    idle_files = sorted([p for p in BURSTS.glob('idle-*.png') if not p.name.endswith('-wide.png')])
    if len(idle_files) < 4:
        print('no idle burst in', BURSTS)
        return 1
    idle_imgs = [load(p) for p in idle_files]
    idle_shapes = [shape(i) for i in idle_imgs]
    ref_img = np.mean(np.stack(idle_imgs), axis=0)
    ref_shape = idle_shapes[0]
    mask = sil(ref_img)

    # baselines, measured on the SAME session/background as the shots (that is the point)
    noise_pixels = float(np.median([pix_changed(a, b, mask) for a, b in zip(idle_imgs, idle_imgs[1:])]))
    noise_whole = float(np.median([pix_changed(a, b, np.ones_like(mask)) for a, b in zip(idle_imgs, idle_imgs[1:])]))
    noise_sil = float(np.median([sdist(a, b) for a, b in zip(idle_shapes, idle_shapes[1:])]))

    names = [json.loads(s)['state'] for s in [STATES.read_text(encoding='utf-8-sig')]][0] if False else None
    plan = json.loads(STATES.read_text(encoding='utf-8-sig'))
    picked = {}
    rows = []
    for entry in plan:
        st = entry['state']
        files = sorted([p for p in BURSTS.glob(f'{st}-*.png') if not p.name.endswith('-wide.png')])
        if not files:
            rows.append({'state': st, 'error': 'no burst'})
            continue
        best = None
        for p in files:
            img = load(p)
            d = sdist(ref_shape, shape(img))
            if best is None or d > best[0]:
                best = (d, p, img)
        d, p, img = best
        dst = SHOW / f'state-{st}.png'
        wide = p.with_name(p.stem + '-wide.png')
        shutil.copyfile(wide if wide.exists() else p, dst)
        picked[st] = {'burstFrames': len(files), 'chosen': p.name, 'silhouetteDistance': round(d, 2),
                      'xNoiseSilhouette': round(d / noise_sil, 2) if noise_sil else None,
                      'pixelVsIdleOnCharacter': round(pix_changed(ref_img, img, mask), 2),
                      'pixelVsIdleWholeCrop': round(pix_changed(ref_img, img, np.ones_like(mask)), 2),
                      'writing': str(dst)}
        rows.append({'state': st, 'chosen': p.name, 'd': round(d, 2),
                     'x': round(d / noise_sil, 2) if noise_sil else None,
                     'pixChar': round(pix_changed(ref_img, img, mask), 2),
                     'pixWhole': round(pix_changed(ref_img, img, np.ones_like(mask)), 2)})

    # pairwise on the final 11 images
    # pairwise on the CHOSEN TIGHT frames (same crop as the baseline; the shipped images
    # are the wide panel+character view and are not comparable with a 225x195 reference)
    final = {st: load(BURSTS / v['chosen']) for st, v in picked.items() if 'chosen' in v}
    pairs_pix, pairs_sil, pairs_sil_rel = [], [], []
    keys = sorted(final)
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            pa, pb = final[a], final[b]
            c = pix_changed(pa, pb, np.ones_like(mask))
            s = sdist(shape(pa), shape(pb))
            pairs_pix.append({'a': a, 'b': b, 'pixelWhole': round(c, 2)})
            pairs_sil.append({'a': a, 'b': b, 'silhouette': round(s, 2)})
            pairs_sil_rel.append(s / noise_sil if noise_sil else 0)
    worst_pix = min(pairs_pix, key=lambda r: r['pixelWhole'])
    worst_sil = min(pairs_sil, key=lambda r: r['silhouette'])
    report = {
        'baseline': {'idleFrames': len(idle_imgs), 'pixelNoiseOnCharacter': round(noise_pixels, 2),
                     'pixelNoiseWholeCrop': round(noise_whole, 2), 'silhouetteJitter': round(noise_sil, 2)},
        'picked': picked,
        'pairwise': {'pairs': len(pairs_pix), 'pixelWholeMean': round(float(np.mean([r['pixelWhole'] for r in pairs_pix])), 2),
                     'pixelWholeWorst': worst_pix,
                     'silhouetteMean': round(float(np.mean([r['silhouette'] for r in pairs_sil])), 2),
                     'silhouetteWorst': worst_sil,
                     'silhouetteWorstXBaseline': round(min(pairs_sil_rel), 2)},
    }
    report['passPixelAboveBaseline'] = bool(report['pairwise']['pixelWholeWorst']['pixelWhole'] > noise_whole)
    report['passSilhouette2x'] = bool(report['pairwise']['silhouetteWorstXBaseline'] >= 2.0)
    (HERE / 'showcase-pairs-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')

    lines = ['=== 11 showcase states, re-shot at the motion peak (task-15 §6.1) ===',
             f"baseline (idle burst, {len(idle_imgs)} frames): pixels on her {noise_pixels:.2f}%  whole crop {noise_whole:.2f}%  silhouette jitter {noise_sil:.2f}",
             '',
             'per state, the chosen burst frame:',
             '%-12s %-14s %8s %7s %9s %9s' % ('state', 'chosen', 'sil.dist', 'x jitter', 'pix(char)', 'pix(whole)')]
    for r in rows:
        if 'error' in r:
            lines.append('%-12s %s' % (r['state'], r['error']))
        else:
            lines.append('%-12s %-14s %8.2f %7s %9.2f %9.2f' % (r['state'], r['chosen'], r['d'], r['x'], r['pixChar'], r['pixWhole']))
    pw = report['pairwise']
    lines += ['', f"pairwise over {pw['pairs']} image pairs:",
              f"  pixels   : mean {pw['pixelWholeMean']}%   worst {pw['pixelWholeWorst']['pixelWhole']}% ({pw['pixelWholeWorst']['a']} vs {pw['pixelWholeWorst']['b']})"
              f"   -> {'ABOVE' if report['passPixelAboveBaseline'] else 'BELOW'} the {noise_whole:.2f}% baseline",
              f"  silhouette: mean {pw['silhouetteMean']}   worst {pw['silhouetteWorst']['silhouette']} ({pw['silhouetteWorst']['a']} vs {pw['silhouetteWorst']['b']})"
              f" = {pw['silhouetteWorstXBaseline']}x jitter -> {'PASS' if report['passSilhouette2x'] else 'FAIL'} (bar 2x)"]
    txt = '\n'.join(lines)
    (HERE / 'showcase-pairs-report.txt').write_text(txt, encoding='utf-8')
    print(txt)
    return 0


if __name__ == '__main__':
    sys.exit(main())
