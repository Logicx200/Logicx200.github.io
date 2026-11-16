# -*- coding: utf-8 -*-
import time
import urllib.request
import urllib.parse

TARGETS = [
    ("GET", "https://overpass-api.openstreetmap.fr/api/interpreter", "[out:json][timeout:20];way(37.87,112.54,37.88,112.55);out count;"),
    ("GET", "https://overpass.osm.ch/api/interpreter", "[out:json][timeout:20];way(37.87,112.54,37.88,112.55);out count;"),
    ("GET", "https://overpass.osm.jp/api/interpreter", "[out:json][timeout:20];way(37.87,112.54,37.88,112.55);out count;"),
    ("GET", "https://overpass-api.de/api/interpreter", "[out:json][timeout:20];way(37.87,112.54,37.88,112.55);out count;"),
    ("OSM", "https://api.openstreetmap.org/api/0.6/map", "bbox=37.87,112.54,37.88,112.55"),
]

for kind, url, q in TARGETS:
    t0 = time.time()
    try:
        if kind == "GET":
            data = urllib.parse.urlencode({"data": q}).encode("utf-8")
            req = urllib.request.Request(url, data=data, headers={"User-Agent": "probe/1.0"})
        else:
            req = urllib.request.Request(url + "?" + q, headers={"User-Agent": "probe/1.0"})
        with urllib.request.urlopen(req, timeout=25) as r:
            body = r.read()
        print("OK  %.1fs  %s  (%d bytes)" % (time.time() - t0, url, len(body)), flush=True)
    except Exception as e:
        print("FAIL %.1fs  %s  %s" % (time.time() - t0, url, e), flush=True)
