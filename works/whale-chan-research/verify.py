# -*- coding: utf-8 -*-
"""最终验收：检查两份产物是否都完整可用。

用法（务必在纯 ASCII 路径下运行，中文路径传给子进程会乱码）：
    python verify.py
"""
import io
import os
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

TARGETS = [
    r"F:\whale-chan-research",
    "F:\\DeepSeek\u5de5\u4f5c\u533a\\whale-chan-research",
]

EXPECT_IMAGES = 28


def check(base):
    print("=" * 62)
    print("目录:", base)
    if not os.path.isdir(base):
        print("  目录不存在 FAIL")
        return False

    ok = True
    img_dir = os.path.join(base, "img")
    n_img = len(os.listdir(img_dir)) if os.path.isdir(img_dir) else 0
    print("  img 张数: %d %s" % (n_img, "OK" if n_img == EXPECT_IMAGES else "FAIL"))
    ok &= n_img == EXPECT_IMAGES

    html = os.path.join(base, "\u5019\u9009\u56fe\u5e93.html")
    if os.path.isfile(html):
        t = open(html, encoding="utf-8").read()
        uri = len(re.findall(r'src="data:image/', t))
        ext = len(re.findall(r'src="(?!data:)', t))
        cards = len(re.findall(r'<figure class="card">', t))
        groups = len(re.findall(r'<section class="group">', t))
        size_mb = os.path.getsize(html) / 1024 / 1024
        good = (uri == n_img) and (ext == 0) and (cards == n_img)
        ok &= good
        print("  HTML: %.2f MB | 内嵌图 %d | 卡片 %d | 分组 %d | 外链图 %d | %s"
              % (size_mb, uri, cards, groups, ext, "OK" if good else "FAIL"))
    else:
        ok = False
        print("  HTML: 缺失 FAIL")

    md = os.path.join(base, "\u5019\u9009\u6c47\u603b.md")
    if os.path.isfile(md):
        t = open(md, encoding="utf-8").read()
        refs = re.findall(r'!\[[^\]]*\]\(([^)]+)\)', t)
        missing = [r for r in refs
                   if not os.path.isfile(os.path.join(base, r.replace("/", os.sep)))]
        bad = [r for r in refs if not r.startswith("img/")]
        good = (not missing) and (not bad)
        ok &= good
        print("  MD: 引用 %d | 缺文件 %d | 路径不规范 %d | %s"
              % (len(refs), len(missing), len(bad), "OK" if good else "FAIL"))
        if missing:
            print("       缺失前几个:", missing[:5])
    else:
        ok = False
        print("  MD: 缺失 FAIL")

    return ok


if __name__ == "__main__":
    results = [check(b) for b in TARGETS]
    print("=" * 62)
    print("总体验收:", "PASS" if all(results) else "FAIL")
    sys.exit(0 if all(results) else 1)
