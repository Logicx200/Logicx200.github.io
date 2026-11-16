# -*- coding: utf-8 -*-
"""按 TIFF 瓦片字节范围精确抓取指定 UTM 窗口的全分辨率影像。"""
import os
import struct
import zlib
import sys
import certifi
import numpy as np
import requests
from PIL import Image

OUT = r'F:\DeepSeek工作区\jilong\s2'
os.makedirs(OUT, exist_ok=True)
s = requests.Session()
s.verify = certifi.where()

TAGS = {256: 'w', 257: 'h', 258: 'bits', 259: 'comp', 273: 'stripoff',
        277: 'spp', 278: 'rps', 279: 'stripcnt', 284: 'planar',
        322: 'tw', 323: 'th', 324: 'toff', 325: 'tcnt', 330: 'subifds',
        254: 'sft', 339: 'sformat'}
TSZ = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 6: 1, 7: 1, 8: 2, 9: 4, 10: 8, 11: 4, 12: 8}


def fetch(url, a, b, tries=5):
    import time
    last = None
    for k in range(tries):
        try:
            r = s.get(url, headers={'Range': 'bytes=%d-%d' % (a, b)}, timeout=180)
            r.raise_for_status()
            return r.content
        except Exception as e:
            last = e
            time.sleep(1.5 * (k + 1))
    raise last


def read_ifd(url, off):
    bo = '<' if fetch(url, 0, 1) == b'II' else '>'
    n = struct.unpack(bo + b'H', fetch(url, off, off + 1))[0]
    raw = fetch(url, off + 2, off + 2 + n * 12 + 4)
    out = {}
    for i in range(n):
        tag, typ, cnt = struct.unpack(bo + b'HHI', raw[i * 12:i * 12 + 8])
        sz = TSZ.get(typ, 1) * cnt
        if sz <= 4:
            val = raw[i * 12 + 8:i * 12 + 8 + sz]
        else:
            p = struct.unpack(bo + b'I', raw[i * 12 + 8:i * 12 + 12])[0]
            val = fetch(url, p, p + sz - 1)
        if typ == 3:
            arr = list(struct.unpack(bo + b'%dH' % cnt, val[:cnt * 2]))
        elif typ == 4:
            arr = list(struct.unpack(bo + b'%dI' % cnt, val[:cnt * 4]))
        else:
            arr = list(val)
        out[TAGS.get(tag, tag)] = arr
    nxt = struct.unpack(bo + b'I', raw[n * 12:n * 12 + 4])[0]
    return out, nxt, bo


def grab_window(url, name, E0, N0, E1, N1):
    """抓取 UTM 窗口 (E0,N0)-(E1,N1) 的全分辨率 RGB。"""
    d, _, bo = read_ifd(url, 8)
    W, H = d['w'][0], d['h'][0]
    tw, th = d['tw'][0], d['th'][0]
    TO, TC = d['toff'], d['tcnt']
    # 瓦片 0 的左上角 = 影像左上角
    # 由 gdalinfo 得: gt=(300000, 10, 0, 3200040, 0, -10)
    gx, gy, res = 300000.0, 3200040.0, 10.0
    c0 = int((E0 - gx) / res); c1 = int((E1 - gx) / res)
    r0 = int((gy - N1) / res); r1 = int((gy - N0) / res)
    # 对齐到瓦片边界
    c0 = max(0, c0 // tw * tw); c1 = min(W, -(-c1 // tw) * tw)
    r0 = max(0, r0 // th * th); r1 = min(H, -(-r1 // th) * th)
    across = (W + tw - 1) // tw
    print('  %s: 影像 %dx%d, 目标行列 %d..%d / %d..%d' % (name, W, H, r0, r1, c0, c1))
    buf = np.zeros((r1 - r0, c1 - c0, 3), dtype=np.uint8)
    ntl = 0
    tot = 0
    for ty in range(r0 // th, (r1 + th - 1) // th):
        for tx in range(c0 // tw, (c1 + tw - 1) // tw):
            k = ty * across + tx
            if k >= len(TO):
                continue
            o, c = TO[k], TC[k]
            if c == 0:
                continue
            raw = fetch(url, o, o + c - 1)
            tot += len(raw)
            comp = d.get('comp', [8])[0]
            if comp in (8, 32946):
                raw = zlib.decompress(raw)
            arr = np.frombuffer(raw, dtype=np.uint8)
            need = th * tw * 3
            if arr.size < need:
                arr = np.concatenate([arr, np.zeros(need - arr.size, np.uint8)])
            arr = arr[:need].reshape(th, tw, 3)
            # 贴入
            y0 = ty * th - r0; x0 = tx * tw - c0
            ys, ye = max(0, y0), min(buf.shape[0], y0 + th)
            xs, xe = max(0, x0), min(buf.shape[1], x0 + tw)
            buf[ys:ye, xs:xe] = arr[ys - y0:ye - y0, xs - x0:xe - x0]
            ntl += 1
    print('    下载 %d 瓦片, %.2f MB -> %dx%d' % (ntl, tot / 1e6, buf.shape[1], buf.shape[0]))
    np.save(os.path.join(OUT, name + '.npy'), buf)
    lo = np.percentile(buf, 2, axis=(0, 1)); hi = np.percentile(buf, 98, axis=(0, 1))
    o8 = np.clip((buf - lo) / np.maximum(hi - lo, 1), 0, 1)
    Image.fromarray((o8 * 255).astype(np.uint8)).save(os.path.join(OUT, name + '.png'))
    print('    -> %s.png   UTM E%.0f..%.0f N%.0f..%.0f' % (name, gx + c0 * res, gx + c1 * res, gy - r1 * res, gy - r0 * res))
    return buf


if __name__ == '__main__':
    base = 'https://sentinel-cogs.s3.us-west-2.amazonaws.com/sentinel-s2-l2a-cogs/45/R/UM/2026'
    jobs = [
        ('overview_northeast', '8/S2C_45RUM_20260812_0_L2A', 330000, 3140000, 360000, 3170000),
    ]
    for name, sub, E0, N0, E1, N1 in jobs:
        url = '%s/%s/TCI.tif' % (base, sub)
        print('=== %s ===' % name)
        try:
            grab_window(url, name, E0, N0, E1, N1)
        except Exception as e:
            print('  FAIL %s' % e)
