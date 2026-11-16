# -*- coding: utf-8 -*-
"""查询覆盖源区与口岸的 Sentinel-2 瓦片，并检查哪一景质量最好。"""
import json
import urllib.request

BBOX = [85.15, 28.20, 85.62, 28.62]          # 源区+口岸+下游
DATES = "2026-08-01T00:00:00Z/2026-10-05T00:00:00Z"

q = {
    "collections": ["sentinel-2-l2a"],
    "bbox": BBOX,
    "datetime": DATES,
    "limit": 200,
    "fields": {"include": ["id", "properties.datetime", "properties.eo:cloud_cover",
                           "properties.grid:code", "assets.visual.href"],
               "exclude": ["geometry", "links"]},
}
body = json.dumps(q).encode()
req = urllib.request.Request(
    "https://earth-search.aws.element84.com/v1/search",
    data=body, headers={"Content-Type": "application/json"})
with urllib.request.urlopen(req, timeout=90) as r:
    d = json.loads(r.read().decode())

feats = d.get("features", [])
print("命中 %d 景" % len(feats))
tiles = {}
for f in feats:
    p = f["properties"]
    code = p.get("grid:code", "?")
    tiles.setdefault(code, []).append(
        (p["datetime"][:10], p.get("eo:cloud_cover", -1), f["id"],
         f.get("assets", {}).get("visual", {}).get("href", "")))

for code in sorted(tiles):
    rows = sorted(tiles[code])
    print()
    print("=== 瓦片 %s : %d 景 ===" % (code, len(rows)))
    for dt, cc, iid, href in rows:
        mark = ""
        if dt >= "2026-08-26":
            mark = "  <== 灾后"
        print("  %s cloud=%5.1f  %-34s%s" % (dt, cc, iid[:34], mark))
    # 打印该瓦片 TCI 路径模板
    if rows and rows[0][3]:
        print("  TCI: %s" % rows[0][3])
