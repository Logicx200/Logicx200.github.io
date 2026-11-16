"""Masked (character-only) perceptual maths - the honest measurement.

Why a mask: the crop around her overlaps the panel, and the panel's own UI (token
counters, job rows, progress) changes more pixels than her whole body.  Measuring the
raw crop therefore drowns every reaction in background noise (that was task-14's
methodological hole).  This script builds a character mask from the pixels themselves -
her art is bright and saturated, the panel is dark grey - excludes the label rectangle,
and reports the numbers on the mask only.  The mask is written out as a PNG so it can be
eyeballed instead of trusted.

usage: python perceptual_masked.py <dir-with-frames> [idle-prefix]
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
NOISE_PIXEL = 8
FACE_FRAC = 0.45
VISIBLE_MULT = 2.0


def load(p):
    return np.asarray(Image.open(p).convert('RGB'), dtype=np.int16)


def character_mask(img):
    """her pixels: bright enough AND saturated enough; the panel is dark grey."""
    mx = img.max(axis=2).astype(np.float32)
    mn = img.min(axis=2).astype(np.float32)
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1), 0)
    return (mx > 60) & (sat > 0.12)


def changed(a, b, mask, thr=NOISE_PIXEL):
    d = np.abs(a - b).max(axis=2)
    return float((d[mask] > thr).mean()) * 100.0


def main():
    d = Path(sys.argv[1]) if len(sys.argv) > 1 else (HERE / 'motion-sweep')
    idle = sorted(d.glob('idle-*.png'))
    others = [p for p in sorted(d.glob('*.png')) if not p.name.startswith('idle-')]
    if len(idle) < 3:
        print('need >=3 idle frames in', d)
        return 1
    imgs = [load(p) for p in idle]
    ref = np.mean(np.stack(imgs), axis=0)
    mask = character_mask(ref)
    h = mask.shape[0]
    face = np.zeros_like(mask)
    face[:int(h * FACE_FRAC)] = True
    face &= mask
    body = mask & ~face
    Image.fromarray((mask * 255).astype(np.uint8)).save(d / 'character-mask.png')

    noise_all = float(np.median([changed(a, b, mask) for a, b in zip(imgs, imgs[1:])]))
    noise_face = float(np.median([changed(a, b, face) for a, b in zip(imgs, imgs[1:])]))
    rows = []
    for p in others:
        img = load(p)
        row = {'frame': p.stem}
        for thr in (NOISE_PIXEL, 25, 40):
            n_all = float(np.median([changed(a, b, mask, thr) for a, b in zip(imgs, imgs[1:])]))
            n_face = float(np.median([changed(a, b, face, thr) for a, b in zip(imgs, imgs[1:])]))
            c_all, c_face, c_body = (changed(ref, img, mask, thr), changed(ref, img, face, thr),
                                     changed(ref, img, body, thr))
            row['thr%d' % thr] = {'noiseAll': round(n_all, 2), 'noiseFace': round(n_face, 2),
                                  'char': round(c_all, 2), 'face': round(c_face, 2), 'body': round(c_body, 2),
                                  'xFace': round(c_face / n_face, 2) if n_face else None,
                                  'visible': bool(n_face and c_face >= VISIBLE_MULT * n_face)}
        rows.append(row)
    out = {'dir': str(d), 'maskPixels': int(mask.sum()), 'maskPct': round(float(mask.mean()) * 100, 1),
           'facePixels': int(face.sum()), 'baselineNoiseOnCharacter': round(noise_all, 2),
           'baselineNoiseFace': round(noise_face, 2), 'bar': VISIBLE_MULT, 'frames': rows}
    (d / 'masked-report.json').write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
    lines = [f"=== masked (character-only) measurement in {d} ===",
             f"mask: {out['maskPixels']} px ({out['maskPct']}% of the crop), face band {out['facePixels']} px",
             f"baseline noise: on character {out['baselineNoiseOnCharacter']}%   face band {out['baselineNoiseFace']}%",
             f"bar: face-band difference >= {VISIBLE_MULT}x baseline"]
    for r in rows:
        parts = []
        for thr in (NOISE_PIXEL, 25, 40):
            b = r['thr%d' % thr]
            parts.append('thr%-2d face %5.2f%% = %5sx %s' % (thr, b['face'], b['xFace'],
                         'VISIBLE' if b['visible'] else '-'))
        lines.append('  %-14s %s' % (r['frame'], '  |  '.join(parts)))
    txt = '\n'.join(lines)
    (d / 'masked-report.txt').write_text(txt, encoding='utf-8')
    print(txt)
    return 0


if __name__ == '__main__':
    sys.exit(main())
