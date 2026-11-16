# -*- coding: utf-8 -*-
"""
构建 MassFlow 吉隆冰崩工程。
依据（文献约束）：
  - 源区：蓝塘里壤峰北坡冰川，约 5200 m 处断裂
  - 冰崩体：980 m x 780 m，面积 0.76 km2
  - 体积：> 70e6 m3  -> 平均厚约 92 m
  - 与口岸落差约 3500 m，水平运动约 22 km，历时 6-7 分钟(约400 s)
  - 口岸(核心受灾点)：85.3775108E, 28.2785535N, 高程约1783 m
输出：z.txt / h.txt / input.txt / slbl.txt / V.txt
"""
import os
import numpy as np
from osgeo import osr

W = r'F:\DeepSeek工作区\jilong'
A = np.load(W + r'\dem30_final.npy').astype('f8')
ny, nx = A.shape
GE0, GN1, GRES = 322000.0, 3161000.0, 30.0
valid = A > -1000

s1 = osr.SpatialReference(); s1.ImportFromEPSG(4326); s1.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
s2 = osr.SpatialReference(); s2.ImportFromEPSG(32645); s2.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
ctU = osr.CoordinateTransformation(s1, s2)
ctL = osr.CoordinateTransformation(s2, s1)


def lonlat2rc(lon, lat):
    x, y, _ = ctU.TransformPoint(float(lon), float(lat))
    return int((x - GE0) / GRES), int((GN1 - y) / GRES), x, y


# ============ 计算域：裁剪子域 ============
# 底图有效范围 E>=322900, N 3125600..3161000
# 需覆盖: 源区(col371,row241) + 沟道(col124..629) + 口岸(col629,row1062)
E0, E1 = 322900.0, 346000.0
N0, N1 = 3126000.0, 3161000.0
c0 = int((E0 - GE0) / GRES); c1 = int((E1 - GE0) / GRES)
r0 = int((GN1 - N1) / GRES); r1 = int((GN1 - N0) / GRES)
print('子域 行 %d..%d 列 %d..%d' % (r0, r1, c0, c1))
Z = A[r0:r1, c0:c1].copy()
V = valid[r0:r1, c0:c1]
nz, nz2 = Z.shape[1], Z.shape[0]      # nx, ny
print('子域网格 %d (nx) x %d (ny)' % (nz, nz2))
print('  有效率 %.1f%%  高程 %.0f..%.0f m' % (100 * V.mean(), Z[V].min(), Z[V].max()))

# NoData 用最近邻填充（MassFlow 不接受空洞）
if not V.all():
    from scipy import ndimage
    ind = ndimage.distance_transform_edt(~V, return_distances=False, return_indices=True)
    Z[~V] = Z[tuple(ind[:, ~V])]
    print('  已用最近邻填充 %d 个空洞像元' % (~V).sum())

# ============ 源区（冰崩体）============
SRC_LON, SRC_LAT = 85.2953, 28.4997
sc, sr, sx, sy = lonlat2rc(SRC_LON, SRC_LAT)
sc -= c0; sr -= r0                      # 转到子域坐标
print()
print('源区中心 子域 col=%d row=%d 高程=%.0f m' % (sc, sr, Z[sr, sc]))

# 冰崩体 980 m x 780 m -> 32.7 x 26 格 (30m)
LEN_M, WID_M = 780.0, 980.0             # 长(流向) x 宽
AREA_T = 0.76e6                          # m2
VOL_T = 70e6                             # m3
# 采用椭圆高斯型厚度分布
a = LEN_M / 2.0                          # 半长
b = WID_M / 2.0                          # 半宽
# 流向：源区 -> 口岸方向
dx = (629 - c0) - sc; dy = (1062 - r0) - sr
theta = np.arctan2(dy, dx)               # 图像坐标(y向下)
print('流向角(图像坐标) %.1f deg' % np.degrees(theta))

yy, xx = np.mgrid[0:nz2, 0:nz]
px = (xx - sc) * GRES; py = (yy - sr) * GRES
# 旋转到流向坐标
u = px * np.cos(theta) + py * np.sin(theta)
v = -px * np.sin(theta) + py * np.cos(theta)
inside = (np.abs(u) <= a) & (np.abs(v) <= b)
ell = (u / a) ** 2 + (v / b) ** 2
# 厚度剖面：沿流向抛物线(前缘厚)，横向高斯
h_shape = np.zeros_like(Z)
prof = np.clip(1.0 - (u / a) ** 2, 0, None) ** 0.5      # 沿流向
lat = np.exp(-(v / (b * 0.55)) ** 2)                     # 横向
h_shape = np.where(inside, prof * lat, 0.0)
area = (h_shape > 0).sum() * GRES * GRES
scale_h = VOL_T / (h_shape.sum() * GRES * GRES)          # 使体积=V
H = h_shape * scale_h
print('源区: 面积 %.3f km2 (目标0.76), 体积 %.1f e6 m3 (目标70), 最大厚 %.1f m, 平均厚 %.1f m'
      % (area / 1e6, H.sum() * GRES * GRES / 1e6, H.max(), H[H > 0].mean()))

# ============ 输出 MassFlow 输入 ============
OUT = W + r'\mf_run'
os.makedirs(OUT, exist_ok=True)


def write_ascii(path, arr, xll, yll, cellsize, nodata):
    with open(path, 'w', encoding='ascii') as f:
        f.write('ncols         %d\n' % arr.shape[1])
        f.write('nrows         %d\n' % arr.shape[0])
        f.write('xllcorner     %.6f\n' % xll)
        f.write('yllcorner     %.6f\n' % yll)
        f.write('cellsize      %.6f\n' % cellsize)
        f.write('NODATA_value  %.1f\n' % nodata)
        for r in range(arr.shape[0]):
            f.write(' '.join('%.3f' % v for v in arr[r]) + '\n')


write_ascii(os.path.join(OUT, 'z.txt'), Z, E0, N0, GRES, -9999.0)
write_ascii(os.path.join(OUT, 'h.txt'), H, E0, N0, GRES, 0.0)
print()
print('已写出 z.txt / h.txt  (nx=%d, ny=%d, xll=%.0f, yll=%.0f, cellsize=%.0f)'
      % (nz, nz2, E0, N0, GRES))

# input.txt
inp = """!计算区块数
*nregions,1
!分析类型,1：单层单相流
*type,1
!考虑侵蚀,0：不考虑,1：考虑
*erosion,0
!考虑密度演化,0：不考虑,1：考虑
*density,0
!考虑惯性力
*grav_inertia,0
!计算维度,2：二维(准三维)
*ndim,2
!边界虚拟节点
*mbc,0
!网格重划分
*remesh,0
!分布式并行
*mpi,0
!共享内存并行（OpenMP）线程数
*omp,8
!通量限制器,1：minmod
*limiter,1
!初始流体高度,1：实际高度
*q1_flag,1
!求解器,1：有限差分法
*solver,1
!创建,网格信息 nx ny xll yll dx dy
*create,grid,input,1,{nx},{ny},{xll:.6f},{yll:.6f},{cs:.1f},{cs:.1f}
!创建,基底高程
*create,topo,file,dem,1,z.txt
!创建,流体
*create,h,file,dem,1,h.txt
!创建,边界
*create,bound,custom,1
!材料,编号,密度,密度值  (冰岩混合体 2000 kg/m3)
*material,1,density,2000
!材料,编号,摩擦模型,库伦模型,粘聚力,基底摩擦系数,孔隙水压力系数
*material,1,friction,1,0,0.15,0
!材料,编号,土压力系数,内摩擦角,基底摩擦角
*material,1,earthpress,0.65,0.4228
!材料分配
*material_assign,1,0,1
!时间步长: 变步长,总时间,初始步长,库郎数
*time,1,400,0.01,0.25
!输出: tecplot, 面形式, 区块1, 固定间隔, 每5秒
*output,1,tecplot,1,1,1,5
""".format(nx=nz, ny=nz2, xll=E0, yll=N0, cs=GRES)
with open(os.path.join(OUT, 'input.txt'), 'w', encoding='gbk') as f:
    f.write(inp)
print('已写出 input.txt  (总时长 400 s, 每 5 s 输出一帧, mu=0.15, c=0)')

# 保存源区信息供后续标定
np.save(os.path.join(OUT, 'Z.npy'), Z)
np.save(os.path.join(OUT, 'H.npy'), H)
meta = dict(E0=E0, N0=N0, N1=N1, E1=E1, res=GRES, nx=nz, ny=nz2,
            src_col=int(sc), src_row=int(sr), src_lon=SRC_LON, src_lat=SRC_LAT,
            port_lon=85.3775108377208, port_lat=28.2785535398864,
            area_km2=float(area / 1e6), vol_e6=float(H.sum() * GRES * GRES / 1e6),
            hmax=float(H.max()))
import json
json.dump(meta, open(os.path.join(OUT, 'meta.json'), 'w'), indent=2)
print('已写出 meta.json')
