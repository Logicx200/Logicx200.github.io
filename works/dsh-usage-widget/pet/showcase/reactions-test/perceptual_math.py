"""Perceptual (visibility) gate maths for verify-project.ps1.

Input : a frames index (JSON) produced by reactions-visibility.ps1 / perceptual-check.ps1
        plus the pet/showcase/state-*.png images.
Output: perceptual-report.json (+ .txt) with, for every reaction, the pixel difference
        against the idle reference measured on the WHOLE crop and on the FACE band, and
        that difference expressed as a multiple of the baseline frame-to-frame noise
        (captured while the state was constant - her breathing/blinking).

A reaction is "visible" only if it clears VISIBLE_MULT x the baseline noise.  The same
bar is applied to the accepted 11-state showcase images (pairwise), because those are the
pictures a human actually looks at.

usage: python perceptual_math.py <frames-index.json> [<out-dir>]
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
FRAMES = HERE / 'frames'
NOISE_PIXEL = 8
FACE_BAND = 0.45
VISIBLE_MULT = 2.0


def load(path):
    return np.asarray(Image.open(path).convert('RGB'), dtype=np.int16)


def changed_pct(a, b, y0=0.0, y1=1.0):
    h = a.shape[0]
    lo, hi = int(h * y0), max(int(h * y0) + 1, int(h * y1))
    d = np.abs(a[lo:hi] - b[lo:hi]).max(axis=2)
    return float((d > NOISE_PIXEL).mean()) * 100.0


def mean_index(imgs):
    return np.mean(np.stack(imgs, axis=0), axis=0)


def main():
    idx_path = Path(sys.argv[1]) if len(sys.argv) > 1 else (HERE / 'perceptual-frames.json')
    doc = json.loads(idx_path.read_text(encoding='utf-8-sig'))
    frames = doc if isinstance(doc, list) else doc.get('frames', [])
    groups = {}
    for f in frames:
        p = FRAMES / f['file']
        if p.exists():
            groups.setdefault(f['group'], []).append(load(p))

    report = {'source': str(idx_path), 'noisePixelThreshold': NOISE_PIXEL, 'visibleMultiple': VISIBLE_MULT,
              'groups': {k: len(v) for k, v in groups.items()}, 'reactions': [], 'showcase': {}}
    if 'baseline' not in groups or len(groups['baseline']) < 4:
        report['pass'] = False
        report['reason'] = 'no baseline group with >=4 frames'
    else:
        base = groups['baseline']
        noise_face = float(np.median([changed_pct(a, b, 0.0, FACE_BAND) for a, b in zip(base, base[1:])]))
        noise_whole = float(np.median([changed_pct(a, b) for a, b in zip(base, base[1:])]))
        idle = mean_index(base)
        report['baseline'] = {'frames': len(base), 'noiseFacePct': round(noise_face, 3),
                              'noiseWholePct': round(noise_whole, 3)}
        ok = True
        for name, imgs in sorted(groups.items()):
            if name == 'baseline':
                continue
            ref = mean_index(imgs)
            face = changed_pct(idle, ref, 0.0, FACE_BAND)
            whole = changed_pct(idle, ref)
            mult_face = round(face / noise_face, 2) if noise_face > 0 else None
            mult_whole = round(whole / noise_whole, 2) if noise_whole > 0 else None
            visible = (mult_face is not None and mult_face >= VISIBLE_MULT)
            if not visible:
                ok = False
            report['reactions'].append({'name': name, 'frames': len(imgs),
                                        'faceChangedPct': round(face, 3), 'wholeChangedPct': round(whole, 3),
                                        'xNoiseFace': mult_face, 'xNoiseWhole': mult_whole, 'visible': visible})
        report['allReactionsVisible'] = ok

    # the accepted showcase images, pairwise, against the same bar
    show = sorted((HERE.parent).glob('state-*.png'))
    if show and 'baseline' in report:
        imgs = {p.stem.replace('state-', ''): load(p) for p in show}
        names = sorted(imgs)
        worst = None
        pairs = []
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                c = changed_pct(imgs[a], imgs[b])
                pairs.append({'a': a, 'b': b, 'changedPct': round(c, 3)})
                if worst is None or c < worst['changedPct']:
                    worst = {'a': a, 'b': b, 'changedPct': round(c, 3)}
        noise_whole = report['baseline']['noiseWholePct']
        report['showcase'] = {
            'images': len(imgs), 'pairs': len(pairs),
            'minPairChangedPct': worst,
            'xNoiseMinPair': round(worst['changedPct'] / noise_whole, 2) if noise_whole else None,
            'visible': bool(noise_whole and worst['changedPct'] >= VISIBLE_MULT * noise_whole),
        }
        report['allShowcasePairsVisible'] = report['showcase']['visible']

    report['pass'] = bool(report.get('allReactionsVisible') and report.get('allShowcasePairsVisible'))
    (HERE / 'perceptual-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')

    lines = ['=== perceptual (visibility) gate ===',
             f"frames index : {idx_path}",
             f"bar          : reaction face-band difference >= {VISIBLE_MULT}x the baseline noise"]
    if 'baseline' in report:
        lines.append(f"baseline     : {report['baseline']['frames']} frames, noise face {report['baseline']['noiseFacePct']}% / whole {report['baseline']['noiseWholePct']}%")
    for r in report['reactions']:
        lines.append('  %-18s face %7.3f%% = %5sx noise   whole %7.3f%% = %5sx   %s'
                     % (r['name'], r['faceChangedPct'], r['xNoiseFace'], r['wholeChangedPct'], r['xNoiseWhole'],
                        'VISIBLE' if r['visible'] else 'FAIL(<2x)'))
    if 'showcase' in report and report['showcase']:
        s = report['showcase']
        lines.append('  showcase     : %d images, %d pairs, worst pair %s changed %s%% = %sx noise -> %s'
                     % (s['images'], s['pairs'], s['minPairChangedPct'], s['minPairChangedPct']['changedPct'],
                        s['xNoiseMinPair'], 'VISIBLE' if s['visible'] else 'FAIL(<2x)'))
    lines.append('  RESULT       : ' + ('PASS' if report['pass'] else 'FAIL'))
    txt = '\n'.join(lines)
    (HERE / 'perceptual-report.txt').write_text(txt, encoding='utf-8')
    print(txt)


if __name__ == '__main__':
    sys.exit(main())
