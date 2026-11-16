# -*- coding: utf-8 -*-
"""第七 ~ 第九章 应用光学：几何光学基础、理想光学系统、像差与光路计算。

覆盖考点：
    * 符号规则、折射/反射球面近轴物像关系、平板与棱镜
    * 理想光学系统的基点基面、图解法与解析法、双光组/多光组组合
    * 近轴光路计算（y-nu 递推）、子午面内实际光线计算、球差
    * 孔径光阑 / 视场光阑 / 入射光瞳 / 出射光瞳 / 入射窗 / 出射窗

**符号规则（郁道银《工程光学》体系）**：
    光线自左向右传播；l 由球面顶点算起，向右为正，向左为负；
    高度 y 在光轴上方为正；角度 u 由光轴转到光线，顺时针为正。
    近轴公式：  n'/l' - n/l = (n' - n)/r ，  垂轴放大率 beta = n l' / (n' l)
"""
from __future__ import annotations

import numpy as np

# ---------------------------------------------------------------- 近轴公式


def gauss_image(u, f):
    """高中式高斯成像公式 1/v + 1/u = 1/f（u、v 均为正值，物在左像在右）。

    返回像距 v；v < 0 表示虚像（在同侧）。u 可为数组。
    """
    u = np.asarray(u, dtype=float)
    f = np.asarray(f, dtype=float)
    denom = 1.0 / f - 1.0 / u
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(np.abs(denom) < 1e-15, np.inf, 1.0 / np.where(denom == 0, 1.0, denom))


def gauss_image_signed(l: float, f: float) -> float:
    """工程光学符号规则：1/l' - 1/l = 1/f'（实物 l < 0，实像 l' > 0）。"""
    return 1.0 / (1.0 / f + 1.0 / l)


def transverse_magnification(l: float, l_prime: float, n: float = 1.0, n_prime: float = 1.0):
    """垂轴放大率 beta = n l' / (n' l)。beta < 0 表示倒立。"""
    return n * l_prime / (n_prime * l)


def axial_magnification(beta: float, n: float = 1.0, n_prime: float = 1.0):
    """轴向放大率 alpha = beta^2 * n' / n。"""
    return beta ** 2 * n_prime / n


def angular_magnification(beta: float, n: float = 1.0, n_prime: float = 1.0):
    """角放大率 gamma = 1/beta * n / n'... 由拉赫不变量 gamma = n/(n' beta)。"""
    return n / (n_prime * beta)


def newton_formula(x: float, f: float) -> float:
    """牛顿公式 x x' = f f'；返回 x'。"""
    return f ** 2 / x


def refraction_sphere(l: float, r: float, n: float, n_prime: float):
    """单个折射球面近轴成像：返回 (l', beta)。

    由 n'/l' - n/l = (n' - n)/r 解出 l' = n' / [(n'-n)/r + n/l]。
    """
    l_prime = n_prime / ((n_prime - n) / r + n / l)
    beta = n * l_prime / (n_prime * l)
    return l_prime, beta


def mirror_image(l: float, r: float) -> float:
    """球面镜成像 1/l' + 1/l = 2/r（l、l' 均在镜前为正），返回 l'。"""
    return 1.0 / (2.0 / r - 1.0 / l)


def mirror_focal_length(r: float) -> float:
    """球面镜焦距 f = r/2（凹面镜 r > 0）。"""
    return r / 2.0


def plane_plate_displacement(d: float, n: float, u1: float) -> float:
    """平行平板侧向位移：Delta = d sin(u1 - u1') / cos(u1')。"""
    u1p = np.arcsin(np.sin(u1) / n)
    return d * np.sin(u1 - u1p) / np.cos(u1p)


def plane_plate_axial_shift(d: float, n: float) -> float:
    """垂直入射时平行平板引起的轴向位移 Delta l' = d (1 - 1/n)。"""
    return d * (1.0 - 1.0 / n)


# ---------------------------------------------------------------- 近轴光路计算
def paraxial_trace(surfaces, y1: float, u1: float, n_start: float = 1.0):
    """共轴球面系统的近轴光路计算（y-u 递推），对应“子午面近轴光路计算”。

    surfaces : [dict(r=..., d=..., n=...), ...]
        r : 球面半径（球心在顶点右侧为正，平面用 np.inf）
        d : 该面顶点到下一面顶点的距离（最后一面可省略 d）
        n : **该面之后**的介质折射率
    y1, u1   : 入射光线在第一个面上的高度与物方孔径角
    n_start  : 第一个面之前的介质折射率

    递推关系： n' u' = n u - y (n' - n)/r ； y_{k+1} = y_k + d_k u'_k
    返回 list[dict]，逐面给出 (y, u, u_after, n, n_after)。
    """
    out = []
    y, u, n = float(y1), float(u1), float(n_start)
    for s in surfaces:
        r, n2 = s.get("r", np.inf), s["n"]
        u2 = u if np.isinf(r) else (n * u - y * (n2 - n) / r) / n2
        out.append(dict(r=r, y=y, u=u, u_after=u2, n=n, n_after=n2, d=s.get("d", 0.0)))
        n = n2
        u = u2
        if "d" in s:
            y = y + s["d"] * u2
    return out


def refract_sphere_real(h: float, u: float, r: float, n1: float, n2: float):
    """子午面内**实际光线**在单个折射球面上的折射（非近轴，用于算球差）。

    参数：h 入射高度（相对于球面顶点处的光轴）、u 入射角（弧度）、
          r 球面半径（球心在 z=r 处）、n1 入射介质、n2 出射介质。
    返回 dict(z, y, u_out) 或 None（全反射 / 光线不与球面相交）。
    """
    tu = np.tan(u)
    A = 1.0 + tu ** 2
    B = 2.0 * h * tu - 2.0 * r
    C = h ** 2
    disc = B ** 2 - 4.0 * A * C
    if disc < 0:
        return None
    z1 = (-B - np.sqrt(disc)) / (2.0 * A)  # 靠近顶点的那个交点
    y1 = h + tu * z1
    # 出射面法线（由球心指向入射点）
    N = np.array([(z1 - r), y1]) / abs(r)
    d = np.array([np.cos(u), np.sin(u)])
    if np.dot(d, N) > 0:  # 让法线朝向入射侧
        N = -N
    c_i = float(-np.dot(d, N))
    mu = n1 / n2
    s2 = 1.0 - mu ** 2 * (1.0 - c_i ** 2)
    if s2 < 0:
        return None  # 发生全反射
    c_t = np.sqrt(s2)
    t = mu * d + (mu * c_i - c_t) * N
    u_out = float(np.arctan2(t[1], t[0]))
    return dict(z=z1, y=y1, u_out=u_out, cos_i=c_i)


def spherical_aberration_focus(h: float, r: float, n1: float, n2: float):
    """平行光（u=0）在高度 h 入射单折射面后与光轴的交点到顶点的距离。

    与近轴像距 l'_par = n2 r / (n2 - n1) 之差即**轴向球差**。
    """
    res = refract_sphere_real(h, 0.0, r, n1, n2)
    if res is None:
        return np.nan
    z1, y1, u2 = res["z"], res["y"], res["u_out"]
    if abs(np.tan(u2)) < 1e-15:
        return np.inf
    return z1 - y1 / np.tan(u2)


def paraxial_focus_sphere(r: float, n1: float, n2: float) -> float:
    """物在无穷远时单折射面的近轴像距 l' = n2 r / (n2 - n1)。"""
    return n2 * r / (n2 - n1)


def longitudinal_spherical_aberration(h, r: float, n1: float, n2: float):
    """轴向球差 delta L' = l'_h - l'_par（<0 表示边缘光线交点在近轴焦点之前）。"""
    l_par = paraxial_focus_sphere(r, n1, n2)
    return np.array([spherical_aberration_focus(hh, r, n1, n2) for hh in np.atleast_1d(h)]) - l_par


# ---------------------------------------------------------------- 近轴矩阵（ABCD）
def transfer_matrix(d: float) -> np.ndarray:
    """间隔 d 的传播矩阵（[y, u] 约定，u 为真实角度）。"""
    return np.array([[1.0, d], [0.0, 1.0]])


def refract_matrix(r: float, n1: float, n2: float) -> np.ndarray:
    """球面折射矩阵：u' = (n1/n2) u - y (n2-n1)/(n2 r)。r = inf 表示平面。"""
    if np.isinf(r):
        return np.array([[1.0, 0.0], [0.0, n1 / n2]])
    return np.array([[1.0, 0.0], [-(n2 - n1) / (n2 * r), n1 / n2]])


def thin_lens_matrix(f: float) -> np.ndarray:
    """薄透镜矩阵 u' = u - y/f。"""
    return np.array([[1.0, 0.0], [-1.0 / f, 1.0]])


class ParaxialSystem:
    """共轴系统的近轴矩阵模型，用于成像、基点和光阑分析。

    elements 为字典列表，按光传播顺序给出：
        {"type": "gap",     "d": 距离}
        {"type": "refract", "R": 半径, "n_after": 折射率, "semi": 半口径}
        {"type": "lens",    "f": 焦距, "semi": 半口径}
        {"type": "stop",    "semi": 半口径}          # 薄光阑（不改变光线的零功率面）
    n_start 为入射介质折射率。若物不在第一个面上，请在列表最前面加一个 gap。
    """

    def __init__(self, elements, n_start: float = 1.0):
        self.elements = [dict(e) for e in elements]
        self.n_start = float(n_start)

    # -- 基础 --------------------------------------------------------
    def _step(self, M, n, e):
        t = e["type"]
        if t == "gap":
            return transfer_matrix(e["d"]) @ M, n
        if t == "stop":
            return M, n
        if t == "refract":
            n2 = e.get("n_after", n)
            return refract_matrix(e.get("R", np.inf), n, n2) @ M, n2
        if t == "lens":
            return thin_lens_matrix(e["f"]) @ M, n
        raise ValueError(f"未知元件类型: {t}")

    def matrix(self, upto: int | None = None, n_start: float | None = None):
        """返回 (M, n_out)。upto 为元件个数（从左起前 upto 个），None 表示全部。"""
        elems = self.elements if upto is None else self.elements[:upto]
        M = np.eye(2)
        n = self.n_start if n_start is None else n_start
        for e in elems:
            M, n = self._step(M, n, e)
        return M, n

    # -- 成像 --------------------------------------------------------
    def trace_ray(self, y0: float, u0: float):
        """从物面出发追迹一条近轴光线。

        返回 [(z, y, u, index或None), ...]：z 为自物面起算的累计轴向距离；
        index 为该点所在元件的索引（gap 的终点记为下一个元件的平面）。
        """
        M, n, z = np.eye(2), self.n_start, 0.0
        pts = [(0.0, float(y0), float(u0), None)]
        for i, e in enumerate(self.elements):
            if e["type"] == "gap":
                z += e["d"]
                M, n = self._step(M, n, e)
                continue
            M, n = self._step(M, n, e)
            pts.append((z, float(M[0, 0] * y0 + M[0, 1] * u0),
                        float(M[1, 0] * y0 + M[1, 1] * u0), i))
        return pts

    def plane_positions(self):
        """返回 [(z, index), ...]，给出每个非 gap 元件所在平面的轴向位置。"""
        z, out = 0.0, []
        for i, e in enumerate(self.elements):
            if e["type"] == "gap":
                z += e["d"]
            else:
                out.append((z, i))
        return out

    def image_plane(self, n_end_back: float | None = None):
        """在系统之后追加大气间隔，使 B = 0，返回 (像距, 总矩阵, 放大率)。

        像距为相对最后一个元件所在平面的距离；放大率 beta = det(M)/D。
        """
        M, n = self.matrix()
        if abs(M[1, 1]) < 1e-15:
            return np.nan, M, np.nan
        t = -M[0, 1] / M[1, 1]
        Mt = transfer_matrix(t) @ M
        beta = Mt[0, 0]
        return float(t), Mt, float(beta)

    def effective_focal_length(self):
        """系统的像方有效焦距 f' = -1/C（对单折射面即 f' = n' r /(n' - n)）。"""
        M, _ = self.matrix()
        return float(-1.0 / M[1, 0])

    def back_focal_distance(self):
        """像方焦点到最后一个面的距离 l_F' = -A/C（沿 +z 测量）。"""
        M, _ = self.matrix()
        return float(-M[0, 0] / M[1, 0])

    def front_focal_distance(self):
        """物方焦点到第一个面的距离 l_F = -D/C。

        本函数返回“向左为正”的距离：正值表示焦点位于第一个面之前。
        """
        M, _ = self.matrix()
        return float(-M[1, 1] / M[1, 0])

    # -- 光阑 --------------------------------------------------------
    def apertures(self):
        """返回 [(元件索引, 累计矩阵, 半口径, 累计折射率 n), ...]（只含有 semi 的元件）。

        累计矩阵自物面（系统起点）算到该元件所在平面，因此矩阵元素
        B 就是“物方孔径角 u 到该面上入射高度 y”的传递系数。
        """
        res, M, n = [], np.eye(2), self.n_start
        for i, e in enumerate(self.elements):
            M, n = self._step(M, n, e)
            if e.get("semi") is not None:
                res.append((i, M.copy(), float(e["semi"]), n))
            elif e["type"] == "refract":
                pass
        return res

    def aperture_stop(self, n_object: float | None = None):
        """确定孔径光阑。

        判据：物方孔径角 u_i = (D_i / 2) / B_i，其中 B_i 是把各光阑
        计入前面系统的累计矩阵元素（入射高度 y_i = B_i u_0）。
        u_i 最小（入射光束最先被拦住）者即孔径光阑。
        返回 (元件索引, 各光阑数据列表)。
        """
        data = []
        for i, M, semi, n in self.apertures():
            B = M[0, 1]
            u = semi / abs(B) if abs(B) > 1e-15 else np.inf
            data.append(dict(index=i, semi=semi, u_object=u, M=M))
        idx = int(np.argmin([d["u_object"] for d in data]))
        return data[idx]["index"], data

    def entrance_pupil(self):
        """入射光瞳：孔径光阑被其**前面**系统所成的像。

        返回 dict(index, position, diameter, magnification)。
        position 以系统第一个元件所在平面为原点，向左（物方）为正。
        """
        stop, _ = self.aperture_stop()
        sub = ParaxialSystem(self.elements[:stop], self.n_start)
        M, n_s = sub.matrix()
        if M[0, 0] == 0 and M[0, 1] == 0:
            return dict(index=stop, position=0.0, diameter=2 * self._semi(stop), magnification=1.0)
        det = float(np.linalg.det(M))
        M_rev = (1.0 / det) * np.array([[M[1, 1], M[0, 1]], [M[1, 0], M[0, 0]]])
        t = -M_rev[0, 1] / M_rev[1, 1] if abs(M_rev[1, 1]) > 1e-15 else np.inf
        beta = float(np.linalg.det(M_rev) / M_rev[1, 1]) if abs(M_rev[1, 1]) > 1e-15 else np.inf
        return dict(index=stop, position=float(t), diameter=2 * self._semi(stop) * abs(beta),
                    magnification=float(beta))

    def exit_pupil(self):
        """出射光瞳：孔径光阑被其**后面**系统所成的像。

        position 以最后一个元件所在平面为原点，向右（像方）为正。
        """
        stop, _ = self.aperture_stop()
        _, n_after_stop = self.matrix(upto=stop + 1)
        M = np.eye(2)
        n = n_after_stop
        for e in self.elements[stop + 1:]:
            M, n = self._step(M, n, e)
        if abs(M[1, 1]) > 1e-15:
            t = -M[0, 1] / M[1, 1]
            beta = float(np.linalg.det(M) / M[1, 1])
        else:
            t, beta = np.inf, np.nan
        return dict(index=stop, position=float(t), diameter=2 * self._semi(stop) * abs(beta),
                    magnification=float(beta))

    def field_stop(self):
        """视场光阑：用主光线（过入射光瞳中心）判据求和。

        主光线过光阑中心，在元件 i 上的高度 y_i = y0 (A_i - B_i A_s / B_s)，
        限制 y0 最小者即视场光阑。返回 (元件索引, 数据列表)。
        """
        stop, _ = self.aperture_stop()
        Ms, _ = self.matrix(upto=stop + 1)  # 注意：矩阵到光阑所在面
        As, Bs = Ms[0, 0], Ms[0, 1]
        if abs(Bs) < 1e-15:
            return stop, []
        data = []
        for i, M, semi, n in self.apertures():
            if i == stop:
                continue
            k = M[0, 0] - M[0, 1] * As / Bs
            y0 = semi / abs(k) if abs(k) > 1e-15 else np.inf
            data.append(dict(index=i, semi=semi, object_height=y0))
        if not data:
            return None, data
        idx = int(np.argmin([d["object_height"] for d in data]))
        return data[idx]["index"], data

    def _semi(self, idx: int) -> float:
        s = self.elements[idx].get("semi")
        return 0.0 if s is None else float(s)


# ---------------------------------------------------------------- 双光组组合
def two_lens_combination(f1: float, f2: float, d: float):
    """双光组（空气中薄透镜）组合公式。

    取正值焦距 F1、F2，光学间隔 Delta = d - F1 - F2（工程光学里写作
    Delta = d - f1' + f2，其中 f2 是第二光组的物方焦距，f2 = -F2）。

        f' = -F1 F2 / Delta
        l_F' = f' (1 - d/F1)     后焦点到第二光组的距离（沿 +z）
        l_F  = f' (1 - d/F2)     前焦点到第一光组的距离（向左为正）

    返回 dict(f, lF, lFp, delta, f1, f2, d)。
    """
    delta = d - f1 - f2
    f = -f1 * f2 / delta if delta != 0 else np.inf
    lFp = f * (1.0 - d / f1)   # 像方焦点位置（相对第二光组）
    lF = f * (1.0 - d / f2)    # 物方焦点位置（相对第一光组，向左为正）
    return dict(f=f, lF=lF, lFp=lFp, delta=delta, f1=f1, f2=f2, d=d)


def two_lens_combination_from_matrix(f1: float, f2: float, d: float):
    """用近轴矩阵核对双光组组合公式，返回与 two_lens_combination 相同结构的 dict。"""
    sysm = ParaxialSystem([
        {"type": "lens", "f": f1},
        {"type": "gap", "d": d},
        {"type": "lens", "f": f2},
    ])
    M, n = sysm.matrix()
    f = float(-n / M[1, 0])
    return dict(f=f, lF=float(-M[1, 1] / M[1, 0]), lFp=float(-M[0, 0] / M[1, 0]))
