# -*- coding: utf-8 -*-
"""
用高分辨率插值后的流体重建 Blender 场景。

改进:
  - 流体从粗网格 (20x140 m) 换为 30 m 各向同性, 与地形对齐
  - 湿区边缘用距离变换锥化, 消除锯齿
  - 厚度额外夸张 FLOW_EXAG 倍 (地形保持 EXAG)
  - 流体恢复深度伪彩 + 波纹法线 + 平滑着色

输出: F:\DeepSeek工作区\jilong\blender\jilong_scene.blend
"""
import bpy
import os
import numpy as np
from mathutils import Vector

B = r'F:\DeepSeek工作区\jilong'
BLD = os.path.join(B, 'blender')
NPZ = os.path.join(BLD, 'flow_hr.npz')
BLEND = os.path.join(BLD, 'jilong_scene.blend')

EXAG = 1.5          # 地形垂向放大
FLOW_EXAG = 2.5     # 流体厚度额外夸张 (相对地形)
FPS = 12
WET = 0.05

d = np.load(NPZ)
ZT = d['terrain_Z'].astype(np.float64)
TR = float(d['TR']); hNY, hNX = int(d['hNY']), int(d['hNX'])
H = d['H'].astype(np.float64)                 # (nf, hNY, hNX)
nf = H.shape[0]
times = d['times']
E0, N1 = float(d['E0']), float(d['N1'])
z0 = float(ZT.min())
cx = E0 + (hNX - 1) * TR / 2.0
cy = N1 - (hNY - 1) * TR / 2.0
span = max(hNX * TR, hNY * TR)
HMAX = max(H.max(), 1e-9)
HP99 = float(d['h_p99']) if 'h_p99' in d.files else HMAX
print('地形 %d x %d (%.0f m)   流体 %d x %d x %d 帧' % (hNX, hNY, TR, hNX, hNY, nf))
print('地形放大 %.1f  流体厚度额外夸张 %.1f  合计 %.1f'
      % (EXAG, FLOW_EXAG, EXAG * FLOW_EXAG))

# 网格坐标
gx = E0 + np.arange(hNX) * TR
gy = N1 - np.arange(hNY) * TR
Xg, Yg = np.meshgrid(gx - cx, -(gy - cy), indexing='ij')
Xf = np.ascontiguousarray(Xg.T).ravel()
Yf = np.ascontiguousarray(Yg.T).ravel()
GZf = ((ZT - z0) * EXAG).ravel()

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.unit_settings.system = 'METRIC'
sc.render.fps = FPS
sc.frame_start = 0
sc.frame_end = nf - 1

# ============================================ 地形
TV = np.column_stack([np.ascontiguousarray(Xg.T).ravel(),
                      np.ascontiguousarray(Yg.T).ravel(), GZf])
r = np.arange(hNY - 1); c = np.arange(hNX - 1)
R, C = np.meshgrid(r, c, indexing='ij')
TF = np.column_stack([(R * hNX + C).ravel(), (R * hNX + C + 1).ravel(),
                      ((R + 1) * hNX + C + 1).ravel(), ((R + 1) * hNX + C).ravel()])
me_t = bpy.data.meshes.new('terrain_hr')
me_t.from_pydata(TV.tolist(), [], TF.tolist())
me_t.update(); me_t.validate(verbose=False)
for p in me_t.polygons:
    p.use_smooth = True
ob_t = bpy.data.objects.new('Terrain_HR', me_t)
sc.collection.objects.link(ob_t)
ob_t['source'] = 'native DEM ~30 m, %d x %d' % (hNX, hNY)
ob_t['vertical_exaggeration'] = EXAG
mat_t = bpy.data.materials.new('terrain_rock')
mat_t.use_nodes = True
nt = mat_t.node_tree; nt.nodes.clear()
o_ = nt.nodes.new('ShaderNodeOutputMaterial'); o_.location = (400, 0)
b_ = nt.nodes.new('ShaderNodeBsdfPrincipled'); b_.location = (150, 0)
b_.inputs['Base Color'].default_value = (0.30, 0.29, 0.28, 1)
b_.inputs['Roughness'].default_value = 0.88
nt.links.new(b_.outputs['BSDF'], o_.inputs['Surface'])
me_t.materials.append(mat_t)
print('地形 %d 顶点 / %d 面 (平滑着色)' % (len(TV), len(TF)))

# ============================================ 流体材质
mat_f = bpy.data.materials.new('water')
mat_f.use_nodes = True
nt = mat_f.node_tree; nt.nodes.clear()
o = nt.nodes.new('ShaderNodeOutputMaterial'); o.location = (1000, 0)
bs = nt.nodes.new('ShaderNodeBsdfPrincipled'); bs.location = (650, 0)
attr = nt.nodes.new('ShaderNodeVertexColor'); attr.location = (-1000, 250)
attr.layer_name = 'Depth'
ramp = nt.nodes.new('ShaderNodeValToRGB'); ramp.location = (-700, 250)
crmp = ramp.color_ramp
crmp.interpolation = 'LINEAR'
while len(crmp.elements) > 1:
    crmp.elements.remove(crmp.elements[-1])
crmp.elements[0].position = 0.0
crmp.elements[0].color = (0.05, 0.10, 0.65, 1)
for pos, col in [(0.30, (0.05, 0.65, 0.90, 1)), (0.55, (0.35, 0.90, 0.45, 1)),
                 (0.78, (0.98, 0.85, 0.15, 1)), (1.00, (0.85, 0.10, 0.05, 1))]:
    e = crmp.elements.new(pos); e.color = col
nt.links.new(attr.outputs['Color'], ramp.inputs['Fac'])
nt.links.new(ramp.outputs['Color'], bs.inputs['Base Color'])
texco = nt.nodes.new('ShaderNodeTexCoord'); texco.location = (-1000, -200)
mp = nt.nodes.new('ShaderNodeMapping'); mp.location = (-800, -200)
fn = nt.nodes.new('ShaderNodeValue'); fn.location = (-1200, -450)
try:
    fc = fn.outputs[0].driver_add('default_value')
    fc.driver.type = 'SCRIPTED'; fc.driver.expression = 'frame / 40.0'
except Exception:
    pass
cmb = nt.nodes.new('ShaderNodeCombineXYZ'); cmb.location = (-1000, -450)
nt.links.new(fn.outputs[0], cmb.inputs['X'])
nt.links.new(fn.outputs[0], cmb.inputs['Y'])
nt.links.new(texco.outputs['Object'], mp.inputs['Vector'])
nt.links.new(cmb.outputs['Vector'], mp.inputs['Location'])
n1 = nt.nodes.new('ShaderNodeTexNoise'); n1.location = (-560, -120)
n1.inputs['Scale'].default_value = 14.0; n1.inputs['Detail'].default_value = 8.0
n2 = nt.nodes.new('ShaderNodeTexNoise'); n2.location = (-560, -400)
n2.inputs['Scale'].default_value = 46.0; n2.inputs['Detail'].default_value = 5.0
nt.links.new(mp.outputs['Vector'], n1.inputs['Vector'])
nt.links.new(mp.outputs['Vector'], n2.inputs['Vector'])
mx = nt.nodes.new('ShaderNodeMixRGB'); mx.location = (-300, -260)
mx.inputs['Fac'].default_value = 0.35
nt.links.new(n1.outputs['Fac'], mx.inputs['Color1'])
nt.links.new(n2.outputs['Fac'], mx.inputs['Color2'])
bp = nt.nodes.new('ShaderNodeBump'); bp.location = (200, -260)
bp.inputs['Strength'].default_value = 0.30; bp.inputs['Distance'].default_value = 0.25
nt.links.new(mx.outputs['Color'], bp.inputs['Height'])
nt.links.new(bp.outputs['Normal'], bs.inputs['Normal'])
bs.inputs['Roughness'].default_value = 0.22
nt.links.new(bs.outputs['BSDF'], o.inputs['Surface'])
print('流体材质: 深度伪彩 + 波纹法线')

# ============================================ 流体帧序列
col = bpy.data.collections.new('Flow_frames')
sc.collection.children.link(col)
tot_v = 0
for fi in range(nf):
    h = H[fi]
    wet = h > WET
    if not wet.any():
        me = bpy.data.meshes.new('flow_%03d' % fi)
        ob = bpy.data.objects.new('Flow_t%04d' % int(round(times[fi])), me)
        col.objects.link(ob); ob.hide_render = True; ob.hide_viewport = True
        continue
    cell = wet[:-1, :-1] & wet[1:, :-1] & wet[:-1, 1:] & wet[1:, 1:]
    ri, ci = np.where(cell)
    need = np.zeros((hNY, hNX), bool)
    need[ri, ci] = True; need[ri, ci + 1] = True
    need[ri + 1, ci] = True; need[ri + 1, ci + 1] = True
    pidx = np.flatnonzero(need.ravel())
    remap = -np.ones(hNY * hNX, np.int64); remap[pidx] = np.arange(pidx.size)
    zz = GZf[pidx] + h.ravel()[pidx] * EXAG * FLOW_EXAG
    P = np.column_stack([Xf[pidx], Yf[pidx], zz])
    Fq = np.column_stack([remap[ri * hNX + ci], remap[ri * hNX + ci + 1],
                          remap[(ri + 1) * hNX + ci + 1], remap[(ri + 1) * hNX + ci]])
    me = bpy.data.meshes.new('flow_%03d' % fi)
    me.from_pydata(P.tolist(), [], Fq.tolist())
    me.update(); me.validate(verbose=False)
    for p in me.polygons:
        p.use_smooth = True
    hn = np.clip(h.ravel()[pidx] / HP99, 0, 1)   # 用 99% 分位, 避免大部分区域挤在蓝色
    me.color_attributes.new(name='Depth', type='FLOAT_COLOR', domain='POINT')
    me.color_attributes['Depth'].data.foreach_set(
        'color', np.column_stack([hn, hn, hn, np.ones_like(hn)]).ravel())
    me.materials.append(mat_f)
    ob = bpy.data.objects.new('Flow_t%04d' % int(round(times[fi])), me)
    col.objects.link(ob)
    ob.hide_render = True; ob.hide_viewport = True
    tot_v += len(me.vertices)
    if fi % 20 == 0:
        print('  帧 %3d 单元 %6d 顶点 %6d' % (fi, ri.size, len(me.vertices)))
print('流体 %d 帧, 顶点合计 %s' % (nf, format(tot_v, ',')))

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

# ============================================ 站点标记
def marker(name, utm, col_):
    """utm = (E, N) 绝对坐标"""
    gxx, gyy = float(utm[0]), float(utm[1])
    xi = int(np.clip(round((gxx - E0) / TR), 0, hNX - 1))
    yi = int(np.clip(round((N1 - gyy) / TR), 0, hNY - 1))
    bpy.ops.mesh.primitive_uv_sphere_add(radius=300.0,
        location=(gxx - cx, -(gyy - cy), (ZT[yi, xi] - z0) * EXAG + 220))
    ob = bpy.context.active_object; ob.name = name
    m = bpy.data.materials.new(name + '_m'); m.use_nodes = True
    nn = m.node_tree.nodes.get('Principled BSDF')
    if nn:
        nn.inputs['Base Color'].default_value = col_
        nn.inputs['Roughness'].default_value = 0.45
    ob.data.materials.append(m)

marker('SRC_source', d['src_utm'], (0.20, 0.55, 1.0, 1))
marker('LAKE_barrier_lake', d['lake_utm'], (1.0, 0.15, 0.85, 1))
marker('PORT_Jilong_port', d['port_utm'], (0.15, 0.90, 0.95, 1))
print('站点标记: 源区(%.0f,%.0f) 堰塞湖(%.0f,%.0f) 口岸(%.0f,%.0f)'
      % (d['src_utm'][0], d['src_utm'][1], d['lake_utm'][0], d['lake_utm'][1],
         d['port_utm'][0], d['port_utm'][1]))

# ============================================ 相机 / 光照 / 世界
cam_d = bpy.data.cameras.new('Camera')
cam_d.lens = 40.0; cam_d.clip_start = 100.0; cam_d.clip_end = 5e6
cam = bpy.data.objects.new('Camera', cam_d); sc.collection.objects.link(cam)
tv = bpy.data.objects.new('TrackTarget', None); sc.collection.objects.link(tv)
tv.location = (0, 0, float(((ZT - z0) * EXAG).mean()))
con = cam.constraints.new(type='TRACK_TO'); con.target = tv
con.track_axis = 'TRACK_NEGATIVE_Z'; con.up_axis = 'UP_Y'
dist = span * 1.30
cam.location = (dist * np.cos(np.radians(52)) * np.sin(np.radians(258)),
                dist * np.cos(np.radians(52)) * np.cos(np.radians(258)),
                dist * np.sin(np.radians(52)))
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
    bg.inputs['Color'].default_value = (0.055, 0.07, 0.10, 1)
    bg.inputs['Strength'].default_value = 0.7
sc.render.resolution_x = 1920; sc.render.resolution_y = 1080
sc.render.engine = 'BLENDER_EEVEE_NEXT'
sc.frame_set(0)
bpy.ops.wm.save_as_mainfile(filepath=BLEND)
print()
print('已保存 %s' % BLEND)
print('  地形 %.0f m 网格, 放大 %.1f' % (TR, EXAG))
print('  流体 30 m 各向同性(插值), 厚度额外夸张 %.1f' % FLOW_EXAG)
print('HR_OK')
