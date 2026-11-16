# -*- coding: utf-8 -*-
"""
修正:
  1) 地形改为平滑着色 + 自动平滑角度(保留山脊棱线)
  2) 流体恢复"深度伪彩"着色(蓝->青->黄->红), 但保留水的低粗糙度与波纹
"""
import bpy
import numpy as np

BLEND = r'F:\DeepSeek工作区\jilong\blender\jilong_scene.blend'
bpy.ops.wm.open_mainfile(filepath=BLEND)
sc = bpy.context.scene

# ================================================ 1) 地形平滑
ob_t = bpy.data.objects['Terrain_HR']
me = ob_t.data
n = 0
for p in me.polygons:
    if not p.use_smooth:
        p.use_smooth = True
        n += 1
print('地形: %d 个面改为平滑' % n)

# 自动平滑(Blender 4.x 无 use_auto_smooth 属性, 用 Modifier 或 sharp edge)
angle = np.radians(38.0)
try:
    bpy.context.view_layer.objects.active = ob_t
    bpy.ops.object.select_all(action='DESELECT')
    ob_t.select_set(True)
    bpy.ops.object.shade_smooth_by_angle(angle=angle)
    print('  已应用 shade_smooth_by_angle(%.0f deg)' % np.degrees(angle))
except Exception as e:
    print('  shade_smooth_by_angle 不可用(%s), 改用纯平滑' % e)

# 细分一级, 让轮廓更顺(可控内存: 270k -> ~1.08M 顶点)
try:
    if 'Subdiv' not in [m.name for m in ob_t.modifiers]:
        sub = ob_t.modifiers.new('Subdiv', 'SUBSURF')
        sub.subdivision_type = 'SIMPLE'     # 只细分不改变几何形状
        sub.levels = 1
        sub.render_levels = 1
        print('  已加入 SIMPLE 细分 1 级')
except Exception as e:
    print('  细分失败: %s' % e)

# ================================================ 2) 流体恢复深度伪彩
mat = bpy.data.materials.get('water')
nt = mat.node_tree
nt.nodes.clear()
out = nt.nodes.new('ShaderNodeOutputMaterial'); out.location = (1000, 0)
bs = nt.nodes.new('ShaderNodeBsdfPrincipled'); bs.location = (650, 0)

attr = nt.nodes.new('ShaderNodeVertexColor'); attr.location = (-1000, 250)
attr.layer_name = 'Depth'

# 深度伪彩: 蓝 -> 青 -> 黄 -> 红
ramp = nt.nodes.new('ShaderNodeValToRGB'); ramp.location = (-700, 250)
cr = ramp.color_ramp
cr.interpolation = 'LINEAR'
# 清掉默认两点后重建
while len(cr.elements) > 1:
    cr.elements.remove(cr.elements[-1])
cr.elements[0].position = 0.0
cr.elements[0].color = (0.05, 0.10, 0.65, 1.0)     # 深蓝
for pos, col in [(0.30, (0.05, 0.65, 0.90, 1.0)),   # 青
                 (0.55, (0.35, 0.90, 0.45, 1.0)),   # 绿
                 (0.78, (0.98, 0.85, 0.15, 1.0)),   # 黄
                 (1.00, (0.85, 0.10, 0.05, 1.0))]:  # 红
    e = cr.elements.new(pos)
    e.color = col
nt.links.new(attr.outputs['Color'], ramp.inputs['Fac'])
nt.links.new(ramp.outputs['Color'], bs.inputs['Base Color'])

# 保留水的光学特征: 低粗糙度 + 随时间流动的波纹法线
texco = nt.nodes.new('ShaderNodeTexCoord'); texco.location = (-1000, -200)
mp = nt.nodes.new('ShaderNodeMapping'); mp.location = (-800, -200)
fnode = nt.nodes.new('ShaderNodeValue'); fnode.location = (-1200, -450)
try:
    fc = fnode.outputs[0].driver_add('default_value')
    fc.driver.type = 'SCRIPTED'; fc.driver.expression = 'frame / 40.0'
except Exception:
    pass
cmb = nt.nodes.new('ShaderNodeCombineXYZ'); cmb.location = (-1000, -450)
nt.links.new(fnode.outputs[0], cmb.inputs['X'])
nt.links.new(fnode.outputs[0], cmb.inputs['Y'])
nt.links.new(texco.outputs['Object'], mp.inputs['Vector'])
nt.links.new(cmb.outputs['Vector'], mp.inputs['Location'])
n1 = nt.nodes.new('ShaderNodeTexNoise'); n1.location = (-560, -120)
n1.inputs['Scale'].default_value = 12.0; n1.inputs['Detail'].default_value = 8.0
n2 = nt.nodes.new('ShaderNodeTexNoise'); n2.location = (-560, -400)
n2.inputs['Scale'].default_value = 40.0; n2.inputs['Detail'].default_value = 5.0
nt.links.new(mp.outputs['Vector'], n1.inputs['Vector'])
nt.links.new(mp.outputs['Vector'], n2.inputs['Vector'])
mx = nt.nodes.new('ShaderNodeMixRGB'); mx.location = (-300, -260)
mx.inputs['Fac'].default_value = 0.35
nt.links.new(n1.outputs['Fac'], mx.inputs['Color1'])
nt.links.new(n2.outputs['Fac'], mx.inputs['Color2'])
bp = nt.nodes.new('ShaderNodeBump'); bp.location = (200, -260)
bp.inputs['Strength'].default_value = 0.35; bp.inputs['Distance'].default_value = 0.3
nt.links.new(mx.outputs['Color'], bp.inputs['Height'])
nt.links.new(bp.outputs['Normal'], bs.inputs['Normal'])

bs.inputs['Roughness'].default_value = 0.22
if 'IOR' in bs.inputs:
    bs.inputs['IOR'].default_value = 1.333
for k in ('Transmission Weight', 'Transmission'):
    if k in bs.inputs:
        bs.inputs[k].default_value = 0.10
        break
nt.links.new(bs.outputs['BSDF'], out.inputs['Surface'])
print('流体: 已恢复深度伪彩(蓝-青-绿-黄-红), 保留波纹与低粗糙度')

bpy.ops.wm.save_as_mainfile(filepath=BLEND)
print('SMOOTH_OK')
