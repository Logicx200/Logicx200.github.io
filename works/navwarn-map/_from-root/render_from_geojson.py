# -*- coding: utf-8 -*-
"""
把 BBBike 的 Osmium GeoJSON(.geojson.xz) 渲染为无名称标注的 SVG 底图。
只保留道路几何中心线，不渲染任何名称标签。
"""
import json
import lzma
import math
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(BASE, "out")
os.makedirs(OUT_DIR, exist_ok=True)

# 城市 -> (输入文件, 南纬, 西经, 北纬, 东经)
CITIES = {
    "太原": ("data/taiyuan.geojson.xz", 37.62, 112.35, 38.08, 112.78),
    "南京": ("data/nanjing.geojson.xz", 31.85, 118.58, 32.25, 119.05),
}

ROAD_WIDTH = {
    "motorway": 4.0,
    "trunk": 3.0,
    "primary": 2.2,
    "secondary": 1.6,
    "tertiary": 1.15,
    "unclassified": 0.8,
    "residential": 0.75,
    "living_street": 0.75,
    "service": 0.5,
    "pedestrian": 0.5,
    "road": 0.8,
    "footway": 0.35,
    "cycleway": 0.35,
    "path": 0.3,
    "track": 0.4,
}

WIDTH = 2400

# 非机动车道/步行道，作为「纯道路」模式时剔除，减少背景噪点
NOISE = {"footway", "cycleway", "path", "track", "pedestrian", "steps", "bridleway"}


def norm_highway(h):
    if isinstance(h, str) and h.endswith("_link"):
        h = h[:-5]
    return h


def get_highway(props):
    if not isinstance(props, dict):
        return None
    h = props.get("highway")
    if h is None and isinstance(props.get("tags"), dict):
        h = props["tags"].get("highway")
    return h


def extract_buckets(features, skip=None):
    skip = skip or set()
    buckets = {}
    for f in features:
        if not isinstance(f, dict):
            continue
        h = get_highway(f.get("properties"))
        if not h:
            continue
        cls = norm_highway(h)
        if cls not in ROAD_WIDTH or cls in skip:
            continue
        geom = f.get("geometry") or {}
        gtype = geom.get("type")
        coords = geom.get("coordinates")
        if not coords:
            continue
        rings = []
        if gtype == "LineString":
            rings = [coords]
        elif gtype == "MultiLineString":
            rings = list(coords)
        elif gtype == "Polygon":
            if coords:
                rings = [coords[0]]
        elif gtype == "MultiPolygon":
            for poly in coords:
                if poly:
                    rings.append(poly[0])
        else:
            continue
        for ring in rings:
            pts = [(c[0], c[1]) for c in ring if isinstance(c, (list, tuple)) and len(c) >= 2]
            if len(pts) >= 2:
                buckets.setdefault(cls, []).append(pts)
    return buckets


def make_projector(s, w, n, e, width):
    xmin = math.radians(w)
    xmax = math.radians(e)
    ymin = math.log(math.tan(math.pi / 4 + math.radians(s) / 2))
    ymax = math.log(math.tan(math.pi / 4 + math.radians(n) / 2))
    span_x = xmax - xmin
    span_y = ymax - ymin
    height = int(round(width * span_y / span_x))

    def project(lon, lat):
        x = (math.radians(lon) - xmin) / span_x * width
        y = (ymax - math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))) / span_y * height
        return x, y

    return project, width, height


def render_svg(buckets, width, height, color):
    body = []
    for cls in sorted(ROAD_WIDTH, key=lambda c: -ROAD_WIDTH[c]):
        lines = buckets.get(cls)
        if not lines:
            continue
        d_parts = []
        for pts in lines:
            x0, y0 = pts[0]
            d = "M %.1f %.1f" % (x0, y0)
            for x, y in pts[1:]:
                d += " L %.1f %.1f" % (x, y)
            d_parts.append(d)
        if not d_parts:
            continue
        body.append(
            '<path d="%s" fill="none" stroke="%s" stroke-width="%s" '
            'stroke-linecap="round" stroke-linejoin="round"/>'
            % (" ".join(d_parts), color, ROAD_WIDTH[cls])
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" '
        'width="%d" height="%d" shape-rendering="geometricPrecision">\n'
        "%s\n"
        "</svg>\n"
    ) % (width, height, width, height, "\n".join(body))


def load_geojson(path):
    with lzma.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)


def main():
    inspect = "--inspect" in sys.argv
    roads_only = "--roads-only" in sys.argv
    skip = NOISE if roads_only else set()
    for city, (path, s, w, n, e) in CITIES.items():
        if not os.path.exists(path):
            print("[%s] 缺少文件 %s，跳过" % (city, path), flush=True)
            continue
        print("[%s] 读取 %s ..." % (city, path), flush=True)
        gj = load_geojson(path)
        features = gj.get("features", []) if isinstance(gj, dict) else gj
        print("[%s] 共 %d 个要素" % (city, len(features)), flush=True)
        if inspect and features:
            print("[%s] 首个要素:", json.dumps(features[0], ensure_ascii=False)[:600], flush=True)
        buckets = extract_buckets(features, skip)
        total = sum(len(v) for v in buckets.values())
        print("[%s] 提取道路折线 %d 条, 分类:" % (city, total), flush=True)
        for cls in sorted(ROAD_WIDTH, key=lambda c: -ROAD_WIDTH[c]):
            if buckets.get(cls):
                print("      %-12s %d 条" % (cls, len(buckets[cls])), flush=True)
        project, width, height = make_projector(s, w, n, e, WIDTH)
        # 投影：把经纬度坐标转为画布像素坐标
        proj = {}
        for cls, lines in buckets.items():
            proj[cls] = [[project(lon, lat) for lon, lat in pts] for pts in lines]
        print("[%s] 画布 %dx%d" % (city, width, height), flush=True)
        for name, color in (("深色", "#16181d"), ("浅色", "#ffffff")):
            out_path = os.path.join(OUT_DIR, "%s-道路-%s.svg" % (city, name))
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(render_svg(proj, width, height, color))
            print("[%s] 已生成 %s" % (city, out_path), flush=True)
    print("渲染完成。", flush=True)


if __name__ == "__main__":
    main()
