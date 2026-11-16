# -*- coding: utf-8 -*-
"""在线窗口读取 Sentinel-2 TCI（修正窗口 + 显式 CA 证书）。"""
import os
from osgeo import gdal

gdal.UseExceptions()
CAB = r'D:\QGIS\bin\curl-ca-bundle.crt'
for k, v in [('GDAL_HTTP_VERSION', '1.1'), ('GDAL_HTTP_TIMEOUT', '120'),
             ('GDAL_HTTP_CONNECTTIMEOUT', '40'),
             ('GDAL_DISABLE_READDIR_ON_OPEN', 'EMPTY_DIR'),
             ('CPL_VSIL_CURL_ALLOWED_EXTENSIONS', '.tif'),
             ('VSI_CACHE', 'TRUE'), ('VSI_CACHE_SIZE', '300000000')]:
    gdal.SetConfigOption(k, v)
if os.path.exists(CAB):
    gdal.SetConfigOption('GDAL_CA_BUNDLE', CAB)
    os.environ['CURL_CA_BUNDLE'] = CAB
    os.environ['SSL_CERT_FILE'] = CAB
    print('CA bundle:', CAB)

# 瓦片 45RUM: gt=(300000,10,0,3200040,0,-10), 10980x10980
# 有效纬度下界约 28.30N -> N 3128000 (row 7204)
WIN = {
    # 源区大窗口（覆盖东北部所有高山候选）
    'src': [322000, 3136000, 358000, 3160000],   # 36 x 24 km
    # 口岸窗口
    'port': [330000, 3125000, 352000, 3134000],  # 22 x 9 km
}
BASE = 'https://sentinel-cogs.s3.us-west-2.amazonaws.com/sentinel-s2-l2a-cogs/45/R/UM/2026'
SCENES = {
    'pre_20260812': '8/S2C_45RUM_20260812_0_L2A',
    'post_20260916': '9/S2B_45RUM_20260916_0_L2A',
    'post_20260827': '8/S2B_45RUM_20260827_0_L2A',
}
OUT = r'F:\DeepSeek工作区\jilong\s2'
os.makedirs(OUT, exist_ok=True)

for name, sub in SCENES.items():
    url = '%s/%s/TCI.tif' % (BASE, sub)
    for tag, b in WIN.items():
        dst = os.path.join(OUT, '%s_%s.tif' % (name, tag))
        if os.path.exists(dst):
            print('  跳过 %s' % os.path.basename(dst)); continue
        print('  取 %s ...' % os.path.basename(dst), flush=True)
        try:
            gdal.Translate(dst, '/vsicurl/' + url,
                           projWin=[b[0], b[3], b[2], b[1]],
                           projWinSRS='EPSG:32645', format='GTiff',
                           creationOptions=['COMPRESS=DEFLATE', 'TILED=YES'])
            ds = gdal.Open(dst)
            print('     OK %dx%d' % (ds.RasterXSize, ds.RasterYSize), flush=True)
            ds = None
        except Exception as e:
            print('     FAIL %s' % e, flush=True)
print('完成')
