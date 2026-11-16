# -*- coding: utf-8 -*-
"""地形白模预览：多角度批量渲染，便于确认几何。"""
import bpy
import math
import os
import sys
from mathutils import Vector

BLEND = r'F:\DeepSeek工作区\jilong\blender\jilong_terrain.blend'
OUTDIR = r'F:\DeepSeek工作区\jilong\blender'
os.makedirs(OUTDIR, exist_ok=True)

VIEWS = [
    ('persp_NE', 35.0, 40.0, 35.0),    # 从东北方俯视
    ('persp_S', 180.0, 35.0, 40.0),    # 从南方看
    ('top', 0.0, 89.0, 35.0),          # 近正射俯视
    ('low_valley', 20.0, 14.0, 50.0),  # 低角度沿河谷
]

bpy.ops.wm.open_mainfile(filepath=BLEND)
sc = bpy.context.scene
terr = bpy.data.objects['Terrain']
bb = [terr.matrix_world @ Vector(c) for c in terr.bound_box]
xs = [v.x for v in bb]; ys = [v.y for v in bb]; zs = [v.z for v in bb]
center = ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, (min(zs) + max(zs)) / 2)
size_x = max(xs) - min(xs); size_y = max(ys) - min(ys)
diag = math.sqrt(size_x ** 2 + size_y ** 2)

tv = bpy.data.objects.get('TrackTarget')
if tv is None:
    tv = bpy.data.objects.new('TrackTarget', None)
    sc.collection.objects.link(tv)
tv.location = center

cam = sc.camera
for c in list(cam.constraints):
    cam.constraints.remove(c)
con = cam.constraints.new(type='TRACK_TO')
con.target = tv
con.track_axis = 'TRACK_NEGATIVE_Z'
con.up_axis = 'UP_Y'

sc.render.engine = 'BLENDER_EEVEE_NEXT'
sc.render.resolution_x = 1600
sc.render.resolution_y = 900
sc.render.resolution_percentage = 100
try:
    sc.eevee.taa_render_samples = 24
except Exception:
    pass
sc.render.image_settings.file_format = 'PNG'

for name, az_d, el_d, lens in VIEWS:
    cam.data.lens = lens
    sensor = cam.data.sensor_width
    fov_h = 2 * math.atan(sensor / (2 * lens))
    fov_v = 2 * math.atan((sensor * sc.render.resolution_y / sc.render.resolution_x) / (2 * lens))
    fov = min(fov_h, fov_v)
    dist = (diag / 2.0) / math.tan(fov / 2.0) * 1.12
    az = math.radians(az_d); el = math.radians(el_d)
    cam.location = (center[0] + dist * math.cos(el) * math.sin(az),
                    center[1] - dist * math.cos(el) * math.cos(az),
                    center[2] + dist * math.sin(el))
    bpy.context.view_layer.update()
    out = os.path.join(OUTDIR, 'preview_%s.png' % name)
    sc.render.filepath = out
    bpy.ops.render.render(write_still=True)
    print('VIEW %-12s az=%5.0f el=%5.0f lens=%.0f  dist=%.0f  -> %s  (%d bytes)'
          % (name, az_d, el_d, lens, dist, out, os.path.getsize(out) if os.path.exists(out) else 0))
print('ALL_VIEWS_DONE')
