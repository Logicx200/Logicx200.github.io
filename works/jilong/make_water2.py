# -*- coding: utf-8 -*-
"""
流体层材质 v2：让它真正"像水"且看得见。

经验: 在 16 km 尺度、流体仅数十米厚的情况下, 高透射的纯水体会接近隐形。
因此采用"写实水的视觉特征 + 足够的存在感":
  - 明确的青蓝色基色 (浅滩更亮, 深槽更暗)
  - 低粗糙度 -> 明显的高光与天空反射
  - 适度透射 (0.35) 而非全透 -> 保留体积感
  - 程序化波纹法线, 随帧流动, 尺度调大以在远景可见
  - 边缘增亮(菲涅尔)勾勒出流线
"""
import bpy
import numpy as np

BLEND = r'F:\DeepSeek工作区\jilong\blender\jilong_scene.blend'
bpy.ops.wm.open_mainfile(filepath=BLEND)
sc = bpy.context.scene
col = bpy.data.collections.get('Flow_frames')

mat = bpy.data.materials.get('flow_mat')
mat.use_nodes = True
nt = mat.node_tree
nt.nodes.clear()

out = nt.nodes.new('ShaderNodeOutputMaterial'); out.location = (1100, 0)
bsdf = nt.nodes.new('ShaderNodeBsdfPrincipled'); bsdf.location = (700, 0)

# ---- 厚度属性 ----
attr = nt.nodes.new('ShaderNodeVertexColor'); attr.location = (-1100, 300)
attr.layer_name = 'Depth'

# 厚度 -> 颜色 (浅: 亮青  ->  深: 深青蓝)
ramp = nt.nodes.new('ShaderNodeValToRGB'); ramp.location = (-800, 300)
ramp.color_ramp.elements[0].position = 0.03
ramp.color_ramp.elements[0].color = (0.62, 0.88, 0.97, 1.0)
ramp.color_ramp.elements[1].position = 0.85
ramp.color_ramp.elements[1].color = (0.05, 0.32, 0.62, 1.0)
nt.links.new(attr.outputs['Color'], ramp.inputs['Fac'])
nt.links.new(ramp.outputs['Color'], bsdf.inputs['Base Color'])

# ---- 波纹法线 (物件空间, 随帧流动) ----
texco = nt.nodes.new('ShaderNodeTexCoord'); texco.location = (-1100, -200)
mapping = nt.nodes.new('ShaderNodeMapping'); mapping.location = (-900, -200)
mapping.inputs['Scale'].default_value = (1.0, 1.0, 1.0)

fnode = nt.nodes.new('ShaderNodeValue'); fnode.location = (-1300, -450)
try:
    fc = fnode.outputs[0].driver_add('default_value')
    fc.driver.type = 'SCRIPTED'
    fc.driver.expression = 'frame / 45.0'
except Exception as e:
    print('  帧驱动失败: %s' % e)

comb = nt.nodes.new('ShaderNodeCombineXYZ'); comb.location = (-1100, -450)
nt.links.new(fnode.outputs[0], comb.inputs['X'])
nt.links.new(fnode.outputs[0], comb.inputs['Y'])
nt.links.new(texco.outputs['Object'], mapping.inputs['Vector'])
nt.links.new(comb.outputs['Vector'], mapping.inputs['Location'])

n1 = nt.nodes.new('ShaderNodeTexNoise'); n1.location = (-650, -120)
n1.inputs['Scale'].default_value = 9.0
n1.inputs['Detail'].default_value = 8.0
n1.inputs['Roughness'].default_value = 0.6
n2 = nt.nodes.new('ShaderNodeTexNoise'); n2.location = (-650, -400)
n2.inputs['Scale'].default_value = 34.0
n2.inputs['Detail'].default_value = 5.0
nt.links.new(mapping.outputs['Vector'], n1.inputs['Vector'])
nt.links.new(mapping.outputs['Vector'], n2.inputs['Vector'])

mixn = nt.nodes.new('ShaderNodeMixRGB'); mixn.location = (-380, -260)
mixn.blend_type = 'MIX'; mixn.inputs['Fac'].default_value = 0.35
nt.links.new(n1.outputs['Fac'], mixn.inputs['Color1'])
nt.links.new(n2.outputs['Fac'], mixn.inputs['Color2'])

bump = nt.nodes.new('ShaderNodeBump'); bump.location = (200, -260)
bump.inputs['Strength'].default_value = 0.45
bump.inputs['Distance'].default_value = 0.35
nt.links.new(mixn.outputs['Color'], bump.inputs['Height'])
nt.links.new(bump.outputs['Normal'], bsdf.inputs['Normal'])

# ---- 水的光学参数 ----
bsdf.inputs['Roughness'].default_value = 0.05
if 'IOR' in bsdf.inputs:
    bsdf.inputs['IOR'].default_value = 1.333
for k in ('Transmission Weight', 'Transmission'):
    if k in bsdf.inputs:
        bsdf.inputs[k].default_value = 0.35
        break
if 'Specular IOR Level' in bsdf.inputs:
    bsdf.inputs['Specular IOR Level'].default_value = 0.6
nt.links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])

try:
    mat.use_screen_refraction = True
except Exception:
    pass
print('水体材质 v2 完成')

# 渲染: 开启光追以得到反射/折射
sc.render.engine = 'BLENDER_EEVEE_NEXT'
try:
    sc.eevee.use_raytracing = True
except Exception:
    pass

bpy.ops.wm.save_as_mainfile(filepath=BLEND)
print('已保存 WATER2_OK')
