# -*- coding: utf-8 -*-
"""S0 收尾：保存探针产物、清理软件目录、关闭软件、写结论。"""
import glob
import os
import shutil

ROOT = r"D:\XGGDCOSSim2"
WS = os.path.join(ROOT, "Data", "WorkSpaceFile")
OUT = r"F:\DeepSeek工作区\_cossim_auto\ir_deploy"
PROBE = os.path.join(OUT, "probe")
os.makedirs(PROBE, exist_ok=True)

# 1) 探针想定存档（若存在）
src = os.path.join(WS, "_probe_atmo.xml")
if os.path.exists(src):
    shutil.copy2(src, os.path.join(PROBE, "_probe_atmo.xml"))
    os.remove(src)
    print("已存档并移除软件目录中的 _probe_atmo.xml")

# 2) 确认关键文件已恢复原始
DB = os.path.join(ROOT, "Data", "SystemBaseFile", "ModelDatabase.xml")
CFG = os.path.join(ROOT, "Data", "config", "pluginMgr", "plugin_prepare_cfg.ini")
print("ModelDatabase 大小:", os.path.getsize(DB), "B (原始 31009)")
print("plugin_cfg 大小:", os.path.getsize(CFG), "B (原始 519)")
t = open(DB, "rb").read().decode("utf-8")
print("传感器条目数:", t.count("<SubSensorInfo"), "(原始 2)")
c = open(CFG, "rb").read().decode("utf-8")
print("ThermalPropertyModel 行:", [l for l in c.splitlines() if "ThermalPropertyModel" in l])
print("AtmosphericModel 行:", [l for l in c.splitlines() if "AtmosphericModel=" in l])

# 3) 生成的空目录（本次仿真无帧）
for d in glob.glob(os.path.join(ROOT, "Data", "RealTimeProcessData", "ImageData", "*")):
    bmps = glob.glob(os.path.join(d, "*.bmp"))
    if not bmps:
        print("空输出目录(可留):", os.path.basename(d))

# 4) 关闭软件
import psutil
for p in psutil.process_iter(["pid", "name"]):
    if "XGCOSSim" in (p.info["name"] or ""):
        p.terminate()
        print("已关闭软件 PID", p.info["pid"])

# 5) 结论文件
rep = os.path.join(OUT, "S0_动态探针结论.md")
open(rep, "w", encoding="utf-8").write("""# S0 动态探针结论：大气数据文件格式

## 做法
1. 从 `XGSchedule.dll` 提取到报错模板：“无法打开文件 / 列数不匹配 / 数据列数 / 与初始化的列数”
   → 证明软件内部有 CSV 式按列解析器。
2. 构造探针想定，把 `TranRadAtmModelFile` 与 `BandAtmTranRadFile` 指向假文件（1 行 1 列）。
3. 依次执行：载入想定 → 仿真准备 → 初始化 → 开始仿真（6 秒）→ 结束仿真，逐段抓日志。

## 结果
| 阶段 | 是否报错 | 日志表现 |
|---|---|---|
| 仿真准备 | 否 | 仅“仿真准备指令执行完毕” |
| 初始化 | 否 | 仅 `SimInit() emit sglDriveSyncSignal` 序列 |
| 开始仿真 | 否 | 仅 `SlotSceneUpdate 帧号…渲染刷新时间` |
| 结束仿真 | 否 | 正常结束 |

**全程没有任何与这两个文件相关的读取/解析日志，也没有“无法打开文件 / 列数不匹配”。**

## 结论
- 在「单机推演」模式下，该环境参数（`AtmMode` / 三类大气数据文件）**不进入渲染计算链**：
  软件不读这些文件，`大气透过率` 恒为 1、`路径辐射/背景辐射` 恒为 0。
- 因此：
  1. 无法通过“喂一个文件”来点亮红外通道；
  2. 也无法用动态报错反推文件格式；
  3. 这些文件很可能只在「注入式/辐射式」硬件在环模式下使用（日志枚举为 “注入式 2：辐射式 3：单机推演”）。
- 结合此前结果（红外帧全黑、遥测辐射列恒 0、无 IR 纹理），
  结论是：**该部署不具备可用的红外成像链路，需厂家提供完整数据与支持。**

## 建议
1. 向厂家索要：`TranRadAtmModelFile`（MODTRAN 大气卡片）、`BandAtmTranRadFile`（波段 1 大气辐射传输数据）、以及红外纹理/热物性数据；
2. 询问是否需切换到「注入式/辐射式」模式才能启用辐射链路；
3. 若拿不到，红外部分继续使用本项目 V3.0 的 HITRAN 自建链路（已交付）。
""")
print("结论文件:", rep)
