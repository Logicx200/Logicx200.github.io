# -*- coding: utf-8 -*-
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TARGETS = ["F16", "f22", "nimitz", "hm", "agzfsc", "albk"]
BASE = Path(r"D:\XGGDCOSSim2\Data\ModelData\Target")
OUT = Path(r"F:\DeepSeek工作区\正式仿真")
OUT.mkdir(parents=True, exist_ok=True)

result = {}
for t in TARGETS:
    f = BASE / t / f"{t}_vis.osg"
    if not f.exists():
        # file may be lowercase or different name
        cands = list((BASE / t).glob("*.osg"))
        if not cands:
            result[t] = {"error": "no osg"}
            continue
        f = cands[0]
    lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
    mins = [1e30, 1e30, 1e30]
    maxs = [-1e30, -1e30, -1e30]
    n_pts = 0
    i = 0
    while i < len(lines):
        m = re.match(r"\s*VertexArray\s+Vec3Array\s+(\d+)", lines[i])
        if m:
            n = int(m.group(1))
            i += 1
            for k in range(n):
                if i >= len(lines):
                    break
                parts = lines[i].split()
                i += 1
                if len(parts) < 3:
                    continue
                try:
                    x, y, z = map(float, parts[:3])
                except ValueError:
                    continue
                mins = [min(mins[j], (x, y, z)[j]) for j in range(3)]
                maxs = [max(maxs[j], (x, y, z)[j]) for j in range(3)]
                n_pts += 1
        else:
            i += 1
    if n_pts:
        dims = [maxs[j] - mins[j] for j in range(3)]
        result[t] = {
            "file": str(f),
            "n_vertices": n_pts,
            "min": [round(v, 3) for v in mins],
            "max": [round(v, 3) for v in maxs],
            "dim_m": [round(v, 3) for v in dims],
            "max_dim_m": round(max(dims), 3),
        }
    else:
        result[t] = {"error": "no vertices", "file": str(f)}

(OUT / "target_bbox.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
for k, v in result.items():
    print(k, v)
