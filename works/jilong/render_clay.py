# -*- coding: utf-8 -*-
"""
用 Workbench(clay/studio) 引擎渲染地形白模 —— 这是查看几何最清晰的方式。
参数: -- <输出目录> [分辨率宽]
"""
import bpy
import math
import os
import sys
from mathutils import Vector

BLEND = r'F:\DeepSeek工作区\jilong\blender\jilong_terrain.blend'
OUTDIR = r'F:\DeepSeek工作区\jilong\blender'
argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
if len(argv) >= 1:
    OUTDIR = argv[0]

VIEWS = [
    ('clay_persp', 35.0, 38.0, 35.0),
    ('clay_top', 0.0, 88.0, 35.0),
    ('clay_low', 25.0, 16.0, 45.0),
    ('clay_south', 200.0, 32.0, 40.0),
]

bpy.ops.wm.open_mainfile(filepath=BLEND)
sc = bpy.context.scene

terr = bpy.data.objects['Terrain']
bb = [terr.matrix_world @ Vector(c) for c in terr.bound_box]
xs = [v.x for v in bb]; ys = [v.y for v in bb]; zs = [v.z for v in bb]
center = ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, (min(zs) + max(zs)) / 2)
diag = math.sqrt((max(xs) - min(xs)) ** 2 + (max(ys) - min(ys)) ** 2)

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

# ---- Workbench: 干净的 studio 打光, 无阴影污染 ----
sc.render.engine = 'BLENDER_WORKBENCH'
sh = sc.display.shading
sh.light = 'STUDIO'
sh.studio_light = 'Default'
sh.color_type = 'SINGLE'
sh.single_color = (0.78, 0.78, 0.80)
sh.show_shadows = True
sh.shadow_intensity = 0.35
sh.show_cavity = True
sh.cavity_type = 'BOTH'
sh.curvature_ridge_factor = 1.0
sh.curvature_valley_factor = 1.0
sh.show_object_outline = False
sh.show_specular_highlight = True
sh.background_type = 'VIEWPORT'
sh.background_color = (0.11, 0.12, 0.15)
sc.display.render_aa = '16'

sc.render.resolution_x = 1920
sc.render.resolution_y = 1080
sc.render.resolution_percentage = 100
sc.render.image_settings.file_format = 'PNG'
sc.render.film_transparent = False

for name, az_d, el_d, lens in VIEWS:
    cam.data.lens = lens
    sensor = cam.data.sensor_width
    fov_h = 2 * math.atan(sensor / (2 * lens))
    fov_v = 2 * math.atan((sensor * sc.render.resolution_y / sc.render.resolution_x) / (2 * lens))
    fov = min(fov_h, fov_v)
    dist = (diag / 2.0) / math.tan(fov / 2.0) * 1.10
    az = math.radians(az_d); el = math.radians(el_d)
    cam.location = (center[0] + dist * math.cos(el) * math.sin(az),
                    center[1] - dist * math.cos(el) * math.cos(az),
                    center[2] + dist * math.sin(el))
    bpy.context.view_layer.update()
    out = os.path.join(OUTDIR, '%s.png' % name)
    sc.render.filepath = out
    bpy.ops.render.render(write_still=True)
    print('CLAY %-13s -> %s (%d bytes)' % (name, out,
          os.path.getsize(out) if os.path.exists(out) else 0))
print('CLAY_DONE')
