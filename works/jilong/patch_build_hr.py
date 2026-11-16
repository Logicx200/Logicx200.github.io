# -*- coding: utf-8 -*-
"""修正 build_hr.py：配色归一化改用 99% 分位；站点标记改用绝对 UTM 坐标。"""
import re

P = r'F:\DeepSeek工作区\jilong\build_hr.py'
s = open(P, encoding='utf-8').read()

# 1) 配色归一化改用 99% 分位
old1 = "hn = np.clip(h.ravel()[pidx] / HMAX, 0, 1)"
new1 = "hn = np.clip(h.ravel()[pidx] / HP99, 0, 1)   # 用 99% 分位, 避免大部分区域挤在蓝色"
assert old1 in s, '未找到配色归一化行'
s = s.replace(old1, new1)

old2 = "HMAX = max(H.max(), 1e-9)"
new2 = ("HMAX = max(H.max(), 1e-9)\n"
        "HP99 = float(d['h_p99']) if 'h_p99' in d.files else HMAX")
assert old2 in s, '未找到 HMAX 行'
s = s.replace(old2, new2)

# 2) 站点标记改用绝对 UTM
i0 = s.index("def marker(name, c_, r_, col_):")
i1 = s.index("# ============================================ 相机")
new_block = '''def marker(name, utm, col_):
    """utm = (E, N) 绝对坐标"""
    gxx, gyy = float(utm[0]), float(utm[1])
    xi = int(np.clip(round((gxx - E0) / TR), 0, hNX - 1))
    yi = int(np.clip(round((N1 - gyy) / TR), 0, hNY - 1))
    bpy.ops.mesh.primitive_uv_sphere_add(radius=300.0,
        location=(gxx - cx, -(gyy - cy), (ZT[yi, xi] - z0) * EXAG + 220))
    ob = bpy.context.active_object; ob.name = name
    m = bpy.data.materials.new(name + '_m'); m.use_nodes = True
    nn = m.node_tree.nodes.get('Principled BSDF')
    if nn:
        nn.inputs['Base Color'].default_value = col_
        nn.inputs['Roughness'].default_value = 0.45
    ob.data.materials.append(m)

marker('SRC_source', d['src_utm'], (0.20, 0.55, 1.0, 1))
marker('LAKE_barrier_lake', d['lake_utm'], (1.0, 0.15, 0.85, 1))
marker('PORT_Jilong_port', d['port_utm'], (0.15, 0.90, 0.95, 1))
print('站点标记: 源区(%.0f,%.0f) 堰塞湖(%.0f,%.0f) 口岸(%.0f,%.0f)'
      % (d['src_utm'][0], d['src_utm'][1], d['lake_utm'][0], d['lake_utm'][1],
         d['port_utm'][0], d['port_utm'][1]))

'''
s = s[:i0] + new_block + s[i1:]
open(P, 'w', encoding='utf-8').write(s)
print('build_hr.py 已更新')
for ln in s.split('\n'):
    if 'HP99' in ln or 'src_utm' in ln:
        print('  ' + ln.strip())
