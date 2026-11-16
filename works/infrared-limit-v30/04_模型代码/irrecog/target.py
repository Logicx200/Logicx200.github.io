# -*- coding: utf-8 -*-
"""
irrecog.target —— 软件模型库 6 个实际目标的几何与辐射特征

尺寸口径（两套，均登记，主/备可切换）
------------------------------------
* ``sqrt_area``（主）：D_eff = sqrt(W_proj × H)，W_proj = max(水平两轴)，
  H = 垂直轴。等效方目标口径，与 NVESD TTP 的 √A_t 思路一致，
  避免"用最大边长"把长条形目标（舰船）高估。
* ``max_dim``（备）：D_eff = max(W, L, H)，即最大边口径，用于敏感性对照。

注意：包围盒由 OSG 顶点计算、按"1 单位 = 1 m"解释，**未做几何标定**；
这是本项目登记的主要不确定度之一（见参数依据说明），
两套口径的识别距离差约 1.5–2.3 倍，报告须同时给出。
"""

from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np

from . import params


@dataclass(frozen=True)
class Target:
    key: str
    name: str
    kind: str
    dims: Tuple[float, float, float]      # (W, L, H) m
    z_m: float                            # 目标离地/海面高度 m
    eps: float = 0.90
    size_rule: str = "sqrt_area"          # sqrt_area | max_dim

    @property
    def area_proj_m2(self) -> float:
        """侧向投影面积近似：水平最大轴 × 垂直轴。"""
        w, l, h = self.dims
        return float(max(w, l) * h)

    @property
    def d_eff_m(self) -> float:
        if self.size_rule == "max_dim":
            return float(max(self.dims))
        return float(np.sqrt(self.area_proj_m2))

    @property
    def d_max_m(self) -> float:
        return float(max(self.dims))

    def theta_mrad(self, r_slant_km: float) -> float:
        """目标等效角尺寸 mrad（m / km ≡ mrad）。"""
        return self.d_eff_m / max(r_slant_km, 1e-9)


def build_targets(size_rule: str = "sqrt_area", eps: Optional[float] = None) -> List[Target]:
    out = []
    for t in params.TARGETS:
        out.append(Target(key=t["key"], name=t["name"], kind=t["kind"], dims=t["dims"],
                          z_m=t["z_m"], eps=t["eps"] if eps is None else eps,
                          size_rule=size_rule))
    return out


def get_target(key: str, size_rule: str = "sqrt_area") -> Target:
    for t in build_targets(size_rule):
        if t.key == key:
            return t
    raise KeyError(key)


def summary_table(size_rule: str = "sqrt_area") -> List[dict]:
    rows = []
    for t in build_targets(size_rule):
        rows.append(dict(key=t.key, name=t.name, kind=t.kind,
                         W_m=t.dims[0], L_m=t.dims[1], H_m=t.dims[2],
                         area_proj_m2=round(t.area_proj_m2, 2),
                         d_eff_m=round(t.d_eff_m, 3),
                         d_max_m=round(t.d_max_m, 3),
                         z_m=t.z_m))
    return rows
