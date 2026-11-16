# -*- coding: utf-8 -*-
"""
从 OpenStreetMap 下载城市道路矢量数据，并渲染为「不含任何名称标注」的 SVG 底图。

实现要点:
  * 把城市范围切成小块(tile)分别查询 Overpass，避免大查询被中断/超时;
  * 每块结果落盘缓存，失败重试，断点续跑;
  * 按道路 id 去重合并，只保留道路几何(中心线)，不渲染任何道路名/地名标签;
  * 按道路等级分线宽，透明背景，每城生成深色/浅色两种配色。

用法:  python roadmap_svg.py
新增城市:  修改 CITIES 字典(城市名 -> 南纬,西经,北纬,东经)。
"""
import json
import math
import os
import time
import urllib.request
import urllib.parse

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE, "data")
CACHE_DIR = os.path.join(DATA_DIR, "cache")
OUT_DIR = os.path.join(BASE, "out")
for d in (DATA_DIR, CACHE_DIR, OUT_DIR):
    os.makedirs(d, exist_ok=True)

# 城市 -> (南纬, 西经, 北纬, 东经)，覆盖主城区范围
CITIES = {
    "太原": (37.62, 112.35, 38.08, 112.78),
    "南京": (31.85, 118.58, 32.25, 119.05),
}

# 分块大小(度)
TILE = 0.08

# 单次请求超时(秒)，小块请求应秒回
TIMEOUT = 30

# 道路等级 -> 线宽(输出像素)
ROAD_WIDTH = {
    "motorway": 4.0,
    "trunk": 3.0,
    "primary": 2.2,
    "secondary": 1.6,
    "tertiary": 1.15,
    "unclassified": 0.8,
    "residential": 0.75,
    "living_street": 0.75,
    "road": 0.8,
}

HIGHWAY_RE = r"^(motorway|trunk|primary|secondary|tertiary|unclassified|residential|living_street|road)(_link)?$"

WIDTH = 2400

# 已知可用端点优先; 备用端点在后
ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]


def tiles_for(bbox):
    s, w, n, e = bbox
    out = []
    lat = s
    while lat < n - 1e-9:
        lon = w
        while lon < e - 1e-9:
            out.append((lat, lon, min(lat + TILE, n), min(lon + TILE, e)))
            lon += TILE
        lat += TILE
    return out


def tile_query(tb):
    s, w, n, e = tb
    return (
        "[out:json][timeout:30];\n"
        'way["highway"~"%s"](%s,%s,%s,%s);\n'
        "out geom;" % (HIGHWAY_RE, s, w, n, e)
    )


def fetch_tile(tb):
    q = tile_query(tb)
    data = urllib.parse.urlencode({"data": q}).encode("utf-8")
    last_err = None
    for url in ENDPOINTS:
        try:
            req = urllib.request.Request(
                url, data=data,
                headers={"User-Agent": "roadmap-svg/1.0 (design-background generator)"},
            )
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            last_err = e
    raise RuntimeError(str(last_err))


def cache_path(city, tb):
    return os.path.join(CACHE_DIR, city, "tile_%.4f_%.4f.json" % (tb[0], tb[1]))


def ensure_data(city, bbox):
    tiles = tiles_for(bbox)
    ways = {}
    failed = []
    print("[%s] 共 %d 个分块" % (city, len(tiles)), flush=True)
    for i, tb in enumerate(tiles):
        cp = cache_path(city, tb)
        os.makedirs(os.path.dirname(cp), exist_ok=True)
        els = None
        if os.path.exists(cp):
            try:
                with open(cp, "r", encoding="utf-8") as f:
                    els = json.load(f).get("elements", [])
            except Exception:  # noqa: BLE001
                els = None
        if els is None:
            try:
                gj = fetch_tile(tb)
                with open(cp, "w", encoding="utf-8") as f:
                    json.dump(gj, f, ensure_ascii=False)
                els = gj.get("elements", [])
            except Exception as e:  # noqa: BLE001
                failed.append((tb, str(e)))
        if els:
            for el in els:
                if el.get("type") == "way" and el.get("id") not in ways:
                    ways[el["id"]] = el
        if (i + 1) % 5 == 0:
            print("[%s] 进度 %d/%d (已收集 %d 条)" % (city, i + 1, len(tiles), len(ways)), flush=True)
        time.sleep(0.15)

    if failed:
        print("[%s] 有 %d 个分块失败，重试..." % (city, len(failed)), flush=True)
        still = []
        for tb, _ in failed:
            try:
                gj = fetch_tile(tb)
                cp = cache_path(city, tb)
                with open(cp, "w", encoding="utf-8") as f:
                    json.dump(gj, f, ensure_ascii=False)
                for el in gj.get("elements", []):
                    if el.get("type") == "way" and el.get("id") not in ways:
                        ways[el["id"]] = el
            except Exception as e:  # noqa: BLE001
                still.append((tb, str(e)))
            time.sleep(0.3)
        if still:
            print("[%s] 仍有 %d 个分块失败(跳过): %s" % (city, len(still), still[:5]), flush=True)

    elements = list(ways.values())
    with open(os.path.join(DATA_DIR, city + ".geojson"), "w", encoding="utf-8") as f:
        json.dump({"elements": elements}, f, ensure_ascii=False)
    print("[%s] 合计去重后 %d 条道路" % (city, len(elements)), flush=True)
    return elements


def norm_highway(h):
    if h.endswith("_link"):
        h = h[:-5]
    return h


def make_projector(bbox, width):
    s, w, n, e = bbox
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
            if len(pts) < 2:
                continue
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


def main():
    for city, bbox in CITIES.items():
        elements = ensure_data(city, bbox)
        project, width, height = make_projector(bbox, WIDTH)
        buckets = {}
        for el in elements:
            h = el.get("tags", {}).get("highway")
            if not h:
                continue
            cls = norm_highway(h)
            if cls not in ROAD_WIDTH:
                continue
            geom = el.get("geometry") or []
            pts = [project(p["lon"], p["lat"]) for p in geom if "lon" in p and "lat" in p]
            if len(pts) >= 2:
                buckets.setdefault(cls, []).append(pts)

        total = sum(len(v) for v in buckets.values())
        print("[%s] 渲染 %d 条道路 (画布 %dx%d)" % (city, total, width, height), flush=True)
        for name, color in (("深色", "#16181d"), ("浅色", "#ffffff")):
            out_path = os.path.join(OUT_DIR, "%s-道路-%s.svg" % (city, name))
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(render_svg(buckets, width, height, color))
            print("[%s] 已生成 %s" % (city, out_path), flush=True)

    print("全部完成。", flush=True)


if __name__ == "__main__":
    main()
