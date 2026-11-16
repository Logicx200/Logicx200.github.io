# -*- coding: utf-8 -*-
"""轮询并下载 BBBike 已触发的 geojson.xz 提取。"""
import os
import time
import urllib.request

BASE = "https://download2.bbbike.org/osm/extract/"
UA = {"User-Agent": "Mozilla/5.0"}

FILES = {
    "太原": ("planet_112.35000,37.62000_112.78000,38.08000.osm.geojson.xz", "data/taiyuan.geojson.xz"),
    "南京": ("planet_118.58000,31.85000_119.05000,32.25000.osm.geojson.xz", "data/nanjing.geojson.xz"),
}

os.makedirs("data", exist_ok=True)


def check(url):
    req = urllib.request.Request(url, headers=UA, method="HEAD")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, int(r.headers.get("Content-Length", "0") or 0)
    except urllib.error.HTTPError as e:
        return e.code, 0
    except Exception as e:  # noqa: BLE001
        return -1, 0


def download(url, path):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=600) as r, open(path, "wb") as f:
        total = 0
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
            total += len(chunk)
    return total


def main():
    deadline = time.time() + 20 * 60
    remaining = dict(FILES)
    while remaining and time.time() < deadline:
        for city, (name, path) in list(remaining.items()):
            url = BASE + name
            code, length = check(url)
            print("[%s] %s -> HTTP %s (%d bytes)" % (city, name, code, length), flush=True)
            if code == 200 and length > 0:
                print("[%s] 下载中... %s" % (city, url), flush=True)
                try:
                    got = download(url, path)
                    print("[%s] 完成: %s (%d bytes)" % (city, path, got), flush=True)
                    del remaining[city]
                except Exception as e:  # noqa: BLE001
                    print("[%s] 下载失败(重试): %s" % (city, e), flush=True)
        if remaining:
            time.sleep(20)
    if remaining:
        print("超时未完成:", list(remaining), flush=True)
    else:
        print("全部下载完成。", flush=True)


if __name__ == "__main__":
    main()
