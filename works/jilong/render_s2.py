# -*- coding: utf-8 -*-
"""渲染 Sentinel-2 TCI 窗口为 PNG，并输出统计，用于判读冰崩源区。"""
import os
import sys
import numpy as np
from osgeo import gdal

gdal.UseExceptions()
W = r'F:\DeepSeek工作区\jilong\s2'


def render(src, dst, maxw=1400, stretch=(2, 98), gamma=1.0, tag=''):
    ds = gdal.Open(src)
    if ds is None:
        print('  无法打开 %s' % src)
        return
    nx, ny = ds.RasterXSize, ds.RasterYSize
    step = max(1, int(np.ceil(nx / maxw)))
    nx2, ny2 = nx // step, ny // step
    arr = ds.ReadAsArray(0, 0, nx2 * step, ny2 * step)
    arr = arr[:, :ny2 * step, :nx2 * step]
    # 用块平均降采样
    a = arr.reshape(arr.shape[0], ny2, step, nx2, step).mean(axis=(2, 4))
    rgb = np.transpose(a[:3], (1, 2, 0))
    gt = ds.GetGeoTransform()
    print('  %s %dx%d -> %dx%d step=%d' % (os.path.basename(src), nx, ny, nx2, ny2, step))
    for i, cn in enumerate('RGB'):
        ch = rgb[:, :, i]
        print('    %s: min=%3.0f p2=%3.0f p50=%3.0f p98=%3.0f max=%3.0f mean=%3.0f'
              % (cn, ch.min(), np.percentile(ch, 2), np.percentile(ch, 50),
                 np.percentile(ch, 98), ch.max(), ch.mean()))
    # 拉伸
    lo = np.percentile(rgb, stretch[0], axis=(0, 1))
    hi = np.percentile(rgb, stretch[1], axis=(0, 1))
    out = np.clip((rgb - lo) / np.maximum(hi - lo, 1e-6), 0, 1)
    if gamma != 1.0:
        out = out ** (1.0 / gamma)
    img = (out * 255).astype(np.uint8)
    drv = gdal.GetDriverByName('PNG')
    if os.path.exists(dst):
        drv.Delete(dst)
    ods = drv.Create(dst, nx2, ny2, 3, gdal.GDT_Byte)
    for i in range(3):
        ods.GetRasterBand(i + 1).WriteArray(img[:, :, i])
    ods = None
    print('  -> %s' % dst)
    print('     范围 E %.0f..%.0f  N %.0f..%.0f' % (
        gt[0], gt[0] + nx * gt[1], gt[3] + ny * gt[5], gt[3]))


for f in sys.argv[1:]:
    p = os.path.join(W, f)
    if not os.path.exists(p) or os.path.getsize(p) < 1000:
        print('跳过 %s (不存在或不完整)' % f)
        continue
    render(p, os.path.join(W, os.path.splitext(f)[0] + '.png'))
    print()
