"""task-15 E: the perceptual gate.

Measured quantity: the CHARACTER'S SILHOUETTE, not raw pixels.  Raw pixels are useless
here because a Live2D character jitters her own shading by >8/255 on ~30% of her pixels
every frame while looking perfectly still, which drowns every real reaction (task-14's
hole).  The silhouette - the bounding box and area of her art - is what the eye actually
notices: idle jitter moves it by ~0-3 px, a real gesture (raising an arm, a splash)
moves it by 10-30 px.

Gate: a reaction is PERCEPTUALLY VISIBLE only if its silhouette change is >= 2x the
baseline silhouette jitter.  mode=measure  : capture baseline + reaction frames now.
      mode=images   : judge a directory of images (e.g. the 11 showcase states).
      mode=dir <d>  : judge an existing frame directory (used to show the OLD state FAILs).

writes perceptual-gate.json / perceptual-gate.txt next to this file.
"""
import json
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
MULT = 2.0


def load(p):
    return np.asarray(Image.open(p).convert('RGB'), dtype=np.int16)


def silhouette(img):
    """her art: bright + saturated (the panel behind is dark grey)."""
    mx = img.max(axis=2).astype(np.float32)
    mn = img.min(axis=2).astype(np.float32)
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1), 0)
    m = (mx > 60) & (sat > 0.12)
    return m


def shape(img):
    m = silhouette(img)
    ys, xs = np.nonzero(m)
    if len(xs) == 0:
        return None
    return {'w': int(xs.max() - xs.min() + 1), 'h': int(ys.max() - ys.min() + 1),
            'area': int(m.sum()), 'cx': float(xs.mean()), 'cy': float(ys.mean())}


def shape_distance(a, b):
    if a is None or b is None:
        return None
    return float(abs(a['w'] - b['w']) + abs(a['h'] - b['h'])
                 + abs(a['area'] - b['area']) / 50.0
                 + abs(a['cx'] - b['cx']) + abs(a['cy'] - b['cy']))


def judge(pairs, shapes=None, label=''):
    """pairs: list of (reference_shape, frame_shape); returns the report fragment."""
    d = [shape_distance(x, y) for x, y in pairs]
    d = [v for v in d if v is not None]
    if not d:
        return None
    return {'label': label, 'frames': len(d), 'medianDistance': round(float(np.median(d)), 2),
            'maxDistance': round(float(np.max(d)), 2)}


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else 'measure'
    report = {'mode': mode, 'multiplier': MULT, 'at': time.strftime('%Y-%m-%d %H:%M:%S')}

    if mode == 'measure':
        frames = HERE / 'gate-frames'
        frames.mkdir(exist_ok=True)
        for f in frames.glob('*.png'):
            f.unlink()
        import subprocess
        cap = HERE.parent.parent / 'host' / 'experiments' / 'gate-capture.ps1'
        r = subprocess.run(['powershell.exe', '-NoProfile', '-File', str(cap), '-OutDir', str(frames)],
                           capture_output=True, text=True)
        if r.returncode != 0:
            report['error'] = (r.stderr or r.stdout or 'capture failed')[-400:]
        base = [shape(load(p)) for p in sorted(frames.glob('idle-*.png'))]
        react = [(p.stem, shape(load(p))) for p in sorted(frames.glob('reaction-*.png'))]
        if len(base) >= 3 and react:
            jitter = judge(list(zip(base, base[1:])), label='baseline silhouette jitter')
            report['baseline'] = jitter
            ref = base[0]
            reactions = []
            for name, s in react:
                j = judge([(ref, s)], label=name)
                j['xBaseline'] = round(j['medianDistance'] / jitter['medianDistance'], 2) if jitter['medianDistance'] else None
                j['visible'] = bool(j['xBaseline'] and j['xBaseline'] >= MULT)
                reactions.append(j)
            report['reactions'] = reactions
            best = max(reactions, key=lambda x: x['xBaseline'] or 0)
            report['best'] = best
            report['allVisible'] = all(x['visible'] for x in reactions)
            report['peakVisible'] = bool(best['xBaseline'] and best['xBaseline'] >= MULT)
            report['pass'] = report['peakVisible']
            report['criterion'] = 'peak of the gesture >= %.1fx baseline jitter' % MULT

    elif mode == 'images':
        d = Path(sys.argv[2]) if len(sys.argv) > 2 else HERE / 'gate-frames'
        files = sorted(d.glob('state-*.png'))
        shapes = [(p.stem.replace('state-', ''), shape(load(p))) for p in files]
        if len(shapes) >= 2:
            ref = shapes[0][1]
            j = judge([(ref, s) for _, s in shapes[1:]], label='showcase states vs ' + shapes[0][0])
            base = report.get('baseline', {})
            report['showcaseStates'] = len(shapes)
            report['showcase'] = j
            report['pass'] = None      # judged together with mode=measure by verify-project

    elif mode == 'dir':
        d = Path(sys.argv[2])
        base = [shape(load(p)) for p in sorted(d.glob('idle-*.png'))]
        react = [(p.stem, shape(load(p))) for p in sorted(d.glob('*.png')) if p.stem not in ('character-mask',) and not p.name.startswith('idle-')]
        if len(base) >= 3 and react:
            jitter = judge(list(zip(base, base[1:])), label='baseline silhouette jitter')
            ref = base[0]
            reactions = []
            for name, s in react:
                j = judge([(ref, s)], label=name)
                j['xBaseline'] = round(j['medianDistance'] / jitter['medianDistance'], 2) if jitter['medianDistance'] else None
                j['visible'] = bool(j['xBaseline'] and j['xBaseline'] >= MULT)
                reactions.append(j)
            report['baseline'] = jitter
            report['reactions'] = reactions
            best = max(reactions, key=lambda x: x['xBaseline'] or 0)
            report['best'] = best
            report['allVisible'] = all(x['visible'] for x in reactions)
            report['peakVisible'] = bool(best['xBaseline'] and best['xBaseline'] >= MULT)
            report['pass'] = report['peakVisible']
            report['criterion'] = 'peak of the gesture >= %.1fx baseline jitter' % MULT

    (HERE / 'perceptual-gate.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    lines = ['=== perceptual gate (silhouette metric, bar = %.1fx baseline jitter) ===' % MULT,
             'mode: ' + mode]
    if 'baseline' in report:
        lines.append('baseline silhouette jitter: median %.2f  max %.2f  (%d frame pairs)'
                     % (report['baseline']['medianDistance'], report['baseline']['maxDistance'], report['baseline']['frames']))
    for r in report.get('reactions', []):
        lines.append('  %-18s distance %6.2f  = %5sx jitter   %s'
                     % (r['label'], r['medianDistance'], r['xBaseline'], 'VISIBLE' if r['visible'] else 'FAIL(<2x)'))
    if 'showcase' in report:
        lines.append('  showcase %d states: median distance %.2f  max %.2f'
                     % (report['showcaseStates'], report['showcase']['medianDistance'], report['showcase']['maxDistance']))
    if 'best' in report:
        lines.append('  peak: %s = %sx jitter   (criterion: %s)' % (report['best']['label'], report['best']['xBaseline'], report.get('criterion', '')))
    if 'pass' in report and report['pass'] is not None:
        lines.append('  RESULT: ' + ('PASS' if report['pass'] else 'FAIL'))
    if 'error' in report:
        lines.append('  ERROR: ' + report['error'])
    txt = '\n'.join(lines)
    (HERE / 'perceptual-gate.txt').write_text(txt, encoding='utf-8')
    print(txt)
    return 0


if __name__ == '__main__':
    sys.exit(main())
