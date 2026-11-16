# -*- coding: utf-8 -*-
"""
直读远程 COG 的 IFD + 概览层，只抓字节范围，不做整景下载。
用于快速判读冰崩源区。
"""
import os
import struct
import zlib
import certifi
import numpy as np
import requests

URL = ('https://sentinel-cogs.s3.us-west-2.amazonaws.com/sentinel-s2-l2a-cogs'
       '/45/R/UM/2026/8/S2C_45RUM_20260812_0_L2A/TCI.tif')
OUT = r'F:\DeepSeek工作区\jilong\s2'

s = requests.Session()
s.verify = certifi.where()


def get(a, b):
    r = s.get(URL, headers={'Range': 'bytes=%d-%d' % (a, b)}, timeout=120)
    r.raise_for_status()
    return r.content


# --- TIFF 头 ---
hdr = get(0, 15)
bo = '<' if hdr[:2] == b'II' else '>'
magic, ifd0 = struct.unpack(bo + 'HI', hdr[2:8])
print('byteorder=%s magic=%d firstIFD=%d' % (bo, magic, ifd0))

TAGS = {256: 'width', 257: 'height', 258: 'bits', 259: 'compression',
        262: 'photometric', 273: 'stripoffsets', 277: 'samplesperpixel',
        278: 'rowsperstrip', 279: 'stripbytecounts', 284: 'planarconfig',
        322: 'tilewidth', 323: 'tilelength', 324: 'tileoffsets',
        325: 'tilebytecounts', 330: 'subifds', 254: 'newsubfiletype',
        339: 'sampleformat'}
TYPESIZE = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 6: 1, 7: 1, 8: 2, 9: 4, 10: 8,
            11: 4, 12: 8, 16: 8, 17: 8, 18: 8}


def read_ifd(off):
    head = get(off, off + 1)
    n = struct.unpack(bo + b'H', head)[0]
    raw = get(off + 2, off + 2 + n * 12 + 4)
    out = {}
    for i in range(n):
        tag, typ, cnt = struct.unpack(bo + b'HHI', raw[i * 12:i * 12 + 8])
        sz = TYPESIZE.get(typ, 1) * cnt
        if sz <= 4:
            val = raw[i * 12 + 8:i * 12 + 8 + sz]
        else:
            p = struct.unpack(bo + b'I', raw[i * 12 + 8:i * 12 + 12])[0]
            val = get(p, p + sz)
        if typ == 3:
            arr = list(struct.unpack(bo + b'%dH' % cnt, val[:cnt * 2]))
        elif typ == 4:
            arr = list(struct.unpack(bo + b'%dI' % cnt, val[:cnt * 4]))
        else:
            arr = list(val)
        out[TAGS.get(tag, tag)] = arr
    nextoff = struct.unpack(bo + b'I', raw[n * 12:n * 12 + 4])[0]
    return out, nextoff


ifds = []
off = ifd0
while off:
    d, off = read_ifd(off)
    ifds.append(d)
print('共 %d 个 IFD（含概览层）' % len(ifds))
for i, d in enumerate(ifds):
    w = d.get('width', [0])[0]
    h = d.get('height', [0])[0]
    nt = len(d.get('tileoffsets', d.get('stripoffsets', [])))
    comp = d.get('compression', [1])[0]
    print('  IFD%d  %5dx%-5d  块数=%-5d compression=%d  subfiletype=%s'
          % (i, w, h, nt, comp, d.get('newsubfiletype', ['-'])[0]))

# 选一个约 1372x1372 或更小的概览层做快速判读
target = None
for i, d in enumerate(ifds):
    w = d.get('width', [0])[0]
    if 900 <= w <= 3000:
        target = (i, d)
        break
if target is None:
    target = (len(ifds) - 1, ifds[-1])
i, d = target
w, h = d['width'][0], d['height'][0]
print()
print('选用 IFD%d  %dx%d  做快速判读' % (i, w, h))

tw = d.get('tilewidth', [w])[0]
th = d.get('tilelength', [h])[0]
offs = d['tileoffsets']
cnts = d.get('tilebytecounts', [0] * len(offs))
across = (w + tw - 1) // tw
down = (h + th - 1) // th
print('  瓦片 %dx%d, 网格 %dx%d, 压缩=%d, 像素格式 bits=%s spp=%s'
      % (tw, th, across, down, d.get('compression', [1])[0],
         d.get('bits', ['?']), d.get('samplesperpixel', ['?'])))

# 下载所有瓦片（概览层瓦片很小）
buf = np.zeros((down * th, across * tw, 3), dtype=np.uint8)
tot = 0
for ty in range(down):
    for tx in range(across):
        k = ty * across + tx
        if k >= len(offs):
            continue
        o, c = offs[k], cnts[k]
        if c == 0:
            continue
        raw = get(o, o + c - 1)
        tot += len(raw)
        comp = d.get('compression', [1])[0]
        if comp == 8 or comp == 32946:
            raw = zlib.decompress(raw)
        elif comp == 1:
            pass
        elif comp == 5:
            raise SystemExit('LZW 压缩未实现')
        else:
            raise SystemExit('未支持的压缩 %d' % comp)
        arr = np.frombuffer(raw, dtype=np.uint8)
        arr = arr.reshape(th, tw, 3)
        buf[ty * th:ty * th + th, tx * tw:tx * tw + tw, :] = arr
print('  下载 %.2f MB' % (tot / 1e6))

img = buf[:h, :w, :]
os.makedirs(OUT, exist_ok=True)
np.save(os.path.join(OUT, 'overview_20260812.npy'), img)

# 存 PNG
from PIL import Image
lo = np.percentile(img, 2, axis=(0, 1))
hi = np.percentile(img, 98, axis=(0, 1))
out = np.clip((img - lo) / np.maximum(hi - lo, 1), 0, 1) ** (1 / 1.0)
Image.fromarray((out * 255).astype(np.uint8)).save(
    os.path.join(OUT, 'overview_20260812.png'))
print('  已存 overview_20260812.png (%dx%d)' % (w, h))
print('  瓦片覆盖 UTM E 300000..409800, N 3200040..3090240')
