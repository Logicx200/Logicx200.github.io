# -*- coding: utf-8 -*-
"""
修正版 priority-flood：只在"有效数据外边界"种子，避免把被裁断的河谷灌满。
然后用 D8 汇流，从口岸向上游回溯真实沟道。
"""
import heapq
import numpy as np

W = r'F:\DeepSeek工作区\jilong'
A = np.load(W + r'\dem30_final.npy').astype('f8')
ny, nx = A.shape
valid = A > -1000
Z = np.where(valid, A, np.nan)

# 有效区外边界 = 与无效像元或栅格边缘相邻的有效像元
NB8 = [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)]
edge = np.zeros((ny, nx), bool)
for r in range(ny):
    for c in range(nx):
        if not valid[r, c]:
            continue
        if r == 0 or r == ny - 1 or c == 0 or c == nx - 1:
            edge[r, c] = True
            continue
        for dy, dx in NB8:
            if not valid[r + dy, c + dx]:
                edge[r, c] = True
                break
print('有效区外边界 %d 格' % edge.sum())

filled = Z.copy()
closed = ~valid.copy()
pq = []
for r, c in zip(*np.where(edge)):
    heapq.heappush(pq, (filled[r, c], r, c)); closed[r, c] = True
while pq:
    z, r, c = heapq.heappop(pq)
    for dy, dx in NB8:
        r2, c2 = r + dy, c + dx
        if 0 <= r2 < ny and 0 <= c2 < nx and not closed[r2, c2] and valid[r2, c2]:
            closed[r2, c2] = True
            filled[r2, c2] = max(filled[r2, c2], z)
            heapq.heappush(pq, (filled[r2, c2], r2, c2))
d = filled[valid] - A[valid]
print('填洼: 最大抬升 %.1f m, 中位 %.2f m, >10m 的占 %.2f%%' % (
    d.max(), np.median(d), 100 * (d > 10).mean()))
np.save(W + r'\filled_pf2.npy', filled)

# D8
dist = np.array([1, 1, 1, 1, 1.41421356, 1.41421356, 1.41421356, 1.41421356])
best = np.full((ny, nx), -1, np.int8)
bs = np.full((ny, nx), -1e18)
fv = filled.copy()
for k, (dy, dx) in enumerate(NB8):
    sh = np.roll(np.roll(fv, dy, 0), dx, 1)
    s = (fv - sh) / dist[k]
    s[~valid] = -1e18
    m = s > bs
    bs[m] = s[m]; best[m] = k
best[~valid] = -1
print('D8 完成')

# 累积：升序
accv = np.where(valid, 1.0, 0.0).ravel().copy()
bestv = best.ravel()
for i in np.argsort(np.where(valid, fv, np.inf).ravel()):
    if bestv[i] < 0:
        continue
    r, c = divmod(i, nx)
    dy, dx = NB8[bestv[i]]
    r2, c2 = r + dy, c + dx
    if 0 <= r2 < ny and 0 <= c2 < nx:
        accv[r2 * nx + c2] += accv[i]
acc = accv.reshape(ny, nx)
np.save(W + r'\flowacc2.npy', acc)
print('累积: max=%.0f 格 = %.0f km2' % (acc.max(), acc.max() * 900 / 1e6))
for t in (100, 1000, 10000):
    print('   >%6d : %6d 像元' % (t, (acc > t).sum()))

# 口岸位置
PORT_UTM = (340806.0, 3130075.0)
E0, RES = 322000.0, 30.0
gt_N1 = 3161000.0
pc = int((PORT_UTM[0] - E0) / RES); pr = int((gt_N1 - PORT_UTM[1]) / RES)
print()
print('口岸 col=%d row=%d 高程=%.0f m 累积=%.0f 格 (%.2f km2)' % (
    pc, pr, A[pr, pc], acc[pr, pc], acc[pr, pc] * 900 / 1e6))

# 口岸上游回溯
r, c = pr, pc
path = [(r, c)]
seen = {(r, c)}
for _ in range(30000):
    bn = None
    for dy, dx in NB8:
        r2, c2 = r + dy, c + dx
        if not (0 <= r2 < ny and 0 <= c2 < nx) or not valid[r2, c2] or (r2, c2) in seen:
            continue
        k = best[r2, c2]
        if k < 0:
            continue
        ddy, ddx = NB8[k]
        if r2 + ddy == r and c2 + ddx == c:
            if bn is None or acc[r2, c2] > acc[bn[0], bn[1]]:
                bn = (r2, c2)
    if bn is None:
        break
    r, c = bn
    seen.add((r, c))
    path.append((r, c))
print('口岸上游沟道回溯 %d 格 = %.1f km, 终点 row=%d col=%d 高程=%.0f m' % (
    len(path), len(path) * 30 / 1000, r, c, A[r, c]))
np.save(W + r'\port_upstream.npy', np.array(path))
print()
print('=== 口岸上游沟道剖面 ===')
for k in range(0, len(path), max(1, len(path) // 25)):
    rr, cc = path[k]
    print('  row%4d col%4d 高程%5.0f m  离口岸 %.1f km' % (
        rr, cc, A[rr, cc], k * 30 / 1000))
