# -*- coding: utf-8 -*-
"""
彩色版 v2: 真实卫星影像地形 + 彩色流体 + 白色无影墙 + 立方体厚度 + 倒三角立体文字标记

相对 v1 的修正:
  1) 方向修正: 原来 y = -(N-cy) (Y 轴指南), 雅可比 < 0, 整个模型是真实地形的南北镜像。
     现在改为 x = E-cx, y = N-cy (+X 东, +Y 北), 并把 ZT/H 的行序翻转为"行0=南"。
  2) 地形由面片改为实体块: 顶面 + 四周侧壁 + 底面, 像从立方体上雕出来的。
  3) 背景: 白色无影墙(自发光、不投影、不参与照明) + 世界相机光线纯白兜底, 不再是灰色。
  4) 标记: 球体换成倒三角(三棱锥, 尖端朝下) + 立体中文文字。

用法: blender -b --factory-startup --python sat_anim.py -- <outdir> <width> [fps] [sub]
环境: SSTILL=帧号(可逗号分隔) 只出静帧; STOPDOWN=1 出正射俯视图(用于校验镜像)
"""
import bpy
import math
import os
import sys
import numpy as np
from mathutils import Vector, Matrix

B = r'F:\DeepSeek工作区\jilong'
BLD = os.path.join(B, 'blender')
NPZ = os.path.join(BLD, 'flow_hr.npz')
BLEND = os.path.join(BLD, 'jilong_scene.blend')
SAT = os.environ.get('STEX', os.path.join(B, 'sat_utm.jpg'))
FONT_CJK = r'C:\Windows\Fonts\simhei.ttf'

argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
OUTDIR = argv[0] if argv else os.path.join(B, 'results')
W = int(argv[1]) if len(argv) > 1 else 1920
FPS = int(argv[2]) if len(argv) > 2 else 24
SUB = int(argv[3]) if len(argv) > 3 else 2

EXAG = 1.0            # 地形垂向比例: 1.0 = 真实高程
FEXAG = 3.0           # 流体厚度放大
LIFT = 90.0           # 流体整体抬升(m)
BLOCK_BASE = -1500.0  # 块体底面相对最低地形的高度(m), 给地形一块"雕出来的"底座
AZ, EL, LENS = 284.0, 38.0, 40.0
AZ = float(os.environ.get('WAZ', AZ))
EL = float(os.environ.get('WEL', EL))
WET = 0.05
FIT = 0.93

CMAP = [(0.00, (0.70, 0.93, 1.00)),
        (0.25, (0.05, 0.80, 1.00)),
        (0.60, (0.02, 0.45, 0.98)),
        (1.00, (0.35, 0.10, 0.88))]
LOGT = (math.log10(0.5), math.log10(100.0))
C_BLOCK = (0.60, 0.59, 0.57, 1.0)     # 块体侧壁/底面 (暖灰, 与纯白背景区分开)
C_MARK = (0.88, 0.10, 0.10, 1.0)      # 倒三角
C_TEXT = (0.07, 0.07, 0.09, 1.0)      # 文字


def cmap(t):
    t = np.clip(t, 0.0, 1.0)
    out = np.zeros(t.shape + (3,))
    for i in range(len(CMAP) - 1):
        t0, c0 = CMAP[i]
        t1, c1 = CMAP[i + 1]
        m = (t >= t0) & (t <= t1)
        if m.any():
            f = ((t[m] - t0) / (t1 - t0))[:, None]
            out[m] = np.array(c0)[None, :] * (1 - f) + np.array(c1)[None, :] * f
    out[t <= CMAP[0][0]] = CMAP[0][1]
    out[t >= CMAP[-1][0]] = CMAP[-1][1]
    return out


def solid_mat(name, rgba, rough=0.55, emis=0.0):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree; nt.nodes.clear()
    o = nt.nodes.new('ShaderNodeOutputMaterial'); o.location = (400, 0)
    b = nt.nodes.new('ShaderNodeBsdfPrincipled'); b.location = (100, 0)
    b.inputs['Base Color'].default_value = rgba
    b.inputs['Roughness'].default_value = rough
    if emis > 0 and 'Emission Color' in b.inputs:
        b.inputs['Emission Color'].default_value = rgba
        b.inputs['Emission Strength'].default_value = emis
    nt.links.new(b.outputs['BSDF'], o.inputs['Surface'])
    m.diffuse_color = rgba
    return m


os.makedirs(OUTDIR, exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=BLEND)
sc = bpy.context.scene

d = np.load(NPZ)
# ---- 行序翻转: 行0 由"北"改为"南", 使 y = N - cy 指向北 ----
ZT = d['terrain_Z'].astype(np.float64)[::-1, :].copy()
H = d['H'].astype(np.float64)[:, ::-1, :].copy()
TR = float(d['TR']); hNY, hNX = int(d['hNY']), int(d['hNX'])
nf = H.shape[0]; times = d['times']
E0, N1 = float(d['E0']), float(d['N1'])
E1 = E0 + (hNX - 1) * TR
N0 = N1 - (hNY - 1) * TR
z0 = float(ZT.min())
cx = E0 + (hNX - 1) * TR / 2.0
cy = N0 + (hNY - 1) * TR / 2.0
print('域 E %.0f..%.0f  N %.0f..%.0f  网格 %dx%d  %d 帧' % (E0, E1, N0, N1, hNX, hNY, nf))
print('H 统计: max %.1f  p99 %.1f  p50 %.2f' %
      (H.max(), np.percentile(H[H > WET], 99), np.percentile(H[H > WET], 50)))

gx = E0 + np.arange(hNX) * TR          # 西 -> 东
gy = N0 + np.arange(hNY) * TR          # 南 -> 北
Xg, Yg = np.meshgrid(gx - cx, gy - cy, indexing='ij')   # (hNX,hNY)
Xf = np.ascontiguousarray(Xg.T).ravel()
Yf = np.ascontiguousarray(Yg.T).ravel()
Zg = (ZT - z0) * EXAG                   # (hNY,hNX) >= 0
GZf = Zg.ravel()
Uf = (gx - E0) / (E1 - E0)
Vf = (gy - N0) / (N1 - N0)
Ug, Vg = np.meshgrid(Uf, Vf, indexing='ij')
UVf = np.column_stack([np.ascontiguousarray(Ug.T).ravel(),
                       np.ascontiguousarray(Vg.T).ravel()])

# ---------------- 地形实体块: 顶面 + 侧壁 + 底面 ----------------
for nm in ('Terrain_HR', 'Terrain_Block'):
    o = bpy.data.objects.get(nm)
    if o:
        m = o.data; bpy.data.objects.remove(o, do_unlink=True)
        if m.users == 0:
            bpy.data.meshes.remove(m)

top = np.column_stack([Xf, Yf, GZf])
ii, jj = np.meshgrid(np.arange(hNY - 1), np.arange(hNX - 1), indexing='ij')
v00 = (ii * hNX + jj).ravel()
topf = np.column_stack([v00, v00 + 1, v00 + hNX + 1, v00 + hNX])
n_top = len(top)

# 周长环 (自上而下看为逆时针): 南 -> 东 -> 北 -> 西
peri = [(0, j) for j in range(hNX)]
peri += [(i, hNX - 1) for i in range(1, hNY)]
peri += [(hNY - 1, j) for j in range(hNX - 2, -1, -1)]
peri += [(i, 0) for i in range(hNY - 2, 0, -1)]
peri_idx = np.array([i * hNX + j for i, j in peri], np.int64)
zb = Zg.min() + BLOCK_BASE
base = np.column_stack([Xf[peri_idx], Yf[peri_idx], np.full(len(peri_idx), zb)])
allv = np.vstack([top, base])
nb = n_top + np.arange(len(peri_idx))

wallf = []
for k in range(len(peri_idx)):
    k2 = (k + 1) % len(peri_idx)
    wallf.append([int(peri_idx[k]), int(nb[k]), int(nb[k2]), int(peri_idx[k2])])
botf = [nb[::-1].tolist()]

F = topf.tolist() + wallf + botf
tme = bpy.data.meshes.new('Terrain_HR')
tme.from_pydata(allv.tolist(), [], F)
tme.update(); tme.validate(verbose=False)
uvl = tme.uv_layers.new(name='UVMap')
for k, lp in enumerate(tme.loops):
    vi = lp.vertex_index
    uvl.data[k].uv = UVf[vi] if vi < n_top else (0.0, 0.0)
for p in tme.polygons:
    p.use_smooth = True
# 侧壁/底面不平滑, 保持棱角
for p in tme.polygons[n_top:]:
    p.use_smooth = False

sat_img = bpy.data.images.load(SAT, check_existing=True)
sat_img.colorspace_settings.name = 'sRGB'
mt = bpy.data.materials.get('sat_terrain') or bpy.data.materials.new('sat_terrain')
mt.use_nodes = True
nt = mt.node_tree; nt.nodes.clear()
out = nt.nodes.new('ShaderNodeOutputMaterial'); out.location = (400, 0)
bsdf = nt.nodes.new('ShaderNodeBsdfPrincipled'); bsdf.location = (100, 0)
tex = nt.nodes.new('ShaderNodeTexImage'); tex.location = (-260, 0)
tex.image = sat_img; tex.interpolation = 'Linear'
nt.links.new(tex.outputs['Color'], bsdf.inputs['Base Color'])
bsdf.inputs['Roughness'].default_value = 0.92
if 'Specular IOR Level' in bsdf.inputs:
    bsdf.inputs['Specular IOR Level'].default_value = 0.15
if 'Emission Color' in bsdf.inputs:
    nt.links.new(tex.outputs['Color'], bsdf.inputs['Emission Color'])
    bsdf.inputs['Emission Strength'].default_value = 0.45
nt.links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])
mb = solid_mat('block_side', C_BLOCK, 0.75)
tme.materials.append(mt)
tme.materials.append(mb)
for p in tme.polygons[n_top:]:
    p.material_index = 1
terr = bpy.data.objects.new('Terrain_HR', tme)
_tc = bpy.data.collections.get('Terrain')
(_tc or sc.collection).objects.link(terr)
print('块体顶点 %d 面 %d (顶面 %d + 侧壁 %d + 底面 1)' %
      (len(tme.vertices), len(tme.polygons), len(topf), len(wallf)))

# ---------------- 流体材质 ----------------
mf = bpy.data.materials.get('flow_depth') or bpy.data.materials.new('flow_depth')
mf.use_nodes = True
nf_ = mf.node_tree; nf_.nodes.clear()
o2 = nf_.nodes.new('ShaderNodeOutputMaterial'); o2.location = (400, 0)
b2 = nf_.nodes.new('ShaderNodeBsdfPrincipled'); b2.location = (100, 0)
vc = nf_.nodes.new('ShaderNodeVertexColor'); vc.location = (-260, 0)
vc.layer_name = 'Col'
nf_.links.new(vc.outputs['Color'], b2.inputs['Base Color'])
b2.inputs['Roughness'].default_value = 0.30
if 'Emission Color' in b2.inputs:
    nf_.links.new(vc.outputs['Color'], b2.inputs['Emission Color'])
    b2.inputs['Emission Strength'].default_value = 0.22
nf_.links.new(b2.outputs['BSDF'], o2.inputs['Surface'])

# ---------------- 流体帧 ----------------
col = bpy.data.collections.get('Flow_frames')
for o in list(col.objects):
    me = o.data; col.objects.unlink(o); bpy.data.objects.remove(o, do_unlink=True)
    if me.users == 0:
        bpy.data.meshes.remove(me)

sub_idx = []; frame_times = []
for i in range(nf - 1):
    for k in range(SUB):
        sub_idx.append((i, k / float(SUB)))
        frame_times.append(times[i] + (k / float(SUB)) * (times[i + 1] - times[i]))
sub_idx.append((nf - 1, 0.0)); frame_times.append(times[nf - 1])
NS = len(sub_idx)
print('插值后 %d 帧 (原 %d 帧 x%d)' % (NS, nf, SUB))

meshes = []
fz_max = -1e18
for si, (i0, frac) in enumerate(sub_idx):
    h = H[i0] if frac == 0.0 else (H[i0] * (1 - frac) + H[i0 + 1] * frac)
    wet = h > WET
    me = bpy.data.meshes.new('flow_%04d' % si)
    cols = None
    if wet.any():
        cell = wet[:-1, :-1] & wet[1:, :-1] & wet[:-1, 1:] & wet[1:, 1:]
        ri, ci = np.where(cell)
        if ri.size:
            need = np.zeros((hNY, hNX), bool)
            need[ri, ci] = True; need[ri, ci + 1] = True
            need[ri + 1, ci] = True; need[ri + 1, ci + 1] = True
            pidx = np.flatnonzero(need.ravel())
            remap = -np.ones(hNY * hNX, np.int64); remap[pidx] = np.arange(pidx.size)
            hv = h.ravel()[pidx]
            zz = GZf[pidx] + hv * FEXAG + LIFT
            fz_max = max(fz_max, float(zz.max()))
            P = np.column_stack([Xf[pidx], Yf[pidx], zz])
            Fq = np.column_stack([remap[ri * hNX + ci], remap[ri * hNX + ci + 1],
                                  remap[(ri + 1) * hNX + ci + 1], remap[(ri + 1) * hNX + ci]])
            me.from_pydata(P.tolist(), [], Fq.tolist())
            me.update(); me.validate(verbose=False)
            for p in me.polygons:
                p.use_smooth = True
            t = np.clip((np.log10(np.maximum(hv, 1e-3)) - LOGT[0]) / (LOGT[1] - LOGT[0]), 0, 1)
            cols = cmap(t)
    if cols is None:
        cols = np.zeros((len(me.vertices), 3))
    ca = me.color_attributes.new(name='Col', type='FLOAT_COLOR', domain='POINT')
    for k in range(len(me.vertices)):
        ca.data[k].color = (cols[k, 0], cols[k, 1], cols[k, 2], 1.0)
    me.materials.append(mf)
    meshes.append(me)
    if si % 60 == 0:
        print('   建网格 %d/%d' % (si, NS - 1))
print('流体最大高程 %.0f m' % fz_max)

# ---------------- 逐帧对象 + 可见性关键帧 ----------------
# .blend 里存不了 Python handler, 所以改成 241 个对象各自只在自己那一帧可见。
# 完全自包含: 打开文件拖时间轴就能看动画, 直接渲染也对。
_pref_old = bpy.context.preferences.edit.keyframe_new_interpolation_type
bpy.context.preferences.edit.keyframe_new_interpolation_type = 'CONSTANT'


def key_vis(ob, f, last):
    if f > 1:
        ob.hide_viewport = True; ob.hide_render = True
        ob.keyframe_insert('hide_viewport', frame=1)
        ob.keyframe_insert('hide_render', frame=1)
    ob.hide_viewport = False; ob.hide_render = False
    ob.keyframe_insert('hide_viewport', frame=f)
    ob.keyframe_insert('hide_render', frame=f)
    if f < last:
        ob.hide_viewport = True; ob.hide_render = True
        ob.keyframe_insert('hide_viewport', frame=f + 1)
        ob.keyframe_insert('hide_render', frame=f + 1)


flow_objs = []
for si, me in enumerate(meshes):
    o = bpy.data.objects.new('Flow_%04d' % (si + 1), me)
    col.objects.link(o)
    o.visible_shadow = False
    key_vis(o, si + 1, NS)
    flow_objs.append(o)
print('流体逐帧对象 %d 个 (可见性已打 CONSTANT 关键帧)' % len(flow_objs))

# ---------------- 标记: 倒三角 + 立体文字 ----------------
for o in list(sc.objects):
    if o.name in ('SRC_source', 'LAKE_barrier_lake', 'PORT_Jilong_port') or o.name.startswith('MK_'):
        m = o.data if o.type in ('MESH', 'FONT') else None
        bpy.data.objects.remove(o, do_unlink=True)
        if m is not None and m.users == 0:
            try: bpy.data.meshes.remove(m)
            except Exception: pass

try:
    cjk = bpy.data.fonts.load(FONT_CJK)
except Exception as e:
    print('中文字体加载失败 %s' % e)
    cjk = None

MARKERS = [('源头', d['src_utm']), ('堰塞湖', d['lake_utm']), ('吉隆口岸', d['port_utm'])]
print('标记 UTM: ' + ' | '.join('%s %.0f %.0f' % (n, p[0], p[1]) for n, p in MARKERS))

TRI_R = 360.0     # 倒三角底半径
TRI_H = 800.0     # 倒三角高
HOVER = 300.0     # 三角尖端离地高度
TXT_SZ = 850.0    # 文字大小
mark_top = []
SHOW_MARKERS = os.environ.get('SMARK', '0').strip() == '1'   # 默认关闭地点标记

for nm, (E, N) in (MARKERS if SHOW_MARKERS else []):
    j = int(round((E - E0) / TR)); i = int(round((N - N0) / TR))
    j = max(0, min(hNX - 1, j)); i = max(0, min(hNY - 1, i))
    zt = Zg[i, j]
    px, py = E - cx, N - cy
    ztip = zt + HOVER
    # 倒三角: radius1=0(下, 尖), radius2=TRI_R(上)
    bpy.ops.mesh.primitive_cone_add(vertices=3, radius1=0.0, radius2=TRI_R,
                                    depth=TRI_H, location=(px, py, ztip + TRI_H / 2),
                                    rotation=(0, 0, math.radians(90)))
    tri = bpy.context.active_object
    tri.name = 'MK_tri_' + nm
    tri.data.materials.clear(); tri.data.materials.append(solid_mat('mark_red', C_MARK, 0.42, 0.25))
    tri.visible_shadow = False
    for p in tri.data.polygons:
        p.use_smooth = False
    # 立体文字
    td = bpy.data.curves.new('MK_txt_' + nm, type='FONT')
    td.body = nm
    td.size = TXT_SZ
    td.extrude = TXT_SZ * 0.05
    td.align_x = 'CENTER'; td.align_y = 'BOTTOM'
    if cjk is not None:
        td.font = cjk
    tx = bpy.data.objects.new('MK_txt_' + nm, td)
    sc.collection.objects.link(tx)
    tx.location = (px, py, ztip + TRI_H + 130.0)
    tx.data.materials.append(solid_mat('mark_text', C_TEXT, 0.5, 0.12))
    # 白色底板: 深色字压在深色地形上读不出来, 加个牌子
    nch = len(nm)
    tw = nch * TXT_SZ * 1.03
    th = TXT_SZ * 1.20
    pad = TXT_SZ * 0.22
    bpy.ops.mesh.primitive_plane_add(size=1.0)
    plate = bpy.context.active_object
    plate.name = 'MK_plate_' + nm
    plate.parent = tx
    plate.location = (0.0, th * 0.5 - TXT_SZ * 0.10, -TXT_SZ * 0.30)
    plate.rotation_euler = (0.0, 0.0, 0.0)
    plate.scale = (tw + 2 * pad, th + 2 * pad, 1.0)
    pm = solid_mat('mark_plate', (1.0, 1.0, 1.0, 1.0), 0.9, 0.85)
    plate.data.materials.append(pm)
    plate.visible_shadow = False
    for a in ('visible_diffuse', 'visible_glossy'):
        try:
            setattr(plate, a, False)
        except Exception:
            pass
    mark_top.append(Vector((px, py, ztip + TRI_H + 130.0 + TXT_SZ * 1.30)))

# 时间戳: 同样做成逐帧对象 (字符串没法打关键帧, 只能一帧一个)
for o in list(sc.objects):
    if o.name == 'TimeTxt' or o.name.startswith('T_'):
        c = o.data if o.type == 'FONT' else None
        bpy.data.objects.remove(o, do_unlink=True)
        if c is not None and c.users == 0:
            bpy.data.curves.remove(c)
_tcol = bpy.data.collections.get('TimeLabels')
if _tcol is None:
    _tcol = bpy.data.collections.new('TimeLabels')
    sc.collection.children.link(_tcol)

txm = solid_mat('txt_mat', (0.08, 0.08, 0.10, 1.0), 0.5, 0.15)  # 深色: 背景已改纯白, 白字会隐形
time_objs = []
for si in range(NS):
    tdc = bpy.data.curves.new('T_%04d' % (si + 1), type='FONT')
    tdc.body = 'T+%d s' % int(round(frame_times[si]))
    tdc.size = 62.0
    tdc.align_x = 'LEFT'; tdc.align_y = 'BOTTOM'
    tdc.materials.append(txm)
    o = bpy.data.objects.new('T_%04d' % (si + 1), tdc)
    _tcol.objects.link(o)
    key_vis(o, si + 1, NS)
    time_objs.append(o)
print('时间戳逐帧对象 %d 个' % len(time_objs))

# ---------------- 相机 ----------------
lo = np.array([Xf.min(), Yf.min(), Zg.min()])
hi = np.array([Xf.max(), Yf.max(), Zg.max()])
hi[2] = max(hi[2], fz_max)
center = (lo + hi) / 2.0
print('包围盒 %.0f x %.0f x %.0f' % tuple(hi - lo))

cam = sc.camera
cam.data.lens = LENS; cam.data.clip_start = 100.0; cam.data.clip_end = 1e7
sc.render.resolution_x = W
sc.render.resolution_y = int(round(W * 9 / 16))
sensor = cam.data.sensor_width
fov_h = 2 * math.atan(sensor / (2 * LENS))
fov_v = 2 * math.atan((sensor * sc.render.resolution_y / sc.render.resolution_x) / (2 * LENS))
tg = bpy.data.objects.get('TrackTarget')
for c in list(cam.constraints):
    cam.constraints.remove(c)
con = cam.constraints.new(type='TRACK_TO'); con.target = tg
con.track_axis = 'TRACK_NEGATIVE_Z'; con.up_axis = 'UP_Y'
az_r, el_r = math.radians(AZ), math.radians(EL)
vdir = Vector((math.cos(el_r) * math.sin(az_r), math.cos(el_r) * math.cos(az_r), math.sin(el_r)))
# 相机的世界右/上轴, 用于把内容平移到画面正中
right = Vector((-math.cos(az_r), math.sin(az_r), 0.0)).normalized()
up = vdir.cross(right).normalized()
pts = top[::8]
th = math.tan(fov_h / 2)
tv_ = math.tan(fov_v / 2)
tgt = Vector(center)


def _proj(dist):
    tg.location = tuple(tgt)
    cam.location = tgt + vdir * dist
    bpy.context.view_layer.update()
    dg2 = bpy.context.evaluated_depsgraph_get()
    M = np.array(cam.evaluated_get(dg2).matrix_world.inverted())
    Q = pts @ M[:3, :3].T + M[:3, 3]
    return Q, -Q[:, 2]


def fits(dist):
    Q, z = _proj(dist)
    if (z <= 1.0).any():
        return False
    return (np.abs(Q[:, 0]) / z <= th * FIT).all() and (np.abs(Q[:, 1]) / z <= tv_ * FIT).all()


def fit_dist(d0):
    d_hi = d0
    for _ in range(40):
        if fits(d_hi):
            break
        d_hi *= 1.3
    d_lo = d_hi * 0.3
    for _ in range(45):
        d_mid = 0.5 * (d_lo + d_hi)
        if fits(d_mid):
            d_hi = d_mid
        else:
            d_lo = d_mid
    return d_hi


dist = fit_dist(float(np.linalg.norm(hi - lo)) * 2.5)
# 迭代: 把投影包围盒的中心推到画面正中 (整体平移相机rig + 重拟合距离)
ox = oy = 0.0
for _ in range(12):
    Q, z = _proj(dist)
    nx = Q[:, 0] / z / th
    ny = Q[:, 1] / z / tv_
    ox = 0.5 * (float(nx.min()) + float(nx.max()))
    oy = 0.5 * (float(ny.min()) + float(ny.max()))
    if abs(ox) < 2e-4 and abs(oy) < 2e-4:
        break
    tgt = tgt + right * (ox * th * dist) + up * (oy * tv_ * dist)
    dist = fit_dist(dist * 1.15)
Q, z = _proj(dist)
nx = Q[:, 0] / z / th
ny = Q[:, 1] / z / tv_
print('相机距离 %.0f m  居中残差(ndc) %.5f, %.5f  占用 宽%.2f 高%.2f'
      % (dist, 0.5 * (float(nx.min()) + float(nx.max())),
         0.5 * (float(ny.min()) + float(ny.max())),
         float(nx.max() - nx.min()), float(ny.max() - ny.min())))

# 文字朝向镜头
for o in sc.objects:
    if o.name.startswith('MK_txt_'):
        dd = (cam.location - o.location).normalized()
        o.rotation_euler = dd.to_track_quat('Z', 'Y').to_euler()

for o in time_objs:
    o.parent = cam
    o.matrix_parent_inverse = Matrix.Identity(4)
    o.location = (-800.0, -432.0, -2000.0)
    o.rotation_euler = (0.0, 0.0, 0.0)
bpy.context.preferences.edit.keyframe_new_interpolation_type = _pref_old

# ---------------- 白色无影墙 ----------------
for o in list(sc.objects):
    if o.name.startswith('Backdrop'):
        bpy.data.objects.remove(o, do_unlink=True)
diag = float(np.linalg.norm(hi - lo))
wall_d = diag * 2.2
wall_s = diag * 7.0
bpy.ops.mesh.primitive_plane_add(size=wall_s, location=tuple(center - np.array(vdir[:]) * wall_d))
wall = bpy.context.active_object
wall.name = 'Backdrop'
wd = (center - np.array(vdir[:]) * wall_d) - np.array(cam.location[:])
wall.rotation_euler = Vector(wd).normalized().to_track_quat('Z', 'Y').to_euler()
wm = bpy.data.materials.new('wall_white')
wm.use_nodes = True
wn2 = wm.node_tree; wn2.nodes.clear()
wo = wn2.nodes.new('ShaderNodeOutputMaterial'); wo.location = (300, 0)
we = wn2.nodes.new('ShaderNodeEmission'); we.location = (0, 0)
we.inputs['Color'].default_value = (1, 1, 1, 1)
we.inputs['Strength'].default_value = 1.0
wn2.links.new(we.outputs['Emission'], wo.inputs['Surface'])
wall.data.materials.append(wm)
wall.visible_shadow = False
for a in ('visible_diffuse', 'visible_glossy', 'visible_transmission'):
    try:
        setattr(wall, a, False)
    except Exception:
        pass
print('无影墙: 尺寸 %.0f m, 距相机 %.0f m' % (wall_s, wall_d + diag))

# ---------------- 光照 ----------------
for nm in ('Sun_key', 'Area_fill', 'Sun'):
    o = bpy.data.objects.get(nm)
    if o:
        bpy.data.objects.remove(o, do_unlink=True)
sd = bpy.data.lights.new('Sun', type='SUN')
sd.energy = 2.2
sd.angle = math.radians(2.0)
sun = bpy.data.objects.new('Sun', sd)
sc.collection.objects.link(sun)
sun.rotation_euler = (math.radians(52), 0.0, math.radians(215))

w = bpy.data.worlds.get('World') or bpy.data.worlds.new('World')
sc.world = w
w.use_nodes = True
wn = w.node_tree; wn.nodes.clear()
wout = wn.nodes.new('ShaderNodeOutputWorld'); wout.location = (400, 0)
mix = wn.nodes.new('ShaderNodeMixShader'); mix.location = (200, 0)
bg_cam = wn.nodes.new('ShaderNodeBackground'); bg_cam.location = (0, -120)
bg_amb = wn.nodes.new('ShaderNodeBackground'); bg_amb.location = (0, 80)
lp = wn.nodes.new('ShaderNodeLightPath'); lp.location = (-220, 200)
bg_cam.inputs['Color'].default_value = (1.0, 1.0, 1.0, 1)   # 相机看到纯白, 不再灰
bg_cam.inputs['Strength'].default_value = 1.0
bg_amb.inputs['Color'].default_value = (0.48, 0.55, 0.68, 1)
bg_amb.inputs['Strength'].default_value = 0.95
wn.links.new(lp.outputs['Is Camera Ray'], mix.inputs['Fac'])
wn.links.new(bg_amb.outputs['Background'], mix.inputs[1])
wn.links.new(bg_cam.outputs['Background'], mix.inputs[2])
wn.links.new(mix.outputs['Shader'], wout.inputs['Surface'])

# ---------------- 渲染 ----------------
sc.render.engine = 'BLENDER_EEVEE_NEXT'
ee = sc.eevee
ee.taa_render_samples = 32
try:
    ee.use_shadows = True
except Exception:
    pass
try:
    ee.use_raytracing = True
except Exception:
    pass
sc.view_settings.view_transform = 'Standard'
sc.view_settings.look = 'None'
sc.render.film_transparent = False
sc.render.fps = FPS
sc.frame_start = 1
sc.frame_end = NS

# ---------------- 保存 .blend (自包含, 贴图打包进文件) ----------------
SAVE = os.environ.get('SSAVE', '').strip()
if SAVE:
    sc.frame_set(1)
    try:
        bpy.ops.file.pack_all()
        print('贴图已打包进 .blend')
    except Exception as e:
        print('打包失败(贴图仍为外链): %s' % e)
    bpy.ops.wm.save_as_mainfile(filepath=SAVE, compress=True)
    print('BLEND_SAVED %s  %.1f MB' % (SAVE, os.path.getsize(SAVE) / 1e6))

if os.environ.get('STOPDOWN', '').strip():
    cam.data.type = 'ORTHO'
    cam.data.ortho_scale = max(hi[0] - lo[0], hi[1] - lo[1]) * 1.02
    cam.constraints.clear()
    cam.location = (center[0], center[1], center[2] + 60000.0)
    cam.rotation_euler = (0.0, 0.0, 0.0)
    sc.frame_set(NS)
    sc.render.resolution_y = int(round(W * (hi[1] - lo[1]) / (hi[0] - lo[0])))
    sc.render.image_settings.file_format = 'PNG'
    sc.render.filepath = os.path.join(OUTDIR, 'topdown.png')
    bpy.ops.render.render(write_still=True)
    print('TOPDOWN_DONE %s' % sc.render.filepath)
    sys.exit(0)

SSTILL = os.environ.get('SSTILL', '').strip()
if SSTILL:
    sc.render.image_settings.file_format = 'PNG'
    for tok in SSTILL.split(','):
        fr = int(tok)
        sc.frame_set(fr)
        sc.render.filepath = os.path.join(OUTDIR, 'still_%04d.png' % fr)
        bpy.ops.render.render(write_still=True)
        print('SAT_STILL_DONE %s' % sc.render.filepath)
else:
    sc.render.image_settings.file_format = 'FFMPEG'
    sc.render.ffmpeg.format = 'MPEG4'
    sc.render.ffmpeg.codec = 'H264'
    sc.render.ffmpeg.constant_rate_factor = 'HIGH'
    sc.render.ffmpeg.ffmpeg_preset = 'GOOD'
    sc.render.ffmpeg.gopsize = 12
    sc.render.ffmpeg.audio_codec = 'NONE'
    sc.render.filepath = os.path.join(OUTDIR, 'jilong_sat_anim')
    sc.render.use_file_extension = True
    print('开始渲染 %d 帧 @ %dx%d %dfps' % (NS, sc.render.resolution_x,
                                            sc.render.resolution_y, FPS))
    bpy.ops.render.render(animation=True)
    print('SAT_ANIM_DONE %s' % OUTDIR)
