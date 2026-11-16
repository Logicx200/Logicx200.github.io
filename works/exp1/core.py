"""
EXP-1 可学性分析: 数据生成、廉价 gate、代理模型、评价指标。

严格 numpy 实现 (环境无 sklearn)。
"""
import numpy as np

from physics import MU, RE, J2, T_WINDOW, coe2rv, rk4_step, propagate
from gate import make_cloud

RNG = np.random.default_rng(20251114)


# ============================================================ 母器轨迹
def sc_traj_batch(oe, dt_out, T=T_WINDOW, nsub=1):
    """oe: (S,6) -> (S, n_out, 6)。nsub = 每个输出步长内的 RK4 子步数。"""
    n_out = int(round(T / dt_out)) + 1
    pos, vel = coe2rv(oe[:, 0], oe[:, 1], oe[:, 2], oe[:, 3], oe[:, 4], oe[:, 5])
    x = np.concatenate([pos, vel], -1)
    h = dt_out / nsub
    out = np.empty((len(oe), n_out, 6))
    out[:, 0] = x
    for k in range(n_out - 1):
        for _ in range(nsub):
            x = rk4_step(x, h)
        out[:, k + 1] = x
    return out


def eval_candidates(oe, deb_pos, deb_vel, dt_out, T=T_WINDOW, dr=30e3, dv=150.0):
    """oe:(S,6) -> (n_unique, n_hits)  精确清除判定"""
    S = len(oe)
    traj = sc_traj_batch(oe, dt_out, T)
    sc_pos, sc_vel = traj[:, :, :3], traj[:, :, 3:]
    nun = np.zeros(S, np.int32)
    nhi = np.zeros(S, np.int32)
    for s in range(S):
        d = deb_pos - sc_pos[s][None, :, :]
        dist = np.sqrt(np.einsum('ntk,ntk->nt', d, d))
        v = deb_vel - sc_vel[s][None, :, :]
        relv = np.sqrt(np.einsum('ntk,ntk->nt', v, v))
        hit = (dist < dr) & (relv < dv)
        nhi[s] = hit.sum()
        nun[s] = hit.any(axis=1).sum()
    return nun, nhi


# ============================================================ 采样
def sample_shapes(n, rng, center=(7200e3, 0.020, 98.05, 76.0),
                  sd=(50e3, 0.008, 0.25, 0.5)):
    a = center[0] + sd[0] * rng.standard_normal(n)
    e = np.clip(center[1] + sd[1] * rng.standard_normal(n), 1e-4, 0.08)
    i = np.deg2rad(center[2] + sd[2] * rng.standard_normal(n))
    Om = np.deg2rad(center[3] + sd[3] * rng.standard_normal(n))
    return np.stack([a, e, i, Om], -1)


def sample_full6(n, rng, box=None):
    """全 6 维采样 (用于 E4 基线)"""
    box = box or dict(a=(7050e3, 7400e3), e=(0.002, 0.055),
                      i=(97.4, 98.7), Om=(74.5, 77.5))
    a = rng.uniform(*box['a'], n)
    e = rng.uniform(*box['e'], n)
    i = np.deg2rad(rng.uniform(*box['i'], n))
    Om = np.deg2rad(rng.uniform(*box['Om'], n))
    w = rng.uniform(0, 2 * np.pi, n)
    M = rng.uniform(0, 2 * np.pi, n)
    return np.stack([a, e, i, Om, w, M], -1)


def phase_grid(nw, nM):
    w = np.linspace(0, 2 * np.pi, nw, endpoint=False)
    M = np.linspace(0, 2 * np.pi, nM, endpoint=False)
    W, MM = np.meshgrid(w, M, indexing='ij')
    return np.stack([W.ravel(), MM.ravel()], -1)


# ============================================================ 廉价 gate 评分
def sc_endpoints(a, e, i, Om, nw):
    """面内角 u 等间隔采样下的位置与速度 (S,nw,3),(S,nw,3)  —— 零推进近似"""
    u = np.linspace(0, 2 * np.pi, nw, endpoint=False)
    S = len(a)
    cO, sO = np.cos(Om)[:, None], np.sin(Om)[:, None]
    ci, si = np.cos(i)[:, None], np.sin(i)[:, None]
    cu, su = np.cos(u)[None, :], np.sin(u)[None, :]
    r = a[:, None] * (1 - e[:, None] ** 2) / (1 + e[:, None] * cu)
    # r_hat
    rx = cO * cu - sO * su * ci
    ry = sO * cu + cO * su * ci
    rz = su * si
    pos = r[..., None] * np.stack([rx, ry, rz], -1)
    h = np.sqrt(MU * a[:, None] * (1 - e[:, None] ** 2))
    vr = MU / h[:, None] * e[:, None] * su
    vt = h[:, None] / r
    vx = vr[..., None] * np.stack([rx, ry, rz], -1)
    # 面内横向单位矢量
    tx = -cO * su - sO * cu * ci
    ty = -sO * su + cO * cu * ci
    tz = cu * si
    vx = vx + vt[..., None] * np.stack([tx, ty, tz], -1)
    return pos, vx


def gate_score(cand, deb_pos_k, nw=180, chunk=2000):
    """cand:(S,6); deb_pos_k:(N*K,3) 碎片在若干时刻的位置 -> (S,) 最小距离(m)"""
    S = len(cand)
    out = np.empty(S)
    for s0 in range(0, S, chunk):
        s1 = min(S, s0 + chunk)
        c = cand[s0:s1]
        pos, _ = sc_endpoints(c[:, 0], c[:, 1], c[:, 2], c[:, 3], nw)
        A = pos.reshape(len(c), -1, 3)
        d2 = ((A[:, :, None, :] - deb_pos_k[None, None, :, :]) ** 2).sum(-1)
        out[s0:s1] = np.sqrt(d2.min(axis=(1, 2)))
    return out


# ============================================================ 特征
def features(shapes, deb_oe, ref):
    a, e, i, Om = shapes[:, 0], shapes[:, 1], shapes[:, 2], shapes[:, 3]
    p = a * (1 - e ** 2)
    n = np.sqrt(MU / a ** 3)
    k = J2 * (RE / p) ** 2 * n
    ci = np.cos(i)
    f = {
        'a': (a - ref[0]) / 10e3,
        'e': (e - ref[1]) / 5e-3,
        'i': (i - ref[2]) / np.deg2rad(0.1),
        'Om': (Om - ref[3]) / np.deg2rad(0.1),
        'n': (n - np.sqrt(MU / ref[0] ** 3)) / 1e-5,
        'dOm_rate': k * ci / 1e-6,
        'dw_rate': k * (5 * ci ** 2 - 1) / 1e-6,
        'L': (Om + 0.0) * 0 + (a / 1e3) * 0,      # 占位, 后续填充
        'da_deb': (a - deb_oe[:, 0].mean()) / 1e3,
        'de_deb': (e - deb_oe[:, 1].mean()) / 1e-3,
        'di_deb': np.rad2deg(i - deb_oe[:, 2].mean()),
        'dOm_deb': np.rad2deg(Om - deb_oe[:, 3].mean()),
    }
    # 轨道面法向夹角 (与碎片云平均面)
    i0 = deb_oe[:, 2].mean(); O0 = deb_oe[:, 3].mean()
    c1 = np.stack([np.sin(i0) * np.sin(O0), -np.sin(i0) * np.cos(O0), np.cos(i0)], -1)
    c2 = np.stack([np.sin(i) * np.sin(Om), -np.sin(i) * np.cos(Om), np.cos(i)], -1)
    ang = np.arccos(np.clip((c1 * c2).sum(-1), -1, 1))
    f['plane_ang'] = np.rad2deg(ang)
    f['radial_gap'] = (a * (1 - e) - (deb_oe[:, 0] * (1 - deb_oe[:, 1])).mean()) / 1e3
    for nm in ['a', 'e', 'i', 'Om']:
        f[nm + '2'] = f[nm] ** 2
    keys = sorted(f.keys())
    return np.stack([f[k] for k in keys], -1), keys


# ============================================================ 代理模型
def knn_predict(Xtr, ytr, Xte, k=16):
    from scipy.spatial import cKDTree
    mu, sd = Xtr.mean(0), Xtr.std(0) + 1e-12
    tree = cKDTree((Xtr - mu) / sd)
    _, idx = tree.query((Xte - mu) / sd, k=k)
    return ytr[idx].mean(1), ytr[idx].std(1)


class FastBoost:
    """梯度提升 (深度 1 桩), 排序+前缀和向量化, numpy 实现"""
    def __init__(self, n_est=200, lr=0.1, n_thr=24, sub=0.8, seed=0):
        self.n_est, self.lr, self.n_thr, self.sub, self.seed = n_est, lr, n_thr, sub, seed

    def fit(self, X, y):
        rng = np.random.default_rng(self.seed)
        self.base = float(y.mean())
        F = np.full(len(y), self.base)
        self.trees = []
        n, d = X.shape
        for _ in range(self.n_est):
            r = y - F
            aidx = rng.choice(n, max(10, int(n * self.sub)), replace=False)
            Xa, ra = X[aidx], r[aidx]
            na = len(aidx)
            best = None
            for j in range(d):
                xj = Xa[:, j]
                o = np.argsort(xj)
                xs, rs = xj[o], ra[o]
                cs = np.cumsum(rs)
                c2 = np.cumsum(rs ** 2)
                tot, tot2 = cs[-1], c2[-1]
                # 只在前 n_thr 个分位处考察
                pos = np.linspace(0.05, 0.95, self.n_thr) * (na - 1)
                pos = np.unique(pos.astype(int))
                pos = pos[(pos >= 3) & (pos <= na - 4)]
                if len(pos) == 0:
                    continue
                nl = (pos + 1).astype(float)
                nr = na - nl
                sl, sl2 = cs[pos], c2[pos]
                sr, sr2 = tot - sl, tot2 - sl2
                sse = (sl2 - sl ** 2 / nl) + (sr2 - sr ** 2 / nr)
                b = int(np.argmin(sse))
                if best is None or sse[b] < best[0]:
                    thr = 0.5 * (xs[pos[b]] + xs[min(pos[b] + 1, na - 1)])
                    best = (float(sse[b]), j, float(thr), float(sl[b] / nl[b]), float(sr[b] / nr[b]))
            if best is None:
                break
            _, j, thr, vl, vr = best
            self.trees.append((j, thr, vl, vr))
            F += self.lr * np.where(X[:, j] <= thr, vl, vr)
        return self

    def predict(self, X):
        F = np.full(len(X), self.base)
        for j, thr, vl, vr in self.trees:
            F += self.lr * np.where(X[:, j] <= thr, vl, vr)
        return F


class MLPEnsemble:
    """深度集成 (M 个单隐层 MLP, Adam), 输出 (均值, 标准差)"""
    def __init__(self, M=5, H=64, epochs=250, lr=3e-3, seed=0, batch=512):
        self.M, self.H, self.epochs, self.lr, self.seed, self.batch = M, H, epochs, lr, seed, batch

    def fit(self, X, y):
        rng = np.random.default_rng(self.seed)
        self.models = [self._fit_one(X, y, int(rng.integers(1 << 30))) for _ in range(self.M)]
        return self

    def _fit_one(self, X, y, seed):
        rng = np.random.default_rng(seed)
        mu, sd = X.mean(0), X.std(0) + 1e-12
        Xs = (X - mu) / sd
        ym, ys = y.mean(), y.std() + 1e-12
        t = (y - ym) / ys
        n, d = Xs.shape
        W1 = rng.normal(0, np.sqrt(2 / d), (d, self.H)); b1 = np.zeros(self.H)
        W2 = rng.normal(0, np.sqrt(2 / self.H), (self.H, 1)); b2 = np.zeros(1)
        par = [W1, b1, W2, b2]
        m = [np.zeros_like(p) for p in par]; v = [np.zeros_like(p) for p in par]
        b1_, b2_, eps = 0.9, 0.999, 1e-8
        for ep in range(1, self.epochs + 1):
            for s in range(0, n, self.batch):
                b = rng.integers(0, n, min(self.batch, n))
                xb, yb = Xs[b], t[b]
                z1 = xb @ W1 + b1
                h1 = np.maximum(z1, 0)
                out = (h1 @ W2 + b2).ravel()
                g = (out - yb)[:, None] / len(b)
                gh = g @ W2.T
                grads = [xb.T @ (gh * (z1 > 0)), (gh * (z1 > 0)).sum(0), h1.T @ g, g.sum(0)]
                for i, gi in enumerate(grads):
                    m[i] = b1_ * m[i] + (1 - b1_) * gi
                    v[i] = b2_ * v[i] + (1 - b2_) * gi ** 2
                    par[i] -= self.lr * (m[i] / (1 - b1_ ** ep)) / (np.sqrt(v[i] / (1 - b2_ ** ep)) + eps)
        return dict(par=par, mu=mu, sd=sd, ym=ym, ys=ys)

    def predict(self, X):
        P = []
        for m in self.models:
            W1, b1, W2, b2 = m['par']
            Xs = (X - m['mu']) / m['sd']
            h1 = np.maximum(Xs @ W1 + b1, 0)
            P.append(((h1 @ W2 + b2).ravel()) * m['ys'] + m['ym'])
        P = np.stack(P, 0)
        return P.mean(0), P.std(0)


# ============================================================ 指标
def r2(y, yh):
    return float(1.0 - ((y - yh) ** 2).sum() / max(((y - y.mean()) ** 2).sum(), 1e-30))


def spearman(x, y):
    rx = np.argsort(np.argsort(x)).astype(float); rx -= rx.mean()
    ry = np.argsort(np.argsort(y)).astype(float); ry -= ry.mean()
    return float((rx * ry).sum() / np.sqrt((rx ** 2).sum() * (ry ** 2).sum()))


def topk_recall(y, yh, frac=0.01):
    k = max(1, int(len(y) * frac))
    th = np.sort(y)[-k]
    sel = np.argsort(yh)[-k:]
    return float((y[sel] >= th).mean())
