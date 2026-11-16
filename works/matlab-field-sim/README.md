# 避雷针电场仿真（MATLAB）

用三维有限差分法求解拉普拉斯方程，模拟圆锥-圆柱组合避雷针周围的电场与电势分布，程序会按运行次数自动生成版本目录（共 6 个版本）。

## 怎么跑 / 怎么看
- 主程序：`避雷针.m`（MATLAB R2024b），运行后自动生成 `LightningRod_Simulation_00x_*` 目录；
- 每个版本含 `figures/`（PNG 图）、`plots/`（可编辑 .fig）、`data/`（CSV 数据）、`reports/`（仿真报告）；
- 关键参数：仿真域 1.0×1.0×3.0 m，60×60×80 网格（28.8 万节点），SOR 超松弛迭代（松弛因子 1.6）；
- `untitled2.m` / `untitled3.m`：从 COMSOL 流速数据 CSV 做后处理的实验脚本（与本仿真无直接关系）。

## 版本与去重
`001_theta30`、`002_theta30`、`003_theta29`、`theta30_Final`、`theta30_RevisedViz`、`theta30_修正版`；跨版本完全相同的 axis/radial CSV 已去重（只保留在 001），其余文件保留。

## 说明
- 来源机器路径：`C:\Users\x1503\Documents\MATLAB`；`.mat` 原始数据（约 26.6MB）体积过大未归档，可用主程序重算。
