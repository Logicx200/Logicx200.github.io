# -*- coding: utf-8 -*-
"""用 STAC 几何精确定位源区/口岸落在哪些 Sentinel-2 瓦片内。"""
import json
import urllib.request
from osgeo import osr

# 候选点（UTM 45N）
PTS = {
    '源区候选A(6.9km2)': (85.2953, 28.4997),
    '源区候选B': (85.3689, 28.5366),
    '源区候选C(蓝塘里壤东坡)': (85.5028, 28.4355),
    '吉隆口岸': (85.3767, 28.2871),
    '域西北角': (85.190, 28.55),
    '域东南角': (85.548, 28.24),
}
s1 = osr.SpatialReference(); s1.ImportFromEPSG(4326); s1.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
s2 = osr.SpatialReference(); s2.ImportFromEPSG(32645); s2.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
ct = osr.CoordinateTransformation(s1, s2)
print('=== 各点 UTM 坐标 ===')
utm = {}
for k, (lon, lat) in PTS.items():
    x, y, _ = ct.TransformPoint(lon, lat)
    utm[k] = (x, y)
    print('  %-24s %.4fE %.4fN -> E %8.0f  N %8.0f' % (k, lon, lat, x, y))

# 查询 STAC 拿瓦片 footprint
q = {"collections": ["sentinel-2-l2a"],
     "bbox": [85.0, 28.1, 85.8, 28.7],
     "datetime": "2026-08-25T00:00:00Z/2026-08-29T00:00:00Z",
     "limit": 50}
req = urllib.request.Request("https://earth-search.aws.element84.com/v1/search",
                             data=json.dumps(q).encode(),
                             headers={"Content-Type": "application/json"})
with urllib.request.urlopen(req, timeout=90) as r:
    d = json.loads(r.read().decode())

print()
print('=== 灾后 1-3 天可用瓦片 ===')
for f in d.get('features', []):
    code = f['properties'].get('grid:code', '?')
    geom = f.get('geometry')
    iid = f['id']
    cc = f['properties'].get('eo:cloud_cover', -1)
    print('  %-14s cloud=%5.1f  %s' % (code, cc, iid))
    if geom and geom.get('type') == 'Polygon':
        xs = [p[0] for p in geom['coordinates'][0]]
        ys = [p[1] for p in geom['coordinates'][0]]
        print('     经度 %.4f..%.4f  纬度 %.4f..%.4f' % (min(xs), max(xs), min(ys), max(ys)))
