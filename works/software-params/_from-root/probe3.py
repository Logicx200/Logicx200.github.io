# -*- coding: utf-8 -*-
import time
import urllib.request

URLS = [
    ("BBBike download", "https://download.bbbike.org/"),
    ("BBBike extract", "https://extract.bbbike.org/"),
    ("Geofabrik China", "https://download.geofabrik.de/asia/china.html"),
    ("OSM API map", "https://www.openstreetmap.org/api/0.6/map?bbox=37.87,112.54,37.88,112.55"),
    ("OSM API capabilities", "https://www.openstreetmap.org/api/capabilities"),
]

for name, url in URLS:
    t0 = time.time()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "probe/1.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            body = r.read()
        print("OK  %.1fs  %-22s %s (%d bytes)" % (time.time() - t0, name, url, len(body)), flush=True)
    except Exception as e:
        print("FAIL %.1fs  %-22s %s" % (time.time() - t0, name, e), flush=True)
