# -*- coding: utf-8 -*-
"""
流体层高分辨率重建（单帧验证版）

思路:
  1) 把 MassFlow 的 H 场 (20m x 140m) 用三次样条插值到高分辨率网格
     —— 与地形网格对齐 (30 m 各向同性), 横向提升 1.3x, 纵向提升 4.7x
  2) 湿区不做硬边界: 用距离变换生成锥化系数, 让厚度在边缘平滑降到 0
     —— 消除锯齿状边缘
  3) 厚度可额外夸张 (FLOW_EXAG)

本版先只输出三帧对比, 确认效果。
"""
import os
import json
import sys
import numpy as np
from scipy.interpolate import RegularGridInterpolator
from scipy import ndimage

B = r'F:\DeepSeek工作区\jilong'
BLD = os.path.join(B, 'blender')
NPZ = os.path.join(BLD, 'flow_data.npz')

d = np.load(NPZ)
ZT = d['terrain_Z'].astype(np.float64)
TRES = float(d['terrain_res']); tNY, tNX = int(d['tNY']), int(d['tNX'])
H = d['H'].astype(np.float64)                   # (nf, fNY, fNX) 粗网格
fDX, fDY = float(d['fDX']), float(d['fDY'])
f_c0, f_r0 = int(d['f_col0']), int(d['f_row0'])
fNX, fNY = int(d['fNX']), int(d['fNY'])
nf = len(d['times'])
E0, N1 = float(d['E0']), float(d['N1'])

# ---- 目标高分辨率网格: 每 HR_STEP 个地形格取一点, 与地形对齐 ----
HR_STEP = 1                    # 1 -> 30 m 各向同性 (与地形同网格)
TR = TRES * HR_STEP
hNX = (tNX - 1) // HR_STEP + 1
hNY = (tNY - 1) // HR_STEP + 1
print('粗网格 %d x %d (%.0f x %.0f m)' % (fNX, fNY, fDX, fDY))
print('目标网格 %d x %d (%.0f m 各向同性)  顶点 %s'
      % (hNX, hNY, TR, format(hNX * hNY, ',')))

# 目标点在 UTM 中的位置
tx = E0 + np.arange(hNX) * TR
ty = N1 - np.arange(hNY) * TR
TX, TY = np.meshgrid(tx, ty)                    # (hNY, hNX)

# 粗网格点在 UTM 中的位置
cx_ = E0 + (f_c0 + np.arange(fNX)) * fDX
cy_ = N1 - (f_r0 + np.arange(fNY)) * fDY

# RegularGridInterpolator 需要升序坐标 -> 用 -N (南向为正) 保持一致
gx_asc = cx_
gy_asc = -cy_[::-1]                              # 升序
Hflip = H[:, ::-1, :]                            # 同步翻转

interp = RegularGridInterpolator(
    (gy_asc, gx_asc), np.zeros((fNY, fNX)),
    method='linear', bounds_error=False, fill_value=0.0)

# 查询点 (以升序坐标表达)
qx = TX.ravel()
qy = (-TY).ravel()
pts = np.column_stack([qy, qx])

TAU = 120.0     # 边缘锥化长度 (m)
ERO = 3         # 腐蚀/膨胀格数

def hr_frame(fi):
    """把第 fi 帧插值到高分辨率, 并做边缘锥化"""
    f = RegularGridInterpolator((gy_asc, gx_asc), Hflip[fi],
                                method='linear', bounds_error=False, fill_value=0.0)
    h = f(pts).reshape(hNY, hNX)
    h = np.maximum(h, 0.0)
    # 轻度平滑, 压掉插值产生的棱角
    h = ndimage.gaussian_filter(h, sigma=1.0, mode='nearest')
    # 湿区 + 距离变换锥化(硬边界 -> 平滑过渡)
    wet = h > 0.05
    if wet.any():
        dist = ndimage.distance_transform_edt(wet) * TR
        taper = np.clip(dist / TAU, 0.0, 1.0)
        taper = taper * taper * (3 - 2 * taper)        # smoothstep
        h = h * taper
    return h

# ---- 先出三帧统计, 确认插值合理 ----
for fi in [0, 6, 11]:
    h = hr_frame(fi)
    print('  帧 %2d: 湿区像元 %6d  最大厚 %6.1f m  总体积 %.4e m3'
          % (fi, int((h > 0.05).sum()), h.max(), h.sum() * TR * TR))

# ---- 站点绝对 UTM 坐标（避免索引平移错误） ----
def flow_utm(col_rel, row_rel):
    """flow_data.npz 中的 col/row 是裁剪后的相对索引, 转成绝对 UTM"""
    x = E0 + (float(d['f_col0']) + float(col_rel)) * fDX
    y = N1 - (float(d['f_row0']) + float(row_rel)) * fDY
    return x, y

src_utm = flow_utm(d['src_col'], d['src_row'])
lake_utm = flow_utm(d['lake_col'], d['lake_row'])
port_utm = flow_utm(d['port_col'], d['port_row'])
print('站点 UTM: 源区(%.0f, %.0f)  堰塞湖(%.0f, %.0f)  口岸(%.0f, %.0f)'
      % (src_utm + lake_utm + port_utm))

# 湿区厚度分位, 用于配色归一化(用最大值会让大部分区域都是蓝色)
allwet = H[H > 0.05]
HP99 = float(np.percentile(allwet, 99.0)) if allwet.size else float(H.max())
print('厚度分位: 中位 %.1f  95%% %.1f  99%% %.1f  最大 %.1f m (配色用 99%% = %.1f)'
      % (np.median(allwet), np.percentile(allwet, 95), HP99, H.max(), HP99))

# ---- 保存重建数据供 Blender 使用 (全部帧) ----
print('生成全部 %d 帧...' % nf)
HR = np.stack([hr_frame(fi) for fi in range(nf)]).astype(np.float32)
print('已生成 %s, %.1f MB' % (HR.shape, HR.nbytes / 1e6))
np.savez_compressed(os.path.join(BLD, 'flow_hr.npz'),
                    H=HR, TR=np.float32(TR), hNX=np.int32(hNX), hNY=np.int32(hNY),
                    times=d['times'],
                    E0=np.float64(E0), N1=np.float64(N1),
                    terrain_Z=ZT.astype(np.float32), terrain_res=np.float32(TRES),
                    src_utm=np.float64(src_utm), lake_utm=np.float64(lake_utm),
                    port_utm=np.float64(port_utm),
                    h_p99=np.float32(HP99), h_max=np.float32(H.max()))
print('已写出 flow_hr.npz  (%.1f MB)' % (os.path.getsize(os.path.join(BLD, 'flow_hr.npz')) / 1e6))
