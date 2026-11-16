# 上传清单（源工作区 → 发布副本）

> 数据源：本机工作区的发布清单（publish.json）与复制脚本输出（tools/report.json）。本仓库 `works/` 下的内容即由下表规则筛选复制而来。

- 生成时间：2026-11-17 01:17
- 权威清单：`publish.json`，共 **36 个发布分组**
- 裁剪规则：单文件 > 8 MB 跳过；每组体积上限 12 MB（部分项目 15–25 MB，见下表）；排除 `node_modules`/`__pycache__`/`.cache`/`dist`/`hapi_db` 等目录与 `*.plt`/`*.npz`/`*.par`/`*.exe`/`*.dll`/`*.zip` 等类型；超限时按「大图/媒体 → 大数据文件 → 其它素材」的顺序裁剪，**`.md`/`.html`/`.htm` 与源码、配置永不裁剪**。
- 瘦身规则（Lead 批准 L1+L2）：同一分组内完全相同文件只保留一份（≥32 KB，被引用最多/路径最浅者优先）；排除旧版本/归档目录（`历史归档` / `_archive` / `历史版本`）中的非文档非代码文件——目录内的 `.md`、代码、配置与各项目封面图仍然保留。不做跨分组去重，不删成果图/热力图/PDF 报告。

## 总计

| 指标 | 数值 |
| --- | ---: |
| 发布分组 | 36 个 |
| 扫描到的源文件（含被排除目录内文件） | 11402 个 / 14.31 GB |
| 实际发布 | **4470 个文件 / 205.32 MB** |
| 未复制（本地保留） | 6932 个文件 / 14.11 GB |
| 工作区全量（inventory.csv） | 11,081 个文件 / 14.37 GB |
| 其中 L1+L2 瘦身减少 | -28 个文件 / -24.18 MB（L1 组内去重 16 个 / -6.73 MB；L2 旧版本归档 12 个 / -17.45 MB） |

## 各分组体积表

| 分组 | 发布目录 | 源位置 | 源文件数 | 源体积 | 发布文件数 | 发布体积 | 跳过数 | 跳过原因 top3 | 体积上限 |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- | ---: |
| 817-optics | works/817-optics | `817光学-Python仿真` | 47 | 3.82 MB | 38 | 3.73 MB | 9 | 被排除目录 ×9 | 12 MB |
| adsb-radar | works/adsb-radar | `adsb-radar` | 48 | 1.61 MB | 31 | 1.47 MB | 17 | 被排除目录 ×17 | 12 MB |
| ascii-studio | works/ascii-studio | `ascii-studio` | 38 | 7.48 MB | 37 | 4.66 MB | 1 | 被排除类型 ×1 | 12 MB |
| hitran-slant | works/hitran-slant | `hitran_slant` | 234 | 257.00 MB | 96 | 11.57 MB | 138 | 被排除类型 ×65；被排除目录 ×62；体积超标裁剪 ×11 | 12 MB |
| quantum-tunneling | works/quantum-tunneling | `quantum_tunneling` | 33 | 47.26 MB | 24 | 9.43 MB | 9 | 被排除类型 ×4；单文件超限 ×3；被排除目录 ×2 | 20 MB |
| infrared-detect-v21 | works/infrared-detect-v21 | `红外目标探测仿真_整合交付_V2.1` | 137 | 38.93 MB | 105 | 10.59 MB | 32 | 体积超标裁剪 ×16；组内重复去重 ×9；旧版本/归档目录 ×6 | 20 MB |
| infrared-limit-v30 | works/infrared-limit-v30 | `红外识别极限重构_V3.0` | 397 | 230.15 MB | 124 | 16.83 MB | 273 | 被排除目录 ×264；被排除类型 ×5；旧版本/归档目录 ×2 | 25 MB |
| atmo-classify | works/atmo-classify | `大气工况分类图` | 81 | 41.74 MB | 59 | 10.57 MB | 22 | 被排除目录 ×9；体积超标裁剪 ×6；旧版本/归档目录 ×4 | 15 MB |
| formal-sim | works/formal-sim | `正式仿真` | 33 | 3.62 MB | 33 | 3.62 MB | 0 | — | 12 MB |
| sim-results | works/sim-results | `sim_results` | 27 | 3.34 MB | 23 | 3.30 MB | 4 | 被排除类型 ×4 | 12 MB |
| jilong | works/jilong | `jilong` | 2139 | 12.87 GB | 1285 | 14.92 MB | 854 | 体积超标裁剪 ×475；被排除类型 ×367；单文件超限 ×9 | 15 MB |
| navwarn-map | works/navwarn-map | `navwarn-map`、`preview.py` 等 9 项 | 64 | 27.08 MB | 57 | 18.89 MB | 7 | 被排除目录 ×4；体积超标裁剪 ×3 | 20 MB |
| navwarn-verify | works/navwarn-verify | `_navwarn_verify` | 83 | 29.70 MB | 67 | 13.95 MB | 16 | 体积超标裁剪 ×9；被排除目录 ×7 | 15 MB |
| cossim-auto | works/cossim-auto | `_cossim_auto` | 217 | 32.25 MB | 179 | 14.58 MB | 38 | 体积超标裁剪 ×34；组内重复去重 ×2；被排除目录 ×1 | 15 MB |
| ets2fix | works/ets2fix | `_ets2fix` | 75 | 20.17 MB | 70 | 5.60 MB | 5 | 组内重复去重 ×3；被排除类型 ×2 | 12 MB |
| software-params | works/software-params | `软件参数提取`、`extract_help.html` 等 10 项 | 74 | 14.45 MB | 73 | 13.96 MB | 1 | 被排除类型 ×1 | 18 MB |
| progress-board | works/progress-board | `进度看板` | 6 | 138.8 KB | 6 | 138.8 KB | 0 | — | 12 MB |
| dsh-live-console | works/dsh-live-console | `dsh-live-console-v15` | 56 | 6.08 MB | 54 | 5.67 MB | 2 | 组内重复去重 ×2 | 15 MB |
| dsh-live-console-ui | works/dsh-live-console-ui | `dsh-live-console-ui` | 5 | 8.0 KB | 5 | 8.0 KB | 0 | — | 12 MB |
| dsh-usage-bridge | works/dsh-usage-bridge | `dsh-usage-bridge` | 9 | 244.0 KB | 9 | 244.0 KB | 0 | — | 12 MB |
| dsh-usage-dashboard | works/dsh-usage-dashboard | `dsh-usage-dashboard` | 27 | 2.29 MB | 27 | 2.29 MB | 0 | — | 12 MB |
| dsh-mood-eyes | works/dsh-mood-eyes | `dsh-mood-eyes`、`dsh-mood-eyes-v2` 等 10 项 | 46 | 3.08 MB | 46 | 3.08 MB | 0 | — | 12 MB |
| dsh-mood-usage | works/dsh-mood-usage | `dsh-mood-usage` | 10 | 35.0 KB | 10 | 35.0 KB | 0 | — | 12 MB |
| dsh-mood-balance | works/dsh-mood-balance | `dsh-mood-balance` | 6 | 5.0 KB | 6 | 5.0 KB | 0 | — | 12 MB |
| photo-journal | works/photo-journal | `photo-journal` | 7261 | 688.47 MB | 1784 | 14.96 MB | 5477 | 被排除目录 ×3891；体积超标裁剪 ×1586 | 15 MB |
| spacetime-cube | works/spacetime-cube | `spacetime-cube` | 123 | 1.05 MB | 116 | 1013.6 KB | 7 | 被排除类型 ×7 | 12 MB |
| lidar-sim | works/lidar-sim | `lidar-sim` | 7 | 1.71 MB | 6 | 1.69 MB | 1 | 被排除目录 ×1 | 12 MB |
| exp1 | works/exp1 | `exp1` | 39 | 1.29 MB | 25 | 242.9 KB | 14 | 被排除类型 ×10；被排除目录 ×4 | 12 MB |
| whale-chan-research | works/whale-chan-research | `whale-chan-research` | 48 | 17.39 MB | 48 | 17.39 MB | 0 | — | 18 MB |
| irsim | works/irsim | `irsim` | 8 | 96.9 KB | 4 | 35.3 KB | 4 | 被排除目录 ×4 | 12 MB |
| figures | works/figures | `figures` | 3 | 279.5 KB | 3 | 279.5 KB | 0 | — | 12 MB |
| boids | works/boids | `boids.html` | 1 | 13.6 KB | 1 | 13.6 KB | 0 | — | 12 MB |
| ecosystem | works/ecosystem | `ecosystem.html` | 1 | 27.4 KB | 1 | 27.4 KB | 0 | — | 12 MB |
| transit-kernel | works/transit-kernel | `transit-kernel.js`、`verify-kernel.js` 等 3 项 | 3 | 44.9 KB | 3 | 44.9 KB | 0 | — | 12 MB |
| notes | works/notes | `ai_enhanced_segmentation_patching_design.md`、`orbital_segmentation_patching_pseudocode.md` 等 12 项 | 12 | 540.5 KB | 12 | 540.5 KB | 0 | — | 15 MB |
| toolbox | works/toolbox | `scripts`、`Move-ProgramFiles-App.ps1` 等 3 项 | 4 | 33.0 KB | 3 | 19.8 KB | 1 | 被排除目录 ×1 | 12 MB |
| **合计** | — | — | **11402** | **14.31 GB** | **4470** | **205.32 MB** | **6932** | — | — |

## 跳过原因分类汇总

### 1. 体积/类型规则跳过（在发布清单内、但未复制）

| 类别 | 文件数 | 体积 | 说明 |
| --- | ---: | ---: | --- |
| 被排除目录 | 4279 | 578.67 MB | `node_modules`/`__pycache__`/`.cache`/`.npm-cache`/`dist`/`hapi_db` 等 |
| 被排除类型 | 471 | 12.46 GB | `*.plt`/`*.npz`/`*.npy`/`*.par`/`*.exe`/`*.dll`/`*.zip`/`*.log` 等 |
| 单文件超限 | 14 | 170.72 MB | 单个文件 > 8 MB（受保护文档/源码除外） |
| 体积超标裁剪 | 2140 | 919.47 MB | 项目总超上限后按优先级丢弃的素材 |
| 旧版本/归档目录 | 12 | 17.45 MB | `历史归档`/`_archive`/`历史版本` 目录中的非文档/非代码文件；目录内的 `.md`、代码、配置与封面仍保留 |
| 组内重复去重 | 16 | 6.73 MB | 同一项目内完全相同文件只保留一份（保留被引用最多/路径最浅者）；不做跨项目去重 |

**被排除目录明细（top 10）**：`dist` ×3328（305.53 MB）、`_hapi_db` ×258（190.11 MB）、`.cache` ×216（21.00 MB）、`node_modules` ×206（32.23 MB）、`.npm-cache` ×141（23.34 MB）、`__pycache__` ×130（6.47 MB）

**被排除类型明细（top 12）**：`*.exe` ×87（106.26 MB）、`*.plt` ×86（11.23 GB）、`*.dll` ×86（69.20 MB）、`*.npy` ×58（218.70 MB）、`*.par` ×54（127.88 MB）、`*.log` ×51（584.6 KB）、`*.npz` ×32（116.20 MB）、`*.tif` ×6（53.42 MB）、`*.blend` ×3（190.77 MB）、`*.blend1` ×3（190.75 MB）、`*.parquet` ×2（1005.7 KB）、`*.webm` ×1（2.82 MB）

**体积超标裁剪明细**：小素材 ×1474（223.48 MB）、大图/媒体 ×488（442.39 MB）、其它素材 ×165（231.61 MB）、大数据文件 ×13（22.00 MB）

**旧版本/归档目录明细**：`07_历史版本` ×6（7.55 MB）、`历史归档` ×2（5.50 MB）、`_archive_v2.0` ×2（2.22 MB）、`_archive_v1.0` ×1（1.10 MB）、`_archive_v1.1` ×1（1.08 MB）

**组内重复去重明细（保留的目标文件，top 10）**：`tool_out.txt` ×2（3.61 MB）、`03_仿真数据/原始结果/v2_workflow.png` ×1（227.3 KB）、`03_仿真数据/原始结果/v2_scenario_map.png` ×1（176.6 KB）、`03_仿真数据/原始结果/v2_dt_heatmap.png` ×1（144.3 KB）、`03_仿真数据/原始结果/software_actual_ne.png` ×1（205.9 KB）、`03_仿真数据/原始结果/v2_turbulence_heatmap.png` ×1（165.6 KB）、`03_仿真数据/原始结果/software_actual_pd.png` ×1（264.9 KB）、`03_仿真数据/原始结果/v2_cloud_matrix.png` ×1（208.1 KB）、`03_仿真数据/原始结果/v2_jam_bar.png` ×1（93.1 KB）、`03_仿真数据/原始结果/software_actual_case_results.csv` ×1（287.3 KB）

### 2. 整体未上传的条目（不在任何发布分组内）

| 条目 | 文件数 | 体积 | 原因 |
| --- | ---: | ---: | --- |
| 地图原始数据（out/，SVG 中间产物） | 4 | 11.77 MB | 见下方 publish.json `excluded` 或内部文件规则 |
| 内部临时/会话状态文件（根目录） | 3 | 76.8 KB | 见下方 publish.json `excluded` 或内部文件规则 |
| 地图原始数据（data/，.geojson.xz） | 3 | 19.26 MB | 见下方 publish.json `excluded` 或内部文件规则 |
| 交付压缩包（根目录 .zip） | 3 | 63.43 MB | 见下方 publish.json `excluded` 或内部文件规则 |
| 内部状态日志（.dsh-acl-recovery/） | 1 | 6.5 KB | 见下方 publish.json `excluded` 或内部文件规则 |
| 内部工具目录（_inventory/） | 1 | 2.9 KB | 见下方 publish.json `excluded` 或内部文件规则 |

publish.json 中声明的 4 个整体排除条目：

| 条目 | 说明 | 声明体积 |
| --- | --- | ---: |
| 仿真原始输出 | jilong 的 86 个 .plt（单文件最大 2.0 GB）、hitran_slant 的 .npz/.par、各项目的 hapi_db 谱线库共约 13.5 GB，远超 GitHub 单文件 100 MB 上限，全部留在本地。 | 13.04 GB |
| 交付压缩包 | 3 个 .zip 交付包（共 66 MB）与 zip 内容重复，不进版本库。 | 65.90 MB |
| 缓存与内部状态 | photo-journal 的 .cache / .npm-cache / node_modules（656 MB 中的绝大部分）、__pycache__、.dsh-acl-recovery 内部日志、_asar_session_status.txt 等临时文件，不适合公开。 | 625.61 MB |
| 地图原始数据 | data/ 下的 .geojson.xz 与 out/ 下的 SVG 是可由脚本重新生成的中间数据（19 MB + 12 MB）。 | 29.66 MB |

## 备注

- 本仓库体积约 205.32 MB，所有文件均 < GitHub 单文件上限 100 MB。
- 每组发布体积均不超过对应上限（受保护文档/源码不受上限裁剪）。
- 索引封面校验：`data/projects.json` 声明的 14 个 cover 中 14 个已确认存在于发布副本。
- 发布副本只含可公开的代码、文档与小体积素材；原始仿真数据、交付压缩包、缓存与本机路径记录都留在本地。

## 发布前预检

扫描范围：站点全部文件（4488 个，其中文本 1438 个）。

| 检查项 | 结果 |
| --- | --- |
| 单文件 > 50 MB | 通过：0 个 |
| 最大文件 | `works/quantum-tunneling/animations/tunneling_above_barrier.gif`（7.87 MB） |
| 疑似密钥（token/password/私钥头等） | 通过：0 处 |
| 含 `F:\` 绝对路径的文本文件 | 278 个（属源工作区记录，不含敏感信息，未修改） |
| `.env` / 密钥文件 | 通过：0 个 |

含 `F:\` 绝对路径最多的文件（前 10）：

- `works/whale-chan-research/交接文档.md`（9 处）
- `works/dsh-live-console/README.md`（6 处）
- `tools/make_docs.py`（5 处）
- `README.md`（4 处）
- `works/infrared-detect-v21/06_进度看板/README.md`（4 处）
- `works/infrared-limit-v30/00_构建脚本/开发过程/历史封存/重制实施规范.md`（4 处）
- `works/navwarn-verify/diag.py`（4 处）
- `works/progress-board/README.md`（4 处）
- `SPEC.md`（3 处）
- `works/atmo-classify/报告/build_formal_report.py`（3 处）

未发现疑似密钥；详细结果见本机 tools/preflight.json（不随站点发布）。
