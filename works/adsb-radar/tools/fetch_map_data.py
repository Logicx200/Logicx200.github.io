#!/usr/bin/env python3
"""Fetch and bundle the line-map data for the radar.

Downloads Natural Earth 110m coastline + country borders and a compact list of
large airports, then writes compact JSON assets into ``adsbradar/web/data/``
that the frontend draws beneath the radar sweep.

Usage:  python tools/fetch_map_data.py
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(os.path.dirname(HERE), "adsbradar", "web", "data")

COAST_URL = "https://cdn.jsdelivr.net/gh/nvkelso/natural-earth-vector@master/geojson/ne_110m_coastline.geojson"
BORDER_URL = "https://cdn.jsdelivr.net/gh/nvkelso/natural-earth-vector@master/geojson/ne_110m_admin_0_boundary_lines_land.geojson"
PROVINCE_URL = "https://cdn.jsdelivr.net/gh/nvkelso/natural-earth-vector@master/geojson/ne_110m_admin_1_states_provinces_lines.geojson"
RIVERS_URL = "https://cdn.jsdelivr.net/gh/nvkelso/natural-earth-vector@master/geojson/ne_110m_rivers_lake_centerlines.geojson"
CITIES_URL = "https://cdn.jsdelivr.net/gh/nvkelso/natural-earth-vector@master/geojson/ne_110m_populated_places.geojson"
AIRPORTS_URL = "https://davidmegginson.github.io/ourairports-data/airports.csv"


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "adsb-radar/0.1"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def extract_lines(geojson: dict) -> list[list[list[float]]]:
    """Return [[lon, lat], ...] polylines from a GeoJSON FeatureCollection."""
    out: list[list[list[float]]] = []
    for feat in geojson.get("features", []):
        geom = feat.get("geometry") or {}
        gtype = geom.get("type")
        coords = geom.get("coordinates") or []
        if gtype == "LineString":
            out.append([[c[0], c[1]] for c in coords])
        elif gtype == "MultiLineString":
            for line in coords:
                out.append([[c[0], c[1]] for c in line])
    return out


def simplify(line: list[list[float]], tol: float = 0.01) -> list[list[float]]:
    """Douglas-Peucker simplification on a polyline (lon/lat, degrees)."""
    if len(line) <= 2:
        return line

    def perp_dist(p, a, b):
        dx, dy = b[0] - a[0], b[1] - a[1]
        if dx == 0 and dy == 0:
            return ((p[0] - a[0]) ** 2 + (p[1] - a[1]) ** 2) ** 0.5
        t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy)
        t = max(0.0, min(1.0, t))
        x, y = a[0] + t * dx, a[1] + t * dy
        return ((p[0] - x) ** 2 + (p[1] - y) ** 2) ** 0.5

    def rec(pts):
        if len(pts) <= 2:
            return pts
        maxd, idx = 0.0, 0
        for i in range(1, len(pts) - 1):
            d = perp_dist(pts[i], pts[0], pts[-1])
            if d > maxd:
                maxd, idx = d, i
        if maxd > tol:
            left = rec(pts[: idx + 1])
            right = rec(pts[idx:])
            return left[:-1] + right
        return [pts[0], pts[-1]]

    return rec(line)


def build_airports(csv_text: str) -> list[dict]:
    rows = []
    for line in csv_text.splitlines():
        if line.startswith('"id"') or not line:
            continue
        cols = line.split(",")
        if len(cols) < 14:
            continue
        try:
            kind = cols[2]
            if kind not in ("large_airport", "medium_airport"):
                continue
            icao, iata = cols[1], cols[13]
            name = cols[3]
            lat, lon = float(cols[4]), float(cols[5])
            if not icao and not iata:
                continue
            rows.append({"icao": icao, "iata": iata, "name": name, "lat": lat, "lon": lon})
        except (ValueError, IndexError):
            continue
    # dedupe by (iata or icao), keep large airports
    rows.sort(key=lambda a: a.get("iata") or a.get("icao") or "")
    seen = set()
    out = []
    for a in rows:
        key = a.get("iata") or a.get("icao")
        if key in seen:
            continue
        seen.add(key)
        out.append(a)
    return out


def extract_cities(geojson: dict) -> list[dict]:
    """Return [{name, lat, lon, pop}] for populated places, bigger first."""
    out = []
    for feat in geojson.get("features", []):
        props = feat.get("properties") or {}
        geom = feat.get("geometry") or {}
        if geom.get("type") != "Point":
            continue
        name = props.get("name") or props.get("NAME") or props.get("nameascii")
        if not name:
            continue
        coords = geom.get("coordinates")
        if not coords or len(coords) < 2:
            continue
        pop = props.get("pop_max") or props.get("POP_MAX") or 0
        out.append({"name": name, "lat": coords[1], "lon": coords[0], "pop": pop})
    out.sort(key=lambda c: -(c["pop"] or 0))
    return out


def main() -> int:
    os.makedirs(DATA_DIR, exist_ok=True)

    print("fetching coastline / borders / provinces / rivers ...")
    lines: list[list[list[float]]] = []
    for label, url in (("coastline", COAST_URL), ("borders", BORDER_URL),
                       ("provinces", PROVINCE_URL), ("rivers", RIVERS_URL)):
        try:
            data = json.loads(fetch(url).decode("utf-8"))
            l = extract_lines(data)
            lines += l
            print(f"  {label}: {len(l)} lines")
        except Exception as e:
            print(f"  {label}: SKIPPED ({e})")

    lines = [simplify(l) for l in lines]
    lines = [l for l in lines if len(l) >= 2]
    with open(os.path.join(DATA_DIR, "coastline.json"), "w", encoding="utf-8") as f:
        json.dump(lines, f, separators=(",", ":"))
    print(f"wrote coastline.json ({len(lines)} polylines)")

    print("fetching cities ...")
    try:
        cities = extract_cities(json.loads(fetch(CITIES_URL).decode("utf-8")))
        has_pop = any(c["pop"] for c in cities)
        if has_pop:
            cities = [c for c in cities if c["pop"] >= 200000]
        for c in cities:
            c.pop("pop", None)
        with open(os.path.join(DATA_DIR, "cities.json"), "w", encoding="utf-8") as f:
            json.dump(cities, f, ensure_ascii=False, separators=(",", ":"))
        print(f"wrote cities.json ({len(cities)} cities)")
    except Exception as e:
        print(f"  cities: SKIPPED ({e})")

    print("fetching airports ...")
    apts = build_airports(fetch(AIRPORTS_URL).decode("utf-8"))
    with open(os.path.join(DATA_DIR, "airports.json"), "w", encoding="utf-8") as f:
        json.dump(apts, f, ensure_ascii=False, separators=(",", ":"))
    print(f"wrote airports.json ({len(apts)} airports)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
