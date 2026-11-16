# -*- coding: utf-8 -*-
"""
搭建吉隆冰崩 Blender 场景：高精度地形 + 流体层时序动画。

关键改进：流体层每帧只建"湿区"网格（H > 阈值），
避免整块矩形网格在干区与地面产生 z-fighting 穿模。

输出: F:\DeepSeek工作区\jilong\blender\jilong_scene.blend
"""
import bpy
import os
import numpy as np
from mathutils import Vector

B = r'F:\DeepSeek工作区\jilong'
BLD = os.path.join(B, 'blender')
NPZ = os.path.join(BLD, 'flow_data.npz')
BLEND = os.path.join(BLD, 'jilong_scene.blend')

EXAG = 1.5
FPS = 12
WET = 0.05          # 干湿阈值 (m)

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
span = max(tNX * TRES, tNY * TRES)
HMAXALL = max(H.max(), 1e-9)
print('地形 %d x %d (%.0f m)  流体 %d x %d x %d 帧' % (tNX, tNY, TRES, fNX, fNY, nf))

# ---- 流体网格点几何 ----
gx = E0 + (f_c0 + np.arange(fNX)) * fDX
gy = N1 - (f_r0 + np.arange(fNY)) * fDY
FX = np.clip((gx - E0) / TRES, 0, tNX - 1.001)
FY = np.clip((N1 - gy) / TRES, 0, tNY - 1.001)
x0 = np.floor(FX).astype(int); x1 = x0 + 1
y0 = np.floor(FY).astype(int); y1 = y0 + 1
tx = (FX - x0)[None, :]; ty = (FY - y0)[:, None]
GZ = ((ZT[np.ix_(y0, x0)] * (1 - tx) + ZT[np.ix_(y0, x1)] * tx) * (1 - ty) +
      (ZT[np.ix_(y1, x0)] * (1 - tx) + ZT[np.ix_(y1, x1)] * tx) * ty)
Xg, Yg = np.meshgrid(gx - cx, -(gy - cy), indexing='ij')
Xg = np.ascontiguousarray(Xg.T); Yg = np.ascontiguousarray(Yg.T)
Xf = Xg.ravel(); Yf = Yg.ravel(); GZf = ((GZ - z0) * EXAG).ravel()

# 每帧湿区统计
wet_counts = [(H[fi] > WET).sum() for fi in range(nf)]
print('湿区像元数: 最小 %d, 最大 %d, 末帧 %d' % (min(wet_counts), max(wet_counts), wet_counts[-1]))

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.unit_settings.system = 'METRIC'
sc.render.fps = FPS
sc.frame_start = 0
sc.frame_end = nf - 1

# ================= A) 高精度地形 =================
print('构建地形...')
txs = E0 + np.arange(tNX) * TRES - cx
tys = -((N1 - np.arange(tNY) * TRES) - cy)
TXg, TYg = np.meshgrid(txs, tys, indexing='ij')
TXg = np.ascontiguousarray(TXg.T); TYg = np.ascontiguousarray(TYg.T)
tverts = np.column_stack([TXg.ravel(), TYg.ravel(), ((ZT - z0) * EXAG).ravel()])
r = np.arange(tNY - 1); c = np.arange(tNX - 1)
R, C = np.meshgrid(r, c, indexing='ij')
tfaces = np.column_stack([
    (R * tNX + C).ravel(), (R * tNX + C + 1).ravel(),
    ((R + 1) * tNX + C + 1).ravel(), ((R + 1) * tNX + C).ravel()])
me_t = bpy.data.meshes.new('terrain_hr')
me_t.from_pydata(tverts.tolist(), [], tfaces.tolist())
me_t.update(); me_t.validate(verbose=False)
ob_t = bpy.data.objects.new('Terrain_HR', me_t)
sc.collection.objects.link(ob_t)
ob_t['source'] = 'native DEM ~30 m, %d x %d = %s verts' % (tNX, tNY, format(tNX * tNY, ','))
ob_t['vertical_exaggeration'] = EXAG
mat_t = bpy.data.materials.new('terrain_clay')
mat_t.use_nodes = True
bs = mat_t.node_tree.nodes.get('Principled BSDF')
if bs:
    bs.inputs['Base Color'].default_value = (0.60, 0.60, 0.62, 1)
    bs.inputs['Roughness'].default_value = 0.9
me_t.materials.append(mat_t)
print('  地形 %d 顶点 / %d 面' % (len(tverts), len(tfaces)))

# ================= B) 流体层: 每帧仅湿区 =================
print('构建流体层（仅湿区）...')
mat_f = bpy.data.materials.new('flow_mat')
mat_f.use_nodes = True
nt = mat_f.node_tree
bsf = nt.nodes.get('Principled BSDF')
if bsf:
    vc = nt.nodes.new('ShaderNodeVertexColor'); vc.layer_name = 'Depth'
    nt.links.new(vc.outputs['Color'], bsf.inputs['Base Color'])
    bsf.inputs['Roughness'].default_value = 0.30
col = bpy.data.collections.new('Flow_frames')
sc.collection.children.link(col)

# 全局顶点索引 -> 局部索引的映射表(每帧重建)
for fi in range(nf):
    h = H[fi]
    wet = h > WET
    # 只保留四角全湿的单元格 -> 形成连续流体, 避免散点状边缘
    cell = wet[:-1, :-1] & wet[1:, :-1] & wet[:-1, 1:] & wet[1:, 1:]
    ri, ci = np.where(cell)
    if ri.size == 0:
        me = bpy.data.meshes.new('flow_%03d' % fi)
        ob = bpy.data.objects.new('Flow_t%04d' % int(round(d['times'][fi])), me)
        col.objects.link(ob); ob.hide_render = True; ob.hide_viewport = True
        continue
    # 该帧用到的网格点
    need = np.zeros((fNY, fNX), bool)
    need[ri, ci] = True; need[ri, ci + 1] = True
    need[ri + 1, ci] = True; need[ri + 1, ci + 1] = True
    pidx = np.flatnonzero(need.ravel())
    remap = -np.ones(fNY * fNX, np.int64)
    remap[pidx] = np.arange(pidx.size)

    zz = GZf[pidx] + h.ravel()[pidx] * EXAG
    P = np.column_stack([Xf[pidx], Yf[pidx], zz])
    i00 = remap[ri * fNX + ci]
    i10 = remap[ri * fNX + ci + 1]
    i11 = remap[(ri + 1) * fNX + ci + 1]
    i01 = remap[(ri + 1) * fNX + ci]
    F = np.column_stack([i00, i10, i11, i01])

    me = bpy.data.meshes.new('flow_%03d' % fi)
    me.from_pydata(P.tolist(), [], F.tolist())
    me.update(); me.validate(verbose=False)
    hn = np.clip(h.ravel()[pidx] / HMAXALL, 0, 1)
    rr_ = np.clip(1.5 - np.abs(4 * hn - 3), 0, 1)
    gg_ = np.clip(1.5 - np.abs(4 * hn - 2), 0, 1)
    bb_ = np.clip(1.5 - np.abs(4 * hn - 1), 0, 1)
    me.color_attributes.new(name='Depth', type='FLOAT_COLOR', domain='POINT')
    me.color_attributes['Depth'].data.foreach_set(
        'color', np.column_stack([rr_, gg_, bb_, np.ones_like(hn)]).ravel())
    me.materials.append(mat_f)
    ob = bpy.data.objects.new('Flow_t%04d' % int(round(d['times'][fi])), me)
    col.objects.link(ob)
    ob.hide_render = True; ob.hide_viewport = True
    if fi % 20 == 0:
        print('  帧 %3d: 湿区单元 %6d, 顶点 %6d' % (fi, ri.size, pidx.size))
print('  共 %d 个帧对象' % len(col.objects))

# 帧切换处理器
HANDLER = '''
import bpy
def _jilong_flow_frame(dummy):
    sc = bpy.context.scene
    col = bpy.data.collections.get('Flow_frames')
    if col is None:
        return
    f = int(round(sc.frame_current))
    for i, ob in enumerate(sorted(col.objects, key=lambda o: o.name)):
        vis = (i == f)
        if ob.hide_viewport == vis:
            ob.hide_viewport = not vis
            ob.hide_render = not vis
_jilong_flow_frame(None)
bpy.app.handlers.frame_change_post.clear()
bpy.app.handlers.frame_change_post.append(_jilong_flow_frame)
'''
txt = bpy.data.texts.new('flow_frame_handler.py')
txt.write(HANDLER)
txt.use_fake_user = True
exec(HANDLER, {'__name__': '__main__'})
print('  帧处理器已注册')

# ================= C) 站点标记 =================
def add_marker(name, col_, row_, color):
    gxx = E0 + (f_c0 + col_) * fDX
    gyy = N1 - (f_r0 + row_) * fDY
    xi = int(np.clip(round((gxx - E0) / TRES), 0, tNX - 1))
    yi = int(np.clip(round((N1 - gyy) / TRES), 0, tNY - 1))
    gz = (ZT[yi, xi] - z0) * EXAG
    bpy.ops.mesh.primitive_uv_sphere_add(radius=380.0,
                                         location=(gxx - cx, -(gyy - cy), gz + 260))
    o = bpy.context.active_object; o.name = name
    m = bpy.data.materials.new(name + '_m'); m.use_nodes = True
    b = m.node_tree.nodes.get('Principled BSDF')
    if b:
        b.inputs['Base Color'].default_value = color
        b.inputs['Roughness'].default_value = 0.4
    o.data.materials.append(m)

add_marker('SRC_source', float(d['src_col']), float(d['src_row']), (0.15, 0.45, 1.0, 1))
add_marker('LAKE_barrier_lake', float(d['lake_col']), float(d['lake_row']), (1.0, 0.10, 0.85, 1))
add_marker('PORT_Jilong_port', float(d['port_col']), float(d['port_row']), (0.10, 0.85, 0.90, 1))

# ================= D) 相机 / 光照 =================
# 由东北方高处俯视, 顺着河谷走向(源区在东北, 口岸在西南)
cam_d = bpy.data.cameras.new('Camera')
cam_d.lens = 40.0; cam_d.clip_start = 100.0; cam_d.clip_end = 5e6
cam = bpy.data.objects.new('Camera', cam_d)
sc.collection.objects.link(cam)
tv = bpy.data.objects.new('TrackTarget', None)
sc.collection.objects.link(tv)
tv.location = (0, 0, float(((ZT - z0) * EXAG).mean()))
con = cam.constraints.new(type='TRACK_TO')
con.target = tv; con.track_axis = 'TRACK_NEGATIVE_Z'; con.up_axis = 'UP_Y'
dist = span * 1.30
az = np.radians(258.0); el = np.radians(52.0)
cam.location = (dist * np.cos(el) * np.sin(az),
                dist * np.cos(el) * np.cos(az),
                dist * np.sin(el))
sc.camera = cam
sd = bpy.data.lights.new('Sun_key', type='SUN'); sd.energy = 3.2; sd.angle = np.radians(6)
sun = bpy.data.objects.new('Sun_key', sd); sc.collection.objects.link(sun)
sun.location = (-span * 0.5, span * 0.4, span * 1.1)
sun.rotation_euler = (np.radians(48), 0, np.radians(-120))
ad = bpy.data.lights.new('Area_fill', type='AREA'); ad.energy = 2.5e8; ad.size = span * 1.2
fill = bpy.data.objects.new('Area_fill', ad); sc.collection.objects.link(fill)
fill.location = (span * 0.6, -span * 0.7, span * 0.6)
fill.rotation_euler = (Vector((0, 0, 0)) - fill.location).to_track_quat('-Z', 'Y').to_euler()
w = bpy.data.worlds.new('World'); sc.world = w; w.use_nodes = True
bg = w.node_tree.nodes.get('Background')
if bg:
    bg.inputs['Color'].default_value = (0.05, 0.06, 0.09, 1)
    bg.inputs['Strength'].default_value = 1.0
sc.render.resolution_x = 1920; sc.render.resolution_y = 1080
sc.render.engine = 'BLENDER_EEVEE_NEXT'
sc.frame_set(0)
bpy.ops.wm.save_as_mainfile(filepath=BLEND)
print()
print('已保存 %s' % BLEND)
print('  Terrain_HR   %s 顶点 (原生 30 m)' % format(len(tverts), ','))
print('  Flow_frames  %d 帧对象（仅湿区）' % nf)
print('  帧范围 %d..%d @ %d fps = %.1f s' % (sc.frame_start, sc.frame_end, FPS, (nf - 1) / FPS))
print('SCENE_OK')
