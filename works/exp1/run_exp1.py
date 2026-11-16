"""
EXP-1 可学性分析主程序。

E1 数值可信性: RK4 收敛性 + 与解析解一致性
E2 结构诊断:   6 维空间中"有解集"的比例 (不同相位网格分辨率)
E3 相关长度:   沿 w / M 的自相关长度; 非零测度随网格变粗的衰减
E4 可预测性:   代理模型对 结构量 / 聚合标签 / 精确标签 的样本外表现
E5 预算效率:   等仿真预算下, gate 筛形状 vs 随机采样

运行:  python run_exp1.py            (小规模快速版)
      python run_exp1.py --full     (更密网格)
"""
import json
import os
import sys
import time
import numpy as np

from physics import (MU, RE, J2, T_WINDOW, coe2rv, rk4_step, propagate,
                     debris_states, encounters, debris_rates)
import physics
import core
from gate import make_cloud

OUT = "results.json"
N_SEED = 10          # E3 种子上限
E3_DT = 30.0         # E3 检测步长 (E2 已证 10->45s 事件损失 <0.3%)


def log(*a):
    print(*a, flush=True)


# ==================================================================== E1
def exp1_verification():
    log("\n" + "=" * 72)
    log("E1 数值可信性验证")
    log("=" * 72)
    res = {}
    # (a) 无 J2 时应严格保持 Kepler 解析解
    a, e, i, Om, w = 7200e3, 0.02, np.deg2rad(98.05), np.deg2rad(76.0), 0.5
    pos0, vel0 = coe2rv(np.atleast_1d(a), np.atleast_1d(e), np.atleast_1d(i),
                        np.atleast_1d(Om), np.atleast_1d(w), np.atleast_1d(0.3))
    x0 = np.concatenate([pos0[0], vel0[0]])
    mu_save = physics.MU
    KJ2_save = physics.KJ2
    physics.KJ2 = 0.0            # 关闭 J2 (注意: rk4_step 使用模块级预计算的 KJ2)
    T = 7200.0
    for dt in (24.0, 12.0, 6.0, 3.0):
        n_out = int(T / dt) + 1
        traj = physics.propagate(x0, T, dt / 4, n_out)
        pos_a, _ = coe2rv(np.atleast_1d(a), np.atleast_1d(e), np.atleast_1d(i),
                          np.atleast_1d(Om), np.atleast_1d(w),
                          np.atleast_1d(0.3 + np.sqrt(mu_save / a ** 3) * T))
        err = np.linalg.norm(traj[-1, :3] - pos_a[0])
        log(f"  [无J2] dt_out={dt:5.1f}s  RK4内步={dt/4:5.2f}s  末端位置误差 = {err:10.3f} m")
        res[f'kepler_err_dt{dt}'] = float(err)
    physics.KJ2 = KJ2_save
    # (a2) J2 引起的 2 h 位置偏移 (量化 J2 的重要性)
    n_ref = int(T / 0.375) + 1
    withj2 = physics.propagate(x0, T, 0.375, n_ref)[-1]
    physics.KJ2 = 0.0
    noj2 = physics.propagate(x0, T, 0.375, n_ref)[-1]
    physics.KJ2 = KJ2_save
    res['j2_offset_2h_m'] = float(np.linalg.norm(withj2[:3] - noj2[:3]))
    log(f"  [J2 重要性] 2 h 内 J2 造成的末端位置偏移 = {res['j2_offset_2h_m']/1e3:.3f} km")
    # (b) 含 J2 时的步长收敛性 (以 dt=0.375s 为参考)
    ref = physics.propagate(x0, T, 0.375, n_ref)[-1]
    for dt in (30.0, 15.0, 7.5, 3.75):
        n_out = int(T / dt) + 1
        tr = physics.propagate(x0, T, dt / 4, n_out)[-1]
        err = np.linalg.norm(tr[:3] - ref[:3])
        log(f"  [含J2] dt_out={dt:5.2f}s  RK4内步={dt/4:5.2f}s  末端位置误差 = {err:10.3f} m")
        res[f'j2_err_dt{dt}'] = float(err)
    # (c) 轨道高度下界是否合理 + 碎片长期漂移量级
    dOm, dw, dM = debris_rates(np.array([a]), np.array([e]), np.array([i]))
    log(f"  [碎片] 24h 内 Ω 漂移 {np.rad2deg(dOm[0])*86400:+.4f}°, "
        f"ω 漂移 {np.rad2deg(dw[0])*86400:+.4f}°, M 漂移 {np.rad2deg(dM[0])*86400:+.4f}°")
    res['debris_drift_deg_per_day'] = [float(np.rad2deg(dOm[0]) * 86400),
                                       float(np.rad2deg(dw[0]) * 86400),
                                       float(np.rad2deg(dM[0]) * 86400)]
    return res


# ==================================================================== 扫描器
def build_ephemeris(cloud, tgrid):
    """碎片在细时间网格上的状态 (N,nT,3) × 2, 全实验共用同一判据"""
    pos, vel = debris_states(cloud, tgrid)
    return pos.astype(np.float64), vel.astype(np.float64)


def scan(shapes, phases, cloud, tgrid, eph, dr=30e3, dv=150.0, chunk=300,
         margin=100e3, stride=1, screen=250e3, nsub=1, outer=60000):
    """
    统一判据的精确扫描 (dt_det = tgrid 步长 = 10 s; E1 已证该步长 2 h 误差仅毫米级)。
    两级剔除:
      1) 窄相位包围盒: 母器轨迹的轴向包围盒(x stride 采样)筛出可能接近的碎片
      2) 逐时刻距离/相对速度判定 (仅对候选碎片)
    自洽性: |v_rel| < 150 m/s ⇒ 一个 10 s 步内相对位移 < 1.5 km ⇒
            以 screen=250 km 做粗筛, 真事件必然落在某个采样点上 (最坏 150/250=0.6 步)
    """
    S, P = len(shapes), len(phases)
    hits = np.zeros((S, P), bool)
    nuniq = np.zeros((S, P), np.int16)
    tgrid = np.asarray(tgrid, float)
    nT = len(tgrid)
    dt_out = float(tgrid[1] - tgrid[0])
    deb_pos, deb_vel = eph
    deb_box = np.stack([deb_pos.min(1), deb_pos.max(1)], 1)     # (N,2,3)
    dr2, dv2 = dr * dr, dv * dv
    cs = max(1, int(round(300.0 / dt_out)))                     # 粗时间筛步长(≈300 s)
    coars_idx = np.arange(0, nT, cs)
    per = max(1, min(chunk, outer // max(1, P)))       # 每批形状数, 保证候选总数 <= outer
    for s0 in range(0, S, per):
        s1 = min(S, s0 + per)
        c = shapes[s0:s1]
        A = np.repeat(c, P, axis=0)
        oe = np.stack([A[:, 0], A[:, 1], A[:, 2], A[:, 3],
                       np.tile(phases[:, 0], len(c)),
                       np.tile(phases[:, 1], len(c))], -1).astype(float)
        traj = core.sc_traj_batch(oe, dt_out, T_WINDOW, nsub=nsub)
        pos = np.ascontiguousarray(traj[:, :, :3], dtype=np.float32)
        vel = np.ascontiguousarray(traj[:, :, 3:], dtype=np.float32)
        debp32 = deb_pos.astype(np.float32, copy=False)
        debv32 = deb_vel.astype(np.float32, copy=False)
        # --- 级剔除 A: 包围盒 ---
        sub = pos[:, ::stride, :]
        lo = sub.min(1) - margin
        hi = sub.max(1) + margin
        keep = (deb_box[None, :, 1, :] >= lo[:, None, :]).all(-1) & \
               (deb_box[None, :, 0, :] <= hi[:, None, :]).all(-1)
        # --- 三级递进剔除 (阈值由 |v_rel|<150 m/s 反推, 保证不漏检) ---
        #   L1: 180 s 采样, 门限 30km + 150m/s*90s = 13.5 km  (超集, 严格安全)
        #   L2:  60 s 采样, 门限 30km + 150m/s*30s =  4.5 km
        #   L3:  10 s 采样, 精确判据 30 km & 150 m/s
        C = len(oe)
        seen_sets = [set() for _ in range(C)]
        lvl1 = np.arange(0, nT, max(1, int(round(180.0 / dt_out))))
        lvl2 = np.arange(0, nT, max(1, int(round(60.0 / dt_out))))
        thL1 = np.float32((30e3 + 150.0 * 90.0) ** 2)
        thL2 = np.float32((30e3 + 150.0 * 30.0) ** 2)
        thL3 = np.float32(250e3 ** 2)
        dr2f = np.float32(dr2)
        dv2f = np.float32(dv2)
        alive = np.ones(C, bool)
        for tag, kidx, th2 in (('L1', lvl1, thL1),
                               ('L2', lvl2, thL2),
                               ('L3', np.arange(nT), thL3)):
            a_idx = np.flatnonzero(alive)
            still = np.zeros(C, bool)
            for k in kidx:
                dp = debp32[:, k, :]
                dv = debv32[:, k, :]
                d = dp[None, :, :] - pos[a_idx, k, None, :]
                d2 = np.einsum('cnd,cnd->cn', d, d)
                m = d2 < th2
                if not m.any():
                    continue
                if tag == 'L3':
                    rows = np.flatnonzero(m.any(1))
                    anym = m.any(0)
                    d2s = d2[rows][:, anym]
                    dps = dp[anym]
                    dvs = dv[anym]
                    ps = pos[a_idx[rows], k, :]
                    vs = vel[a_idx[rows], k, :]
                    # 精确判据: 距离 < 30 km 且相对速度 < 150 m/s
                    for j in range(len(rows)):
                        sel = np.flatnonzero(d2s[j] < dr2f)
                        if sel.size:
                            rvv = dvs[sel] - vs[j]
                            rv2 = np.einsum('nd,nd->n', rvv, rvv)
                            ok = sel[rv2 < dv2f]
                            if ok.size:
                                seen_sets[a_idx[rows[j]]].update(
                                    np.flatnonzero(anym)[ok].tolist())
                else:
                    still[a_idx] |= m.any(1)
            if tag != 'L3':
                alive = still
                if not alive.any():
                    break
        cand_hit = np.array([len(s) > 0 for s in seen_sets])
        nuni = np.array([len(s) for s in seen_sets], np.int16)
        near = alive | cand_hit
        hits[s0:s1] = cand_hit.reshape(s1 - s0, P)
        nuniq[s0:s1] = nuni.reshape(s1 - s0, P)
        if (s1 % max(per * 10, 1) == 0) or s1 == S:
            log(f"    scan {s1}/{S}  包围盒={int(keep.any(1).sum())}  曾近距={int(near.sum())}"
                f"  确证={int(cand_hit.sum())}  最大清除数={int(nuni.max()) if len(nuni) else 0}")
    return hits, nuniq


def make_tgrid(T=T_WINDOW, dt=10.0):
    return np.arange(0.0, T + 1e-9, dt)


def eval_pairs(oe, cloud, tgrid, eph, dr=30e3, dv=150.0, per=20000):
    """配对评估: oe (C,6) 每个候选各用自己的 (w,M)。返回 hits (C,) bool。
    用于 E3 这类"形状-相位已配对"的场景, 不做笛卡尔积。"""
    deb_pos, deb_vel = eph
    debp32 = deb_pos.astype(np.float32, copy=False)
    debv32 = deb_vel.astype(np.float32, copy=False)
    nT = len(tgrid)
    C = len(oe)
    out = np.zeros(C, bool)
    thL1 = np.float32((30e3 + 150.0 * 90.0) ** 2)
    thL3 = np.float32(250e3 ** 2)
    dr2f, dv2f = np.float32(dr * dr), np.float32(dv * dv)
    for c0 in range(0, C, per):
        c1 = min(C, c0 + per)
        traj = core.sc_traj_batch(oe[c0:c1], float(tgrid[1] - tgrid[0]), T_WINDOW)
        pos = np.ascontiguousarray(traj[:, :, :3], dtype=np.float32)
        vel = np.ascontiguousarray(traj[:, :, 3:], dtype=np.float32)
        alive = np.ones(c1 - c0, bool)
        seen = [set() for _ in range(c1 - c0)]
        # L1: 稀疏时间点 + (30km + 150m/s*90s) 门限, 取"任一时刻通过"的并集
        lvl1 = range(0, nT, max(1, int(round(180.0 / (tgrid[1] - tgrid[0])))))
        anyL1 = np.zeros(c1 - c0, bool)
        for k in lvl1:
            d = debp32[:, k, :][None, :, :] - pos[:, k, None, :]
            d2 = np.einsum('cnd,cnd->cn', d, d)
            anyL1 |= (d2 < thL1).any(1)
        alive &= anyL1
        for k in range(nT):
            a_idx = np.flatnonzero(alive)
            if a_idx.size == 0:
                break
            d = debp32[:, k, :][None, :, :] - pos[a_idx, k, None, :]
            d2 = np.einsum('cnd,cnd->cn', d, d)
            m = d2 < thL3
            if not m.any():
                continue
            for j in np.flatnonzero(m.any(1)):
                sel = np.flatnonzero(d2[j] < dr2f)
                if sel.size == 0:
                    continue
                rv = debv32[sel, k, :] - vel[a_idx[j], k, :]
                rv2 = np.einsum('nd,nd->n', rv, rv)
                ok = sel[rv2 < dv2f]
                if ok.size:
                    seen[a_idx[j]].update(ok.tolist())
        out[c0:c1] = np.array([len(s) > 0 for s in seen])
    return out


# ==================================================================== E2
def exp2_summarize(cloud, shapes, hits, nuniq, tgrid, eph, tag='dense', cap=150):
    """E2 汇总 + 网格/时间分辨率敏感性 (在 cap 个形状上做)"""
    S, P = hits.shape
    log("\n" + "=" * 72)
    log(f"E2 结构诊断: {S} 个形状 × {P} 相位网格 (dt_det=10 s)")
    log("=" * 72)
    frac_cand = hits.mean()
    shapes_any = hits.any(axis=1)
    best_per_shape = nuniq.max(axis=1)
    k = hits.sum(axis=1)
    log(f"  候选(shape,phase)中满足清除条件的比例 : {frac_cand*100:.4f}%   ({hits.sum()}/{hits.size})")
    log(f"  至少含 1 个可行相位的形状比例        : {shapes_any.mean()*100:.2f}%")
    log(f"  每个形状的最优清除数: max={best_per_shape.max()}, 均值={best_per_shape.mean():.3f}, "
        f"可行形状上均值={best_per_shape[shapes_any].mean() if shapes_any.any() else 0:.2f}")
    log(f"  可行相位数的分布: 中位数={np.median(k):.0f}, 均值={k.mean():.1f}, 最大={k.max()}")
    # --- 敏感性: 同一 12×12 细网格结果, 抽稀到更粗网格 ---
    res = {}
    sub_shapes = shapes[:min(len(shapes), cap)]
    fine = core.phase_grid(12, 12)
    t0 = time.time()
    hf, nf = scan(sub_shapes, fine, cloud, tgrid, eph)
    log(f"  敏感性基准网格扫描耗时 {time.time()-t0:.1f}s")
    for step in (30, 45, 60, 90, 120):
        nn = 360 // step
        if nn < 2:
            continue
        sel = np.array([i for i in range(len(fine))
                        if (i // 12) % (12 // nn) == 0 and (i % 12) % (12 // nn) == 0])
        h2, n2 = hf[:, sel], nf[:, sel]
        res[step] = dict(frac=float(h2.mean()), n_grid=int(len(sel)),
                         events=int(h2.sum()), size=int(h2.size),
                         events_per_1e5=float(h2.sum() / h2.size * 1e5),
                         max_uniq=int(n2.max()),
                         shapes_any=float(h2.any(1).mean()))
        log(f"    相位步长 {step:3d}° -> 可行比例 {h2.mean()*100:8.4f}%, 网格 {len(sel):3d} 点, "
            f"事件 {int(h2.sum()):4d}/{h2.size:5d} (每10万候选 {h2.sum()/h2.size*1e5:6.1f}), "
            f"单点最大清除 {int(n2.max())}, 可行形状比 {h2.any(1).mean()*100:5.1f}%")
    # --- 检测时间步长敏感性 (对 100 个形状的 12×12 网格) ---
    tim = {}
    for dt in (10, 20, 30, 45):
        st = max(1, int(round(dt / 10.0)))
        tg = tgrid[::st]
        ep = (eph[0][:, ::st, :], eph[1][:, ::st, :])
        h3, n3 = scan(sub_shapes[:100], fine, cloud, tg, ep)
        tim[dt] = dict(frac=float(h3.mean()), events=int(h3.sum()), size=int(h3.size))
        log(f"    检测步长 {dt:3d} s -> 可行比例 {h3.mean()*100:8.4f}%  "
            f"(事件 {int(h3.sum())}/{h3.size})")
    out = dict(frac_candidate=float(frac_cand),
               frac_shapes_with_any=float(shapes_any.mean()),
               best_max=int(best_per_shape.max()),
               best_mean=float(best_per_shape.mean()),
               max_uniq_overall=int(nuniq.max()),
               median_feasible_phases=float(np.median(k)),
               mean_feasible_phases=float(k.mean()),
               grid_sensitivity=res, time_sensitivity=tim)
    return out


# ==================================================================== E3
def exp3_correlation(cloud, shapes, hits, eph, tag='dense'):
    """
    相关长度 / 可达域宽度: 在种子形状的 (w,M) 邻域做细网格扫描, 测量"可行团块"的几何尺寸。
    - w 方向: 固定 M 于最优点, 扫 w ∈ [w*-25°, w*+25°], 步长 1°
    - M 方向: 固定 w 于最优点, 扫 M ∈ [M*-25°, M*+25°], 步长 1°
    相关长度 L 定义为连续可行段的平均宽度。
    """
    log("\n" + "=" * 72)
    log("E3 可达域宽度: 在 (w,M) 上做 ±25° / 1° 细扫, 测量可行团块尺寸")
    log("=" * 72)
    tgrid = make_tgrid(dt=E3_DT)
    P = hits.shape[1]
    nw = int(round(np.sqrt(P))); nM = P // nw
    ph = core.phase_grid(nw, nM)
    nuniq = np.load(os.path.join(tag, "e2_nuniq.npy"))
    good = np.flatnonzero(hits.any(axis=1))[:N_SEED]
    seeds = shapes[good]
    best = ph[[int(np.argmax(nuniq[s])) for s in good]]
    span, step = 25.0, 1.0
    grid = np.arange(-span, span + 1e-9, step)
    out = {'span_deg': span, 'step_deg': step, 'n_seeds': int(len(seeds))}
    for name, axis in (('w', 0), ('M', 1)):
        oe = np.repeat(np.concatenate([seeds, best], -1), len(grid), axis=0).astype(float)
        offs = np.tile(grid, len(seeds))
        if axis == 0:
            oe[:, 4] += np.deg2rad(offs)
        else:
            oe[:, 5] += np.deg2rad(offs)
        t0 = time.time()
        h = eval_pairs(oe, cloud, tgrid, eph).reshape(len(seeds), len(grid))
        widths, nblocks = [], []
        for i in range(len(seeds)):
            row = h[i]
            # 环形连续性: 拼接两遍以处理跨越 0/360 的团块
            ext = np.concatenate([row, row])
            best_run, run, blocks = 0, 0, 0
            for v in ext:
                if v:
                    run += 1; best_run = max(best_run, run)
                else:
                    if run > 0:
                        blocks += 1
                    run = 0
            widths.append(min(best_run, len(grid)) * step)
            nblocks.append(blocks)
        widths = np.array(widths)
        out[name] = dict(mean_width_deg=float(widths.mean()),
                         median_width_deg=float(np.median(widths)),
                         min_width_deg=float(widths.min()),
                         max_width_deg=float(widths.max()),
                         mean_blocks=float(np.mean(nblocks)),
                         widths=[float(x) for x in widths],
                         elapsed_s=float(time.time() - t0))
        log(f"  {name} 方向: 可行团块宽度 均值={widths.mean():5.1f}° 中位={np.median(widths):5.1f}° "
            f"[{widths.min():.0f}, {widths.max():.0f}]°, 平均团块数={np.mean(nblocks):.1f}  "
            f"({time.time()-t0:.1f}s)")
    return out


# ==================================================================== E4
def exp4_predictability(cloud, shapes, phases, hits, nuniq, ref):
    log("\n" + "=" * 72)
    log("E4 可预测性: 代理模型对三种标签的样本外表现")
    log("=" * 72)
    S, P = hits.shape
    # --- 标签定义 ---
    y_struct = hits.mean(axis=1)            # 形状层面: 可行相位占比 (聚合/光滑)
    y_agg = nuniq.mean(axis=1)              # 形状层面: 平均清除数 (聚合)
    y_exact = nuniq.max(axis=1)             # 形状层面: 最优清除数 (含极值, 难)
    X, keys = core.features(shapes, cloud, ref)
    X = X[:, np.all(np.isfinite(X), 0)]
    ntr = int(S * 0.7)
    idx = np.random.default_rng(0).permutation(S)
    tr, te = idx[:ntr], idx[ntr:]
    log(f"  特征维数 {X.shape[1]} (= {', '.join(keys)}), 训练 {len(tr)} / 测试 {len(te)}")
    res = {}
    for nm, y in (('可行相位占比', y_struct), ('平均清除数', y_agg), ('最优清除数', y_exact)):
        out = {}
        # 仅用形状坐标 (a,e,i,Om) 的 4 维输入, 作为对照
        X4 = X[:, :4] if X.shape[1] >= 4 else X
        for model_name, fn in (('常数基线', None), ('kNN', 'knn'), ('提升树', 'boost'), ('MLP集成', 'mlp')):
            if fn is None:
                pred = np.full(len(te), y[tr].mean())
            elif fn == 'knn':
                pred, _ = core.knn_predict(X[tr], y[tr], X[te], k=16)
            elif fn == 'boost':
                pred = core.FastBoost(n_est=250, lr=0.06, seed=1).fit(X[tr], y[tr]).predict(X[te])
            else:
                pred, _ = core.MLPEnsemble(M=3, H=64, epochs=180, seed=2).fit(X[tr], y[tr]).predict(X[te])
            out[model_name] = dict(r2=core.r2(y[te], pred),
                                   rho=core.spearman(y[te], pred),
                                   top1=core.topk_recall(y[te], pred, 0.01))
        log(f"  标签 = {nm:8s} | 常数 R²={out['常数基线']['r2']:+.3f} | "
            f"kNN R²={out['kNN']['r2']:+.3f} ρ={out['kNN']['rho']:+.3f} | "
            f"Boost R²={out['提升树']['r2']:+.3f} ρ={out['提升树']['rho']:+.3f} | "
            f"MLP R²={out['MLP集成']['r2']:+.3f} ρ={out['MLP集成']['rho']:+.3f}")
        res[nm] = out
    return res


# ==================================================================== E5
def exp5_budget(cloud, eph, n_pool=4000, budget=80, nw=12, nM=12, seed=3):
    """等仿真预算比较三种"把预算花在哪"的策略。
    预算 = budget × (nw·nM) 次候选-仿真; 三个策略相同。
    gate = 忽略相位的廉价几何量: 候选轨道与碎片云的最小"面内点集距离" (t=0 采样)。"""
    log("\n" + "=" * 72)
    log(f"E5 预算效率: 池 {n_pool}, 形状预算 {budget}, 每形状 {nw}×{nM} 相位")
    log("=" * 72)
    rng = np.random.default_rng(seed)
    pool = core.sample_full6(n_pool, rng, box=dict(a=(7050e3, 7400e3), e=(0.002, 0.055),
                                                   i=(97.4, 98.7), Om=(74.5, 77.5)))
    debk = eph[0][:, 0, :].astype(np.float64)      # 碎片 t=0 位置 (N,3)
    g = core.gate_score(pool, debk, nw=90)
    ph = core.phase_grid(nw, nM)
    tgrid = make_tgrid(dt=10.0)
    out = {'gate_quantiles': [float(np.quantile(g, q)) for q in (0.01, 0.5, 0.99)]}
    for nm, sel in (('随机采样', rng.choice(n_pool, budget, replace=False)),
                    ('gate筛选(最近云)', np.argsort(g)[:budget]),
                    ('gate反选(最远云)', np.argsort(g)[-budget:])):
        sh = pool[sel][:, :4]
        h, nu = scan(sh, ph, cloud, tgrid, eph)
        best_per = nu.max(1)
        out[nm] = dict(max_clear=int(nu.max()),
                       n_cand_with_hit=int((best_per > 0).sum()),
                       sum_uniq=int(best_per.sum()),
                       mean_best=float(best_per.mean()),
                       frac_feasible=float(h.mean()),
                       best_phases=int(h.sum()))
        log(f"  {nm:16s} 单候选最优清除={int(nu.max()):3d}  含可行相位候选="
            f"{int((best_per>0).sum()):3d}/{budget}  (shape,phase) 事件={int(h.sum()):5d}  "
            f"可行比例={h.mean()*100:.3f}%")
    return out


# ==================================================================== main
def main():
    full = '--full' in sys.argv
    stage, tag = 'all', 'dense'
    cloud_sd = dict(a_sd=40e3, e_sd=0.006, i_sd=0.12, Om_sd=0.25)
    for ar in sys.argv:
        if ar.startswith('--stage='):
            stage = ar.split('=', 1)[1]
        if ar.startswith('--tag='):
            tag = ar.split('=', 1)[1]
        if ar.startswith('--cloud='):
            parts = dict(p.split(':') for p in ar.split('=', 1)[1].split(','))
            cloud_sd = {k: float(v) for k, v in parts.items()}
    import os
    os.makedirs(tag, exist_ok=True)
    OUT = os.path.join(tag, "results.json")
    t_start = time.time()
    log("=" * 72)
    log(f"EXP-1  可学性分析   情形 = {tag}   云参数 = {cloud_sd}")
    log("前提: 赛题真实 345 碎片数据未公开, 使用与论文最终解一致的合成碎片云")
    log("=" * 72)
    cloud = make_cloud(n=345, seed=7, rng_center=cloud_sd)
    ref = (cloud[:, 0].mean(), cloud[:, 1].mean(), cloud[:, 2].mean(), cloud[:, 3].mean())
    log(f"碎片云: a={cloud[:,0].mean()/1e3:.1f}±{cloud[:,0].std()/1e3:.2f} km, "
        f"e={cloud[:,1].mean():.4f}±{cloud[:,1].std():.4f}, "
        f"i={np.rad2deg(cloud[:,2].mean()):.3f}±{np.rad2deg(cloud[:,2].std()):.3f}°, "
        f"Om={np.rad2deg(cloud[:,3].mean()):.3f}±{np.rad2deg(cloud[:,3].std()):.4f}°")
    tgrid = make_tgrid(dt=10.0)
    t0 = time.time()
    eph = build_ephemeris(cloud, tgrid)
    log(f"碎片细星历: {eph[0].shape}, 构建耗时 {time.time()-t0:.1f}s")

    results = {}
    rng = np.random.default_rng(11)
    n_shapes = (3000 if full else 800)
    shapes = core.sample_shapes(n_shapes, rng)
    nw = nM = 12

    hits_f = os.path.join(tag, "e2_hits.npy")
    if os.path.exists(hits_f) and stage != 'data':
        hp = np.load(hits_f)
        nu_arr = np.load(os.path.join(tag, "e2_nuniq.npy"))
        shapes = np.load(os.path.join(tag, "e2_shapes.npy"))
        log(f"载入已有主网格数据 {hits_f}  {hp.shape}")
    else:
        t0 = time.time()
        hp, nu_arr = scan(shapes, core.phase_grid(nw, nM), cloud, tgrid, eph)
        log(f"E2 主网格扫描耗时 {time.time()-t0:.1f}s")
        np.save(hits_f, hp)
        np.save(os.path.join(tag, "e2_nuniq.npy"), nu_arr)
        np.save(os.path.join(tag, "e2_shapes.npy"), shapes)

    results['E1'] = exp1_verification()
    results['E2'] = exp2_summarize(cloud, shapes, hp, nu_arr, tgrid, eph, tag=tag, cap=150)
    results['meta0'] = dict(tag=tag, cloud_sd=cloud_sd, shapes=int(len(shapes)),
                            nw=nw, nM=nM, T_window=T_WINDOW, dt_det=10.0)
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=float)
    log(f"\nE1+E2 完成, 耗时 {time.time()-t_start:.1f}s -> {OUT}")
    if stage in ('e2', 'data'):
        return

    good = np.flatnonzero(hp.any(axis=1))
    log(f"\n  可用作 E3 种子的形状数: {len(good)} / {len(shapes)}")
    results['E3'] = exp3_correlation(cloud, shapes, hp, eph, tag=tag) if len(good) >= 5 \
        else {'note': 'seed 不足'}
    results['E4'] = exp4_predictability(cloud, shapes, core.phase_grid(nw, nM),
                                        hp, nu_arr, ref)
    results['E5'] = exp5_budget(cloud, eph)
    results['meta'] = dict(cloud_n=int(len(cloud)), shapes=int(len(shapes)),
                           nw=nw, nM=nM, T_window=T_WINDOW,
                           tgrid_n=int(len(tgrid)), dt_det=10.0,
                           elapsed_s=time.time() - t_start)
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=float)
    log(f"\n全部完成, 总耗时 {time.time()-t_start:.1f}s -> {OUT}")


if __name__ == '__main__':
    main()
