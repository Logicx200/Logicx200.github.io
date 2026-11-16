# -*- coding: utf-8 -*-
"""
地形白模预览渲染。
相机距离按域对角线 + 镜头视场自动计算, 并用 TrackTo 约束朝向域中心,
避免手工估算欧拉角出错。
"""
import bpy
import math
import os
import sys

BLEND = r'F:\DeepSeek工作区\jilong\blender\jilong_terrain.blend'
OUT = r'F:\DeepSeek工作区\jilong\blender\preview_terrain.png'
argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
if len(argv) >= 1:
    OUT = argv[0]
AZ_DEG = float(argv[1]) if len(argv) > 1 else 35.0
EL_DEG = float(argv[2]) if len(argv) > 2 else 42.0
LENS_MM = float(argv[3]) if len(argv) > 3 else 35.0

bpy.ops.wm.open_mainfile(filepath=BLEND)
sc = bpy.context.scene

# --- 取地形实际包围盒 ---
terr = bpy.data.objects['Terrain']
bb = [terr.matrix_world @ __import__('mathutils').Vector(c) for c in terr.bound_box]
xs = [v.x for v in bb]; ys = [v.y for v in bb]; zs = [v.z for v in bb]
center = ((min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0, (min(zs) + max(zs)) / 2.0)
size_x = max(xs) - min(xs)
size_y = max(ys) - min(ys)
size_z = max(zs) - min(zs)
diag = math.sqrt(size_x ** 2 + size_y ** 2)
print('包围盒  %.0f x %.0f x %.0f m  对角 %.0f m  中心 (%.0f, %.0f, %.0f)'
      % (size_x, size_y, size_z, diag, center[0], center[1], center[2]))

# --- 相机 ---
cam = sc.camera
cam.data.lens = LENS_MM
cam.data.clip_start = 100.0
cam.data.clip_end = 1e7

# 传感器 36mm, 取水平与垂直视场中较小者来决定距离, 保证整域入画
sensor = cam.data.sensor_width
res_x, res_y = sc.render.resolution_x, sc.render.resolution_y
fov_h = 2 * math.atan(sensor / (2 * LENS_MM))
fov_v = 2 * math.atan((sensor * res_y / res_x) / (2 * LENS_MM))
fov = min(fov_h, fov_v)
dist = (diag / 2.0) / math.tan(fov / 2.0) * 1.12     # 留 12% 余量
print('镜头 %.0fmm  视场 %.1f deg  相机距离 %.0f m' % (LENS_MM, math.degrees(fov), dist))

az = math.radians(AZ_DEG)
el = math.radians(EL_DEG)
cam.location = (
    center[0] + dist * math.cos(el) * math.sin(az),
    center[1] - dist * math.cos(el) * math.cos(az),
    center[2] + dist * math.sin(el),
)

# --- 用 TrackTo 约束精确朝向域中心 ---
tv = bpy.data.objects.get('TrackTarget')
if tv is None:
    tv = bpy.data.objects.new('TrackTarget', None)
    sc.collection.objects.link(tv)
tv.location = center
for c in list(cam.constraints):
    cam.constraints.remove(c)
con = cam.constraints.new(type='TRACK_TO')
con.target = tv
con.track_axis = 'TRACK_NEGATIVE_Z'
con.up_axis = 'UP_Y'
bpy.context.view_layer.update()

# --- 渲染 ---
sc.render.engine = 'BLENDER_EEVEE_NEXT'
sc.render.resolution_x = 1600
sc.render.resolution_y = 900
sc.render.resolution_percentage = 100
sc.render.film_transparent = False
try:
    sc.eevee.taa_render_samples = 24
except Exception:
    pass
sc.render.image_settings.file_format = 'PNG'
sc.render.filepath = OUT
bpy.ops.render.render(write_still=True)
print('RENDERED', OUT, os.path.getsize(OUT) if os.path.exists(OUT) else 0)
