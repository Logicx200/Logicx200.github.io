# -*- coding: utf-8 -*-
"""抓取一幅景的源区窗口(全分辨率)并统计，判断云/雪/岩可区分性。"""
import os
import struct
import zlib
import time
import certifi
import numpy as np
import requests
from PIL import Image

W = r'F:\DeepSeek工作区\jilong\s2'
os.makedirs(W, exist_ok=True)
s = requests.Session(); s.verify = certifi.where()
BASE = 'https://sentinel-cogs.s3.us-west-2.amazonaws.com/sentinel-s2-l2a-cogs/45/R/UM/2026'
TAGS = {256: 'w', 257: 'h', 259: 'comp', 322: 'tw', 323: 'th', 324: 'toff', 325: 'tcnt'}
TSZ = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 6: 1, 7: 1, 8: 2, 9: 4, 10: 8, 11: 4, 12: 8}
GX, GY, RES = 300000.0, 3200040.0, 10.0


def fetch(url, a, b, tries=5):
    last = None
    for k in range(tries):
        try:
            r = s.get(url, headers={'Range': 'bytes=%d-%d' % (a, b)}, timeout=180)
            r.raise_for_status(); return r.content
        except Exception as e:
            last = e; time.sleep(1.5 * (k + 1))
    raise last


def ifd0(url):
    h0 = fetch(url, 0, 1)
    bo = b'<' if h0 == b'II' else b'>'
    off = struct.unpack(bo + b'I', fetch(url, 4, 7))[0]
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
        arr = list(struct.unpack(bo + b'%dH' % cnt, val[:cnt*2])) if typ == 3 else \
              list(struct.unpack(bo + b'%dI' % cnt, val[:cnt*4])) if typ == 4 else list(val)
        d[TAGS.get(tag, tag)] = arr
    return d


def grab(url, name, E0, N0, E1, N1, maxpx=2400):
    d = ifd0(url)
    IW, IH = d['w'][0], d['h'][0]
    tw, th = d['tw'][0], d['th'][0]
    TO, TC = d['toff'], d['tcnt']
    c0 = max(0, int((E0 - GX) / RES)); c1 = min(IW, int((E1 - GX) / RES))
    r0 = max(0, int((GY - N1) / RES)); r1 = min(IH, int((GY - N0) / RES))
    # 若窗口太大，按整数步长降采样（只用部分瓦片）
    step = max(1, int(np.ceil(max(r1 - r0, c1 - c0) / maxpx)))
    across = (IW + tw - 1) // tw
    out = np.zeros(((r1 - r0) // step, (c1 - c0) // step, 3), np.uint8)
    ntl = 0; tot = 0
    t0 = time.time()
    for ty in range(r0 // th, (r1 + th - 1) // th):
        for tx in range(c0 // tw, (c1 + tw - 1) // tw):
            k = ty * across + tx
            if k >= len(TO) or TC[k] == 0:
                continue
            o, c = TO[k], TC[k]
            raw = fetch(url, o, o + c - 1)
            tot += len(raw)
            if d['comp'][0] in (8, 32946):
                raw = zlib.decompress(raw)
            a = np.frombuffer(raw, np.uint8)
            need = th * tw * 3
            if a.size < need:
                a = np.concatenate([a, np.zeros(need - a.size, np.uint8)])
            a = a[:need].reshape(th, tw, 3)
            y0 = ty * th - r0; x0 = tx * tw - c0
            # 按 step 抽样贴入
            ys = max(0, y0); ye = min(r1 - r0, y0 + th)
            xs = max(0, x0); xe = min(c1 - c0, x0 + tw)
            if ye <= ys or xe <= xs:
                continue
            sub = a[ys - y0:ye - y0, xs - x0:xe - x0]
            oy = (ys + step - 1) // step * step
            ox = (xs + step - 1) // step * step
            sel = sub[(oy - ys)::step, (ox - xs)::step]
            out[(oy) // step:(oy) // step + sel.shape[0],
                (ox) // step:(ox) // step + sel.shape[1]] = sel
            ntl += 1
    print('  %s: 瓦片 %d, 下载 %.1f MB, %.0fs, 输出 %s (step=%d)' % (
        name, ntl, tot / 1e6, time.time() - t0, out.shape, step), flush=True)
    R, G, B = out[:, :, 0].astype(int), out[:, :, 1].astype(int), out[:, :, 2].astype(int)
    br = (R + G + B) / 3.0
    print('    亮度 p5=%3.0f p50=%3.0f p90=%3.0f p99=%3.0f max=%3.0f' % (
        np.percentile(br, 5), np.percentile(br, 50), np.percentile(br, 90),
        np.percentile(br, 99), br.max()))
    print('    蓝通道 p50=%3.0f  (云通常>150)' % np.percentile(B, 50))
    lo = np.percentile(out, 1, axis=(0, 1)); hi = np.percentile(out, 99, axis=(0, 1))
    o8 = np.clip((out - lo) / np.maximum(hi - lo, 1), 0, 1)
    Image.fromarray((o8 * 255).astype(np.uint8)).save(os.path.join(W, name + '.png'))
    np.save(os.path.join(W, name + '.npy'), out)
    print('    -> %s.png' % name, flush=True)


if __name__ == '__main__':
    # 灾前 08-24(云38.6%) 与 灾后 09-16(云55.4%)，源区窗口
    for nm, sub in [('win_pre_0824', '8/S2B_45RUM_20260824_0_L2A'),
                    ('win_post_0916', '9/S2B_45RUM_20260916_0_L2A')]:
        url = '%s/%s/TCI.tif' % (BASE, sub)
        print('===', nm, flush=True)
        try:
            grab(url, nm, 322000, 3136000, 358000, 3160000, maxpx=2400)
        except Exception as e:
            print('  FAIL', e, flush=True)
