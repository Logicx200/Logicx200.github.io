"""
lidar_sim.py —— 最小可运行的激光雷达点云仿真库（只依赖 numpy）。

包含：
  1. 场景：地面(GroundPlane) + 若干轴对齐包围盒(AABB)，每个面有朗伯反射率
  2. 射线求交：ray-AABB slab 法 + 无限平面求交，numpy 向量化
  3. 光束足迹：每个扫描方向用 (beam_sub × beam_sub) 束子射线模拟有限发散角
  4. 混合像素：子射线命中不同距离的面 → 功率加权平均距离（"边缘悬浮点"）
  5. 测距噪声：σ_R = σ0 + k·R（远端信噪比低、噪声更大）
  6. 强度 / 丢点：反射率 × 入射角余弦 × 1/R² × 斑点，过低即丢点

坐标约定：
  x —— 右，y —— 上（高度），z —— 前方
  传感器默认原点 (0, 2, 0)，朝 +z 看。
  扫描方向由 (方位角 yaw θ, 俯仰角 pitch φ) 决定：
      D = (sinθ·cosφ,  sinφ,  cosθ·cosφ)
"""

import numpy as np


class AABB:
    """轴对齐包围盒（长方体）。lo/hi 为两个对角顶点，reflectance 为朗伯反射率 0~1。"""

    def __init__(self, lo, hi, reflectance=0.5):
        self.lo = np.asarray(lo, dtype=float)
        self.hi = np.asarray(hi, dtype=float)
        self.reflectance = float(reflectance)


class GroundPlane:
    """无限大水平地面 y = y0。"""

    def __init__(self, y=0.0, reflectance=0.3):
        self.y = float(y)
        self.reflectance = float(reflectance)


class LidarSensor:
    """二维光栅扫描式激光雷达的参数化模型（MEMS / 转镜式）。

    参数：
      origin       传感器位置 (x, y, z)
      yaw_fov      方位角范围（度），左右
      pitch_fov    俯仰角范围（度），下/上
      H, V         水平 / 垂直采样点数
      beam_div     光束全发散角（弧度），决定光斑随距离膨胀的速率
      max_range    最大量程（米）
      range_noise  (σ0, k)：测距噪声 σ_R = σ0 + k·R
      speckle      斑点噪声强度（对数正态的 σ）
      min_intensity 低于此强度判为丢点
    """

    def __init__(self,
                 origin=(0.0, 2.0, 0.0),
                 yaw_fov=(-35.0, 35.0),
                 pitch_fov=(-25.0, 5.0),
                 H=240, V=120,
                 beam_div=6e-3,
                 max_range=40.0,
                 range_noise=(0.01, 0.002),
                 speckle=0.35,
                 min_intensity=0.02):
        self.origin = np.asarray(origin, dtype=float)
        self.yaw_fov = tuple(yaw_fov)
        self.pitch_fov = tuple(pitch_fov)
        self.H = int(H)
        self.V = int(V)
        self.beam_div = float(beam_div)
        self.max_range = float(max_range)
        self.range_noise = tuple(range_noise)
        self.speckle = float(speckle)
        self.min_intensity = float(min_intensity)

    def _base_angles(self):
        """返回 (Y, P) 网格，形状 (V, H)，单位弧度。"""
        yaw = np.radians(np.linspace(*self.yaw_fov, self.H))
        pitch = np.radians(np.linspace(*self.pitch_fov, self.V))
        return np.meshgrid(yaw, pitch)

    @staticmethod
    def directions_from(Y, P):
        """由 (yaw, pitch) 角网格构造单位方向向量。形状 (V, H, 3)。"""
        dx = np.sin(Y) * np.cos(P)
        dy = np.sin(P)
        dz = np.cos(Y) * np.cos(P)
        return np.stack([dx, dy, dz], axis=-1)


# ---------------------------------------------------------------------------
# 射线求交
# ---------------------------------------------------------------------------

def ray_box_hit(origin, d, box):
    """向量化 ray-AABB 求交（slab 法）。

    origin: (3,)
    d:      (..., 3)  任意前缀形状的射线方向
    box:    AABB
    返回 (t, hit, normal, reflectance)，t/hit 带前缀形状 (...,)，normal 带 (..., 3)。
    """
    shape = d.shape[:-1]
    dflat = d.reshape(-1, 3)
    n = dflat.shape[0]
    lo, hi = box.lo, box.hi
    with np.errstate(divide='ignore', invalid='ignore'):
        inv = np.where(np.abs(dflat) > 1e-12, 1.0 / dflat, np.inf)

    t1 = (lo - origin) * inv
    t2 = (hi - origin) * inv
    tnear = np.minimum(t1, t2)          # 每条射线对每根轴的“进入参数”
    tfar = np.maximum(t1, t2)           # “离开参数”
    t_enter = tnear.max(axis=1)
    t_exit = tfar.min(axis=1)

    hit = (t_enter <= t_exit) & (t_exit > 0.0)
    t = np.where(t_enter > 0.0, t_enter, t_exit)

    # 入射面的法线：进入参数最大的那根轴就是被击中的面
    axis = tnear.argmax(axis=1)
    normal = np.zeros_like(dflat)
    normal[np.arange(n), axis] = -np.sign(dflat[np.arange(n), axis])

    return (t.reshape(shape), hit.reshape(shape),
            normal.reshape(d.shape), box.reflectance)


def ray_ground_hit(origin, d, plane):
    """向量化无限平面（y = y0）求交。"""
    dflat = d.reshape(-1, 3)
    dy = dflat[:, 1]
    with np.errstate(divide='ignore', invalid='ignore'):
        t = (plane.y - origin[1]) / dy
    hit = (dy < -1e-9) & (t > 0.0)
    normal = np.zeros_like(dflat)
    normal[:, 1] = 1.0
    return (t.reshape(d.shape[:-1]), hit.reshape(d.shape[:-1]),
            normal.reshape(d.shape), plane.reflectance)


def cast_scene(origin, d, objects):
    """对一组射线求最近命中面，返回 (距离, 法线, 反射率)。未命中 → 距离 inf。"""
    shape = d.shape[:-1]
    t_best = np.full(shape, np.inf)
    n_best = np.zeros_like(d)
    rho_best = np.zeros(shape)
    for obj in objects:
        if isinstance(obj, GroundPlane):
            t, hit, n, rho = ray_ground_hit(origin, d, obj)
        else:
            t, hit, n, rho = ray_box_hit(origin, d, obj)
        better = hit & (t < t_best)
        t_best = np.where(better, t, t_best)
        n_best = np.where(better[..., None], n, n_best)
        rho_best = np.where(better, rho, rho_best)
    return t_best, n_best, rho_best


# ---------------------------------------------------------------------------
# 单帧仿真
# ---------------------------------------------------------------------------

def simulate_frame(sensor, objects, seed=0, beam_sub=5, mixed_threshold=0.5):
    """仿真一帧点云。

    流程：
      1. 每个主扫描方向，用 (beam_sub × beam_sub) 束子射线模拟有限光束足迹
      2. 子射线命中距离的极差 > mixed_threshold → 判为混合像素，
         取“功率加权平均距离”（这正是真实雷达边缘悬浮点的来源）
      3. 距离加高斯噪声 σ = σ0 + k·R
      4. 强度 = 反射率 × cos(入射角) × (R_ref/R)² × 斑点
      5. 强度过低 / 超量程 / 无命中 → 丢点

    返回 dict：
      points        (N, 3)   世界坐标
      intensity     (N,)     强度（已含斑点，用于着色）
      range         (N,)     含噪声的距离
      is_mixed      (N,)     bool，是否混合像素
      range_image   (V, H)   距离图（丢点为 nan）
      intensity_image (V, H) 强度图（丢点为 nan）
      stats         dict     统计信息
    """
    rng = np.random.default_rng(seed)
    origin = sensor.origin
    H, V = sensor.H, sensor.V

    # ---- 主方向 + 光束子采样偏移 ----
    Y0, P0 = sensor._base_angles()
    d_main = sensor.directions_from(Y0, P0)          # (V, H, 3)
    half = sensor.beam_div / 2.0   # beam_div 已经是弧度，不要再转 np.radians
    offsets = np.linspace(-1.0, 1.0, beam_sub) * 0.85  # 子射线落在光束圆盘内

    t_all = np.zeros((V, H, beam_sub, beam_sub))
    n_all = np.zeros((V, H, beam_sub, beam_sub, 3))
    rho_all = np.zeros((V, H, beam_sub, beam_sub))

    for i, sx in enumerate(offsets):
        for j, sy in enumerate(offsets):
            Y = Y0 + half * sx
            P = P0 + half * sy
            d_sub = sensor.directions_from(Y, P)
            t, n, rho = cast_scene(origin, d_sub, objects)
            t_all[:, :, i, j] = t
            n_all[:, :, i, j, :] = n
            rho_all[:, :, i, j] = rho

    hit_any = np.isfinite(t_all)                       # (V, H, s, s)
    valid_count = hit_any.sum(axis=(2, 3))             # (V, H)

    # ---- 子射线“功率”：反射率 × cos入射 × 1/R² ----
    cos_inc = np.clip(-np.einsum('vhijk,vhijk->vhij', n_all,
                                 d_main[..., None, None, :]), 0.0, 1.0)
    power = np.where(hit_any, rho_all * cos_inc / np.clip(t_all ** 2, 0.05, None), 0.0)

    S = beam_sub * beam_sub
    power_flat = power.reshape(V, H, S)
    t_flat = t_all.reshape(V, H, S)
    n_flat = n_all.reshape(V, H, S, 3)
    rho_flat = rho_all.reshape(V, H, S)
    hit_flat = hit_any.reshape(V, H, S)

    sum_power = power_flat.sum(axis=-1)                # (V, H)
    # 功率加权平均距离（混合像素 = 这里取到两面之间的中间值）
    # 注意：未命中的子射线 t=inf 而 power=0，直接相乘会得到 nan，
    # 所以先把未命中距离置 0（其对功率的贡献本来就是 0）。
    t_flat_safe = np.where(hit_flat, t_flat, 0.0)
    t_centroid = np.where(
        sum_power > 0.0,
        (power_flat * t_flat_safe).sum(axis=-1) / np.clip(sum_power, 1e-9, None),
        np.inf)

    # 命中距离极差 → 是否混合像素
    t_for_min = np.where(hit_any, t_all, np.inf)
    t_for_max = np.where(hit_any, t_all, -np.inf)
    t_min = t_for_min.min(axis=(2, 3))
    t_max = t_for_max.max(axis=(2, 3))
    spread = np.where(valid_count > 0, t_max - t_min, 0.0)
    is_mixed = (valid_count >= 2) & (spread > mixed_threshold)

    # ---- 主命中的法线 / 反射率（取功率最大的子射线）----
    kmax = np.argmax(power_flat, axis=-1)              # (V, H)
    ii, jj = np.indices((V, H))
    n_dom = n_flat[ii, jj, kmax, :]                    # (V, H, 3)
    rho_dom = rho_flat[ii, jj, kmax]

    # ---- 测距噪声：σ = σ0 + k·R（只对有效距离加噪声，避免 inf 传播）----
    R = np.where(sum_power > 0.0, t_centroid, np.inf)
    finite = np.isfinite(R)
    sigma = np.where(finite, sensor.range_noise[0] + sensor.range_noise[1] * R, 0.0)
    R = np.where(finite, R + rng.normal(0.0, sigma), np.inf)

    # ---- 强度：反射率 × cos入射 × (R_ref/R)² × 斑点 ----
    cos_dom = np.clip(-np.einsum('vhi,vhi->vh', n_dom, d_main), 0.0, 1.0)
    R_ref = 10.0
    I = rho_dom * cos_dom * (R_ref ** 2 / np.clip(R, 0.2, None) ** 2)
    speckle = np.exp(sensor.speckle * rng.standard_normal((V, H))
                     - 0.5 * sensor.speckle ** 2)     # 对数正态，均值 ≈ 1
    I = I * speckle

    # ---- 丢点：无命中 / 超量程 / 强度过低 ----
    keep = (sum_power > 0.0) & (R <= sensor.max_range) & (I >= sensor.min_intensity)

    points = origin + d_main * R[..., None]           # (V, H, 3)
    R_img = np.where(keep, R, np.nan)
    I_img = np.where(keep, I, np.nan)

    flat = {
        'points': points[keep],
        'intensity': I[keep],
        'range': R[keep],
        'is_mixed': is_mixed[keep],
    }

    stats = {
        'total_rays': H * V,
        'hits': int(keep.sum()),
        'dropouts': int((~keep).sum()),
        'mixed_pixels': int(flat['is_mixed'].sum()),
        'mean_range': float(np.nanmean(R_img)),
    }

    return {
        **flat,
        'range_image': R_img,
        'intensity_image': I_img,
        'stats': stats,
    }
