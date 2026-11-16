# -*- coding: utf-8 -*-
"""
下载研究区真实卫星影像并重投影到与 DEM 完全一致的 UTM 45N 网格。

源: Esri World Imagery (server.arcgisonline.com tile 接口, 直连可用)
目标: EPSG:32645, E 338000-356000, N 3125500-3139000, 8192x6144

输出: sat_utm.jpg (+ sat_utm.jgw 世界文件)
"""
import os
import io
import math
import sys
import time
import concurrent.futures as cf

import requests
from requests.adapters import HTTPAdapter
from PIL import Image

try:
    import certifi
    CA = certifi.where()
except Exception:
    CA = True

B = r'F:\DeepSeek工作区\jilong'
TILE_DIR = os.path.join(B, 'sat_tiles')
OUT_JPG = os.path.join(B, 'sat_utm.jpg')

Z = 16                      # 2.1 m/px @28.3N
E0, E1 = 338000.0, 356000.0
N0, N1 = 3125500.0, 3139000.0
OW, OH = 8192, 6144

# UTM 45N 域四角
CORNERS_UTM = [(E0, N0), (E1, N0), (E1, N1), (E0, N1)]

TILE_URL = ('https://server.arcgisonline.com/ArcGIS/rest/services/'
            'World_Imagery/MapServer/tile/%d/%%d/%%d' % Z)
EMPTY_LIMIT = 2000          # 小于此字节数视为空瓦片


def utm_to_lonlat(pts):
    from osgeo import osr
    s_srs = osr.SpatialReference(); s_srs.ImportFromEPSG(32645)
    t_srs = osr.SpatialReference(); t_srs.ImportFromEPSG(4326)
    s_srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    t_srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    ct = osr.CoordinateTransformation(s_srs, t_srs)
    return [ct.TransformPoint(x, y)[:2] for x, y in pts]


def lonlat_to_merc(lon, lat):
    R = 6378137.0
    x = R * math.radians(lon)
    y = R * math.log(math.tan(math.pi / 4.0 + math.radians(lat) / 2.0))
    return x, y


def merc_to_px(x, y, z):
    """Web Mercator -> 全局像素坐标 (原点左上)"""
    world = 2.0 * math.pi * 6378137.0
    res = world / (256 * (2 ** z))
    return (x + world / 2.0) / res, (world / 2.0 - y) / res


def main():
    ll = utm_to_lonlat(CORNERS_UTM)
    print('UTM 角点 -> 经纬度:')
    for (x, y), (lo, la) in zip(CORNERS_UTM, ll):
        print('   %9.0f %9.0f -> %.6f %.6f' % (x, y, lo, la))

    me = [lonlat_to_merc(lo, la) for lo, la in ll]
    px = [merc_to_px(x, y, Z) for x, y in me]

    tx0 = int(math.floor(min(p[0] for p in px) / 256))
    tx1 = int(math.floor(max(p[0] for p in px) / 256))
    ty0 = int(math.floor(min(p[1] for p in px) / 256))
    ty1 = int(math.floor(max(p[1] for p in px) / 256))
    ntx, nty = tx1 - tx0 + 1, ty1 - ty0 + 1
    print('zoom=%d  tiles x=%d..%d  y=%d..%d  -> %d x %d = %d tiles'
          % (Z, tx0, tx1, ty0, ty1, ntx, nty, ntx * nty))

    os.makedirs(TILE_DIR, exist_ok=True)
    sess = requests.Session()
    sess.mount('https://', HTTPAdapter(pool_connections=32, pool_maxsize=32))
    sess.headers['User-Agent'] = 'Mozilla/5.0'

    jobs = [(x, y) for y in range(ty0, ty1 + 1) for x in range(tx0, tx1 + 1)]
    todo = [j for j in jobs
            if not os.path.exists(os.path.join(TILE_DIR, '%d_%d.jpg' % j))]
    print('缓存命中 %d, 需下载 %d' % (len(jobs) - len(todo), len(todo)))

    t0 = time.time()

    def fetch(j):
        x, y = j
        p = os.path.join(TILE_DIR, '%d_%d.jpg' % (x, y))
        for attempt in range(3):
            try:
                r = sess.get(TILE_URL % (y, x), timeout=30, verify=CA)
                if r.status_code == 200 and len(r.content) > EMPTY_LIMIT:
                    with open(p, 'wb') as f:
                        f.write(r.content)
                    return 1
                return 0
            except Exception:
                time.sleep(0.6 * (attempt + 1))
        return -1

    if todo:
        done = 0
        with cf.ThreadPoolExecutor(max_workers=16) as ex:
            for i, r in enumerate(ex.map(fetch, todo), 1):
                done += 1
                if i % 100 == 0:
                    print('   %d/%d  (%.0fs)' % (i, len(todo), time.time() - t0))
        print('下载完成 %.1fs' % (time.time() - t0))
    else:
        print('全部命中缓存')

    # ---- 拼接 ----
    W, H = ntx * 256, nty * 256
    print('拼接画布 %d x %d' % (W, H))
    canvas = Image.new('RGB', (W, H), (0, 0, 0))
    miss = 0
    for jy, y in enumerate(range(ty0, ty1 + 1)):
        for jx, x in enumerate(range(tx0, tx1 + 1)):
            p = os.path.join(TILE_DIR, '%d_%d.jpg' % (x, y))
            if not os.path.exists(p):
                miss += 1
                continue
            canvas.paste(Image.open(p).convert('RGB'), (jx * 256, jy * 256))
    print('缺失瓦片 %d' % miss)

    # ---- 裁到 UTM 域在 Mercator 下的最小外接框 ----
    pxmin = min(p[0] for p in px) - tx0 * 256
    pxmax = max(p[0] for p in px) - tx0 * 256
    pymin = min(p[1] for p in px) - ty0 * 256
    pymax = max(p[1] for p in px) - ty0 * 256
    canvas = canvas.crop((int(math.floor(pxmin)), int(math.floor(pymin)),
                          int(math.ceil(pxmax)), int(math.ceil(pymax))))
    cw, ch = canvas.size
    print('裁切后 %d x %d' % (cw, ch))

    # Mercator 下这个子图的边界
    world = 2.0 * math.pi * 6378137.0
    res = world / (256 * (2 ** Z))
    mx0 = (int(math.floor(pxmin)) + tx0 * 256) * res - world / 2.0
    mx1 = (int(math.ceil(pxmax)) + tx0 * 256) * res - world / 2.0
    my1 = world / 2.0 - (int(math.floor(pymin)) + ty0 * 256) * res
    my0 = world / 2.0 - (int(math.ceil(pymax)) + ty0 * 256) * res

    merc_jpg = os.path.join(B, 'sat_merc.jpg')
    canvas.save(merc_jpg, quality=92)

    # 世界文件 (Mercator)
    with open(os.path.join(B, 'sat_merc.jgw'), 'w') as f:
        f.write('%.10f\n0\n0\n%.10f\n%.10f\n%.10f\n'
                % ((mx1 - mx0) / cw, -(my1 - my0) / ch,
                   mx0 + (mx1 - mx0) / cw / 2, my1 - (my1 - my0) / ch / 2))
    with open(os.path.join(B, 'sat_merc.prj'), 'w') as f:
        f.write('PROJCS["WGS_1984_Web_Mercator_Auxiliary_Sphere",'
                'GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",'
                'SPHEROID["WGS_1984",6378137.0,298.257223563]],'
                'PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]],'
                'PROJECTION["Mercator_Auxiliary_Sphere"],'
                'PARAMETER["False_Easting",0.0],PARAMETER["False_Northing",0.0],'
                'PARAMETER["Central_Meridian",0.0],PARAMETER["Standard_Parallel_1",0.0],'
                'PARAMETER["Auxiliary_Sphere_Type",0.0],UNIT["Meter",1.0]]')
    print('写出 %s' % merc_jpg)

    # ---- gdalwarp 到 UTM 45N 精确网格 ----
    from osgeo import gdal
    gdal.UseExceptions()
    opts = gdal.WarpOptions(
        format='JPEG', dstSRS='EPSG:32645',
        outputBounds=[E0, N0, E1, N1], width=OW, height=OH,
        resampleAlg=gdal.GRA_Cubic, srcSRS='EPSG:3857',
        creationOptions=['QUALITY=92'],
    )
    ds = gdal.Warp(OUT_JPG, merc_jpg, options=opts)
    ds = None
    print('写出 %s  (%.1f MB)' % (OUT_JPG, os.path.getsize(OUT_JPG) / 1e6))

    im = Image.open(OUT_JPG)
    print('最终影像 %d x %d, %.2f m/px' % (im.width, im.height, (E1 - E0) / im.width))


if __name__ == '__main__':
    main()
