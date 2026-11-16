# -*- coding: utf-8 -*-
"""
用 DEM 做汇流分析，确定口岸的上游集水区，并列出其中的冰川候选。
D8 汇流 + 上游累积，定位真正汇入口岸的源区。
"""
import numpy as np
from scipy import ndimage

W = r'F:\DeepSeek工作区\jilong'
A = np.load(W + r'\dem30_final.npy').astype('f8')
ny, nx = A.shape
# 处理 NoData
ND = -9999
valid = A > -1000
A2 = np.where(valid, A, np.nan)

# 填平洼地（简单的优先淹没法：迭代抬升）
print('填洼中...', flush=True)
B = A2.copy()
for it in range(60):
    nb = np.full_like(B, np.inf)
    for dy, dx in [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)]:
        sh = np.roll(np.roll(B, dy, 0), dx, 1)
        nb = np.minimum(nb, sh + 0.01)
    B2 = np.maximum(B, nb)
    B2[~valid] = np.nan
    d = np.nanmax(np.abs(np.nan_to_num(B2 - B)))
    B = B2
    if d < 1e-4:
        print('  第 %d 轮收敛 (最大抬升 %.4f m)' % (it, d), flush=True)
        break
print('  填洼完成', flush=True)

# D8 最陡下降方向
dirs = [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)]
dist = np.array([1.0, 1.0, 1.0, 1.0, 1.414, 1.414, 1.414, 1.414])
best = np.full((ny, nx), -1, np.int8)
slope = np.zeros((ny, nx))
for k, (dy, dx) in enumerate(dirs):
    sh = np.roll(np.roll(B, dy, 0), dx, 1)
    s = (B - sh) / dist[k]
    m = s > slope
    slope[m] = s[m]
    best[m] = k
best[~valid] = -1
print('D8 方向完成', flush=True)

# 上游累积（迭代流向法，多轮传播）
acc = np.ones((ny, nx), np.float32)
acc[~valid] = 0
# 按高程从高到低处理
idx = np.argsort(np.nan_to_num(B, nan=-1e9).ravel())[::-1]
order = np.unravel_index(idx, B.shape)
print('累积流量计算中...', flush=True)
accf = acc.copy()
for n in range(0, ny * nx, 1):
    pass
# 向量化：按高程降序，逐个把 acc 推给下游
Bv = np.nan_to_num(B, nan=1e9).ravel()
ordv = np.argsort(Bv)          # 升序：低处先处理，acc 已含全部上游
accv = acc.ravel().copy()
bestv = best.ravel()
for i in ordv:
    if bestv[i] < 0:
        continue
    r, c = divmod(i, nx)
    dy, dx = dirs[bestv[i]]
    r2, c2 = r + dy, c + dx
    if 0 <= r2 < ny and 0 <= c2 < nx:
        j = r2 * nx + c2
        if valid[r2, c2]:
            accv[j] += accv[i]
acc = accv.reshape(ny, nx)
np.save(W + r'\flowacc.npy', acc)
np.save(W + r'\filled.npy', B)

# 口岸位置
pc, pr = 627, 1031
print()
print('口岸 (col%d,row%d) 上游累积 = %.0f 格 = %.1f km2'
      % (pc, pr, acc[pr, pc], acc[pr, pc] * 900 / 1e6))
# 河网: 累积 > 阈值
for thr in (200, 1000, 5000):
    riv = acc > thr
    print('  累积>%d 的像元 %d 个 (%.0f km2)' % (thr, riv.sum(), riv.sum() * 900 / 1e6))

# 从口岸向上游回溯主河道
print()
print('=== 口岸上游主河道轨迹 (逆向) ===')
# 找每个像元的下游，构建反向查找
r, c = pr, pc
path = [(r, c)]
for step in range(3000):
    # 找流向该点的上游邻居
    bestn = None
    for dy, dx in dirs:
        r2, c2 = r + dy, c + dx
        if not (0 <= r2 < ny and 0 <= c2 < nx) or not valid[r2, c2]:
            continue
        k = best[r2, c2]
        if k < 0:
            continue
        ddy, ddx = dirs[k]
        if r2 + ddy == r and c2 + ddx == c:
            if bestn is None or acc[r2, c2] > acc[bestn[0], bestn[1]]:
                bestn = (r2, c2)
    if bestn is None:
        break
    r, c = bestn
    path.append((r, c))
print('  回溯长度 %d 格 = %.1f km' % (len(path), len(path) * 30 / 1000))
print('  终点 row=%d col=%d 高程=%.0f m 累积=%.0f 格' % (r, c, A[r, c], acc[r, c]))
np.save(W + r'\mainpath.npy', np.array(path))
print('  已存 mainpath.npy / flowacc.npy / filled.npy')
