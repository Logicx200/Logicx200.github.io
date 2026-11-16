# 软件参数提取 —— 交付索引（XGGDCOSSim2 光电环境仿真软件）

> 任务：**只读**分析 `D:\XGGDCOSSim2` 内部设置参数，整理为结构化数据，供另一个模型升级仿真使用。
> 约束遵守情况：源目录 **未做任何写操作**（全部读取 + 复制到本工作区后解码）；所有输出均为 **UTF-8 中文**。
> 工作区：`F:\DeepSeek工作区\软件参数提取\`

---

## 1. 交付物清单

| # | 交付物 | 路径 | 规模 | 说明 |
|---|---|---|---|---|
| 1 | Q2 数据块索引 | `Q2解析\atmosphere_index.csv` | 2 行 × 24 列 | 每数据块一行（band/location/region_type/atm_no/rt_file/时空/波长/温湿压/气溶胶/大气模式/天气/俯仰步长/n_rows/row_start/row_end） |
| 2 | Q2 全量数据行 | `Q2解析\atmosphere_data\*.csv` + `Q2解析\atmosphere_data.parquet` | **6 个分块、44,010 行 × 30 列**；parquet 单文件 502.9 KB | 全部数据行 + 每行自带完整元数据；CSV 为 utf-8-sig，parquet 为 zstd 压缩（已回读校验） |
| 3 | 场景条件汇总 | `Q2解析\scenario_summary.md` | 17 KB | 地点/地域/大气编号/条件组合统计、网格覆盖、物理量范围、异常、**10 类背景可用性判定** |
| 4 | 模型与想定参数 | `模型与想定参数.md` + `models.json` | 35 KB + 301 KB | 枚举 tips 原文、默认想定全参数、模型库清单、Config.ini 波段/温度/辐亮度、模型包围盒/尺寸 |
| 5 | 传感器说明 | `sensor_notes.md` | 15 KB | 默认红外传感器可用参数、派生几何量、缺失参数清单、可复用的导引头参数模板、推荐辐射链路 |
| 6 | 解析脚本 | `scripts\decode_files.py`、`scripts\parse_q2.py`、`scripts\summarize_q2.py`、`scripts\parse_models.py`、`scripts\to_parquet.py` | 5 个 | 可重复运行（确定性输出） |
| 7 | 中间证据 | `_decoded\*.utf8.txt`、`_reports\models_autogen.md` | — | 源文件 UTF-8 解码副本（含编码报告）、自动生成附表 |

辅助文件：`Q2解析\condition_combos.csv`、`Q2解析\grid_summary.csv`、`Q2解析\parse_report.json`、`Q2解析\verify_report.json`。

---

## 2. 复现步骤

```powershell
cd F:\DeepSeek工作区\软件参数提取
python scripts\decode_files.py     # 1) 把 D:\XGGDCOSSim2 的配置/XML 解码为 UTF-8 副本到 _decoded\
python scripts\parse_q2.py         # 2) 解析 Q2_M/Q2_L -> atmosphere_index.csv + atmosphere_data\*.csv
python scripts\summarize_q2.py     # 3) 回读校验 + 网格/条件统计（verify_report.json）
python scripts\parse_models.py     # 4) 解析 XML/INI/OSG -> models.json + _reports\models_autogen.md
python scripts\to_parquet.py       # 5) 合并 6 个 CSV 分块 -> atmosphere_data.parquet（含回读校验）
```

依赖：Python 3.11，仅标准库（无第三方包、无联网）。

---

## 3. 关键结论速览

1. **Q2 查找表**：`Q2_M.csv`（中波 3.7~4.8 μm）与 `Q2_L.csv`（长波 **7.7~10.3 μm**）各含 **1 个数据块**（并非"多块"）、各 22,005 行，合计 **44,010 行**，GB18030 编码，解析后行数/元数据/物理量均回读校验通过。
2. **场景覆盖极窄**：仅 **1 个地点（洛阳）/ 1 种地域（城市）/ 1 个大气参数编号（01）/ 1 组大气条件（10 ℃、50%、25 m 能见度、1013.25 hPa、沙漠型气溶胶、美国标准大气、无云雨）/ 1 个时刻**；可覆盖 10 类背景中的 **1 类（城市）直接可用**，沙漠/戈壁/荒漠仅能近似其大气路径项，其余 6 类须重算。
3. **重大异常**：能见度 25 m（疑似应为 25 km）、气溶胶"沙漠型"与城市地点不匹配、视点高度上限 5000 m < 默认传感器 8000 m、长波波长两套口径（8~12 vs 7.7~10.3）、RT 大气卡片文件未随软件交付。
4. **模型**：6 个目标模型（F16/F22/尼米兹/阿利伯克/悍马/爱国者发射车）+ 1 个背景模型（与那国岛，220 km×220 km）；**全部 7 个模型 Config.ini 的波段/温度/辐亮度参数完全相同**（中波 3.7~4.8、长波 8~12、环境温度 20 ℃、温度范围 0~60 ℃）；中波辐亮度上下限（0.43/3.76）与可见光同值，疑似错误。
5. **尺寸**：已从 `.osg` 顶点算出包围盒（F16 9.66×14.85×4.57 m、F22 13.50×18.60×4.00 m、尼米兹 85.73×340.66×75.22 m、悍马 2.81×5.09×3.20 m、阿利伯克 20.27×151.32×47.74 m、爱国者发射车 10.24×22.57×10.98 m、与那国岛 220000×220000×215.66 m）；`.flt` 为二进制未解析（同源 `.osg` 已覆盖）。
6. **传感器**：默认传感器是"中波红外 3.7~4.8 μm / FOV 3.75°×3° / 1024×768 / 50 Hz / 8 bit / 高度 8000 m / 俯仰 -90°"，带 ResCoefficient=1746、ResBias=1733 的显示链路映射；**缺 NETD、口径、焦距、像元尺寸、积分时间、光谱响应、噪声模型**，属渲染/注入参数而非辐射传感器模型；但软件在"光学成像导引头"模板里预留了完整字段（波长/视场/入瞳/焦距/像元数/积分时间/帧频/灰度/四段辐射-灰度响应/噪声方差），默认全 0，可作为升级接口范式。
7. **编码修正**：`ModelDatabase.xml` 实测为 **UTF-8**（非线索所称 UTF-16LE）；`DefaultPlanFile.xml` 为 GB18030；`DefaultModelDatabase.xml` 为 UTF-8。

---

## 4. 数据消费建议（给升级仿真模型）

- 直接可读：`models.json`（枚举+想定+模型+包围盒一体）、`Q2解析\atmosphere_data\*.csv`（pandas 直接 concat）。
- 大气链路：用 `path_transmittance` / `path_radiance_W_m2sr` 作大气修正，`background_radiance_W_m2sr` 仅限"城市+沙漠型气溶胶"这一组条件；其他背景/地点/季节/能见度必须外部补算（Q2 的 RT 卡片未提供，无法复现）。
- 传感器链路：几何（FOV/分辨率/高度/俯仰）与波段可直接沿用；辐射-灰度环节需按 `sensor_notes.md` §4 补齐参数，建议按 §5 的导引头字段对齐接口、按 §6 的公式重建物理链路。
