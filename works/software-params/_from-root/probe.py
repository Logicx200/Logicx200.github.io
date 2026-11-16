# -*- coding: utf-8 -*-
import json
import time
import urllib.request
import urllib.parse

ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.nchc.org.tw/api/interpreter",
]

Q = "[out:json][timeout:20];way(37.87,112.54,37.88,112.55);out count;"
data = urllib.parse.urlencode({"data": Q}).encode("utf-8")

for url in ENDPOINTS:
    t0 = time.time()
    try:
        req = urllib.request.Request(url, data=data, headers={"User-Agent": "probe/1.0"})
        with urllib.request.urlopen(req, timeout=25) as r:
            body = r.read().decode("utf-8")
        dt = time.time() - t0
        print("OK  %.1fs  %s  (%d bytes)" % (dt, url, len(body)), flush=True)
    except Exception as e:
        dt = time.time() - t0
        print("FAIL %.1fs  %s  %s" % (dt, url, e), flush=True)
