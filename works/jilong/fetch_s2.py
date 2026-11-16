# -*- coding: utf-8 -*-
"""用 requests+certifi 下载 Sentinel-2 TCI 整景（带进度、断点续传）。"""
import os
import sys
import time
import certifi
import requests

OUT = r'F:\DeepSeek工作区\jilong\s2'
os.makedirs(OUT, exist_ok=True)
BASE = 'https://sentinel-cogs.s3.us-west-2.amazonaws.com/sentinel-s2-l2a-cogs/45/R/UM/2026'
SCENES = {
    'S2C_45RUM_20260812_0_L2A': '8/S2C_45RUM_20260812_0_L2A',   # 灾前14天 云18.7%
    'S2B_45RUM_20260824_0_L2A': '8/S2B_45RUM_20260824_0_L2A',   # 灾前2天  云38.6%
    'S2B_45RUM_20260916_0_L2A': '9/S2B_45RUM_20260916_0_L2A',   # 灾后21天 云55.4%
}

sess = requests.Session()
sess.verify = certifi.where()

for name, sub in SCENES.items():
    url = '%s/%s/TCI.tif' % (BASE, sub)
    dst = os.path.join(OUT, '%s_TCI.tif' % name)
    part = dst + '.part'
    print('=== %s ===' % name, flush=True)
    try:
        h = sess.get(url, headers={'Range': 'bytes=0-0'}, timeout=90)
        total = int(h.headers['Content-Range'].split('/')[-1])
    except Exception as e:
        print('  取大小失败: %s' % e, flush=True)
        continue
    done = os.path.getsize(part) if os.path.exists(part) else 0
    if os.path.exists(dst) and os.path.getsize(dst) == total:
        print('  已完成，跳过 (%.1f MB)' % (total / 1e6), flush=True)
        continue
    print('  大小 %.1f MB，已下载 %.1f MB' % (total / 1e6, done / 1e6), flush=True)
    t0 = time.time()
    try:
        with sess.get(url, headers={'Range': 'bytes=%d-' % done}, timeout=180,
                      stream=True) as r:
            r.raise_for_status()
            with open(part, 'ab') as f:
                last = time.time()
                for chunk in r.iter_content(1 << 20):
                    f.write(chunk)
                    done += len(chunk)
                    if time.time() - last > 10:
                        el = time.time() - t0
                        sp = (done - (os.path.getsize(part) - done)) / max(el, 1)
                        print('    %5.1f/%.1f MB  %4.0f KB/s' % (
                            done / 1e6, total / 1e6, sp / 1024), flush=True)
                        last = time.time()
        os.replace(part, dst)
        print('  完成 %.1f MB, 用时 %.0f s' % (total / 1e6, time.time() - t0), flush=True)
    except Exception as e:
        print('  下载中断: %s' % e, flush=True)
print('全部结束', flush=True)
