# -*- coding: utf-8 -*-
"""
把流体层 121 帧写为 Alembic 网格序列缓存。

关键点:
  - 帧对象必须可见, 否则 Alembic 导出器会跳过
  - 用 Blender 自带导出器, 参数名按 4.5 的 RNA 自查结果
输出: F:\DeepSeek工作区\jilong\blender\jilong_flow.abc
"""
import bpy
import os
import numpy as np

B = r'F:\DeepSeek工作区\jilong'
BLD = os.path.join(B, 'blender')
NPZ = os.path.join(BLD, 'flow_data.npz')
ABC = os.path.join(BLD, 'jilong_flow.abc')

EXAG = 2.0
SCALE = 100.0

d = np.load(NPZ)
ZT = d['terrain_Z'].astype(np.float64)
TRES = float(d['terrain_res']); tNY, tNX = int(d['tNY']), int(d['tNX'])
H = d['H'].astype(np.float64)
fDX, fDY = float(d['fDX']), float(d['fDY'])
f_c0, f_r0 = int(d['f_col0']), int(d['f_row0'])
fNX, fNY = int(d['fNX']), int(d['fNY'])
nf = len(d['times'])
E0, N1 = float(d['E0']), float(d['N1'])
z0 = float(ZT.min())
cx = E0 + (tNX - 1) * TRES / 2.0
cy = N1 - (tNY - 1) * TRES / 2.0

# 地面高程(双线性取样自高精度地形)
gx = E0 + (f_c0 + np.arange(fNX)) * fDX
gy = N1 - (f_r0 + np.arange(fNY)) * fDY
FX = (gx - E0) / TRES
FY = (N1 - gy) / TRES
x0 = np.clip(np.floor(FX).astype(int), 0, tNX - 1); x1 = np.minimum(x0 + 1, tNX - 1)
y0 = np.clip(np.floor(FY).astype(int), 0, tNY - 1); y1 = np.minimum(y0 + 1, tNY - 1)
tx = np.clip(FX - x0, 0, 1)[None, :]; ty = np.clip(FY - y0, 0, 1)[:, None]
GZ = ((ZT[np.ix_(y0, x0)] * (1 - tx) + ZT[np.ix_(y0, x1)] * tx) * (1 - ty) +
      (ZT[np.ix_(y1, x0)] * (1 - tx) + ZT[np.ix_(y1, x1)] * tx) * ty)     # (fNY, fNX)

Xg, Yg = np.meshgrid((gx - cx), -(gy - cy), indexing='ij')   # (fNX, fNY)
Xg = np.ascontiguousarray(Xg.T); Yg = np.ascontiguousarray(Yg.T)
base = np.column_stack([(Xg / SCALE).ravel(), (Yg / SCALE).ravel(),
                        (((GZ - z0) * EXAG) / SCALE).ravel()])

rf = np.arange(fNY - 1); cf = np.arange(fNX - 1)
Rf, Cf = np.meshgrid(rf, cf, indexing='ij')
faces = np.column_stack([
    (Rf * fNX + Cf).ravel(), (Rf * fNX + Cf + 1).ravel(),
    ((Rf + 1) * fNX + Cf + 1).ravel(), ((Rf + 1) * fNX + Cf).ravel()])
print('流体 %d 顶点 / %d 面 / %d 帧' % (len(base), len(faces), nf))

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.fps = 12
sc.frame_start = 0
sc.frame_end = nf - 1

objs = []
for fi in range(nf):
    P = base.copy()
    P[:, 2] += (H[fi].ravel() * EXAG) / SCALE
    me = bpy.data.meshes.new('flow_%03d' % fi)
    me.from_pydata(P.tolist(), [], faces.tolist())
    me.update()
    ob = bpy.data.objects.new('flow_%03d' % fi, me)
    sc.collection.objects.link(ob)
    obj_fi = fi
    # 每帧对象按 fi 关键帧隐藏, 使 Alembic 每帧只保留一个网格
    ob.hide_viewport = False
    ob.hide_render = False
    ob.hide_set(False)
    objs.append(ob)

bpy.ops.object.select_all(action='DESELECT')
for o in objs:
    o.select_set(True)
bpy.context.view_layer.objects.active = objs[0]
print('已建 %d 个帧对象, 全部可见' % len(objs))

bpy.ops.wm.alembic_export(
    filepath=ABC, start=0, end=nf - 1,
    selected=True, flatten=False,
    export_hair=False, export_particles=False,
    normals=True, uvs=False, vcolors=True, face_sets=False,
    use_instancing=False, apply_subdiv=False,
    global_scale=1.0, as_background_job=False,
    visible_objects_only=False,
)
sz = os.path.getsize(ABC) if os.path.exists(ABC) else -1
print('ABC_EXPORTED %s  %.1f MB' % (ABC, sz / 1e6))
