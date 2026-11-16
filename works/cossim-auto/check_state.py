# -*- coding: utf-8 -*-
"""按 GB18030 读取 COSSIM 日志并检查仿真状态。"""
import glob, os, time

LOG = r"D:\XGGDCOSSim2\bin\Logs\Log.log"
RT = r"D:\XGGDCOSSim2\Data\RealTimeProcessData"

raw = open(LOG, "rb").read()
for enc in ("gb18030", "utf-8"):
    try:
        txt = raw.decode(enc)
        print(f"[{enc}] 解码成功, {len(txt)} 字符")
        break
    except Exception as e:
        print(f"[{enc}] 失败: {e}")

lines = txt.splitlines()
print("总行数:", len(lines))
print("--- 最近含关键词的行 ---")
keys = ["仿真准备", "初始化指令", "开始仿真", "结束仿真", "仿真退出", "帧号"]
hit = [l for l in lines if any(k in l for k in keys)]
for l in hit[-12:]:
    print("  ", l.strip()[:150])

runs = sorted(glob.glob(os.path.join(RT, "ImageData", "*")))
print("\n输出目录:", [os.path.basename(r) for r in runs])
for r in runs[-2:]:
    bmps = glob.glob(os.path.join(r, "*.bmp"))
    print(f"  {os.path.basename(r)}: {len(bmps)} 帧")
