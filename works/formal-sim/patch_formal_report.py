# -*- coding: utf-8 -*-
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

OLD = Path(r"F:\DeepSeek工作区\大气工况分类图\报告\build_report.py")
BLOCK = Path(r"F:\DeepSeek工作区\正式仿真\formal_sections_block.py.txt")
OUT = Path(r"F:\DeepSeek工作区\大气工况分类图\报告\build_formal_report.py")

text = OLD.read_text(encoding="utf-8")
block = BLOCK.read_text(encoding="utf-8")

text = text.replace(
    'OUT = os.path.join(HERE, "红外大气参数化与成像效果评估_阶段报告.docx")',
    'OUT = os.path.join(HERE, "红外大气参数化与成像效果评估_正式报告_V1.0.docx")',
)
text = text.replace('("报告版本", "V0.9（阶段讨论稿）"),', '("报告版本", "V1.0（正式报告）"),')
text = text.replace('("编制日期", "2026 年 10 月"),', '("编制日期", "2026 年 11 月"),')
text = text.replace('("报告性质", "方法研究与可行性验证（非装备定型依据）"),',
                    '("报告性质", "正式研究报告：方法、算例与数据质量评估"),')
text = text.replace('r = p.add_run("阶 段 研 究 报 告")', 'r = p.add_run("正 式 研 究 报 告")')

new_abs = (
    "本报告在阶段研究基础上完成正式化升级。报告首先系统梳理 XGGDCOSSim2 光电环境仿真软件的内部设置参数，"
    "包括 14 类背景/场景类型、6 个目标模型（含 OSG 包围盒尺寸）、默认中波红外显示参数，以及 Q2 中波/长波大气辐射传输查找表；"
    "针对软件不提供完整红外辐射传感器的现状，报告以软件波段、视场、分辨率、帧率为锚点，定义了包含口径、焦距、像元、IFOV、NETD、积分时间与 MTF 链的红外传感器模型。"
    "在此基础上给出正式场景矩阵与两套仿真引擎：面向软件 Q2 大气样本的城市背景 Q2-LUT 引擎，以及面向其余背景/目标类型的参数化引擎。"
    "基于 Q2 数据完成了 F16/F22 空中目标在 3.7–4.8 μm、洛阳城市大气、目标高度 500/1000 m、传感器高度 5000 m 下的视在温差与任务概率算例："
    "ΔT_app 约 4.2–38.2 K；20 km 探测概率约 0.84–0.95；识别与辨认的 50% 距离分别约 8.7–11.0 km 与 4.9–6.9 km。"
    "报告同时指出软件数据在能见度单位、气溶胶类型、视点高度上限、长波波段口径、RT 卡片缺失与模型尺寸等方面的质量问题，并给出数据补充、传感器实测与模型验证建议。"
)
pattern = re.compile(r'body\("围绕红外目标探测.*?下一步工作建议。?"\)', re.S)
if not pattern.search(text):
    raise SystemExit("abstract pattern not found")
text = pattern.sub('body("' + new_abs + '")', text, count=1)

start = text.index('heading("7  结论与下一步", 1)')
end = text.index("# ---------------- appendix A ----------------")
text = text[:start] + block + "\n\n" + text[end:]

OUT.write_text(text, encoding="utf-8")
print("written", OUT)
