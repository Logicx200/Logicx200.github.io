"""
物理内核: 赛题动力学模型 (第十五届全国大学生周培源力学竞赛 "空间轨道设计")

严格依据赛题:
  母航天器: 中心引力 + J2 摄动完整项, 瞬时脉冲
      r'' = -mu/r^3 * r + a_J2
      a_J2 = (3/2) J2 mu Re^2 / r^5 * [ (5 z^2/r^2 - 1) x,
                                        (5 z^2/r^2 - 1) y,
                                        (5 z^2/r^2 - 3) z ]
  碎片:     中心引力 + J2 一阶长期摄动 (根数漂移解析式)
      Omega(t) = Omega0 - (3/2) J2 (Re/p)^2 n cos i * (t - t0)
      omega(t) = omega0 + (3/4) J2 (Re/p)^2 n (5 cos^2 i - 1) * (t - t0)
      M(t)     = M0 + [ n + (3/4) J2 (Re/p)^2 n sqrt(1-e^2) (3 cos^2 i - 1) ] * (t - t0)
      a, e, i  常数;  p = a(1-e^2);  n = sqrt(mu/a^3)

常数取自赛题表 1 (J2 取 EGM96 常用值)。
"""
import numpy as np

MU = 3.986004418e14          # m^3/s^2
RE = 6378137.0               # m
J2 = 1.08262668e-3           # EGM96 (赛题: 从 EGM96 系数文件读取)
OMEGA_E = 7.2921151467e-5    # rad/s

T0 = 0.0                     # 碎片根数历元(相对训练窗口起点, s) —— 可调
T_WINDOW = 7200.0            # 训练窗口长度: 2 h (论文用 8 h/窗口, 这里为控制算力缩短)


# ---------------------------------------------------------------- 根数 -> 状态
def coe2rv(a, e, i, Om, w, M):
    """经典根数 -> 地心惯性系位置速度。a 单位 m; 角度 rad; 支持广播。"""
    a, e, i, Om, w, M = np.broadcast_arrays(
        np.asarray(a, float), np.asarray(e, float), np.asarray(i, float),
        np.asarray(Om, float), np.asarray(w, float), np.asarray(M, float))
    p = a * (1.0 - e * e)
    # Kepler 方程 (Mikkola 三次迭代, 对 e<1 稳健)
    E = M.copy()
    for _ in range(30):
        f = E - e * np.sin(E) - M
        fp = 1.0 - e * np.cos(E)
        d = -f / fp
        d = np.where(np.abs(d) > 1.0, np.sign(d) * 1.0, d)
        E = E + d
        if np.max(np.abs(d)) < 1e-12:
            break
    sE, cE = np.sin(E), np.cos(E)
    r = a * (1.0 - e * cE)
    nu = np.arctan2(np.sqrt(1.0 - e * e) * sE, cE - e)
    u = w + nu
    cu, su = np.cos(u), np.sin(u)
    cO, sO = np.cos(Om), np.sin(Om)
    ci, si = np.cos(i), np.sin(i)
    x = r * (cO * cu - sO * su * ci)
    y = r * (sO * cu + cO * su * ci)
    z = r * (su * si)
    h = np.sqrt(MU * p)
    vx = (-MU / h) * (cO * (su + e * np.sin(w)) + sO * (cu + e * np.cos(w)) * ci)
    vy = (-MU / h) * (sO * (su + e * np.sin(w)) - cO * (cu + e * np.cos(w)) * ci)
    vz = (MU / h) * (cu + e * np.cos(w)) * si
    return np.stack([x, y, z], -1), np.stack([vx, vy, vz], -1)


# ---------------------------------------------------------------- 动力学
KJ2 = 1.5 * J2 * MU * RE * RE


def rk4_step(x, h):
    """单步 RK4, 全部内联以避免中间数组分配 (x: (...,6))"""
    # k1
    x1, y1, z1 = x[..., 0], x[..., 1], x[..., 2]
    r2 = x1 * x1 + y1 * y1 + z1 * z1
    r = np.sqrt(r2)
    ir3 = 1.0 / (r2 * r)
    ir5 = ir3 / r2
    f = KJ2 * ir5
    zz = 5.0 * z1 * z1 / r2
    a1 = np.empty_like(x)
    a1[..., 0] = x[..., 3]
    a1[..., 1] = x[..., 4]
    a1[..., 2] = x[..., 5]
    a1[..., 3] = -MU * x1 * ir3 + f * (zz - 1.0) * x1
    a1[..., 4] = -MU * y1 * ir3 + f * (zz - 1.0) * y1
    a1[..., 5] = -MU * z1 * ir3 + f * (zz - 3.0) * z1

    # k2
    u = x + (0.5 * h) * a1
    x1, y1, z1 = u[..., 0], u[..., 1], u[..., 2]
    r2 = x1 * x1 + y1 * y1 + z1 * z1
    r = np.sqrt(r2); ir3 = 1.0 / (r2 * r); ir5 = ir3 / r2
    f = KJ2 * ir5; zz = 5.0 * z1 * z1 / r2
    a2 = np.empty_like(x)
    a2[..., 0] = u[..., 3]
    a2[..., 1] = u[..., 4]
    a2[..., 2] = u[..., 5]
    a2[..., 3] = -MU * x1 * ir3 + f * (zz - 1.0) * x1
    a2[..., 4] = -MU * y1 * ir3 + f * (zz - 1.0) * y1
    a2[..., 5] = -MU * z1 * ir3 + f * (zz - 3.0) * z1

    # k3
    u = x + (0.5 * h) * a2
    x1, y1, z1 = u[..., 0], u[..., 1], u[..., 2]
    r2 = x1 * x1 + y1 * y1 + z1 * z1
    r = np.sqrt(r2); ir3 = 1.0 / (r2 * r); ir5 = ir3 / r2
    f = KJ2 * ir5; zz = 5.0 * z1 * z1 / r2
    a3 = np.empty_like(x)
    a3[..., 0] = u[..., 3]
    a3[..., 1] = u[..., 4]
    a3[..., 2] = u[..., 5]
    a3[..., 3] = -MU * x1 * ir3 + f * (zz - 1.0) * x1
    a3[..., 4] = -MU * y1 * ir3 + f * (zz - 1.0) * y1
    a3[..., 5] = -MU * z1 * ir3 + f * (zz - 3.0) * z1

    # k4
    u = x + h * a3
    x1, y1, z1 = u[..., 0], u[..., 1], u[..., 2]
    r2 = x1 * x1 + y1 * y1 + z1 * z1
    r = np.sqrt(r2); ir3 = 1.0 / (r2 * r); ir5 = ir3 / r2
    f = KJ2 * ir5; zz = 5.0 * z1 * z1 / r2
    a4 = np.empty_like(x)
    a4[..., 0] = u[..., 3]
    a4[..., 1] = u[..., 4]
    a4[..., 2] = u[..., 5]
    a4[..., 3] = -MU * x1 * ir3 + f * (zz - 1.0) * x1
    a4[..., 4] = -MU * y1 * ir3 + f * (zz - 1.0) * y1
    a4[..., 5] = -MU * z1 * ir3 + f * (zz - 3.0) * z1

    return x + (h / 6.0) * (a1 + 2.0 * a2 + 2.0 * a3 + a4)


def propagate(x0, T, dt, n_out):
    """从 x0 (...,6) 定步长 RK4 推进 T 秒, 输出 n_out 个等间距状态 (含 t=0)。
    要求 (T/dt) 为 n_out-1 的整数倍。返回 (n_out, ..., 6)。"""
    per = int(round(T / dt / (n_out - 1)))
    assert abs(per * (n_out - 1) * dt - T) < 1e-6 * max(1.0, T), "T/dt 与 n_out 不匹配"
    out = [x0.copy()]
    x = x0
    for _ in range(n_out - 1):
        for _ in range(per):
            x = rk4_step(x, dt)
        out.append(x.copy())
    return np.stack(out, 0)


# ---------------------------------------------------------------- 碎片长期摄动
def debris_rates(a, e, i):
    """返回 (dOm, dw, dM) 长期变化率 rad/s"""
    p = a * (1.0 - e * e)
    n = np.sqrt(MU / a ** 3)
    k = J2 * (RE / p) ** 2 * n
    ci = np.cos(i)
    dOm = -1.5 * k * ci
    dw = 0.75 * k * (5.0 * ci ** 2 - 1.0)
    dM = n + 0.75 * k * np.sqrt(1.0 - e * e) * (3.0 * ci ** 2 - 1.0)
    return dOm, dw, dM


def debris_states(oe0, tgrid):
    """oe0 = (a,e,i,Om,w,M) 数组, 形状 (N,6); tgrid 形状 (T,)。
    返回 pos (N,T,3), vel (N,T,3)"""
    a, e, i, Om, w, M = [np.asarray(oe0[:, k], float) for k in range(6)]
    dOm, dw, dM = debris_rates(a, e, i)
    dt = tgrid[None, :] - T0
    Om_t = Om[:, None] + dOm[:, None] * dt
    w_t = w[:, None] + dw[:, None] * dt
    M_t = M[:, None] + dM[:, None] * dt
    A = np.broadcast_to(a[:, None], M_t.shape)
    E = np.broadcast_to(e[:, None], M_t.shape)
    I = np.broadcast_to(i[:, None], M_t.shape)
    pos, vel = coe2rv(A, E, I, Om_t, w_t, M_t)
    return pos, vel


# ---------------------------------------------------------------- 清除判定
def encounters(sc_pos, sc_vel, deb_pos, deb_vel, dr_max=30e3, dv_max=150.0):
    """sc_pos (T,3), deb_pos (N,T,3) -> 被清除碎片编号(按首次接近去重)"""
    d = deb_pos - sc_pos[None, :, :]
    dist = np.sqrt(np.einsum('ntk,ntk->nt', d, d))
    v = deb_vel - sc_vel[None, :, :]
    relv = np.sqrt(np.einsum('ntk,ntk->nt', v, v))
    hit = (dist < dr_max) & (relv < dv_max)
    idx = np.flatnonzero(hit.any(axis=1))
    return idx
