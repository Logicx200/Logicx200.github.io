# -*- coding: utf-8 -*-
"""
跨全部 Sentinel-2 景，统计源区/口岸窗口的晴空像元比例。
思路：抓取低分辨率概览层(IFD3, 1373x1373, 80m/px) 的源区瓦片，很小，逐景评估。
云判据：TCI 蓝通道高且 RGB 均高（云亮）；另用 SCL 更准但体积大。
这里用简易判据：max(R,G,B) > 200 且 |B-R| 小 => 云/雪候选，再用蓝通道 > 220 判云。
真正区分云/雪需要 SCL，本步只做"可用性排序"。
"""
import os
import struct
import zlib
import time
import certifi
import numpy as np
import requests

OUT = r'F:\DeepSeek工作区\jilong\s2'
os.makedirs(OUT, exist_ok=True)
s = requests.Session()
s.verify = certifi.where()
BASE = 'https://sentinel-cogs.s3.us-west-2.amazonaws.com/sentinel-s2-l2a-cogs/45/R/UM/2026'

# 源区大窗口（UTM 45N）
E0, N0, E1, N1 = 322000, 3136000, 358000, 3160000
GX, GY, RES = 300000.0, 3200040.0, 10.0

TAGS = {256: 'w', 257: 'h', 258: 'bits', 259: 'comp', 273: 'stripoff',
        277: 'spp', 278: 'rps', 279: 'stripcnt', 284: 'planar',
        322: 'tw', 323: 'th', 324: 'toff', 325: 'tcnt', 330: 'subifds',
        254: 'sft'}
TSZ = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 6: 1, 7: 1, 8: 2, 9: 4, 10: 8, 11: 4, 12: 8}

SCENES = [
    ('2026-08-11', '8/S2A_45RUM_20260811_0_L2A'),
    ('2026-08-12', '8/S2C_45RUM_20260812_0_L2A'),
    ('2026-08-14', '8/S2B_45RUM_20260814_1_L2A'),
    ('2026-08-19', '8/S2C_45RUM_20260819_0_L2A'),
    ('2026-08-22', '8/S2C_45RUM_20260822_0_L2A'),
    ('2026-08-24', '8/S2B_45RUM_20260824_0_L2A'),
    ('2026-08-27', '8/S2B_45RUM_20260827_0_L2A'),
    ('2026-08-29', '8/S2C_45RUM_20260829_0_L2A'),
    ('2026-09-03', '9/S2B_45RUM_20260903_0_L2A'),
    ('2026-09-08', '9/S2C_45RUM_20260908_0_L2A'),
    ('2026-09-16', '9/S2B_45RUM_20260916_0_L2A'),
    ('2026-09-18', '9/S2C_45RUM_20260918_0_L2A'),
    ('2026-09-20', '9/S2A_45RUM_20260920_0_L2A'),
    ('2026-09-21', '9/S2C_45RUM_20260921_0_L2A'),
]


def fetch(url, a, b, tries=4):
    last = None
    for k in range(tries):
        try:
            r = s.get(url, headers={'Range': 'bytes=%d-%d' % (a, b)}, timeout=120)
            r.raise_for_status()
            return r.content
        except Exception as e:
            last = e
            time.sleep(1.0 * (k + 1))
    raise last


def ifds(url):
    h0 = fetch(url, 0, 1)
    bo = b'<' if h0 == b'II' else b'>'
    off = struct.unpack(bo + b'I', fetch(url, 4, 7))[0]
    res = []
    while off:
        n = struct.unpack(bo + b'H', fetch(url, off, off + 1))[0]
        raw = fetch(url, off + 2, off + 2 + n * 12 + 4)
        d = {}
        for i in range(n):
            tag, typ, cnt = struct.unpack(bo + b'HHI', raw[i * 12:i * 12 + 8])
            sz = TSZ.get(typ, 1) * cnt
            if sz <= 4:
                val = raw[i * 12 + 8:i * 12 + 8 + sz]
            else:
                p = struct.unpack(bo + b'I', raw[i * 12 + 8:i * 12 + 12])[0]
                val = fetch(url, p, p + sz - 1)
            arr = list(struct.unpack(bo + b'%dH' % cnt, val[:cnt * 2])) if typ == 3 else \
                  list(struct.unpack(bo + b'%dI' % cnt, val[:cnt * 4])) if typ == 4 else list(val)
            d[TAGS.get(tag, tag)] = arr
        res.append(d)
        off = struct.unpack(bo + b'I', raw[n * 12:n * 12 + 4])[0]
    return res, bo


def clear_fraction(url):
    ds, bo = ifds(url)
    d = ds[3]                      # 1373x1373 (~80 m/px)
    W, H = d['w'][0], d['h'][0]
    tw, th = d['tw'][0], d['th'][0]
    sc = 10980.0 / W               # 概览层对应原图缩放
    r0 = max(0, int((GY - N1) / RES / sc) // th * th)
    r1 = min(H, -(-int((GY - N0) / RES / sc) // th) * th)
    c0 = max(0, int((E0 - GX) / RES / sc) // tw * tw)
    c1 = min(W, -(-int((E1 - GX) / RES / sc) // tw) * tw)
    across = (W + tw - 1) // tw
    buf = np.full((r1 - r0, c1 - c0, 3), 255, np.uint8)
    for ty in range(r0 // th, (r1 + th - 1) // th):
        for tx in range(c0 // tw, (c1 + tw - 1) // tw):
            k = ty * across + tx
            if k >= len(d['toff']):
                continue
            o, c = d['toff'][k], d['tcnt'][k]
            if c == 0:
                continue
            raw = fetch(url, o, o + c - 1)
            if d.get('comp', [8])[0] in (8, 32946):
                raw = zlib.decompress(raw)
            a = np.frombuffer(raw, np.uint8)
            need = th * tw * 3
            if a.size < need:
                a = np.concatenate([a, np.zeros(need - a.size, np.uint8)])
            a = a[:need].reshape(th, tw, 3)
            y0 = ty * th - r0; x0 = tx * tw - c0
            ys, ye = max(0, y0), min(buf.shape[0], y0 + th)
            xs, xe = max(0, x0), min(buf.shape[1], x0 + tw)
            buf[ys:ye, xs:xe] = a[ys - y0:ye - y0, xs - x0:xe - x0]
    # 云判据：亮且偏蓝白
    R, G, B = buf[:, :, 0].astype(int), buf[:, :, 1].astype(int), buf[:, :, 2].astype(int)
    bright = (R + G + B) / 3.0
    cloud = (bright > 165) & (B > 150) & (np.abs(B - R) < 40)
    dark = bright < 8
    return 1.0 - cloud.mean(), cloud.mean(), dark.mean(), buf


print('%-12s %8s %8s %8s' % ('日期', '晴空%', '云%', '极暗%'))
rows = []
for dt, sub in SCENES:
    url = '%s/%s/TCI.tif' % (BASE, sub)
    try:
        t0 = time.time()
        clr, cld, dk, buf = clear_fraction(url)
        rows.append((clr, dt, sub, cld, dk))
        print('%-12s %7.1f%% %7.1f%% %7.1f%%   (%.0fs)' % (dt, clr * 100, cld * 100, dk * 100, time.time() - t0), flush=True)
        np.save(os.path.join(OUT, 'ov_%s.npy' % dt.replace('-', '')), buf)
    except Exception as e:
        import traceback
        print('%-12s FAIL %s' % (dt, e), flush=True)
        traceback.print_exc()

rows.sort(reverse=True)
print()
print('=== 按源区晴空率排序 ===')
for clr, dt, sub, cld, dk in rows:
    print('  %s  晴空 %5.1f%%  云 %5.1f%%  %s' % (dt, clr * 100, cld * 100, sub))
