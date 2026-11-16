# -*- coding: utf-8 -*-
"""
渲染流体层时序验证图并拼成一张对比表。
用法: -- <输出png> <帧号csv> [每帧宽]
"""
import bpy
import os
import sys
import numpy as np

BLEND = r'F:\DeepSeek工作区\jilong\blender\jilong_scene.blend'
argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
OUT = argv[0] if argv else r'F:\DeepSeek工作区\jilong\blender\anim_check.png'
FRAMES = [int(x) for x in argv[1].split(',')] if len(argv) > 1 else [0, 15, 30, 45, 60, 75, 90, 120]
W = int(argv[2]) if len(argv) > 2 else 900

bpy.ops.wm.open_mainfile(filepath=BLEND)
sc = bpy.context.scene
sc.render.engine = 'BLENDER_EEVEE_NEXT'
sc.render.resolution_x = W
sc.render.resolution_y = int(W * 9 / 16)
sc.render.resolution_percentage = 100
try:
    sc.eevee.taa_render_samples = 16
except Exception:
    pass
sc.render.image_settings.file_format = 'PNG'

col = bpy.data.collections.get('Flow_frames')
objs = sorted(col.objects, key=lambda o: o.name)
print('Flow_frames 对象数 %d' % len(objs))


def show_only(f):
    """直接设置可见性, 不依赖 frame_change 处理器"""
    for i, o in enumerate(objs):
        vis = (i == f)
        o.hide_viewport = not vis
        o.hide_render = not vis


tmp = []
for f in FRAMES:
    sc.frame_set(f)
    show_only(f)
    bpy.context.view_layer.update()
    vis = [o for o in objs if not o.hide_render]
    nv = len(vis[0].data.vertices) if vis else 0
    print('FRAME %3d  可见 %s  顶点 %d' % (f, [o.name for o in vis], nv))
    p = OUT.replace('.png', '_f%03d.png' % f)
    sc.render.filepath = p
    bpy.ops.render.render(write_still=True)
    tmp.append(p)

try:
    from PIL import Image
    ims = [Image.open(p) for p in tmp]
    w, h = ims[0].size
    cols = 4
    rows = int(np.ceil(len(ims) / cols))
    sheet = Image.new('RGB', (w * cols, h * rows), (18, 20, 26))
    for i, im in enumerate(ims):
        sheet.paste(im, ((i % cols) * w, (i // cols) * h))
    sheet.save(OUT)
    print('SHEET %s %s' % (OUT, sheet.size))
    for p in tmp:
        os.remove(p)
except Exception as e:
    print('拼接失败: %s' % e)
print('DONE')
