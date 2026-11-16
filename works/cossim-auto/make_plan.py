# -*- coding: utf-8 -*-
"""由软件自带 DefaultPlanFile 派生一份可运行想定：与那国岛背景 + F16 空中目标。

只改 5 处字段（其余保持软件默认），输出 GB18030 到 Data\\WorkSpaceFile。
"""
import os
import shutil

SRC = r"F:\DeepSeek工作区\红外目标探测仿真_整合交付_V2.1\05_软件参数提取\_decoded\Data__SystemBaseFile__DefaultPlanFile.xml.utf8.txt"
DST = r"D:\XGGDCOSSim2\Data\WorkSpaceFile\Anchor_F16_yngd.xml"

s = open(SRC, encoding="utf-8").read()

repl = [
    # 背景类型：1 沙漠 → 9 海岛（与那国岛在模型库中 Type=9 / Class=1）
    ('<BgType remark="背景类型" type="unsigned char" value="1" read="1">',
     '<BgType remark="背景类型" type="unsigned char" value="9" read="1">'),
    # 背景名称
    ('value="桃园机场"', 'value="与那国岛"'),
    # 背景范围 300 m → 100000 m（与那国岛 100 km×100 km）
    ('<BgSpaceLength remark="背景范围-长" type="double" unit="m" min="0" max="1000000" value="300" read="1" />',
     '<BgSpaceLength remark="背景范围-长" type="double" unit="m" min="0" max="1000000" value="100000" read="1" />'),
    ('<BgSpaceWidth remark="背景范围-宽" type="double" unit="m" min="0" max="1000000" value="300" read="1" />',
     '<BgSpaceWidth remark="背景范围-宽" type="double" unit="m" min="0" max="1000000" value="100000" read="1" />'),
    # 目标型号：ah64 → F16，目标类型 2 地面运动 → 5 空中飞机
    ('value="ah64直升机"', 'value="F16战斗机"'),
    ('<TargetType remark="目标类型" type="unsigned char" value="2" read="1" >',
     '<TargetType remark="目标类型" type="unsigned char" value="5" read="1" >'),
    # 目标高度 10 m → 500 m（空中目标）
    ('<EntityPosZ remark="实体坐标-天" type="double" unit="m" min="-1000000" max="1000000" value="10" />',
     '<EntityPosZ remark="实体坐标-天" type="double" unit="m" min="-1000000" max="1000000" value="500" />'),
    # 地理原点：默认 126.1234567E / 45.1234567N 在地图外，改为与那国岛中心
    ('value="126.1234567"', 'value="122.9875683"'),
    ('value="45.1234567"', 'value="24.4562142"'),
    # 成像波段：默认 1=可见光成像，与中波红外传感器不一致 → 2=中波红外成像
    ('<ImagBand1Class remark="波段1类型" type="unsigned char" value="1" read="1">',
     '<ImagBand1Class remark="波段1类型" type="unsigned char" value="2" read="1">'),
    # 背景建模/材质温度数据路径（与那国岛红外渲染需要，取自模型库 BackgroundModelingPath/MaterialPath）
    ('<BgModelResultFile remark="地面背景建模结果文件路径" type="char[256]" value="" visible="0" read="1" />',
     '<BgModelResultFile remark="地面背景建模结果文件路径" type="char[256]" value="/background/city/FLT" visible="0" read="1" />'),
    ('<BgMaterialTemperatureDataFile remark="地面背景材质温度数据文件路径" type="char[256]" value="" visible="0" read="1" />',
     '<BgMaterialTemperatureDataFile remark="地面背景材质温度数据文件路径" type="char[256]" value="/background/city/FLT/texture" visible="0" read="1" />'),
]

for a, b in repl:
    n = s.count(a)
    print(f"替换 {n:2d} 处: {a[:58]}")
    s = s.replace(a, b)

os.makedirs(os.path.dirname(DST), exist_ok=True)
with open(DST, "w", encoding="gb18030", errors="replace") as f:
    f.write(s)
print("written:", DST, os.path.getsize(DST), "bytes")

# 回读校验
back = open(DST, encoding="gb18030").read()
for key in ["与那国岛", "F16战斗机", 'value="9" read="1"', 'value="100000" read="1"']:
    print(f"  回读包含 {key!r}:", key in back)
