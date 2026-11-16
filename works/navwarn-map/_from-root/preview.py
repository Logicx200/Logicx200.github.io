# -*- coding: utf-8 -*-
"""用 Pillow 从同一份数据+投影画 PNG 预览，便于快速查看路网形态。"""
from PIL import Image, ImageDraw
from render_from_geojson import load_geojson, extract_buckets, make_projector, NOISE, ROAD_WIDTH, CITIES

PW = 1400  # 预览宽度


def preview(city, path, s, w, n, e):
    gj = load_geojson(path)
    features = gj.get("features", []) if isinstance(gj, dict) else gj
    buckets = extract_buckets(features, NOISE)
    project, width, height = make_projector(s, w, n, e, PW)
    img = Image.new("RGB", (width, height), (255, 255, 255))
    d = ImageDraw.Draw(img)
    scale = PW / 2400.0
    for cls in sorted(ROAD_WIDTH, key=lambda c: -ROAD_WIDTH[c]):
        lw = max(1, round(ROAD_WIDTH[cls] * scale))
        color = (30, 30, 34) if ROAD_WIDTH[cls] >= 1.0 else (90, 90, 95)
        for pts in buckets.get(cls, []):
            flat = []
            for lon, lat in pts:
                x, y = project(lon, lat)
                flat.extend((x, y))
            if len(flat) >= 4:
                d.line(flat, fill=color, width=lw)
    out = "preview_%s.png" % city
    img.save(out)
    print(out, "%dx%d" % (width, height), flush=True)


for city, (path, s, w, n, e) in CITIES.items():
    preview(city, path, s, w, n, e)
print("预览完成。", flush=True)
