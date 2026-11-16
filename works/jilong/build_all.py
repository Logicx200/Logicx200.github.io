# -*- coding: utf-8 -*-
"""
吉隆冰崩 Blender 场景 — 一体化构建脚本
（从零重建，避免多脚本反复覆盖导致的状态混乱）

包含:
  Terrain_HR       原生 30 m 高精度地形 (270,000 顶点)
  Flow_frames      121 帧流体层, 仅湿区, 水体材质, 随帧切换
  站点标记 / 相机 / 光照 / 暗色世界

运行:
  "D:\\Blender 4.5\\blender.exe" -b --factory-startup --python build_all.py
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
WET = 0.05

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
HMAX = max(H.max(), 1e-9)
print('数据: 地形 %dx%d(%.0fm)  流体 %dx%d x %d帧' % (tNX, tNY, TRES, fNX, fNY, nf))

# ---- 流体网格点 ----
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
Xf = np.ascontiguousarray(Xg.T).ravel()
Yf = np.ascontiguousarray(Yg.T).ravel()
GZf = ((GZ - z0) * EXAG).ravel()

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.unit_settings.system = 'METRIC'
sc.render.fps = FPS
sc.frame_start = 0
sc.frame_end = nf - 1

# ================================================== 地形
txs = E0 + np.arange(tNX) * TRES - cx
tys = -((N1 - np.arange(tNY) * TRES) - cy)
TXg, TYg = np.meshgrid(txs, tys, indexing='ij')
TV = np.column_stack([np.ascontiguousarray(TXg.T).ravel(),
                      np.ascontiguousarray(TYg.T).ravel(),
                      ((ZT - z0) * EXAG).ravel()])
r = np.arange(tNY - 1); c = np.arange(tNX - 1)
R, C = np.meshgrid(r, c, indexing='ij')
TF = np.column_stack([(R * tNX + C).ravel(), (R * tNX + C + 1).ravel(),
                      ((R + 1) * tNX + C + 1).ravel(), ((R + 1) * tNX + C).ravel()])
me_t = bpy.data.meshes.new('terrain_hr')
me_t.from_pydata(TV.tolist(), [], TF.tolist())
me_t.update(); me_t.validate(verbose=False)
ob_t = bpy.data.objects.new('Terrain_HR', me_t)
sc.collection.objects.link(ob_t)
ob_t['source'] = 'native DEM ~30 m, %d x %d' % (tNX, tNY)
ob_t['vertical_exaggeration'] = EXAG
mat_t = bpy.data.materials.new('terrain_rock')
mat_t.use_nodes = True
nt = mat_t.node_tree; nt.nodes.clear()
o_ = nt.nodes.new('ShaderNodeOutputMaterial'); o_.location = (400, 0)
b_ = nt.nodes.new('ShaderNodeBsdfPrincipled'); b_.location = (150, 0)
b_.inputs['Base Color'].default_value = (0.30, 0.29, 0.28, 1)   # 深灰岩
b_.inputs['Roughness'].default_value = 0.88
nt.links.new(b_.outputs['BSDF'], o_.inputs['Surface'])
me_t.materials.append(mat_t)
print('地形 %d 顶点 / %d 面' % (len(TV), len(TF)))

# ================================================== 流体材质（水体）
mat_f = bpy.data.materials.new('water')
mat_f.use_nodes = True
nt = mat_f.node_tree; nt.nodes.clear()
o = nt.nodes.new('ShaderNodeOutputMaterial'); o.location = (1000, 0)
bs = nt.nodes.new('ShaderNodeBsdfPrincipled'); bs.location = (650, 0)
attr = nt.nodes.new('ShaderNodeVertexColor'); attr.location = (-1000, 250)
attr.layer_name = 'Depth'
ramp = nt.nodes.new('ShaderNodeValToRGB'); ramp.location = (-700, 250)
ramp.color_ramp.elements[0].position = 0.04
ramp.color_ramp.elements[0].color = (0.35, 0.80, 0.95, 1)
ramp.color_ramp.elements[1].position = 0.80
ramp.color_ramp.elements[1].color = (0.02, 0.22, 0.55, 1)
nt.links.new(attr.outputs['Color'], ramp.inputs['Fac'])
nt.links.new(ramp.outputs['Color'], bs.inputs['Base Color'])

texco = nt.nodes.new('ShaderNodeTexCoord'); texco.location = (-1000, -200)
mp = nt.nodes.new('ShaderNodeMapping'); mp.location = (-800, -200)
fnode = nt.nodes.new('ShaderNodeValue'); fnode.location = (-1200, -450)
try:
    fc = fnode.outputs[0].driver_add('default_value')
    fc.driver.type = 'SCRIPTED'; fc.driver.expression = 'frame / 40.0'
except Exception:
    pass
cmb = nt.nodes.new('ShaderNodeCombineXYZ'); cmb.location = (-1000, -450)
nt.links.new(fnode.outputs[0], cmb.inputs['X'])
nt.links.new(fnode.outputs[0], cmb.inputs['Y'])
nt.links.new(texco.outputs['Object'], mp.inputs['Vector'])
nt.links.new(cmb.outputs['Vector'], mp.inputs['Location'])
n1 = nt.nodes.new('ShaderNodeTexNoise'); n1.location = (-560, -120)
n1.inputs['Scale'].default_value = 12.0; n1.inputs['Detail'].default_value = 8.0
n2 = nt.nodes.new('ShaderNodeTexNoise'); n2.location = (-560, -400)
n2.inputs['Scale'].default_value = 40.0; n2.inputs['Detail'].default_value = 5.0
nt.links.new(mp.outputs['Vector'], n1.inputs['Vector'])
nt.links.new(mp.outputs['Vector'], n2.inputs['Vector'])
mx = nt.nodes.new('ShaderNodeMixRGB'); mx.location = (-300, -260)
mx.inputs['Fac'].default_value = 0.35
nt.links.new(n1.outputs['Fac'], mx.inputs['Color1'])
nt.links.new(n2.outputs['Fac'], mx.inputs['Color2'])
bp = nt.nodes.new('ShaderNodeBump'); bp.location = (200, -260)
bp.inputs['Strength'].default_value = 0.5; bp.inputs['Distance'].default_value = 0.4
nt.links.new(mx.outputs['Color'], bp.inputs['Height'])
nt.links.new(bp.outputs['Normal'], bs.inputs['Normal'])
bs.inputs['Roughness'].default_value = 0.04
if 'IOR' in bs.inputs:
    bs.inputs['IOR'].default_value = 1.333
for k in ('Transmission Weight', 'Transmission'):
    if k in bs.inputs:
        bs.inputs[k].default_value = 0.25
        break
if 'Metallic' in bs.inputs:
    bs.inputs['Metallic'].default_value = 0.0
nt.links.new(bs.outputs['BSDF'], o.inputs['Surface'])
print('水体材质建立')

# ================================================== 流体帧序列
col = bpy.data.collections.new('Flow_frames')
sc.collection.children.link(col)
for fi in range(nf):
    h = H[fi]
    wet = h > WET
    cell = wet[:-1, :-1] & wet[1:, :-1] & wet[:-1, 1:] & wet[1:, 1:]
    ri, ci = np.where(cell)
    me = bpy.data.meshes.new('flow_%03d' % fi)
    if ri.size > 0:
        need = np.zeros((fNY, fNX), bool)
        need[ri, ci] = True; need[ri, ci + 1] = True
        need[ri + 1, ci] = True; need[ri + 1, ci + 1] = True
        pidx = np.flatnonzero(need.ravel())
        remap = -np.ones(fNY * fNX, np.int64); remap[pidx] = np.arange(pidx.size)
        zz = GZf[pidx] + h.ravel()[pidx] * EXAG
        P = np.column_stack([Xf[pidx], Yf[pidx], zz])
        Fq = np.column_stack([remap[ri * fNX + ci], remap[ri * fNX + ci + 1],
                              remap[(ri + 1) * fNX + ci + 1], remap[(ri + 1) * fNX + ci]])
        me.from_pydata(P.tolist(), [], Fq.tolist())
        me.update(); me.validate(verbose=False)
        for p in me.polygons:
            p.use_smooth = True
        hn = np.clip(h.ravel()[pidx] / HMAX, 0, 1)
        me.color_attributes.new(name='Depth', type='FLOAT_COLOR', domain='POINT')
        me.color_attributes['Depth'].data.foreach_set(
            'color', np.column_stack([hn, hn, hn, np.ones_like(hn)]).ravel())
    me.materials.append(mat_f)
    ob = bpy.data.objects.new('Flow_t%04d' % int(round(d['times'][fi])), me)
    col.objects.link(ob)
    ob.hide_render = True; ob.hide_viewport = True
    if fi % 30 == 0:
        print('  帧 %3d 单元 %5d 顶点 %5d' % (fi, ri.size, len(me.vertices)))
print('流体帧对象 %d 个' % len(col.objects))

# 帧切换处理器
HANDLER = '''
import bpy
def _jl(dummy):
    sc = bpy.context.scene
    c = bpy.data.collections.get('Flow_frames')
    if not c: return
    f = int(round(sc.frame_current))
    for i, ob in enumerate(sorted(c.objects, key=lambda o: o.name)):
        v = (i == f)
        ob.hide_viewport = not v
        ob.hide_render = not v
bpy.app.handlers.frame_change_post.clear()
bpy.app.handlers.frame_change_post.append(_jl)
'''
t = bpy.data.texts.new('flow_frame_handler.py'); t.write(HANDLER); t.use_fake_user = True
exec(HANDLER, {'__name__': '__main__'})

# ================================================== 站点标记
def marker(name, c_, r_, col_):
    gxx = E0 + (f_c0 + c_) * fDX; gyy = N1 - (f_r0 + r_) * fDY
    xi = int(np.clip(round((gxx - E0) / TRES), 0, tNX - 1))
    yi = int(np.clip(round((N1 - gyy) / TRES), 0, tNY - 1))
    bpy.ops.mesh.primitive_uv_sphere_add(radius=300.0,
        location=(gxx - cx, -(gyy - cy), (ZT[yi, xi] - z0) * EXAG + 220))
    ob = bpy.context.active_object; ob.name = name
    m = bpy.data.materials.new(name + '_m'); m.use_nodes = True
    nn = m.node_tree.nodes.get('Principled BSDF')
    if nn:
        nn.inputs['Base Color'].default_value = col_
        nn.inputs['Roughness'].default_value = 0.45
    ob.data.materials.append(m)

marker('SRC_source', float(d['src_col']), float(d['src_row']), (0.20, 0.55, 1.0, 1))
marker('LAKE_barrier_lake', float(d['lake_col']), float(d['lake_row']), (1.0, 0.15, 0.85, 1))
marker('PORT_Jilong_port', float(d['port_col']), float(d['port_row']), (0.15, 0.90, 0.95, 1))

# ================================================== 相机 / 光照 / 世界
cam_d = bpy.data.cameras.new('Camera')
cam_d.lens = 40.0; cam_d.clip_start = 100.0; cam_d.clip_end = 5e6
cam = bpy.data.objects.new('Camera', cam_d); sc.collection.objects.link(cam)
tv = bpy.data.objects.new('TrackTarget', None); sc.collection.objects.link(tv)
tv.location = (0, 0, float(((ZT - z0) * EXAG).mean()))
con = cam.constraints.new(type='TRACK_TO'); con.target = tv
con.track_axis = 'TRACK_NEGATIVE_Z'; con.up_axis = 'UP_Y'
dist = span * 1.30
az = np.radians(258.0); el = np.radians(52.0)
cam.location = (dist * np.cos(el) * np.sin(az), dist * np.cos(el) * np.cos(az), dist * np.sin(el))
sc.camera = cam

sd = bpy.data.lights.new('Sun_key', type='SUN'); sd.energy = 3.0; sd.angle = np.radians(5)
sun = bpy.data.objects.new('Sun_key', sd); sc.collection.objects.link(sun)
sun.location = (-span * 0.5, span * 0.4, span * 1.1)
sun.rotation_euler = (np.radians(46), 0, np.radians(-115))
ad = bpy.data.lights.new('Area_fill', type='AREA'); ad.energy = 1.2e8; ad.size = span * 1.4
fill = bpy.data.objects.new('Area_fill', ad); sc.collection.objects.link(fill)
fill.location = (span * 0.6, -span * 0.7, span * 0.6)
fill.rotation_euler = (Vector((0, 0, 0)) - fill.location).to_track_quat('-Z', 'Y').to_euler()

w = bpy.data.worlds.new('World'); sc.world = w; w.use_nodes = True
bg = w.node_tree.nodes.get('Background')
if bg:
    bg.inputs['Color'].default_value = (0.055, 0.07, 0.10, 1)   # 暗色, 保证对比
    bg.inputs['Strength'].default_value = 0.7

sc.render.resolution_x = 1920; sc.render.resolution_y = 1080
sc.render.engine = 'BLENDER_EEVEE_NEXT'
try:
    sc.eevee.use_raytracing = True
except Exception:
    pass
sc.frame_set(0)

bpy.ops.wm.save_as_mainfile(filepath=BLEND)
print()
print('已保存 %s' % BLEND)
print('  Terrain_HR   %s 顶点' % format(len(TV), ','))
print('  Flow_frames  %d 个帧对象' % len(col.objects))
print('  放大 %.1f 倍, 帧 %d..%d @ %d fps' % (EXAG, sc.frame_start, sc.frame_end, FPS))
print('ALL_OK')
