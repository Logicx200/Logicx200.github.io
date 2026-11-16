# 轨道分段–拼接规划方法：算法伪代码

> 依据：唐子杰, 于宇航, 吴亦烜, 黄哲铖, 喻中扬, 李润道, 张楠.
> 《面向大规模空间碎片清除的轨道分段–拼接规划方法》. 力学与实践, 2026, 48(2): 265-271.
> 对照赛题：《面向卫星解体碎片清除任务的轨道设计与机动规划》(第十五届全国大学生周培源力学竞赛"空间轨道设计"团体赛).
>
> 说明：`<...>` 为论文未明确给出的量（实现自由度）；`▷` 为论文中"未写明但必要"的补充假设，
> 已在文末集中列出，复现时应重点核验。

---

## 0. 全局参数（论文取值）

```
GLOBAL:
    t0_task        = 2030-11-14 08:00:00 UTC      # 任务窗口起点
    T_task         = 24 h                          # 任务总时长
    t_end_task     = t0_task + T_task

    WIN[1..4] = [(08:00,16:00), (14:00,22:00), (20:00,04:00+1), (00:00+1,08:00+1)]
    ▷ 相邻窗口重叠，最终方案对外使用窗口 [T_j, T_j+dt_j]，dt_j 可在赛题 24 h 内增长/平移

    N_SC        = 3          # 母航天器数量上限
    N_SEG       = 4          # 每器轨道基元数 = 窗口数
    K_MAX       = 6          # 每器脉冲机动次数上限
    → 3 个接缝 × 2 次脉冲 = 6 次, 恰好饱和

    H_MIN       = 200   km   # 轨道高度下限（全程）
    DR_MAX      = 30    km   # 清除时刻相对位置上限
    DV_MAX      = 150   m/s  # 清除时刻相对速度上限
    T_PATCH     = 45    min  # 拼接预留转移时长
    NTH_DB      = 8          # 数据库入库阈值: 清除碎片数 > 8
    DT_STEP     = <Δt>       # 递推时间步长
    GRID[6]     = 各根数的搜索网格与步长 (a,e,i,Ω,ω,f)   # 范围由碎片分布聚焦确定
```

---

## 1. 主算法：两阶段"分而治之"框架

```
ALGORITHM OrbitSegmentationAndPatching(Debris, WIN, GRID)
    # ---------------- 阶段一：轨道分段（数据库生成，穷举搜索）----------------
    for j = 1 to 4 do
        DB[j] ← BuildPrimitiveDatabase(Debris, WIN[j], GRID)     # 见 ALG-2
    end for
    DBS ← {DB[1], DB[2], DB[3], DB[4]}

    # ---------------- 阶段二：轨道拼接（组合挑选 + 脉冲拼接）----------------
    Sol ← OptimizePrimitiveSelection(DBS, N_SC, N_SEG)            # 见 ALG-3
    Traj ← PatchOrbitPrimitives(Sol, T_PATCH)                     # 见 ALG-6

    # ---------------- 校验与迭代（论文: 全部方案经官方 ATK 复核）----------------
    if not VerifyWithATK(Traj) then  return  FAILURE              # 回到 ALG-3 继续搜索
    return (Sol, Traj, N_cleared(Sol))
end
```

---

## 2. 阶段一：轨道基元数据库生成（网格穷举）

```
ALGORITHM BuildPrimitiveDatabase(Debris, WIN = [t_a, t_b], GRID)
    DB ← ∅
    # ---------- 2.1 6 维轨道根数全网格穷举 ----------
    for a  in A_LIST do                     # 搜索范围 = 碎片根数高度聚集区
    for e  in E_LIST do
    for i  in I_LIST do
    for Ω  in OM_LIST do
    for ω  in W_LIST do
    for f  in F_LIST do
        oe  ← (a, e, i, Ω, ω, f)
        seq ← FlybySequence(oe, t_a, t_b, Debris)                  # 见 ALG-2.2
        if |seq| > NTH_DB then                                     # 阈值 > 8 才入库
            DB ← DB ∪ { Primitive(oe = oe, win = WIN,
                                  t_a = t_a, t_b = t_b, seq = seq) }
        end if
    end for ... end for

    # ---------- 2.3 质量评估（论文图 3 的分析手段, 非求解必需）----------
    ▷ 对根数空间分块统计 mean(|seq|), 绘 (a,e)/(Ω,i)/(ω,f) 热力图
    return DB
end
```

**ALG-2.2 基元内的飞越/清除判定（正向递推）**

```
ALGORITHM FlybySequence(oe, t_a, t_b, Debris)
    x ← StateFromElements(oe, t_a)          # 位置 r, 速度 v
    seq ← ∅
    repeat
        x ← PropagateRK4(x, F_grav + F_J2, Δt)      # 母器: 中心引力 + J2 摄动完整项
        ▷ 碎片状态用"J2 一阶长期摄动"的根数漂移公式更新, 而非数值积分:
        ▷     Ω(t) = Ω0 − (3/2) J2 (RE/p)² n cos i · (t − t0)
        ▷     ω(t) = ω0 + (3/4) J2 (RE/p)² n (5cos²i − 1) · (t − t0)
        for each debris d ∈ Debris do
            if d ∉ seq then                                  ▷ 去重: 每碎片最多清除一次
                if |r_sc(t) − r_d(t)| < DR_MAX
                   and |v_sc(t) − v_d(t)| < DV_MAX then
                       seq ← seq ∪ {(d, t)}                  ▷ 记录碎片编号与清除时刻
                end if
            end if
        end for
    until t ≥ t_b
    return seq
end
```

> 注：一个轨道基元（一段无脉冲外推弧）可清除 **多个** 碎片，这正是"基元"作为数据库条目的价值来源；
> 论文表中单个基元的清除数为 9–14 个。

---

## 3. 阶段二之一：轨道基元组合挑选（启发式组合优化）

**解编码**：`Sol = (p[1][1..3], p[2][1..3], p[3][1..3], p[4][1..3])`
即 4 个窗口各选 3 个基元（每个基元对应一条完整轨迹的一段），共 **12** 个基元。

```
ALGORITHM OptimizePrimitiveSelection(DBS, N_SC, N_SEG)
    # ---------- 初始解: 各库随机取样 ----------
    Sol ← ( for j = 1..4: RandomSample(DB[j], N_SEG) )
    Elite ← {Sol}
    no_improve ← 0

    # ---------- 局部优化与全局优化交替执行, 直至收敛 ----------
    while no_improve < <MAX_STALL> do
        # ---- (a) 局部优化: 随机替换一段, "不劣即接受" ----
        Sol'  ← Sol
        (j,k) ← RandomPickWindowAndSlot()
        Sol'.p[j][k] ← RandomPick(DB[j])
        if Evaluate(Sol') ≥ Evaluate(Sol) then        # 允许等值接受 ⇒ 可走平台逃逸
            Sol ← Sol' ;  no_improve ← 0
        else
            no_improve ← no_improve + 1
        end if

        # ---- (b) 全局优化: 遗传算法"单点交叉" ----
        (P1, P2) ← TwoDistinctEliteMembers(Elite)
        cut      ← RandomPointIn[1, 4·N_SEG]
        (C1, C2) ← SinglePointCrossover(P1, P2, cut)      # 展平为长度 12 的串后单点交叉
        for C in {C1, C2} do
            if FeasibleByConstruction(C) then             # 每窗口仍须恰为 3 个基元
                Elite ← Elite ∪ {C}
                if Evaluate(C) > Evaluate(Sol) then Sol ← C
            end if
        end for
        Elite ← KeepTopK(Elite, <K_ELITE>)
    end while
    return Sol        # 收敛准则: 无法再获得更优的基元组合
end
```

**目标函数（含拼接预留与去重）**

```
FUNCTION Evaluate(Sol)
    U ← ∅
    for each selected primitive p ∈ Sol do      # 12 个基元: 4 窗口 × 3 航天器
        for each (d, t) ∈ p.seq do
            if t ∈ p.win  and  t ∉ PatchWindow(p) then    # 45 min 转移时长内的清除不计
                U ← U ∪ {d}                               # 重复清除仅计一次
            end if
        end for
    end for
    return |U|
end
```

---

## 4. 阶段二之二：轨道基元拼接（两脉冲 Lambert）

```
ALGORITHM PatchOrbitPrimitives(Sol, T_PATCH)
    # 3 个接缝 × 2 次脉冲 = 6 次脉冲, 满足 ≤ 6 约束
    Im ← (0,0,0)                                 # 累积脉冲
    for s = 1 to N_SC do
        segs ← (Sol.p[1][s], Sol.p[2][s], Sol.p[3][s], Sol.p[4][s])
        Traj[s] ← segs[1]
        for j = 1 to 3 do
            # ---- 4.1 时间窗口重叠 / 时间干涉的避让 ----
            if OverlapConflict(segs[j], segs[j+1]) then
                segs ← ShiftInWindow(segs, T_PATCH)          ▷ 窗口增长/平移, 尽力保留可清除碎片
                if StillConflict(segs[j], segs[j+1]) then
                    Reject(Sol) ; return DISCARD             # "时间干涉, 舍去"
                end if
            end if

            # ---- 4.2 两脉冲拼接: 顺序尝试两种 Lambert 求解方式 ----
            if t_end(segs[j+1]) − t_end(segs[j]) < T_PATCH then Reject(Sol) ; return DISCARD
            ok ← false
            Method A:  ok ← Patch_Direct(segs[j], segs[j+1], Im)          # 见 ALG-5A
            if not ok then
                Method B: ok ← Patch_Retrograde(segs[j], segs[j+1], Im)   # 见 ALG-5B
            end if
            if not ok then Reject(Sol) ; return DISCARD
                # "两种方式中任意一种获得可行解即可完成拼接"

            # ---- 4.3 全程约束校验 ----
            if not CheckAltitude(Traj[s], H_MIN) then Reject(Sol) ; return DISCARD
        end for
    end for
    return Traj
end
```

**ALG-5A 方式一：直接 Lambert**

```
ALGORITHM Patch_Direct(segA, segB, Im)
    (r_A, v_A) ← EndState(segA)                        # 前一基元末端状态
    (r_B, v_B) ← StartState(segB)                      # 后一基元初端状态
    Δt ← t_start(segB) − t_end(segA)                   # ∈ [半个轨道周期, T_PATCH]
    (v1, v2) ← Lambert(r_A, r_B, Δt, prograde=true)    # 调用官方 ATK 求解器
    if not Converged(v1, v2) then return false         # 不收敛
    if not PhysicalOrbit(r_A, v1, r_B, v2) then return false   # 轨道过高/过低等异常
    Im.first  ← v1 − v_A                               # ① 接缝第一脉冲
    Im.second ← v_B − v2                               # ② 接缝第二脉冲
    return true
end
```

**ALG-5B 方式二：先反向 2v 脉冲入逆行轨道，再解 Lambert 并矢量合并**

```
ALGORITHM Patch_Retrograde(segA, segB, Im)
    (r_A, v_A) ← EndState(segA)
    Δt ← t_start(segB) − t_end(segA)
    if Δt ≤ (1/2) · T_orbit(r_A) then return false     # 保证条件: 预留时间 > 半个轨道周期

    Δv_pre ← −2 · v_A                                  # 反向、大小 = 原速度 2 倍 ⇒ 进入逆行轨道
    v_A'   ← v_A + Δv_pre = −v_A
    (v1', v2') ← Lambert(r_A, r_B, Δt, retrograde=true)     # 同样调用 ATK
    if not Converged(v1', v2') then return false

    Im.first ← Δv_pre + v1'                            # 初始逆行脉冲与 ATK 第一个脉冲矢量合并
    Im.second ← v_B − v2'
    return true
end
```

> 结论（论文）：方式二在"两基元相位差别过大"时使用，只要拼接预留时间超过半个轨道周期即可确保拼接成功。

---

## 5. 复杂度与工程实现

```
COST:
    阶段一: O( ∏_{k=1..6} |GRID_k|  ×  (T_window/Δt) × N_debris )   # 主导项, 天然可并行
    阶段二: 局部/全局交替, 单次评估 O(N_SEG × N_SC × |seq|); Lambert 调用为主要开销
实现:  Python;  192 核 AMD EPYC 9654;  端到端约 12 h;  结果由官方 ATK 复核
结果:  3 器分别清除 42 / 41 / 42, 合计 125 个碎片 (冠军)
```

---

## 6. 论文未明确、伪代码中需补充的假设（复现风险点）

| 编号 | 假设 | 依据/说明 |
|---|---|---|
| A1 | 一个基元在**同一时刻附近可连续清除多个碎片**，清除判据用 `<`（严格小于） | 门限为"相对位置小于 30 km、相对速度小于 150 m/s"；单基元清除数 9–14 要求一段弧可覆盖多碎片 |
| A2 | 12 个基元按 **3 槽 × 4 窗口** 绑定：槽 s 的第 j 段 → 第 s 个航天器 | 论文"从 4 个数据库中各选 3 个基元"，表 1 每器各含 4 窗口基元 |
| A3 | 交叉算子对展平后的 **长度 12 的串做单点交叉**，并施加"每窗口恰 3 个基元"的合法性修复 | 论文仅述"借鉴遗传算法的交叉机制…单点交叉" |
| A4 | 局部优化的"不劣即接受"中含**等值接受**，需配合停滞计数/重启判停 | 论文原文"优于或等于原组合，则接受" |
| A5 | 拼接采用 **首尾相连（telescoping）**：每器仅 4 基元 → 3 接缝 → 恰 6 脉冲 | 若允许跨段/重规划，脉冲数将超限 |
| A6 | Lambert **不收敛**或"轨道过高/过低"即判该解不可行，回退方式二或舍弃该组合 | 论文明确列举了这两类失败模式 |
| A7 | 方式二的适用前提写作 **Δt > 半个轨道周期**，实现中可取 T_PATCH = 45 min 作实际判据 | 论文"只要拼接过程预留的时间超过半个轨道周期" |
| A8 | 目标函数**只计清除碎片总数**，Δv 仅作可行性/次生指标（不最小化） | 赛题目标为最大化总清除数 N；表 1 只列基元根数与清除数 |
| A9 | 高度约束在 **整段轨迹连续校核**（基元内 + 拼接弧内），取 H_MIN = 200 km | 赛题约束 (3)"任一航天器的轨道高度必须始终高于 200 km" |
| A10 | 阶段一网格为**嵌套循环穷举**（可并行/可裁剪），不含随机搜索 | 论文"大规模网格搜索/穷举生成" |

---

## 7. 可进一步优化的算法改进点（论文未做，供延伸）

1. **多目标化**：将 `Evaluate` 改为 `(|U|, −Σ|Δv|)` 的字典序或加权目标，在等清除数下降低燃料。
2. **数据库剪枝**：入库时按 `|seq|` 与根数邻域去冗余，减少阶段二的候选规模。
3. **贪心/束搜索替代随机替换**：以边际增益（marginal gain）指导替换，而非均匀随机。
4. **接缝时间作为连续变量**：对每个接缝的 Δt 做一维优化（最大化保留碎片数），而非固定 45 min。
5. **精英池多样性维护**：对 Elite 做去重 + 按"覆盖碎片集合"的 Jaccard 距离做多样性筛选，抑制早熟。
