# -*- coding: utf-8 -*-
"""
固定斜视角 · 白模（灰度）动画渲染

修正:
  1) 相机距离用逐角点投影反解(而非包围球), 取景更紧
  2) 地形/流体/标记用不同灰度, 使流动可读(仍是白模, 无贴图)
  3) 逐帧切换流体可见性

用法:
  blender -b --python render_white_anim.py -- <outdir> <width> [fps]
"""
import bpy
import math
import os
import sys
import numpy as np
from mathutils import Vector

BLEND = r'F:\DeepSeek工作区\jilong\blender\jilong_scene.blend'
argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
OUTDIR = argv[0] if argv else r'F:\DeepSeek工作区\jilong\blender\white_anim'
W = int(argv[1]) if len(argv) > 1 else 1280
FPS = int(argv[2]) if len(argv) > 2 else 12
AZ, EL, LENS = 256.0, 38.0, 40.0
PAD = 1.04

# 灰度方案: 地形亮, 流体暗, 标记中灰
GREY_TERRAIN = 0.82
GREY_FLOW = 0.30
GREY_SRC = 0.55
GREY_LAKE = 0.55
GREY_PORT = 0.55

os.makedirs(OUTDIR, exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=BLEND)
sc = bpy.context.scene

# ---------------- 1) 真实包围盒（地形本体） ----------------
dg = bpy.context.evaluated_depsgraph_get()
terr = bpy.data.objects['Terrain_HR']
ev = terr.evaluated_get(dg)
me = ev.to_mesh()
mw = terr.matrix_world
P = np.array([(mw @ v.co)[:] for v in me.vertices])
ev.to_mesh_clear()
lo, hi = P.min(axis=0), P.max(axis=0)
center = (lo + hi) / 2.0
print('地形包围盒 尺寸 %.0f x %.0f x %.0f  中心 (%.0f,%.0f,%.0f)'
      % (hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2], *center))

# ---------------- 2) 逐角点反解相机距离 ----------------
cam = sc.camera
cam.data.lens = LENS
cam.data.clip_start = 100.0
cam.data.clip_end = 1e7
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
view_dir = Vector((math.cos(el_r) * math.sin(az_r),
                   math.cos(el_r) * math.cos(az_r),
                   math.sin(el_r)))          # 由中心指向相机

corners = np.array([[lo[i & 1], lo[(i >> 1) & 1], lo[(i >> 2) & 1]] for i in range(8)])
rel = corners - center


def fits(dist):
    loc = Vector(center) + view_dir * dist
    cam.location = loc
    bpy.context.view_layer.update()
    inv = cam.matrix_world.inverted()
    for c in corners:
        l = inv @ Vector(c)
        if l.z >= 0:
            return False
        x = abs(l.x / (-l.z)); y = abs(l.y / (-l.z))
        if x > math.tan(fov_h / 2) * PAD or y > math.tan(fov_v / 2) * PAD:
            return False
    return True


d_hi = float(np.linalg.norm(hi - lo)) * 2.0
d_lo = 1000.0
for _ in range(60):
    d_mid = (d_lo + d_hi) / 2
    if fits(d_mid):
        d_hi = d_mid
    else:
        d_lo = d_mid
dist = d_hi
cam.location = Vector(center) + view_dir * dist
bpy.context.view_layer.update()
print('视场 %.1f x %.1f deg  相机距离 %.0f m  全部角点入画=%s'
      % (math.degrees(fov_h), math.degrees(fov_v), dist, fits(dist)))

# ---------------- 3) 白模: Workbench + 分灰度 ----------------
sc.render.engine = 'BLENDER_WORKBENCH'
sh = sc.display.shading
sh.light = 'STUDIO'
sh.studio_light = 'Default'
sh.color_type = 'OBJECT'          # 按对象颜色, 便于分层灰度
sh.show_shadows = True
sh.shadow_intensity = 0.28
sh.show_cavity = True
sh.cavity_type = 'BOTH'
sh.curvature_ridge_factor = 1.0
sh.curvature_valley_factor = 1.0
sh.show_object_outline = False
sh.background_type = 'VIEWPORT'
sh.background_color = (0.10, 0.11, 0.14)
sc.display.render_aa = '16'


def set_grey(ob, g):
    ob.color = (g, g, g, 1.0)


set_grey(terr, GREY_TERRAIN)
for n, g in [('SRC_source', GREY_SRC), ('LAKE_barrier_lake', GREY_LAKE), ('PORT_Jilong_port', GREY_PORT)]:
    o = bpy.data.objects.get(n)
    if o:
        set_grey(o, g)
col = bpy.data.collections.get('Flow_frames')
objs_f = sorted(col.objects, key=lambda o: o.name)
for o in objs_f:
    set_grey(o, GREY_FLOW)
print('灰度: 地形 %.2f  流体 %.2f  标记 %.2f' % (GREY_TERRAIN, GREY_FLOW, GREY_SRC))

# ---------------- 4) 逐帧渲染 ----------------
sc.render.image_settings.file_format = 'PNG'
sc.render.film_transparent = False
nf = len(objs_f)
sc.render.fps = FPS
print('共 %d 帧, 分辨率 %dx%d' % (nf, sc.render.resolution_x, sc.render.resolution_y))
for i in range(nf):
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
print('WHITE_ANIM_DONE %s' % OUTDIR)
