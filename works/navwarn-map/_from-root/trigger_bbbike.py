# -*- coding: utf-8 -*-
"""完整复现 BBBike 表单提交：先取 expire + tile-size，再提交。"""
import http.cookiejar
import json
import re
import urllib.request
import urllib.parse

BASE = "https://extract.bbbike.org/"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}

CITIES = {
    "Taiyuan": (112.35, 37.62, 112.78, 38.08),
    "Nanjing": (118.58, 31.85, 119.05, 32.25),
}


def make_opener():
    cj = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))


def get(opener, url):
    req = urllib.request.Request(url, headers=UA)
    with opener.open(req, timeout=60) as r:
        return r.read().decode("utf-8", "replace"), r.geturl()


def fetch_expire(opener):
    html, _ = get(opener, BASE)
    m = re.search(r'name="expire"\s+value="(\d+)"', html)
    return m.group(1) if m else ""


def fetch_size(opener, fmt, w, s, e, n):
    url = BASE + "cgi/tile-size.cgi?" + urllib.parse.urlencode({
        "format": fmt, "lat_sw": "%.5f" % s, "lng_sw": "%.5f" % w,
        "lat_ne": "%.5f" % n, "lng_ne": "%.5f" % e,
    })
    html, _ = get(opener, url)
    try:
        data = json.loads(html)
        return data
    except Exception:  # noqa: BLE001
        return {"raw": html[:200]}


def submit(opener, fmt, w, s, e, n, city, email, as_val, expire):
    params = [
        ("sw_lng", "%.5f" % w), ("sw_lat", "%.5f" % s),
        ("ne_lng", "%.5f" % e), ("ne_lat", "%.5f" % n),
        ("format", fmt), ("city", city), ("email", email),
        ("as", str(as_val)), ("pg", "1"), ("coords", ""),
        ("oi", "0"), ("layers", ""), ("expire", expire),
        ("lang", "en"), ("submit", "extract"),
    ]
    url = BASE + "?" + urllib.parse.urlencode(params)
    return get(opener, url)


if __name__ == "__main__":
    opener = make_opener()
    expire = fetch_expire(opener)
    print("expire:", expire, flush=True)
    for city, (w, s, e, n) in CITIES.items():
        print("=== %s ===" % city, flush=True)
        sz = fetch_size(opener, "geojson.xz", w, s, e, n)
        print("tile-size:", sz, flush=True)
        as_val = sz.get("size", 10) if isinstance(sz, dict) else 10
        try:
            body, fu = submit(opener, "geojson.xz", w, s, e, n, city, "extract@example.com", as_val, expire)
            m = re.search(r"bbbike_extract_download_url:\s*(\S*)", body)
            st = re.search(r"bbbike_extract_status:\s*([^,\n]*)", body)
            print("final:", fu, flush=True)
            print("status:", st.group(1) if st else "?", "download:", m.group(1) if m else "?", flush=True)
            txt = re.sub(r"<[^>]+>", " ", body)
            txt = re.sub(r"\s+", " ", txt).strip()
            print("text(300):", txt[:300], flush=True)
        except Exception as ex:  # noqa: BLE001
            print("submit fail:", ex, flush=True)
