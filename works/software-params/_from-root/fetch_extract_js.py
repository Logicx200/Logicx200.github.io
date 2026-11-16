# -*- coding: utf-8 -*-
import urllib.request
for name, url in [
    ("extract_js", "https://extract.bbbike.org/html/extract.js"),
    ("extract_lang_js", "https://extract.bbbike.org/html/extract-language.js"),
]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read().decode("utf-8", "replace")
        with open(name + ".txt", "w", encoding="utf-8") as f:
            f.write(body)
        print(name, len(body), "bytes", flush=True)
    except Exception as e:
        print(name, "FAIL", e, flush=True)
