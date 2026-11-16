# -*- coding: utf-8 -*-
"""
白模动画（整模型入画，流体清晰可读）

关键修正:
  1) 颜色改用 MATERIAL 模式 + 独立灰阶材质 (OBJECT 模式在此不生效)
  2) 包围盒用流体几何的真实最大高度, 而非全局最大厚度
  3) 相机由逐角点二分反解, 取景紧凑

用法: blender -b --python white_anim.py -- <outdir> <width> [fps] [flow_total_exag]
"""
import bpy
import math
import os
import sys
import numpy as np
from mathutils import Vector

B = r'F:\DeepSeek工作区\jilong'
BLD = os.path.join(B, 'blender')
NPZ = os.path.join(BLD, 'flow_hr.npz')
BLEND = os.path.join(BLD, 'jilong_scene.blend')

argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
OUTDIR = argv[0] if argv else os.path.join(BLD, 'white_anim')
W = int(argv[1]) if len(argv) > 1 else 1280
FPS = int(argv[2]) if len(argv) > 2 else 12
FEXAG = float(argv[3]) if len(argv) > 3 else 7.0

EXAG, AZ, EL, LENS, PAD = 1.5, 256.0, 38.0, 40.0, 1.04
AZ = float(os.environ.get('WAZ', AZ))
EL = float(os.environ.get('WEL', EL))
G_TERRAIN, G_FLOW, G_MARK = 0.88, 0.10, 0.38
WET = 0.05

os.makedirs(OUTDIR, exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=BLEND)
sc = bpy.context.scene

d = np.load(NPZ)
ZT = d['terrain_Z'].astype(np.float64)
TR = float(d['TR']); hNY, hNX = int(d['hNY']), int(d['hNX'])
H = d['H'].astype(np.float64)
nf = H.shape[0]; times = d['times']
E0, N1 = float(d['E0']), float(d['N1'])
z0 = float(ZT.min())
cx = E0 + (hNX - 1) * TR / 2.0
cy = N1 - (hNY - 1) * TR / 2.0
print('流体厚度总放大 %.1f 倍' % FEXAG)

gx = E0 + np.arange(hNX) * TR
gy = N1 - np.arange(hNY) * TR
Xg, Yg = np.meshgrid(gx - cx, -(gy - cy), indexing='ij')
Xf = np.ascontiguousarray(Xg.T).ravel()
Yf = np.ascontiguousarray(Yg.T).ravel()
GZf = ((ZT - z0) * EXAG).ravel()

# ---------------- 材质: 独立灰阶 ----------------
def make_grey(name, g):
    m = bpy.data.materials.get(name)
    if m is None:
        m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree; nt.nodes.clear()
    o = nt.nodes.new('ShaderNodeOutputMaterial'); o.location = (300, 0)
    b = nt.nodes.new('ShaderNodeBsdfPrincipled'); b.location = (50, 0)
    b.inputs['Base Color'].default_value = (g, g, g, 1)
    b.inputs['Roughness'].default_value = 0.75
    nt.links.new(b.outputs['BSDF'], o.inputs['Surface'])
    m.diffuse_color = (g, g, g, 1)          # 视口/Workbench 兜底
    m.roughness = 0.75
    return m

mat_terr = make_grey('clay_terrain', G_TERRAIN)
mat_flow = make_grey('clay_flow', G_FLOW)
mat_mark = make_grey('clay_mark', G_MARK)

terr = bpy.data.objects['Terrain_HR']
terr.data.materials.clear()
terr.data.materials.append(mat_terr)
for n in ('SRC_source', 'LAKE_barrier_lake', 'PORT_Jilong_port'):
    o = bpy.data.objects.get(n)
    if o:
        o.data.materials.clear()
        o.data.materials.append(mat_mark)

# ---------------- 重建流体帧网格 ----------------
col = bpy.data.collections.get('Flow_frames')
for o in list(col.objects):
    me = o.data
    col.objects.unlink(o)
    bpy.data.objects.remove(o, do_unlink=True)
    if me.users == 0:
        bpy.data.meshes.remove(me)
print('重建流体网格 (%d 帧)...' % nf)
fz_max = -1e18
for fi in range(nf):
    h = H[fi]
    wet = h > WET
    me = bpy.data.meshes.new('flow_%03d' % fi)
    if wet.any():
        cell = wet[:-1, :-1] & wet[1:, :-1] & wet[:-1, 1:] & wet[1:, 1:]
        ri, ci = np.where(cell)
        if ri.size:
            need = np.zeros((hNY, hNX), bool)
            need[ri, ci] = True; need[ri, ci + 1] = True
            need[ri + 1, ci] = True; need[ri + 1, ci + 1] = True
            pidx = np.flatnonzero(need.ravel())
            remap = -np.ones(hNY * hNX, np.int64); remap[pidx] = np.arange(pidx.size)
            zz = GZf[pidx] + h.ravel()[pidx] * FEXAG
            fz_max = max(fz_max, float(zz.max()))
            P = np.column_stack([Xf[pidx], Yf[pidx], zz])
            Fq = np.column_stack([remap[ri * hNX + ci], remap[ri * hNX + ci + 1],
                                  remap[(ri + 1) * hNX + ci + 1], remap[(ri + 1) * hNX + ci]])
            me.from_pydata(P.tolist(), [], Fq.tolist())
            me.update(); me.validate(verbose=False)
            for p in me.polygons:
                p.use_smooth = True
    me.materials.append(mat_flow)
    ob = bpy.data.objects.new('Flow_t%04d' % int(round(times[fi])), me)
    col.objects.link(ob)
    ob.hide_render = True; ob.hide_viewport = True
objs_f = sorted(col.objects, key=lambda o: o.name)
print('流体帧对象 %d, 最大高度 %.0f m' % (len(objs_f), fz_max))

# ---------------- 相机 ----------------
dg = bpy.context.evaluated_depsgraph_get()
ev = terr.evaluated_get(dg); mt = ev.to_mesh()
P = np.array([(terr.matrix_world @ v.co)[:] for v in mt.vertices])
ev.to_mesh_clear()
lo = P.min(axis=0).copy(); hi = P.max(axis=0).copy()
hi[2] = max(hi[2], fz_max)
center = (lo + hi) / 2.0
print('包围盒 尺寸 %.0f x %.0f x %.0f' % tuple(hi - lo))

cam = sc.camera
cam.data.lens = LENS; cam.data.clip_start = 100.0; cam.data.clip_end = 1e7
sc.render.resolution_x = W
sc.render.resolution_y = int(round(W * 9 / 16))
sensor = cam.data.sensor_width
fov_h = 2 * math.atan(sensor / (2 * LENS))
fov_v = 2 * math.atan((sensor * sc.render.resolution_y / sc.render.resolution_x) / (2 * LENS))
tv = bpy.data.objects.get('TrackTarget')
tv.location = tuple(center)
for c in list(cam.constraints):
    cam.constraints.remove(c)
con = cam.constraints.new(type='TRACK_TO'); con.target = tv
con.track_axis = 'TRACK_NEGATIVE_Z'; con.up_axis = 'UP_Y'
az_r, el_r = math.radians(AZ), math.radians(EL)
vdir = Vector((math.cos(el_r) * math.sin(az_r), math.cos(el_r) * math.cos(az_r), math.sin(el_r)))
FIT = 0.94   # 内容最多占半画面的比例
# 用地表真实顶点做投影拟合（AABB 角点会造出不存在的近端低角点，把相机推远）
pts = P[::6]
if fz_max > hi[2]:
    up = np.zeros((1, 3)); up[0] = (center[0], center[1], fz_max)
    pts = np.vstack([pts, up])
print('拟合用点 %d' % len(pts))


def ratio(dist):
    """返回 max(|x|/允许半宽, |y|/允许半高)；<=1 表示全部入画。"""
    cam.location = Vector(center) + vdir * dist
    bpy.context.view_layer.update()
    dg2 = bpy.context.evaluated_depsgraph_get()
    M = np.array(cam.evaluated_get(dg2).matrix_world.inverted())
    Q = pts @ M[:3, :3].T + M[:3, 3]
    z = -Q[:, 2]
    if (z <= 1.0).any():
        return 1e9
    tx = math.tan(fov_h / 2) * FIT
    ty = math.tan(fov_v / 2) * FIT
    return float(max((np.abs(Q[:, 0]) / z / tx).max(), (np.abs(Q[:, 1]) / z / ty).max()))


d_hi = float(np.linalg.norm(hi - lo)) * 2.5
for _ in range(40):
    if ratio(d_hi) <= 1.0:
        break
    d_hi *= 1.3
d_lo = d_hi * 0.25
for _ in range(60):
    d_mid = 0.5 * (d_lo + d_hi)
    if ratio(d_mid) <= 1.0:
        d_hi = d_mid
    else:
        d_lo = d_mid
dist = d_hi
cam.location = Vector(center) + vdir * dist
bpy.context.view_layer.update()
r_now = ratio(dist)
print('相机距离 %.0f m  投影占比 %.3f (<=1 全部入画)' % (dist, r_now))

# ---------------- Workbench 渲染 ----------------
sc.render.engine = 'BLENDER_WORKBENCH'
sh = sc.display.shading
sh.light = 'STUDIO'; sh.studio_light = 'Default'
sh.color_type = 'MATERIAL'
sh.show_shadows = True; sh.shadow_intensity = 0.18
sh.show_cavity = False          # cavity 会在满屏刻出黑沟，把细流体 ribbon 淹掉
sh.show_object_outline = False
sh.background_type = 'VIEWPORT'; sh.background_color = (0.10, 0.11, 0.14)
sc.display.render_aa = '16'
sc.render.image_settings.file_format = 'PNG'
sc.render.film_transparent = False
sc.render.fps = FPS
print('共 %d 帧, %dx%d' % (nf, sc.render.resolution_x, sc.render.resolution_y))
FRAMES_ARG = os.environ.get('WFRAMES', '').strip()
if FRAMES_ARG:
    frame_list = [int(x) for x in FRAMES_ARG.split(',')]
else:
    frame_list = list(range(nf))
for i in frame_list:
    sc.frame_set(i)
    for j, o2 in enumerate(objs_f):
        v = (j == i)
        o2.hide_viewport = not v
        o2.hide_render = not v
    bpy.context.view_layer.update()
    sc.render.filepath = os.path.join(OUTDIR, 'w%04d.png' % i)
    bpy.ops.render.render(write_still=True)
    if i % 20 == 0:
        print('  渲染 %d/%d' % (i, nf - 1))
if not FRAMES_ARG:
    bpy.ops.wm.save_as_mainfile(filepath=BLEND)
print('WHITE_ANIM_DONE %s' % OUTDIR)
