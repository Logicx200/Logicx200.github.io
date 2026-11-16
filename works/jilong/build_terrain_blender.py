# -*- coding: utf-8 -*-
"""
在 Blender 中搭建吉隆冰崩事件区的地形白模（灰模）。

用法:
  "D:\\Blender 4.5\\blender.exe" -b --factory-startup --python build_terrain_blender.py

输入: F:\\DeepSeek工作区\\jilong\\hi15\\Z.npy  +  meta.json
输出: F:\\DeepSeek工作区\\jilong\\blender\\jilong_terrain.blend

坐标约定
  Blender 为 Z-up。本脚本把 UTM 45N 网格映射为:
      X = 东向 (Easting)          -> 域中心为原点
      Y = 北向 (Northing)         -> 域中心为原点
      Z = 高程 (Elevation)        -> 减去最低点, 使谷底为 0
  单位为米。域尺寸 16.0 x 12.15 km, 高差按 EXAG 倍数垂向放大。
"""
import bpy
import json
import os
import sys
import numpy as np

JILONG = r'F:\DeepSeek工作区\jilong'
RUN = os.path.join(JILONG, 'hi15')
OUTDIR = os.path.join(JILONG, 'blender')
os.makedirs(OUTDIR, exist_ok=True)
BLEND = os.path.join(OUTDIR, 'jilong_terrain.blend')

EXAG = 2.0          # 垂向放大倍数（真实比例显得过于扁平；改造时可调）

# ---------------------------------------------------------------- 读数据
meta = json.load(open(os.path.join(RUN, 'meta.json')))
Z = np.load(os.path.join(RUN, 'Z.npy')).astype(np.float64)
NX, NY = meta['NX'], meta['NY']
DX, DY = meta['DX'], meta['DY']
print('数据: %d x %d = %d 顶点,  Z %.0f..%.0f m'
      % (NX, NY, NX * NY, Z.min(), Z.max()))
assert Z.shape == (NY, NX), 'Z 形状与 meta 不一致: %s' % (Z.shape,)

z0 = float(Z.min())
Zrel = (Z - z0) * EXAG                      # 垂向放大后, 谷底为 0

x = (np.arange(NX) * DX)
y = (np.arange(NY) * DY)
xc = x - x.mean()
yc = y - y.mean()

# ---------------------------------------------------------------- 清场景
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.unit_settings.system = 'METRIC'
scene.unit_settings.scale_length = 1.0
scene.render.engine = 'BLENDER_EEVEE_NEXT'

# ---------------------------------------------------------------- 建地形网格
print('构建网格...')
# 顶点: 行优先, 第 r 行对应 DEM 第 r 行(北->南), Blender Y 取负使其朝北
# meshgrid(xc, -yc, indexing='ij') 给出 (NX, NY); 转置回 (NY, NX) 与 Zrel 对齐
Xg, Yg = np.meshgrid(xc, -yc, indexing='ij')   # (NX, NY)
Xg = np.ascontiguousarray(Xg.T)                # (NY, NX)
Yg = np.ascontiguousarray(Yg.T)                # (NY, NX)
assert Xg.shape == (NY, NX), 'Xg 形状错误: %s' % (Xg.shape,)
verts = np.column_stack([
    Xg.ravel(),
    Yg.ravel(),
    Zrel.ravel(),
]).astype(np.float64)

# 面: 每个单元格一个四边形, 顶点顺序按逆时针(法线朝上)
r = np.arange(NY - 1)
c = np.arange(NX - 1)
R, C = np.meshgrid(r, c, indexing='ij')
v00 = (R * NX + C).ravel()
v10 = (R * NX + C + 1).ravel()
v11 = ((R + 1) * NX + C + 1).ravel()
v01 = ((R + 1) * NX + C).ravel()
faces = np.column_stack([v00, v10, v11, v01]).astype(np.int64)
print('  顶点 %d, 面 %d' % (len(verts), len(faces)))

mesh = bpy.data.meshes.new('jilong_terrain')
mesh.from_pydata(verts.tolist(), [], faces.tolist())
mesh.update()
mesh.validate(verbose=False)

# 高程渐变, 让白模也能读出地形结构 (Blender 内置 color attribute, 不是材质)
if not mesh.color_attributes:
    mesh.color_attributes.new(name='elevation', type='FLOAT_COLOR', domain='POINT')
col = mesh.color_attributes['elevation']
h = Zrel / max(Zrel.max(), 1e-9)
rgba = np.column_stack([h, h, h, np.ones_like(h)]).ravel()
col.data.foreach_set('color', rgba)

obj = bpy.data.objects.new('Terrain', mesh)
scene.collection.objects.link(obj)
obj['vertical_exaggeration'] = EXAG
obj['source_note'] = 'Elevation x%.1f ; units = metres ; valley floor = 0' % EXAG
print('地形对象已建立')

# 平直着色(看清真实网格), 材质留待后续
mat = bpy.data.materials.new('terrain_grey')
mat.use_nodes = True
bsdf = mat.node_tree.nodes.get('Principled BSDF')
if bsdf:
    bsdf.inputs['Base Color'].default_value = (0.62, 0.62, 0.62, 1.0)
    bsdf.inputs['Roughness'].default_value = 0.85
mesh.materials.append(mat)

# ---------------------------------------------------------------- 三个站点标记
def add_marker(name, col_idx, row_idx, color):
    """col/row 是网格下标, 可含小数"""
    ci, ri = int(round(col_idx)), int(round(row_idx))
    ci = max(0, min(NX - 1, ci))
    ri = max(0, min(NY - 1, ri))
    px = xc[ci] if hasattr(xc, '__len__') else xc
    py = -yc[ri]
    pz = Zrel[ri, ci]
    bpy.ops.mesh.primitive_uv_sphere_add(radius=420.0, location=(px, py, pz + 300.0))
    o = bpy.context.active_object
    o.name = name
    m = bpy.data.materials.new(name + '_mat')
    m.use_nodes = True
    b = m.node_tree.nodes.get('Principled BSDF')
    if b:
        b.inputs['Base Color'].default_value = color
        b.inputs['Roughness'].default_value = 0.4
    o.data.materials.append(m)
    return o


mk = []
mk.append(add_marker('SRC_ice_avalanche_source', meta['src_col'], meta['src_row'],
                     (0.05, 0.35, 1.0, 1.0)))
mk.append(add_marker('LAKE_barrier_lake', meta['lake_col'], meta['lake_row'],
                     (1.0, 0.1, 0.8, 1.0)))
mk.append(add_marker('PORT_Jilong_port', meta['port_col'], meta['port_row'],
                     (0.1, 0.9, 0.9, 1.0)))
print('站点标记: %d 个' % len(mk))

# ---------------------------------------------------------------- 相机 / 光照
cx, cy = 0.0, 0.0
span = max(NX * DX, NY * DY)
cam_data = bpy.data.cameras.new('Camera')
cam_data.clip_start = 50.0
cam_data.clip_end = 5e6
cam = bpy.data.objects.new('Camera', cam_data)
scene.collection.objects.link(cam)
cam.location = (cx + span * 0.30, cy - span * 0.62, span * 0.42)
cam.rotation_euler = (np.radians(56.0), 0.0, np.radians(27.0))
scene.camera = cam

sun_data = bpy.data.lights.new('Sun', type='SUN')
sun_data.energy = 3.2
sun_data.angle = np.radians(1.5)
sun = bpy.data.objects.new('Sun', sun_data)
scene.collection.objects.link(sun)
sun.location = (span * 0.5, -span * 0.5, span * 0.8)
sun.rotation_euler = (np.radians(48.0), 0.0, np.radians(38.0))

world = bpy.data.worlds.new('World')
scene.world = world
world.use_nodes = True
bg = world.node_tree.nodes.get('Background')
if bg:
    bg.inputs['Color'].default_value = (0.05, 0.06, 0.09, 1.0)
    bg.inputs['Strength'].default_value = 1.0

scene.frame_start = 0
scene.frame_end = 1200
scene.render.resolution_x = 1920
scene.render.resolution_y = 1080

# ---------------------------------------------------------------- 保存
bpy.ops.wm.save_as_mainfile(filepath=BLEND)
print()
print('已保存: %s' % BLEND)
print('顶点 %d / 面 %d / 域 %.2f x %.2f km / 高差 %.0f m (x%.1f 放大)'
      % (len(verts), len(faces), NX * DX / 1000, NY * DY / 1000,
         (Z.max() - Z.min()) * EXAG, EXAG))
print('BLEND_OK')
