# -*- coding: utf-8 -*-
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

P = Path(r"F:\DeepSeek工作区\大气工况分类图\报告\build_formal_report.py")
BLOCK = Path(r"F:\DeepSeek工作区\正式仿真\formal_sections_actual_block.py.txt")

text = P.read_text(encoding="utf-8")
block = BLOCK.read_text(encoding="utf-8")

# version / output rename
text = text.replace("正式报告_V1.0", "正式报告_V1.1")
text = text.replace("正式报告 V1.0", "正式报告 V1.1")
text = text.replace('("报告版本", "V1.0（正式报告）"),', '("报告版本", "V1.1（正式报告，按软件实际资源重写）"),')
text = text.replace('r = hp.add_run("红外目标探测大气参数化与成像效果评估  ·  正式报告 V1.1")',
                    'r = hp.add_run("红外目标探测大气参数化与成像效果评估  ·  正式报告 V1.1")')

new_abs = (
    "本报告按“采用软件内实际存在的工况和目标参数”重写。报告以 XGGDCOSSim2 默认想定（编号 2）为时空与气象基准，"
    "采用软件唯一实际背景模型与那国岛、模型库中实际存在的 6 个目标模型（F16、F22、尼米兹级航母、阿利伯克级驱逐舰、悍马车、爱国者导弹发射车），"
    "以及默认气象参数（晴天、15 °C、50%RH、1013 hPa、10 km、干净大陆、美国标准大气、不考虑湍流）；"
    "软件不含辐射传感器，报告以默认中波显示参数为锚点定义 3.7–4.8 μm 传感器模型（平台 8000 m、FOV 3.75°×3°、1024×768、IFOV 63.9 μrad、NETD 25 mK）。"
    "基于上述实际资源完成 3.7–4.8 μm 正式算例：路径波段平均透过率约 0.62→0.45；F16 视在温差在 20/40/60 °C 热状态约 −0.9/9.9–12.8/22.3–28.1 K；"
    "识别/辨认 50% 距离 F16 约 10.95/3.24 km、F22 约 14.84/6.96 km、爱国者发射车约 18.53/9.50 km，航母/驱逐舰 >20 km，悍马车识别/辨认 <0.5。"
    "报告同时说明默认想定背景/目标占位、Q2 大气样本条件不一致、RT 卡片缺失、无辐射传感器参数等数据质量问题及后续工作。"
)
pat_abs = re.compile(r'body\("本报告在阶段研究基础上完成正式化升级.*?并给出数据补充、传感器实测与模型验证建议。"\)', re.S)
if not pat_abs.search(text):
    raise SystemExit("abstract not found")
text = pat_abs.sub('body("' + new_abs + '")', text, count=1)

# report note
old_note = (
    'r = p.add_run("报告说明：本报告在阶段研究基础上完成正式化升级。第 3 节给出大气参数体系、工况范围与区域参考；"\n'
    '              "第 4–6 节保留阶段基线（视在温差、湍流分辨率、P_d 演示）；第 7 节给出软件内部设置参数提取、正式场景矩阵与传感器模型；"\n'
    '              "第 8 节给出基于软件 Q2 大气数据的城市背景正式算例；第 9 节汇总结论、数据质量问题与后续工作。")'
)
new_note = (
    'r = p.add_run("报告说明：本版按软件内实际资源重写。第 3 节给出大气参数体系与工况范围；"\n'
    '              "第 4–6 节为方法基线（视在温差、湍流分辨率、P_d 演示）；第 7 节给出软件实际想定、背景、目标模型、默认气象与传感器参数；"\n'
    '              "第 8 节给出 6 个实际目标在 3.7–4.8 μm 下的正式算例；第 9 节总结结论、数据质量问题与后续工作。")'
)
if old_note not in text:
    raise SystemExit("report note not found")
text = text.replace(old_note, new_note)

start = text.index('heading("7  软件内部设置参数与正式仿真方案", 1)')
end = text.index("# ---------------- appendix A ----------------")
text = text[:start] + block + "\n\n" + text[end:]

# appendix: append actual assets after the last Q2 formal row
anchor = '    ["进度看板\\\\index.html / progress.json", "实时仿真进度看板"],'
if anchor in text:
    extra = (
        '    ["正式仿真\\\\make_software_actual_case.py", "软件实际资源算例脚本"],\n'
        '    ["正式仿真\\\\results\\\\software_actual_*.png", "图 6–8 实际资源算例图"],\n'
        '    ["正式仿真\\\\results\\\\software_actual_case_results.csv", "6 个实际目标全距离结果"],\n'
        '    ["正式仿真\\\\results\\\\software_actual_summary.csv", "10 km 与 50% 距离汇总"],\n'
    )
    text = text.replace(anchor, anchor + "\n" + extra.rstrip("\n"), 1)

P.write_text(text, encoding="utf-8")
print("patched", P)
