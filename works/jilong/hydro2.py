# -*- coding: utf-8 -*-
"""
标准 priority-flood 填洼 + D8 汇流，得到真实河网与源区->口岸沟道。
priority-flood: 从边界开始用最小堆逐格扩展，保证填充后的面单调下降。
"""
import heapq
import numpy as np

W = r'F:\DeepSeek工作区\jilong'
A = np.load(W + r'\dem30_final.npy').astype('f8')
ny, nx = A.shape
valid = A > -1000
Z = np.where(valid, A, np.inf).copy()
print('有效像元 %d (%.1f%%)' % (valid.sum(), 100 * valid.mean()))

# --- priority-flood 填洼 ---
filled = Z.copy()
closed = ~valid.copy()
pq = []
# 边界种子
for r in range(ny):
    for c in (0, nx - 1):
        if valid[r, c]:
            heapq.heappush(pq, (filled[r, c], r, c)); closed[r, c] = True
for c in range(nx):
    for r in (0, ny - 1):
        if valid[r, c]:
            heapq.heappush(pq, (filled[r, c], r, c)); closed[r, c] = True
print('边界种子 %d 个' % len(pq))

NB = [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)]
n = 0
while pq:
    z, r, c = heapq.heappop(pq)
    n += 1
    for dy, dx in NB:
        r2, c2 = r + dy, c + dx
        if 0 <= r2 < ny and 0 <= c2 < nx and not closed[r2, c2]:
            closed[r2, c2] = True
            filled[r2, c2] = max(filled[r2, c2], z)
            heapq.heappush(pq, (filled[r2, c2], r2, c2))
print('填洼完成，处理 %d 格，最大抬升 %.1f m' % (n, np.nanmax(filled[valid] - A[valid])))
np.save(W + r'\filled_pf.npy', filled)

# --- D8 流向（在填充面上）---
dist = np.array([1, 1, 1, 1, 1.41421356, 1.41421356, 1.41421356, 1.41421356])
best = np.full((ny, nx), -1, np.int8)
bs = np.zeros((ny, nx))
for k, (dy, dx) in enumerate(NB):
    sh = np.roll(np.roll(filled, dy, 0), dx, 1)
    s = (filled - sh) / dist[k]
    s[~valid] = -1
    m = s > bs
    bs[m] = s[m]; best[m] = k
print('D8 流向完成')

# --- 汇流累积：按填充高程升序，把 acc 推给下游 ---
acc = np.where(valid, 1.0, 0.0)
ordv = np.argsort(filled.ravel())
accv = acc.ravel().copy()
bestv = best.ravel()
fy = filled.ravel()
for i in ordv:
    if bestv[i] < 0:
        continue
    r, c = divmod(i, nx)
    dy, dx = NB[bestv[i]]
    j = (r + dy) * nx + (c + dx)
    if 0 <= r + dy < ny and 0 <= c + dx < nx:
        accv[j] += accv[i]
acc = accv.reshape(ny, nx)
np.save(W + r'\flowacc_pf.npy', acc)
np.save(W + r'\flowdir_pf.npy', best)

print()
print('汇流累积: max=%.0f 格 (%.0f km2)' % (acc.max(), acc.max() * 900 / 1e6))
for t in (100, 1000, 10000, 100000):
    print('  >%6d : %6d 像元' % (t, (acc > t).sum()))
i = np.unravel_index(np.argmax(acc), acc.shape)
print('最大累积点 row=%d col=%d 高程=%.0f m acc=%.0f' % (i[0], i[1], A[i], acc[i]))

# --- 从最大累积点向上游回溯主河道 ---
r, c = i
path = [(r, c)]
for _ in range(20000):
    bn = None
    for dy, dx in NB:
        r2, c2 = r + dy, c + dx
        if not (0 <= r2 < ny and 0 <= c2 < nx) or not valid[r2, c2]:
            continue
        k = best[r2, c2]
        if k < 0:
            continue
        ddy, ddx = NB[k]
        if r2 + ddy == r and c2 + ddx == c:
            if bn is None or acc[r2, c2] > acc[bn[0], bn[1]]:
                bn = (r2, c2)
    if bn is None:
        break
    r, c = bn
    path.append((r, c))
print('主河道回溯 %d 格 = %.1f km' % (len(path), len(path) * 30 / 1000))
np.save(W + r'\mainstem.npy', np.array(path))

print()
print('=== 主河道纵剖面 ===')
for k in range(0, len(path), max(1, len(path) // 30)):
    r, c = path[k]
    print('  row%4d col%4d 高程%5.0f m  acc=%8.0f' % (r, c, A[r, c], acc[r, c]))
