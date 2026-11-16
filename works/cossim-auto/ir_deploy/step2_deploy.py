# -*- coding: utf-8 -*-
"""Step 2: 注入中波红外传感器 + 打开热特性/大气/材质插件 + 生成 IR 想定。"""
import os
import re
import datetime

ROOT = r"D:\XGGDCOSSim2"
DB = os.path.join(ROOT, "Data", "SystemBaseFile", "ModelDatabase.xml")
CFG = os.path.join(ROOT, "Data", "config", "pluginMgr", "plugin_prepare_cfg.ini")
PLAN_IN = r"F:\DeepSeek工作区\_cossim_auto\geom\..\ir_deploy\Anchor_F16_yngd_base.xml"
OUT = r"F:\DeepSeek工作区\_cossim_auto\ir_deploy"
PLAN_OUT = os.path.join(ROOT, "Data", "WorkSpaceFile", "Anchor_F16_yngd_IR.xml")
os.makedirs(OUT, exist_ok=True)

# ---------- A. ModelDatabase：复制 Id=0 的可见光传感器，改成中波红外 Id=2 ----------
db = open(DB, "rb").read().decode("utf-8")
m = re.search(r'(<SubSensorInfo remark="传感器ID" Id="0">.*?</SubSensorInfo>)', db, re.S)
assert m, "未找到 Id=0 传感器块"
blk = m.group(1)

ir = blk
ir = ir.replace('Id="0"', 'Id="2"', 1)
ir = ir.replace('<SensorType remark="类型" tips="4:可见光" value="4" />',
                '<SensorType remark="类型" tabs="1:中波红外 2:长波红外-制冷 3:长波红外-非制冷 4:可见光 5:短波" value="1" />')
ir = ir.replace('value="可见光传感器"', 'value="中波红外_测试"')
ir = ir.replace('value="可见光传感器_1"', 'value="中波红外_测试"')
ir = ir.replace('<BandMin remark="波段下限" type="double" decimals="1" min="0" max="999" value="0.4" />',
                '<BandMin remark="波段下限" type="double" decimals="1" min="0" max="999" value="3.7" />')
ir = ir.replace('<BandMax remark="波段上限" type="double" decimals="1" min="0" max="999" value="0.8" />',
                '<BandMax remark="波段上限" type="double" decimals="1" min="0" max="999" value="4.8" />')
ir = ir.replace('<FovH remark="水平视场角" type="double" decimals="2" min="0" max="180" value="40" />',
                '<FovH remark="水平视场角" type="double" decimals="2" min="0" max="180" value="3.75" />')
ir = ir.replace('<FovV remark="垂直视场角" type="double" decimals="2" min="0" max="180" value="30" />',
                '<FovV remark="垂直视场角" type="double" decimals="2" min="0" max="180" value="3" />')
ir = ir.replace('<EffectFovH remark="场景产生器水平视场角" type="double" decimals="2" min="0" max="180" value="40" />',
                '<EffectFovH remark="场景产生器水平视场角" type="double" decimals="2" min="0" max="180" value="3.75" />')
ir = ir.replace('<EffectFovV remark="场景产生器垂直视场角" type="double" decimals="2" min="0" max="180" value="30" />',
                '<EffectFovV remark="场景产生器垂直视场角" type="double" decimals="2" min="0" max="180" value="3" />')
ir = ir.replace('<Colourful remark="是否彩色" tips="1:彩色 2:灰度 3:全波段" value="2" />',
                '<Colourful remark="是否彩色" tips="1:彩色 2:灰度 3:全波段" value="2" />')

assert "中波红外_测试" in ir and 'value="3.7"' in ir and 'value="3.75"' in ir
new_db = db.replace(blk, blk + "\n        " + ir, 1)
open(DB, "wb").write(new_db.encode("utf-8"))
print("A. ModelDatabase 已注入 IR 传感器 Id=2（原文件 %d B -> %d B）" % (len(db), len(new_db)))

# ---------- B. 插件开关 ----------
cfg = open(CFG, "rb").read().decode("utf-8")
orig_cfg = cfg
cfg = re.sub(r'(?m)^MaterialModel=0\s*$', 'MaterialModel=1', cfg)
cfg = re.sub(r'(?m)^ThermalPropertyModel=0\s*$', 'ThermalPropertyModel=1', cfg)
cfg = re.sub(r'(?m)^AtmosphericModel=0\s*$', 'AtmosphericModel=2', cfg)
open(CFG, "wb").write(cfg.encode("utf-8"))
print("B. 插件开关:", "MaterialModel=1" in cfg, "ThermalPropertyModel=1" in cfg, "AtmosphericModel=2" in cfg)

# ---------- C. 生成 IR 想定 ----------
base_src = r"F:\DeepSeek工作区\红外目标探测仿真_整合交付_V2.1\05_软件参数提取\_decoded\Data__SystemBaseFile__DefaultPlanFile.xml.utf8.txt"
s = open(base_src, encoding="utf-8").read()
repl = [
    ('<BgType remark="背景类型" type="unsigned char" value="1" read="1">',
     '<BgType remark="背景类型" type="unsigned char" value="9" read="1">'),
    ('value="桃园机场"', 'value="与那国岛"'),
    ('<BgSpaceLength remark="背景范围-长" type="double" unit="m" min="0" max="1000000" value="300" read="1" />',
     '<BgSpaceLength remark="背景范围-长" type="double" unit="m" min="0" max="1000000" value="100000" read="1" />'),
    ('<BgSpaceWidth remark="背景范围-宽" type="double" unit="m" min="0" max="1000000" value="300" read="1" />',
     '<BgSpaceWidth remark="背景范围-宽" type="double" unit="m" min="0" max="1000000" value="100000" read="1" />'),
    ('value="ah64直升机"', 'value="F16战斗机"'),
    ('<TargetType remark="目标类型" type="unsigned char" value="2" read="1" >',
     '<TargetType remark="目标类型" type="unsigned char" value="5" read="1" >'),
    ('<EntityPosZ remark="实体坐标-天" type="double" unit="m" min="-1000000" max="1000000" value="10" />',
     '<EntityPosZ remark="实体坐标-天" type="double" unit="m" min="-1000000" max="1000000" value="500" />'),
    ('value="126.1234567"', 'value="122.9875683"'),
    ('value="45.1234567"', 'value="24.4562142"'),
    # 传感器指向新模型
    ('<ModelID remark="模型ID" type="unsigned short" value="0" />',
     '<ModelID remark="模型ID" type="unsigned short" value="2" />'),
    ('<SensorModelName remark="传感器型号名称" type="char[64]" value="中波红外" read="1" />',
     '<SensorModelName remark="传感器型号名称" type="char[64]" value="中波红外_测试" read="1" />'),
    ('<SensorDispName remark="传感器显示名称" type="char[128]" value="中波红外" read="1" />',
     '<SensorDispName remark="传感器显示名称" type="char[128]" value="中波红外_测试" read="1" />'),
    # 成像波段：1 可见光 -> 4 中波红外成像
    ('<ImagBand1Class remark="波段1类型" type="unsigned char" value="1" read="1">',
     '<ImagBand1Class remark="波段1类型" type="unsigned char" value="4" read="1">'),
]
for a, b in repl:
    if a not in s:
        print("   [警告] 未找到:", a[:60])
    s = s.replace(a, b)
open(PLAN_OUT, "wb").write(s.encode("gb18030"))
print("C. IR 想定已写入:", PLAN_OUT, os.path.getsize(PLAN_OUT), "B")
print("   校验: '中波红外_测试'", "中波红外_测试" in s,
      "| ImagBand1=4", 'value="4" read="1">' in s)
