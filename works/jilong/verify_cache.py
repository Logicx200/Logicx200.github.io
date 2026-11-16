# -*- coding: utf-8 -*-
"""核查 MDD 缓存与 Flow_surface 网格是否真正匹配。"""
import bpy
import os
import struct
import numpy as np

BLEND = r'F:\DeepSeek工作区\jilong\blender\jilong_scene.blend'
MDD = r'F:\DeepSeek工作区\jilong\blender\jilong_flow.mdd'

bpy.ops.wm.open_mainfile(filepath=BLEND)
sc = bpy.context.scene
print('帧范围 %d..%d  fps=%d' % (sc.frame_start, sc.frame_end, sc.render.fps))
for o in bpy.data.objects:
    if o.type == 'MESH':
        print('对象 %-16s 顶点 %6d  面 %6d' % (o.name, len(o.data.vertices), len(o.data.polygons)))

fo = bpy.data.objects.get('Flow_surface')
print()
print('Flow_surface 修改器:')
for m in fo.modifiers:
    print('   %s  type=%s' % (m.name, m.type))
    if m.type == 'MESH_CACHE':
        print('      cache_format=%s' % m.cache_format)
        print('      filepath=%s' % m.filepath)
        print('      存在=%s' % os.path.exists(bpy.path.abspath(m.filepath)))
        print('      forward_axis=%s up_axis=%s' % (m.forward_axis, m.up_axis))
        try:
            print('      time_mode=%s' % m.time_mode)
            print('      frame_start=%s frame_end=%s' % (m.frame_start, m.frame_end))
        except Exception as e:
            print('      ', e)

# 独立解析 MDD 全文件做完整性校验
size = os.path.getsize(MDD)
with open(MDD, 'rb') as f:
    hdr = struct.unpack('>5if', f.read(24))
samples, fps_, pts, frames, t0, t1 = hdr
per_pt = 3 * 4 + 2 * 4
expect = 24 + pts * frames * per_pt
print()
print('MDD 解析: samples=%d fps=%d points=%d frames=%d time=%.0f..%.0f' % (samples, fps_, pts, frames, t0, t1))
print('  期望大小 %d 字节, 实际 %d 字节, 匹配=%s' % (expect, size, expect == size))
print('  实际/期望 每点字节 %d' % ((size - 24) / (pts * frames)))
print('  网格顶点 %d, MDD 顶点 %d, 一致=%s' % (len(fo.data.vertices), pts, len(fo.data.vertices) == pts))
print('  网格帧数应为 %d' % frames)
