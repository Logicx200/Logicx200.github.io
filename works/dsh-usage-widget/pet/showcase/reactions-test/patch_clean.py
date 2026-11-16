"""Patch analyse.py: separate the panel band from the character-only band.

The crop around the character overlaps the panel (the panel is directly above/behind
her), so a naive "whole crop" diff mixes the panel's own changing text with her motion
and inflates the baseline.  This patch adds a CLEAN band = the rows below the panel's
bottom edge, where only the character (plus the desktop at the edges) is drawn, and
measures the panel band separately so the pollution is visible instead of hidden.
"""
import io
import re
from pathlib import Path

p = Path(r'F:\dsh-usage-widget\pet\showcase\reactions-test\analyse.py')
t = p.read_text(encoding='utf-8')

# 1. read the panel's bottom edge (page coords) and the pet window origin
t = t.replace(
    "def main():\n    report = {'noisePixelThreshold': NOISE_PIXEL, 'faceBand': FACE_BAND, 'runs': {}, 'comparisons': []}",
    """def read_panel_bottom():
    \"\"\"screen y of the panel's bottom edge, and the crop's top y (for the clean band).\"\"\"
    geo = HERE.parents[1] / 'renderer' / 'panel-geometry.json'
    try:
        doc = json.loads(geo.read_text(encoding='utf-8-sig'))
        page = float(doc.get('panelBottomPage'))
    except Exception:
        return None, None, None
    return page, None, None


def main():
    report = {'noisePixelThreshold': NOISE_PIXEL, 'faceBand': FACE_BAND, 'runs': {}, 'comparisons': []}""")

# 2. after loading the indices, work out the clean band from the first frame's crop
t = t.replace(
    "    # ---------------- baseline noise ----------------",
    """    # ---- geometry: which rows of the crop are the character alone (panel excluded) ----
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

    # ---------------- baseline noise ----------------""")

# 3. baseline: measure the panel band, the clean band and the face band separately
t = t.replace(
    """        face = [diff_stats(a, b, 0.0, FACE_BAND) for a, b in zip(base_imgs, base_imgs[1:])]""",
    """        face = [diff_stats(a, b, 0.0, FACE_BAND) for a, b in zip(base_imgs, base_imgs[1:])]
        clean = [diff_stats(a, b, clean0, 1.0) for a, b in zip(base_imgs, base_imgs[1:])]
        panel = [diff_stats(a, b, 0.0, clean0) for a, b in zip(base_imgs, base_imgs[1:])] if clean0 > 0.02 else []""")
t = t.replace(
    """            'faceRegion': {
                'changedPctMedian': round(float(np.median([p['changedPct'] for p in face])), 3),
                'changedPctMax': round(float(np.max([p['changedPct'] for p in face])), 3),
                'meanAbsDiffMedian': round(float(np.median([p['meanAbsDiff'] for p in face])), 3),
            },
        }""",
    """            'faceRegion': {
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
        }""")

# 4. every comparison also carries the clean-band numbers + the ratio against the clean noise
t = t.replace(
    """        rec = {
            'name': name, 'kind': kind, 'trigger': trigger, 'reference': ref_label, 'frame': meta,
            'wholeFrame': diff_stats(ref_img, img),
            'faceRegion': diff_stats(ref_img, img, 0.0, FACE_BAND),
        }
        if noise:
            nf = noise['wholeFrame']['changedPctMedian'] or 0.0
            na = noise['faceRegion']['changedPctMedian'] or 0.0
            rec['xBaselineWhole'] = round(rec['wholeFrame']['changedPct'] / nf, 2) if nf > 0 else None
            rec['xBaselineFace'] = round(rec['faceRegion']['changedPct'] / na, 2) if na > 0 else None""",
    """        rec = {
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
            rec['xBaselineClean'] = round(rec['characterOnlyBand']['changedPct'] / nc, 2) if nc > 0 else None""")

# 5. text report: show the clean band columns too
t = t.replace(
    """    lines.append('%-58s %9s %8s %9s %8s' % ('comparison', 'whole%', 'x noise', 'face%', 'x noise'))
    for cmp in report['comparisons']:
        lines.append('%-58s %9.3f %8s %9.3f %8s' % (
            cmp['name'][:58], cmp['wholeFrame']['changedPct'], cmp['xBaselineWhole'],
            cmp['faceRegion']['changedPct'], cmp['xBaselineFace']))""",
    """    lines.append('%-56s %8s %7s %8s %7s %8s %7s' % ('comparison', 'whole%', 'xnoise', 'face%', 'xnoise', 'clean%', 'xnoise'))
    for cmp in report['comparisons']:
        lines.append('%-56s %8.3f %7s %8.3f %7s %8.3f %7s' % (
            cmp['name'][:56], cmp['wholeFrame']['changedPct'], cmp['xBaselineWhole'],
            cmp['faceRegion']['changedPct'], cmp['xBaselineFace'],
            cmp['characterOnlyBand']['changedPct'], cmp['xBaselineClean']))""")
t = t.replace(
    """        lines.append(f"  noise face band  : {noise['faceRegion']['changedPctMedian']}% pixels changed (max {noise['faceRegion']['changedPctMax']}%)")""",
    """        lines.append(f"  noise face band  : {noise['faceRegion']['changedPctMedian']}% pixels changed (max {noise['faceRegion']['changedPctMax']}%)")
        lines.append(f"  noise character-only band (rows below the panel): {noise['characterOnlyBand']['changedPctMedian']}% (max {noise['characterOnlyBand']['changedPctMax']}%)")
        if noise.get('panelBandBehindHer'):
            lines.append(f"  noise panel band behind her: {noise['panelBandBehindHer']['changedPctMedian']}% (max {noise['panelBandBehindHer']['changedPctMax']}%)")""")

# 6. tiles: show the clean-band multiple as well
t = t.replace(
    """        sub = (f"vs {cmp['reference']}: 整帧 {cmp['wholeFrame']['changedPct']}% ({cmp['xBaselineWhole']}× 噪声)"
               f" 脸区 {cmp['faceRegion']['changedPct']}% ({cmp['xBaselineFace']}×)")""",
    """        sub = (f"vs {cmp['reference']}: 整帧 {cmp['wholeFrame']['changedPct']}%({cmp['xBaselineWhole']}×)"
               f" 身体带 {cmp['characterOnlyBand']['changedPct']}%({cmp['xBaselineClean']}×)")""")

p.write_text(t, encoding='utf-8')
import ast
ast.parse(t)
print('analyse.py patched + parses OK')
