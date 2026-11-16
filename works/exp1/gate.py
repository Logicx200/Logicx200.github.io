"""
快速几何门 (cheap filter) 与形状特征。

目的: 判断在给定 (a,e,i,Omega) 下, 通过对面内相位 (omega, M) 做扫描,
      是否可能存在满足 30 km / 150 m/s 的接近。

做法: 忽略相位, 只比较"两条轨道曲线的点集距离" —— 对母器与碎片各取
      K 个时间样本, 计算所有 (k_sc, k_deb) 配对的最小距离。
      这是真实最近距离的一个上界(且相当紧), 可作为廉价的必要性筛除。
"""
import numpy as np
from physics import MU, coe2rv, debris_states, T_WINDOW


# ------------------------------------------------------------------ 合成碎片云
def make_cloud(n=345, seed=0, rng_center=None,
               a_ref=7200e3, e_ref=0.020, i_ref=98.05, Om_ref=76.0):
    """合成碎片云: 与论文最终解所在区域一致 (a~7200km, e~0.02, i~98.05, Om~76)
    这是可学性研究的替代品 —— 真实 345 碎片数据未随赛题公开。"""
    rng = np.random.default_rng(seed)
    c = rng_center or {}
    a = a_ref + c.get('a_sd', 40e3) * rng.standard_normal(n)
    e = np.clip(e_ref + c.get('e_sd', 0.006) * rng.standard_normal(n), 1e-4, 0.09)
    i = np.deg2rad(i_ref + c.get('i_sd', 0.12) * rng.standard_normal(n))
    Om = np.deg2rad(Om_ref + c.get('Om_sd', 0.25) * rng.standard_normal(n))
    w = rng.uniform(0.0, 2 * np.pi, n)
    M = rng.uniform(0.0, 2 * np.pi, n)
    return np.stack([a, e, i, Om, w, M], -1)


# ------------------------------------------------------------------ 采样几何
def sc_samples(a, e, i, Om, K=100, T=T_WINDOW):
    """母器轨道上 K 个等时间样本的位置 (K,3) —— 单一 (a,e,i,Om) 组合。"""
    M = np.linspace(0.0, 2 * np.pi * T / (2 * np.pi * np.sqrt(a ** 3 / MU)),
                    K, endpoint=False)
    w = np.zeros(K)
    A = np.full(K, a); E = np.full(K, e); I = np.full(K, i); O = np.full(K, Om)
    pos, _ = coe2rv(A, E, I, O, w, M)
    return pos


# ------------------------------------------------------------------ 门函数
def gate_min_dist(sc_pos_list, deb_pos, chunk=64):
    """sc_pos_list: (S,K,3); deb_pos: (N,T,3) -> (S,) 最小点集距离 (m)"""
    S = sc_pos_list.shape[0]
    flat = deb_pos.reshape(-1, 3)                     # (N*T,3)
    out = np.empty(S)
    for s0 in range(0, S, chunk):
        s1 = min(S, s0 + chunk)
        A = sc_pos_list[s0:s1]                        # (B,K,3)
        d2 = (A[:, :, None, :] - flat[None, None, :, :])
        d2 = np.einsum('bknt,bknt->bk', d2, d2).min(axis=1)   # (B,)
        out[s0:s1] = np.sqrt(d2)
    return out


def cube_density(deb_pos, res=400e3):
    """把 (N,T,3) 散射到体素计数立方体, 返回 (counts, origin)"""
    flat = deb_pos.reshape(-1, 3)
    mn = flat.min(0) - res
    idx = np.floor((flat - mn) / res).astype(np.int64)
    dims = idx.max(0) + 3
    cnt = np.zeros(int(np.prod(dims)), np.float32)
    lin = (idx[:, 0] * dims[1] + idx[:, 1]) * dims[2] + idx[:, 2]
    np.add.at(cnt, lin, 1.0)
    return cnt.reshape(dims), mn, res


def stencil_sum(cnt, pos, mn, res, rad):
    """对 pos (S,K,3) 求 rad 半径内体素计数之和 (粗略密度估计)"""
    R = max(1, int(np.ceil(rad / res)))
    idx = np.floor((pos - mn) / res).astype(np.int64)
    dims = np.array(cnt.shape)
    S, K, _ = idx.shape
    c = idx.reshape(-1, 3)
    tot = np.zeros(c.shape[0], np.float32)
    g = np.arange(-R, R + 1)
    for dx in g:
        for dy in g:
            for dz in g:
                q = np.clip(c + (dx, dy, dz), 0, dims - 1)
                lin = (q[:, 0] * dims[1] + q[:, 1]) * dims[2] + q[:, 2]
                tot += cnt.reshape(-1)[lin]
    return tot.reshape(S, K)


# ------------------------------------------------------------------ 形状特征
def shape_features(a, e, i, Om, deb_pos, deb_oe, dmin, cnt, mn, res,
                   rad=700e3, K=100):
    """由 (a,e,i,Om) 生成给代理模型的特征矩阵"""
    S = len(a)
    sc = np.stack([sc_samples(a[s], e[s], i[s], Om[s], K=K) for s in range(S)])
    dens = stencil_sum(cnt, sc, mn, res, rad).mean(axis=1)     # 平均邻域密度
    dmin_km = dmin / 1e3
    n_orb = np.sqrt(MU / a ** 3)
    ci = np.cos(i)
    dOm_rate = -1.5 * J2loc(a, e, i) * ci
    dw_rate = 0.75 * J2loc(a, e, i) * (5 * ci ** 2 - 1)
    feats = {
        'a_km': a / 1e3,
        'e': e,
        'i_deg': np.rad2deg(i),
        'Om_deg': np.rad2deg(Om),
        'log_dmin': np.log10(np.maximum(dmin_km, 1e-2)),
        'dens': dens,
        'n_rad_s': n_orb,
        'dOm_rate': dOm_rate,
        'dw_rate': dw_rate,
        'da_deb': (a - deb_oe[:, 0].mean()) / 1e3,
        'de_deb': e - deb_oe[:, 1].mean(),
        'di_deb_deg': np.rad2deg(i - deb_oe[:, 2].mean()),
        'dOm_deb_deg': np.rad2deg(Om - deb_oe[:, 3].mean()),
        'i_spread': np.rad2deg(deb_oe[:, 2].std()),
        'Om_spread': np.rad2deg(deb_oe[:, 3].std()),
    }
    keys = sorted(feats.keys())
    X = np.stack([feats[k] for k in keys], -1)
    return X, keys


def J2loc(a, e, i):
    from physics import J2, RE
    p = a * (1 - e * e)
    return J2 * (RE / p) ** 2 * np.sqrt(MU / a ** 3)
