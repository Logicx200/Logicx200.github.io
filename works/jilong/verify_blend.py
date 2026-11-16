# -*- coding: utf-8 -*-
"""独立验证 jilong_final.blend: 不依赖任何外部脚本, 仅打开文件并渲染"""
import bpy, os, collections

BLEND = r'F:\DeepSeek工作区\jilong\blender\jilong_final.blend'
OUT = r'F:\DeepSeek工作区\jilong\blender\verify'
os.makedirs(OUT, exist_ok=True)

bpy.ops.wm.open_mainfile(filepath=BLEND)
sc = bpy.context.scene
print('=== 场景 ===')
print('  引擎 %s  %dx%d  fps=%d  帧范围 %d..%d' %
      (sc.render.engine, sc.render.resolution_x, sc.render.resolution_y,
       sc.render.fps, sc.frame_start, sc.frame_end))
print('  色彩变换 %s' % sc.view_settings.view_transform)
print('  Python handlers: %s' % bpy.app.handlers.frame_change_pre)

print('=== 集合 ===')
for c in bpy.data.collections:
    print('  %-14s %4d 对象' % (c.name, len(c.objects)))

print('=== 关键对象 ===')
for n in ('Terrain_HR', 'Backdrop', 'Sun', 'Camera', 'TrackTarget'):
    o = bpy.data.objects.get(n)
    if o is None:
        print('  %-12s 缺失!' % n)
    else:
        print('  %-12s %-8s verts=%-7d mats=%s' %
              (n, o.type, len(o.data.vertices) if o.type == 'MESH' else -1,
               [m.name for m in o.data.materials] if o.type == 'MESH' else '-'))

terr = bpy.data.objects.get('Terrain_HR')
print('=== 地形 ===')
print('  顶点 %d  面 %d  UV层 %d' % (len(terr.data.vertices), len(terr.data.polygons),
                                    len(terr.data.uv_layers)))
mt = terr.data.materials[0]
texn = [n for n in mt.node_tree.nodes if n.type == 'TEX_IMAGE']
if texn:
    im = texn[0].image
    print('  贴图 %s  %dx%d  packed=%s' % (im.name, im.size[0], im.size[1],
                                           im.packed_file is not None))
met = bpy.data.objects.get('Terrain_HR').data
zb = [v.co.z for v in met.vertices]
print('  z 范围 %.0f .. %.0f m' % (min(zb), max(zb)))

print('=== 逐帧可见性检查 ===')
def vis(fr):
    sc.frame_set(fr)
    on = [o.name for o in bpy.data.objects
          if o.name.startswith('Flow_') and not o.hide_render]
    tt = [o.name for o in bpy.data.objects
          if o.name.startswith('T_') and not o.hide_render]
    return on, tt
for fr in (1, 60, 121, 200, 241):
    a, t = vis(fr)
    print('  帧 %3d -> 流体 %s  时间戳 %s' % (fr, a, t))

print('=== 从 .blend 直接渲染 3 帧 ===')
sc.render.image_settings.file_format = 'PNG'
sc.render.resolution_x = 960
sc.render.resolution_y = 540
for fr in (1, 121, 241):
    sc.frame_set(fr)
    sc.render.filepath = os.path.join(OUT, 'v%04d.png' % fr)
    bpy.ops.render.render(write_still=True)
    print('  渲染帧 %d -> %s' % (fr, sc.render.filepath))
print('VERIFY_DONE')
