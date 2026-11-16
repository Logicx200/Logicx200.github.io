# -*- coding: utf-8 -*-
"""
验证流体层动画：渲染若干帧并拼成对比图。
用法: -- <输出png> <帧号列表,逗号分隔> [每帧宽]
"""
import bpy
import math
import os
import sys
import numpy as np
from mathutils import Vector

BLEND = r'F:\DeepSeek工作区\jilong\blender\jilong_scene.blend'
argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
OUT = argv[0] if argv else r'F:\DeepSeek工作区\jilong\blender\anim_check.png'
FRAMES = [int(x) for x in argv[1].split(',')] if len(argv) > 1 else [0, 10, 20, 30, 44, 60, 84, 120]
W = int(argv[2]) if len(argv) > 2 else 960

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

fo = bpy.data.objects.get('Flow_surface')
print('形态键数量 %d, 当前帧 %d' % (len(fo.data.shape_keys.key_blocks), sc.frame_current))

tmp = []
for f in FRAMES:
    sc.frame_set(f)
    p = OUT.replace('.png', '_f%03d.png' % f)
    sc.render.filepath = p
    bpy.ops.render.render(write_still=True)
    # 报告该帧最大厚度位置的高度, 确认动画在变
    dg = bpy.context.evaluated_depsgraph_get()
    ev = fo.evaluated_get(dg)
    me = ev.to_mesh()
    zs = np.array([v.co.z for v in me.vertices])
    base = np.array([v.co.z for v in fo.data.vertices])
    print('FRAME %3d  z_max=%.1f  dz_max=%.1f  非零形变顶点=%d'
          % (f, zs.max(), (zs - base).max(), int((np.abs(zs - base) > 0.5).sum())))
    ev.to_mesh_clear()
    tmp.append(p)

# 拼接
try:
    from PIL import Image
    ims = [Image.open(p) for p in tmp]
    w, h = ims[0].size
    cols = 4
    rows = int(np.ceil(len(ims) / cols))
    sheet = Image.new('RGB', (w * cols, h * rows), (20, 22, 28))
    for i, im in enumerate(ims):
        sheet.paste(im, ((i % cols) * w, (i // cols) * h))
    sheet.save(OUT)
    print('SHEET', OUT, sheet.size)
    for p in tmp:
        os.remove(p)
except Exception as e:
    print('拼接失败:', e)
print('DONE')
