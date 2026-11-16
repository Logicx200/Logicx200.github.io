# -*- coding: utf-8 -*-
"""调试：确认概览层标签与贴图正确性。"""
import struct
import zlib
import certifi
import numpy as np
import requests

URL = ('https://sentinel-cogs.s3.us-west-2.amazonaws.com/sentinel-s2-l2a-cogs'
       '/45/R/UM/2026/8/S2C_45RUM_20260819_0_L2A/TCI.tif')
s = requests.Session(); s.verify = certifi.where()
TAGS = {256: 'w', 257: 'h', 258: 'bits', 259: 'comp', 277: 'spp', 322: 'tw',
        323: 'th', 324: 'toff', 325: 'tcnt', 254: 'sft', 339: 'sformat',
        284: 'planar', 273: 'stripoff', 279: 'stripcnt', 278: 'rps'}
TSZ = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 6: 1, 7: 1, 8: 2, 9: 4, 10: 8, 11: 4, 12: 8}


def fetch(a, b, tries=4):
    for k in range(tries):
        try:
            r = s.get(URL, headers={'Range': 'bytes=%d-%d' % (a, b)}, timeout=120)
            r.raise_for_status(); return r.content
        except Exception:
            import time; time.sleep(1 + k)
    raise RuntimeError('fetch fail')


bo = b'<' if fetch(0, 1) == b'II' else b'>'
off = struct.unpack(bo + b'I', fetch(4, 7))[0]
lv = 0
while off and lv < 6:
    n = struct.unpack(bo + b'H', fetch(off, off + 1))[0]
    raw = fetch(off + 2, off + 2 + n * 12 + 4)
    d = {}
    for i in range(n):
        tag, typ, cnt = struct.unpack(bo + b'HHI', raw[i * 12:i * 12 + 8])
        sz = TSZ.get(typ, 1) * cnt
        if sz <= 4:
            val = raw[i * 12 + 8:i * 12 + 8 + sz]
        else:
            p = struct.unpack(bo + b'I', raw[i * 12 + 8:i * 12 + 12])[0]
            val = fetch(p, p + sz - 1)
        if typ == 3:
            arr = list(struct.unpack(bo + b'%dH' % cnt, val[:cnt * 2]))
        elif typ == 4:
            arr = list(struct.unpack(bo + b'%dI' % cnt, val[:cnt * 4]))
        else:
            arr = list(val)
        d[TAGS.get(tag, tag)] = arr
    print('IFD%d: w=%s h=%s tiles=%s tw=%s th=%s comp=%s spp=%s bits=%s sft=%s'
          % (lv, d.get('w'), d.get('h'), len(d.get('toff', [])), d.get('tw'),
             d.get('th'), d.get('comp'), d.get('spp'), d.get('bits'), d.get('sft')))
    if lv == 3:
        W, H = d['w'][0], d['h'][0]
        tw, th = d['tw'][0], d['th'][0]
        across = (W + tw - 1) // tw
        down = (H + th - 1) // th
        print('   across=%d down=%d  (应等于瓦片数 %d)' % (across, down, len(d['toff'])))
        print('   前 6 个 toff/tcnt:', list(zip(d['toff'][:6], d['tcnt'][:6])))
        # 解一个瓦片看尺寸
        o, c = d['toff'][0], d['tcnt'][0]
        raw = fetch(o, o + c - 1)
        dec = zlib.decompress(raw)
        print('   瓦片0: 压缩 %d 字节 -> 解压 %d 字节 (期望 %d)' % (c, len(dec), th * tw * 3))
        arr = np.frombuffer(dec, np.uint8)
        print('   解压后前 12 字节:', arr[:12].tolist())
    off = struct.unpack(bo + b'I', raw[n * 12:n * 12 + 4])[0]
    lv += 1
