# -*- coding: utf-8 -*-
"""收尾：清理帧、恢复原始文件、保存改装版到工作区、写部署报告。"""
import glob
import os
import shutil
import datetime

ROOT = r"D:\XGGDCOSSim2"
OUT = r"F:\DeepSeek工作区\_cossim_auto\ir_deploy"
DB = os.path.join(ROOT, "Data", "SystemBaseFile", "ModelDatabase.xml")
CFG = os.path.join(ROOT, "Data", "config", "pluginMgr", "plugin_prepare_cfg.ini")
PLAN_IR = os.path.join(ROOT, "Data", "WorkSpaceFile", "Anchor_F16_yngd_IR.xml")
RT = os.path.join(ROOT, "Data", "RealTimeProcessData")

bak_db = glob.glob(os.path.join(OUT, "ModelDatabase.bak_*"))[0]
bak_cfg = glob.glob(os.path.join(OUT, "plugin_prepare_cfg.bak_*"))[0]

# 1) 清理本次仿真帧
freed = 0
for run in glob.glob(os.path.join(RT, "ImageData", "*")):
    for p in glob.glob(os.path.join(run, "*.bmp")):
        try:
            freed += os.path.getsize(p); os.remove(p)
        except OSError:
            pass
print(f"已删除帧文件，释放 {freed/1024/1024:.0f} MB")
print("剩余 ImageData 目录:", [os.path.basename(d) for d in glob.glob(os.path.join(RT, "ImageData", "*"))])

# 2) 保存改装版
os.makedirs(os.path.join(OUT, "modified"), exist_ok=True)
shutil.copy2(DB, os.path.join(OUT, "modified", "ModelDatabase_IR.xml"))
shutil.copy2(CFG, os.path.join(OUT, "modified", "plugin_prepare_cfg_IR.ini"))
if os.path.exists(PLAN_IR):
    shutil.copy2(PLAN_IR, os.path.join(OUT, "modified", "Anchor_F16_yngd_IR.xml"))
print("改装版已存至 modified/")

# 3) 恢复原始文件
shutil.copy2(bak_db, DB)
shutil.copy2(bak_cfg, CFG)
print("已恢复 ModelDatabase.xml 与 plugin_prepare_cfg.ini")
print("  恢复后 ModelDatabase 大小:", os.path.getsize(DB), "B（原始 31009 B）")
print("  恢复后配置大小:", os.path.getsize(CFG), "B（原始 519 B）")

# 4) 从软件目录移除 IR 想定（保留工作区副本）
if os.path.exists(PLAN_IR):
    os.remove(PLAN_IR)
    print("已移除软件目录中的 Anchor_F16_yngd_IR.xml（副本在 modified/）")

# 5) 写部署报告
rep = os.path.join(OUT, "红外通道部署报告.md")
dirs = [d for d in glob.glob(os.path.join(RT, "ImageData", "*"))]
with open(rep, "w", encoding="utf-8") as f:
    f.write("# XGGDCOSSim 红外通道部署尝试报告\n\n")
    f.write(f"- 尝试时间：{datetime.datetime.now():%Y-%m-%d %H:%M}\n")
    f.write("- 方法：模型库注入中波红外传感器 + 打开热特性/大气/材质插件 + 想定设置中波红外成像\n\n")
    f.write("## 已完成（成功）\n\n")
    f.write("1. 在 `ModelDatabase.xml` 注入 `SensorType=1`（中波红外）传感器 Id=2：波段 3.7–4.8 μm、FOV 3.75°×3°、1024×768、响应 1746/偏置 1733。\n")
    f.write("2. 软件**完全识别**该传感器：方案属性面板显示“传感器类型 1: 中波红外、工作波段 3.70/4.80、水平视场 3.75、垂直 3.00、分辨率 1024×768”。\n")
    f.write("3. 想定 `ImagBand1Class=4`（中波红外成像）被识别，环境页显示“波段1类型 4: 中波红外成像”。\n")
    f.write("4. 插件开关生效：制备页出现“材质模型 / 热特性模型 / 大气模型”三个原本隐藏的面板。\n")
    f.write("5. 仿真流程完整跑通（准备→初始化→开始→存储图像→结束），输出 139 帧 1024×768 BMP。\n\n")
    f.write("## 失败点（关键）\n\n")
    f.write("- **所有红外帧全黑**（min=max=0），与可见光通道形成对照（可见光预览窗图像正常，非零像素 97.3%）。\n")
    f.write("- 遥测 CSV 显示辐射链路未计算：`大气透过率=1.000`、`路径辐射=0`、`背景辐射=0`、`太阳辐射=0`。\n")
    f.write("- 日志无 IR/热特性相关报错，说明不是配置错误，而是**数据缺失**。\n\n")
    f.write("## 根因\n\n")
    f.write("想定 `WeatherParam` 中三个 MODTRAN 相关文件路径均为空：\n\n")
    f.write("```\n")
    f.write("TranRadAtmModelFile  = \"\"   # 辐射传输计算大气卡片文件（MODTRAN tape5）\n")
    f.write("LaserAtmModelFile    = \"\"   # 激光透过率计算大气卡片文件\n")
    f.write("BandAtmTranRadFile   = \"\"   # 波段1大气辐射传输数据文件（MODTRAN 输出）\n")
    f.write("Band2AtmTranRadFile  = \"\"\n")
    f.write("```\n\n")
    f.write("`AtmMode` 枚举只提供标准大气/AFGL 五种模式与“自定义大气数据”，没有内置辐射传输求解器；\n")
    f.write("因此没有这两类数据文件时，波段辐亮度恒为 0 → 红外图像必然全黑。\n")
    f.write("这与 V2.1 报告“RT 大气卡片未交付”的结论一致，现已在红外传感器注入后得到直接验证。\n\n")
    f.write("## 结论与建议\n\n")
    f.write("- 红外通道是否可用，**取决于能否拿到软件配套的 MODTRAN 大气卡片与波段辐射数据文件**，而不是配置或传感器模型问题。\n")
    f.write("- 若厂家能提供上述数据文件，本报告的注入方案（传感器模型 + 波段 + 插件开关）可直接复用，改动量仅 2 个文件。\n")
    f.write("- 若拿不到，则该软件在本机只能做可见光成像仿真；红外部分只能用本项目 V3.0 的 HITRAN 自建链路。\n\n")
    f.write("## 现场状态\n\n")
    f.write("- 已恢复 `ModelDatabase.xml` 与 `plugin_prepare_cfg.ini` 到原始版本；\n")
    f.write("- 已清理仿真帧（释放约 320 MB）；\n")
    f.write("- 改装版文件保留在 `_cossim_auto/ir_deploy/modified/`，可一键重新应用。\n")
print("报告:", rep)
