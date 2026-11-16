# -*- coding: utf-8 -*-
"""
把流体层材质改为"水体"外观，并优化几何着色。

要点:
  1. 平滑着色 + 自动平滑, 使表面圆润(不再是硬边带状)
  2. Principled BSDF 水体参数: IOR 1.33, 低粗糙度, 高透射
  3. 程序化波纹法线, 随时间流动(映射节点用 #frame 驱动)
  4. 按深度在"清澈浅水"与"浑浊深水"之间混合
  5. 场景加入渐变天空, 让水面有可反射的内容(否则水体是黑的)

只修改材质与着色, 不动几何与动画。
"""
import bpy
import numpy as np
import os

BLEND = r'F:\DeepSeek工作区\jilong\blender\jilong_scene.blend'
bpy.ops.wm.open_mainfile(filepath=BLEND)
sc = bpy.context.scene
col = bpy.data.collections.get('Flow_frames')

# ================================================================ 1) 几何着色
# 平滑着色 + 自动平滑角度, 让带状网格看起来是连续的水体表面
try:
    bpy.ops.object.select_all(action='DESELECT')
except Exception:
    pass
n = 0
for ob in col.objects:
    me = ob.data
    for p in me.polygons:
        p.use_smooth = True
    # Blender 4.x: 用 modifier 或属性控制自动平滑
    try:
        me.use_auto_smooth = True          # 4.1 之前
        me.auto_smooth_angle = np.radians(40)
    except AttributeError:
        try:
            ob.data.set_sharp_from_angle(angle=np.radians(40))
        except Exception:
            pass
    n += 1
print('已对 %d 个帧对象设置平滑着色' % n)

# ================================================================ 2) 水体材质
mat = bpy.data.materials.get('flow_mat')
if mat is None:
    mat = bpy.data.materials.new('flow_mat')
mat.use_nodes = True
nt = mat.node_tree
nt.nodes.clear()

out = nt.nodes.new('ShaderNodeOutputMaterial'); out.location = (900, 0)
bsdf = nt.nodes.new('ShaderNodeBsdfPrincipled'); bsdf.location = (520, 0)

# --- 厚度属性 ---
attr = nt.nodes.new('ShaderNodeVertexColor'); attr.location = (-900, 200)
attr.layer_name = 'Depth'

# --- 水面波纹: 程序化噪声, 随帧流动 ---
texco = nt.nodes.new('ShaderNodeTexCoord'); texco.location = (-900, -150)
mapping = nt.nodes.new('ShaderNodeMapping'); mapping.location = (-700, -150)
mapping.inputs['Scale'].default_value = (1.0, 1.0, 1.0)

# 用 #frame 驱动偏移, 形成流动感
frame_node = nt.nodes.new('ShaderNodeValue'); frame_node.location = (-900, -400)
try:
    fc = frame_node.outputs[0].driver_add('default_value')
    drv = fc.driver
    drv.type = 'SCRIPTED'
    drv.expression = 'frame / 60.0'
except Exception as e:
    print('  帧驱动添加失败: %s' % e)

# 两个噪声叠加成波纹法线
noise1 = nt.nodes.new('ShaderNodeTexNoise'); noise1.location = (-460, -60)
noise1.inputs['Scale'].default_value = 42.0
noise1.inputs['Detail'].default_value = 6.0
noise1.inputs['Roughness'].default_value = 0.55
noise2 = nt.nodes.new('ShaderNodeTexNoise'); noise2.location = (-460, -330)
noise2.inputs['Scale'].default_value = 128.0
noise2.inputs['Detail'].default_value = 4.0
noise2.inputs['Roughness'].default_value = 0.5

mixn = nt.nodes.new('ShaderNodeMixRGB'); mixn.location = (-220, -180)
mixn.blend_type = 'MIX'; mixn.inputs['Fac'].default_value = 0.42

bump = nt.nodes.new('ShaderNodeBump'); bump.location = (60, -180)
bump.inputs['Strength'].default_value = 0.28
bump.inputs['Distance'].default_value = 0.06

# 波纹随帧移动: 位置 + 时间
combine = nt.nodes.new('ShaderNodeCombineXYZ'); combine.location = (-460, -520)
nt.links.new(frame_node.outputs[0], combine.inputs['X'])
nt.links.new(frame_node.outputs[0], combine.inputs['Y'])
nt.links.new(texco.outputs['Object'], mapping.inputs['Vector'])
nt.links.new(combine.outputs['Vector'], mapping.inputs['Location'])
nt.links.new(mapping.outputs['Vector'], noise1.inputs['Vector'])
nt.links.new(mapping.outputs['Vector'], noise2.inputs['Vector'])
nt.links.new(noise1.outputs['Fac'], mixn.inputs['Color1'])
nt.links.new(noise2.outputs['Fac'], mixn.inputs['Color2'])
nt.links.new(mixn.outputs['Color'], bump.inputs['Height'])
nt.links.new(bump.outputs['Normal'], bsdf.inputs['Normal'])

# --- 水体基础参数 ---
bsdf.inputs['Roughness'].default_value = 0.06
for k in ('IOR',):
    if k in bsdf.inputs:
        bsdf.inputs[k].default_value = 1.333
for k in ('Transmission Weight', 'Transmission'):
    if k in bsdf.inputs:
        bsdf.inputs[k].default_value = 0.85
        break
# 冰水偏青的基色
# 用 厚度 在 浅水(青透) 与 深水(乳白浑浊) 之间混合
ramp = nt.nodes.new('ShaderNodeValToRGB'); ramp.location = (-460, 380)
ramp.color_ramp.elements[0].position = 0.06
ramp.color_ramp.elements[0].color = (0.55, 0.80, 0.92, 1.0)   # 浅: 清透青
ramp.color_ramp.elements[1].position = 0.75
ramp.color_ramp.elements[1].color = (0.86, 0.93, 0.97, 1.0)   # 深: 近乳白
nt.links.new(attr.outputs['Color'], ramp.inputs['Fac'])
nt.links.new(ramp.outputs['Color'], bsdf.inputs['Base Color'])
bsdf.inputs['Alpha'].default_value = 1.0
nt.links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])

mat.blend_method = 'BLEND' if hasattr(mat, 'blend_method') else mat.blend_method
try:
    mat.use_screen_refraction = True
except Exception:
    pass
try:
    mat.use_raytrace_refraction = True
except Exception:
    pass

print('水体材质已建立: IOR 1.333 / 粗糙度 0.06 / 透射 0.85 / 程序化波纹')

# ================================================================ 3) 天空(让水面有反射内容)
w = sc.world
if w and w.use_nodes:
    nt2 = w.node_tree
    nt2.nodes.clear()
    wout = nt2.nodes.new('ShaderNodeOutputWorld'); wout.location = (400, 0)
    bg = nt2.nodes.new('ShaderNodeBackground'); bg.location = (200, 0)
    sky = nt2.nodes.new('ShaderNodeTexSky'); sky.location = (-100, 0)
    try:
        sky.sky_type = 'NISHITA'
        sky.sun_elevation = np.radians(42.0)
        sky.sun_rotation = np.radians(200.0)
        sky.altitude = 4000.0
    except Exception as e:
        print('  天空节点设置失败: %s' % e)
    nt2.links.new(sky.outputs['Color'], bg.inputs['Color'])
    bg.inputs['Strength'].default_value = 0.55
    nt2.links.new(bg.outputs['Background'], wout.inputs['Surface'])
    print('已设置天空背景(Nishita), 供水面反射')

# ================================================================ 4) 渲染设置: 开启折射/反射
sc.render.engine = 'BLENDER_EEVEE_NEXT'
ee = sc.eevee
for attr_name, val in [('use_raytracing', True), ('use_shadows', True),
                       ('use_volumetric_shadows', True)]:
    try:
        setattr(ee, attr_name, val)
    except Exception:
        pass
try:
    ee.ray_tracing_options.use_denoise = True
except Exception:
    pass
sc.render.film_transparent = False

bpy.ops.wm.save_as_mainfile(filepath=BLEND)
print()
print('已保存 %s' % BLEND)
print('WATER_OK')
