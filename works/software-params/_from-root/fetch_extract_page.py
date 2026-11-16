# -*- coding: utf-8 -*-
import urllib.request

for name, url in [
    ("extract_home", "https://extract.bbbike.org/"),
    ("extract_help", "https://extract.bbbike.org/extract.html"),
]:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        html = r.read().decode("utf-8", "replace")
    with open(name + ".html", "w", encoding="utf-8") as f:
        f.write(html)
    print(name, len(html), "bytes", flush=True)
