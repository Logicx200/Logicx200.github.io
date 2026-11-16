# -*- coding: utf-8 -*-
"""Build the stage report DOCX (Chinese technical report) for the IR atmospheric study."""
import os

from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(HERE, "红外大气参数化与成像效果评估_阶段报告.docx")

BODY_FONT = "宋体"
HEAD_FONT = "黑体"
LATIN_FONT = "Times New Roman"


def set_run_font(run, size=10.5, bold=False, color=None, east=HEAD_FONT, latin=LATIN_FONT):
    run.font.name = latin
    run.font.size = Pt(size)
    run.font.bold = bold
    if color is not None:
        run.font.color.rgb = RGBColor(*color)
    rPr = run._element.get_or_add_rPr()
    rFonts = rPr.rFonts
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rPr.append(rFonts)
    rFonts.set(qn("w:ascii"), latin)
    rFonts.set(qn("w:hAnsi"), latin)
    rFonts.set(qn("w:eastAsia"), east)


def shade(cell, hex_color):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_color)
    tcPr.append(shd)


def bottom_border(p, color="1F4E79", sz="8"):
    pPr = p._p.get_or_add_pPr()
    pBdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), sz)
    bottom.set(qn("w:space"), "4")
    bottom.set(qn("w:color"), color)
    pBdr.append(bottom)
    pPr.append(pBdr)


def add_field(paragraph, instr, placeholder=""):
    run = paragraph.add_run()
    fld1 = OxmlElement("w:fldChar")
    fld1.set(qn("w:fldCharType"), "begin")
    it = OxmlElement("w:instrText")
    it.set(qn("xml:space"), "preserve")
    it.text = instr
    fld2 = OxmlElement("w:fldChar")
    fld2.set(qn("w:fldCharType"), "separate")
    t = OxmlElement("w:t")
    t.text = placeholder
    fld3 = OxmlElement("w:fldChar")
    fld3.set(qn("w:fldCharType"), "end")
    run._r.append(fld1)
    run._r.append(it)
    run._r.append(fld2)
    run._r.append(t)
    run._r.append(fld3)
    return run


doc = Document()

# ---------------- page & styles ----------------
sec = doc.sections[0]
sec.page_width = Cm(21.0)
sec.page_height = Cm(29.7)
sec.top_margin = Cm(2.3)
sec.bottom_margin = Cm(2.2)
sec.left_margin = Cm(2.4)
sec.right_margin = Cm(2.4)
sec.header_distance = Cm(1.2)
sec.footer_distance = Cm(1.3)
sec.different_first_page_header_footer = True

normal = doc.styles["Normal"]
normal.font.name = LATIN_FONT
normal.font.size = Pt(10.5)
normal.element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), BODY_FONT)
pf = normal.paragraph_format
pf.line_spacing = 1.4
pf.space_after = Pt(3)
pf.space_before = Pt(0)

for name, size, before, after in [
    ("Heading 1", 15, 18, 8),
    ("Heading 2", 12.5, 12, 6),
    ("Heading 3", 11, 10, 4),
]:
    st = doc.styles[name]
    st.font.name = HEAD_FONT
    st.font.size = Pt(size)
    st.font.bold = True
    st.font.color.rgb = RGBColor(0x1F, 0x3A, 0x5F)
    rPr = st.element.get_or_add_rPr()
    rPr.rFonts.set(qn("w:eastAsia"), HEAD_FONT)
    st.paragraph_format.space_before = Pt(before)
    st.paragraph_format.space_after = Pt(after)
    st.paragraph_format.keep_with_next = True

# header / footer
header = sec.header
hp = header.paragraphs[0]
hp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
r = hp.add_run("红外目标探测大气参数化与成像效果评估  ·  阶段报告")
set_run_font(r, size=8, color=(0x66, 0x66, 0x66), east=BODY_FONT)
bottom_border(hp, color="BFBFBF", sz="4")

footer = sec.footer
fp = footer.paragraphs[0]
fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = fp.add_run("第 ")
set_run_font(r, size=9, color=(0x59, 0x59, 0x59), east=BODY_FONT)
add_field(fp, " PAGE ", "1")
r = fp.add_run(" 页 / 共 ")
set_run_font(r, size=9, color=(0x59, 0x59, 0x59), east=BODY_FONT)
add_field(fp, " NUMPAGES ", "1")
r = fp.add_run(" 页")
set_run_font(r, size=9, color=(0x59, 0x59, 0x59), east=BODY_FONT)


# ---------------- content helpers ----------------
def body(text, indent=True, size=10.5, bold=False, color=None,
         align=WD_ALIGN_PARAGRAPH.JUSTIFY, after=3, before=0):
    p = doc.add_paragraph()
    p.alignment = align
    p.paragraph_format.space_after = Pt(after)
    p.paragraph_format.space_before = Pt(before)
    p.paragraph_format.line_spacing = 1.4
    if indent:
        p.paragraph_format.first_line_indent = Pt(size * 2)
    run = p.add_run(text)
    set_run_font(run, size=size, bold=bold, color=color, east=BODY_FONT)
    return p


def bullet(text, size=10.5):
    p = doc.add_paragraph(style="List Bullet")
    p.paragraph_format.space_after = Pt(2)
    p.paragraph_format.line_spacing = 1.35
    run = p.add_run(text)
    set_run_font(run, size=size, east=BODY_FONT)
    return p


def heading(text, level=1):
    h = doc.add_heading(text, level=level)
    for r in h.runs:
        set_run_font(r, size={1: 15, 2: 12.5, 3: 11}[level], bold=True,
                     color=(0x1F, 0x3A, 0x5F), east=HEAD_FONT)
    return h


def caption(text, before=2, after=8):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(before)
    p.paragraph_format.space_after = Pt(after)
    run = p.add_run(text)
    set_run_font(run, size=9, bold=False, color=(0x40, 0x40, 0x40), east=BODY_FONT)
    return p


def figure(path, width_cm, cap):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(2)
    run = p.add_run()
    run.add_picture(path, width=Cm(width_cm))
    caption(cap)


def table(data, widths, cap, header=True, font=9, align_center=True):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(6)
    p.paragraph_format.space_after = Pt(2)
    p.paragraph_format.keep_with_next = True
    run = p.add_run(cap)
    set_run_font(run, size=9.2, bold=True, color=(0x1F, 0x3A, 0x5F), east=BODY_FONT)
    t = doc.add_table(rows=len(data), cols=len(data[0]))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.autofit = False
    for i, row in enumerate(data):
        for j, val in enumerate(row):
            cell = t.cell(i, j)
            cell.width = Cm(widths[j])
            cell.text = ""
            cp = cell.paragraphs[0]
            cp.alignment = WD_ALIGN_PARAGRAPH.CENTER if (align_center and j > 0) else WD_ALIGN_PARAGRAPH.LEFT
            cp.paragraph_format.space_after = Pt(1)
            cp.paragraph_format.space_before = Pt(1)
            cp.paragraph_format.line_spacing = 1.1
            rr = cp.add_run(str(val))
            set_run_font(rr, size=font, bold=(header and i == 0), east=BODY_FONT)
            if header and i == 0:
                shade(cell, "DCE6F1")
    for j, w in enumerate(widths):
        t.columns[j].width = Cm(w)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)


def page_break():
    doc.add_page_break()


# ---------------- cover ----------------
for _ in range(4):
    doc.add_paragraph()

p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = p.add_run("阶 段 研 究 报 告")
set_run_font(r, size=12, bold=False, color=(0x6C, 0x6C, 0x6C), east=HEAD_FONT)

p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
p.paragraph_format.space_before = Pt(18)
r = p.add_run("红外目标探测大气参数化\n与成像效果评估方法研究")
set_run_font(r, size=24, bold=True, color=(0x1F, 0x3A, 0x5F), east=HEAD_FONT)

p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
p.paragraph_format.space_before = Pt(16)
r = p.add_run("参数体系 · 工况范围 · 视在温差 · 湍流分辨率 · 探测概率")
set_run_font(r, size=11.5, color=(0x44, 0x44, 0x44), east=BODY_FONT)

line = doc.add_paragraph()
line.alignment = WD_ALIGN_PARAGRAPH.CENTER
line.paragraph_format.space_before = Pt(22)
line.paragraph_format.space_after = Pt(26)
bottom_border(line, color="1F4E79", sz="10")

for label, value in [
    ("报告版本", "V0.9（阶段讨论稿）"),
    ("编制日期", "2026 年 10 月"),
    ("适用项目", "红外目标探测大气影响参数化与成像效果检验"),
    ("报告性质", "方法研究与可行性验证（非装备定型依据）"),
]:
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(6)
    r1 = p.add_run(label + "：")
    set_run_font(r1, size=10.5, bold=True, color=(0x33, 0x33, 0x33), east=BODY_FONT)
    r2 = p.add_run(value)
    set_run_font(r2, size=10.5, color=(0x33, 0x33, 0x33), east=BODY_FONT)

for _ in range(4):
    doc.add_paragraph()

p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = p.add_run("本报告为方法研究与可行性验证稿。报告中的传感器、目标、大气与任务参数含大量假设，\n"
              "结论仅用于说明流程与量级趋势，不作为装备定型、指标考核或作战使用的依据。")
set_run_font(r, size=8.5, color=(0x7F, 0x7F, 0x7F), east=BODY_FONT)
page_break()

# ---------------- abstract ----------------
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
p.paragraph_format.space_before = Pt(6)
p.paragraph_format.space_after = Pt(10)
r = p.add_run("摘  要")
set_run_font(r, size=16, bold=True, color=(0x1F, 0x3A, 0x5F), east=HEAD_FONT)

body("围绕红外目标探测中的大气影响参数化与成像效果检验问题，本报告给出阶段性的方法框架与可行性验证结果。"
     "报告首先建立“输入层—中间层—检验层”三层大气参数体系，明确局地系数谱与路径积分量、路径辐亮度、湍流相干直径的物理地位；"
     "随后在 550 nm 气溶胶消光系数 σa(550) 与可降水量 PWV 构成的二维平面上归纳 7 类典型工况，并基于 AERONET 长期站点与 MERRA-2 气候值给出通用范围与区域参考。"
     "在成像检验部分，以 3–5 μm、夜间地面背景为例，采用 HITRAN 逐线吸收与 Ångström 气溶胶消光的简化辐射传输模型，在 (σa, PWV) 网格上计算视在温差 ΔT_app，得到 2.59–4.09 K 的量级范围，"
     "并分析气溶胶消光与水汽的相对作用。进一步以 Fried 相干直径 r0 与可分辨周数 Ne 参数化湍流对分辨率的影响，给出弱、中、强湍流条件下的量级。"
     "最后在假设典型中波红外传感器与 Johnson 型判据下演示探测、识别、辨认概率，50% 距离分别约为 7.3、2.5、1.7 km。"
     "报告明确了当前简化模型的假设与局限，并给出正式辐射传输、实测传感器参数、杂波与 ROC 模型、外场验证等下一步工作建议。")

p = doc.add_paragraph()
p.paragraph_format.space_before = Pt(10)
r = p.add_run("关键词：")
set_run_font(r, size=10.5, bold=True, east=BODY_FONT)
r = p.add_run("红外目标探测；大气参数化；视在温差；Fried 相干直径；可分辨周数；探测概率")
set_run_font(r, size=10.5, east=BODY_FONT)

# 报告说明 box-like paragraph
p = doc.add_paragraph()
p.paragraph_format.space_before = Pt(16)
p.paragraph_format.space_after = Pt(4)
p.paragraph_format.left_indent = Cm(0.4)
p.paragraph_format.right_indent = Cm(0.4)
bottom_border(p, color="BFBFBF", sz="4")
r = p.add_run("报告说明：本报告面向方法研究与流程验证，所有数值均建立在简化模型和假设参数之上；"
              "第 3 节给出通用工况范围与区域参考，第 4–6 节分别给出视在温差、湍流分辨率与探测概率的参数扫描示例，"
              "第 7 节汇总结论、缺口与后续工作。")
set_run_font(r, size=9, color=(0x55, 0x55, 0x55), east=BODY_FONT)
page_break()

# ---------------- 1 introduction ----------------
heading("1  引言", 1)
heading("1.1  研究背景", 2)
body("红外目标探测的成像效果不仅取决于目标与背景的固有温差，还受大气气溶胶消光、水汽吸收、大气自身热发射与散射、湍流导致的图像模糊等多过程共同影响。"
     "工程实践中，仅用“能见度”或单一波段透过率难以支撑成像效果检验：同样的能见度，在干冷沙漠与暖湿海岛对应的红外透过率、路径辐亮度与湍流强度可能完全不同。"
     "因此需要把大气影响组织成可计算、可复现、可检验的参数体系，并在统一流程下把大气参数映射为成像对比度、空间分辨率与最终的探测概率。")
body("本报告是前期讨论与初步计算的阶段性整理。与直接给出一个“大气透过率”不同，报告强调两点：其一，大气参数应按“输入层—中间层—检验层”组织，"
     "把观测几何、气溶胶谱参数、水汽柱总量、湍流剖面与温度等独立输入，和由它们驱动的路径积分量区分开；其二，成像效果应至少从“辐射/对比度”和“空间/分辨率”两个通道评价，"
     "二者最终在探测概率处汇合。")

heading("1.2  阶段目标与范围", 2)
body("本阶段的目标是：建立大气参数化与成像效果检验的流程框架；给出典型工况的参数量级；用简化模型完成视在温差、湍流分辨率与探测概率的参数扫描演示，"
     "识别当前缺口，为下一步接入正式辐射传输模型与实测数据提供依据。")
body("报告的场景约定为：中波红外 3–5 μm、夜间、地面背景、水平路径 2 km、目标与背景分别为 15 °C 与 10 °C。除特别说明外，第 4–6 节的数值均为在上述约定下的简化模型结果，"
     "用于趋势与量级判断，不作为定量结论。")

heading("1.3  符号与约定", 2)
body("σa(550)：550 nm 气溶胶消光系数（km⁻¹）；α：Ångström 消光光谱斜率；Ha：气溶胶标高（km）；PWV：可降水量（cm）；"
     "Cn²(h)：湍流折射率结构常数剖面（m⁻²/³）；r0：Fried 相干直径；θt：目标角尺寸；θeff：系统有效角分辨率；Ne：目标上可分辨单元数；"
     "τ：透过率；L_path：路径辐亮度；L_app：入瞳视在辐亮度；ΔT_app：视在温差；Pd：探测概率。"
     "文中“探测概率”在需要区分任务等级时，特指 Johnson 判据下的探测/识别/辨认概率，并在相应位置注明门限。")

# ---------------- 2 workflow ----------------
heading("2  总体技术路线", 1)
body("图 1 给出了本报告采用的总体技术路线。大气参数首先分为气溶胶、水汽、几何/温度、湍流四组输入；气溶胶链 A 把 σa(550)、α、Ha 外推为波段消光，"
     "水汽链 B 把 PWV 与温湿廓线转换为吸收系数谱，二者沿路径积分得到气溶胶与水汽透过率；链 C 由温度廓线、气溶胶散射参数与太阳几何构造源函数，沿路径积分得到路径辐亮度；"
     "链 D 由 Cn²(h) 剖面积分得到 Fried 相干直径 r0，并进一步进入系统 MTF。")
body("在汇合环节，目标与背景的入瞳辐亮度按 L_app = L_int·τ + L_path 计算，从而得到视在温差 ΔT_app；湍流链给出 θeff 与可分辨周数 Ne。"
     "最后按任务判据（Johnson 周数、MRTD 或 ROC）把 ΔT_app 与 Ne 映射为探测概率 Pd。需要强调：路径辐亮度是确定性加性项，不能由透过率反推；湍流不经过透过率链，"
     "而是通过系统 MTF 影响空间分辨率，其次级效应才是闪烁引入的附加噪声。")

figure(os.path.join(HERE, "fig_workflow.png"), 15.8,
       "图 1  红外目标探测大气参数化与成像效果检验流程")

body("在上述框架中，本阶段实际完成的是“参数扫描 + 简化正向计算”：以 (σa, PWV) 作为工况平面，对每个格点计算 ΔT_app；以 (Cn², 路径长度/目标角尺寸) 计算 r0 与 Ne；"
     "最后用假设传感器参数把二者合成为任务概率。正式版本将把简化模型替换为逐线/带模型辐射传输，并接入实测传感器 MTF/NETD 与外场数据。")

# ---------------- 3 parameter system & scenarios ----------------
heading("3  大气参数体系与工况范围", 1)
heading("3.1  三层参数体系", 2)
body("按“输入层—中间层—检验层”组织大气参数，可以避免把独立输入与导出量混在一起。输入层是观测几何、气溶胶谱参数、水汽柱总量、湍流剖面与温度等独立量；"
     "中间层是由输入驱动的物理量，包括局地系数谱、路径积分透过率、路径辐亮度与 r0；检验层是最终判据量，包括视在温差、SNR 与 Pd，"
     "以及由透过率与阈值导出的等效红外能见度。表 1 给出参数体系的主要内容。")

table([
    ["层级", "参数", "作用与说明"],
    ["输入层", "σa(550)", "550 nm 气溶胶消光系数（km⁻¹），气溶胶消光光谱锚点"],
    ["输入层", "α", "Ångström 消光光谱斜率，反映粒子尺度，仅用于气溶胶外推"],
    ["输入层", "Ha", "气溶胶标高（km），控制消光随高度衰减，斜程/下视路径必需"],
    ["输入层", "PWV", "可降水量（cm），整层水汽柱总量，红外不透明度主控量"],
    ["输入层", "Cn²(h) / HV 参数", "湍流折射率结构常数剖面或 Hufnagel–Valley 参数"],
    ["输入层", "hs, ht, θ, R", "观测几何（传感器/目标高度、天顶角、路径长度），独立输入"],
    ["输入层", "T_ground, T_target, T_bg", "地面、目标、背景温度，用于视在温差与路径辐射"],
    ["中间层", "σa(λ), kH2O(λ)", "局地系数谱（气溶胶消光、水汽吸收）"],
    ["中间层", "τa(λ)", "沿路径积分后的总路径透过率"],
    ["中间层", "L_path(λ)", "源项沿路径积分后的路径辐亮度（热发射 + 散射太阳）"],
    ["中间层", "r0(λim)", "湍流剖面沿路径积分后的 Fried 相干直径"],
    ["检验层", "ΔT_app, SNR, Pd", "独立判据：视在温差、信噪比、探测概率"],
    ["检验层", "τIR, V_IR,equiv", "由波段积分与对比度阈值导出的量，不引入新自由度"],
], [2.4, 4.2, 9.4], "表 1  大气参数体系（输入层—中间层—检验层）")

heading("3.2  关键物理区分", 2)
body("第一，局地系数谱与路径积分量不能混用。σa(λ)、kH2O(λ) 是局地量，τa(λ)=exp[−∫σext ds] 与 L_path(λ)=∫j·exp[−∫σext ds′]ds 是路径积分量，后者还包含源项。"
     "透过率只描述衰减，路径辐亮度描述大气自身加入视线的辐射，二者不可互相替代。")
body("第二，水汽吸收不能使用 Ångström 外推。Ångström 关系仅适用于气溶胶消光随波长的变化；PWV 是柱总量约束，必须配合温湿压廓线逐层计算 kH2O，"
     "或使用线-by-line/k 分布/带模型。把 α 套到水汽上会得到错误的红外不透明度。")
body("第三，路径辐亮度是确定性加性项，不是随机噪声或“光污染”。在热红外，它主要来自大气热发射；白天中波红外还包括散射进入视线的太阳辐射。"
     "若目标与背景同路径且同距离，路径辐亮度在差分中近似抵消，视在温差主要由 τ 与 Planck 反演的非线性决定；若背景是天空或远山，路径辐亮度不能抵消，会直接改变对比度。")
body("第四，湍流不经过透过率链。Cn² 剖面积分得到 r0，r0 通过系统 MTF 影响空间分辨率；次级效应是闪烁与到达角起伏引入附加噪声。把湍流当作“透过率衰减”是常见错误。")

heading("3.3  工况分类与范围", 2)
body("在 (σa(550), PWV) 平面上，可用范围框加第三维 α 的方式框定典型工况。表 2 给出本阶段采用的 7 类工况范围；图 2 为无插值版本："
     "每个工况用一个虚线框表示近似范围，框线颜色表示该工况的典型 α（蓝=粗模态，红=细模态），框内不填色、不做空间插值。")

table([
    ["工况", "σa(550)（km⁻¹）", "PWV（cm）", "α 范围", "说明"],
    ["① 沙漠背景 / 浮尘", "0.05–0.50", "0.5–2.5", "0.2–0.5", "粗模态、水平带状；与乡村清洁低消光端重叠"],
    ["② 沙漠沙尘事件", "0.9–2.0+", "0.5–2.5", "−0.1–0.2", "α 接近 0 或为负；消光可继续增强"],
    ["③ 乡村清洁", "0.02–0.15", "1.0–2.5", "0.5–1.2", "细模态为主；与沙漠背景低消光端重叠"],
    ["④ 乡村农业 / 燃烧", "0.20–0.70", "1.5–4.0", "0.5–1.5", "混合/细模态；秸秆燃烧、生物质燃烧"],
    ["⑤ 海岛 / 海洋清洁", "0.03–0.15", "2.0–5.0", "0.0–1.0", "高 PWV、低消光；海洋性气团"],
    ["⑥ 海岛 / 近岸污染", "0.20–0.80", "2.5–6.0", "0.5–1.5", "高 PWV + 城市/近岸污染，覆盖右上角"],
    ["⑦ 城市 / 工业", "0.30–1.50+", "1.5–4.5", "1.0–1.8", "细模态主导；与乡村污染端、沙尘高消光端重叠"],
], [3.9, 3.3, 2.6, 2.4, 4.4], "表 2  典型工况范围（近似，非硬边界）")

figure(os.path.join(ROOT, "工况分类图_无插值.png"), 15.5,
       "图 2  工况分类图（无插值版）：框线颜色表示典型 α，框内不填色、不做插值")

body("需要特别说明：α 是工况（气溶胶类型）的属性，并不是 σa、PWV 的连续函数。前期曾尝试把 α 作为第三维做连续热力图，但在工况范围重叠区，插值会把两个工况的 α 平均，"
     "导致框内颜色与标签不一致（例如乡村清洁的 α≈0.85 被相邻沙漠背景的 α≈0.35 拉低）。因此本报告最终采用“范围框 + 典型 α 框线色”的离散表达，"
     "并在图注与正文中明确“颜色不对应消光强弱”。")

heading("3.4  典型观测区与通用参数参考", 2)
body("为使工况范围具有可追溯的观测依据，本阶段选取 AERONET 长期站点作为典型观测区，并用 MERRA-2/CERES 逐日数据（2015–2024 年，经 NASA POWER 获取）统计 PWV 与 AOD550 的气候值。"
     "统计方法为：先对每个站点计算中位数与 P10–P90，再按工况汇总；跨站差异与站内分布同时保留。表 3 给出主要代表区与气候值，"
     "其中 PWV/AOD 为 MERRA-2/CERES 的 2015–2024 年逐日统计，α 为 AERONET 多波段观测与文献参考范围。")

table([
    ["工况", "代表区（AERONET 站）", "PWV 中位（P10–P90）cm", "AOD550 中位（P10–P90）", "α 参考"],
    ["沙漠背景/浮尘", "敦煌、民勤、蒙古戈壁", "0.52–0.94（0.18–2.70）", "0.15–0.23（0.03–0.57）", "0.2–0.5"],
    ["沙漠沙尘事件", "喀什、Solar_Village（对照）", "0.89–1.54（0.37–2.44）", "0.14–0.46（0.03–0.77）", "0–0.3（事件更低）"],
    ["乡村清洁", "黄土高原 SACOL、香河清洁日", "1.1–1.3（0.36–2.77）", "0.33–0.48（0.09–0.74）", "0.5–1.2"],
    ["乡村农业/燃烧", "香河、太湖、Alta_Floresta（对照）", "1.3–4.6（0.36–5.99）", "0.28–0.67（0.09–1.37）", "0.5–1.5"],
    ["城市/工业", "北京、上海", "1.3–2.6（0.36–5.92）", "0.48–0.53（0.09–1.27）", "1.0–1.8"],
    ["海岛/近岸污染", "香港（珠三角近岸）", "4.33（2.26–6.07）", "0.48（0.19–1.06）", "0.5–1.5"],
    ["海岛/海洋清洁", "东沙、Lanai、瑙鲁", "3.0–4.9（2.27–6.22）", "0.08–0.30（0.05–0.75）", "0.0–1.0"],
    ["高原清洁/低水汽", "拉萨（补充对照）", "0.47（0.16–1.65）", "0.14（0.04–0.34）", "0.5–1.0"],
], [2.9, 4.4, 3.6, 3.5, 1.8], "表 3  典型观测区与 MERRA-2/CERES 气候值（2015–2024）")

body("表 3 揭示两点：其一，PWV 与气溶胶类型弱相关，不能把 PWV 硬绑进工况定义，否则“乡村燃烧”在华北与亚马逊会得到完全不同的 PWV 范围；"
     "因此建议把 PWV 作为独立轴，或按气候带分层给出分布。其二，MERRA-2 0.5°×0.625° 网格无法区分香河与北京（同一格点），站点级差异必须使用 AERONET 原始观测或更高分辨率数据。"
     "此外，以上数值为气候态，极端沙尘/燃烧/污染事件需按分位数或事件日另行抽样。")

# ---------------- 4 delta T ----------------
page_break()
heading("4  视在温差参数扫描（3–5 μm，夜间地面）", 1)
heading("4.1  计算链路", 2)
body("对波段内每个波长（或波数）计算总消光与透过率：τ(λ)=exp[−∫(σaer(λ,h)+kH2O(λ,h)ρv(h)+σmol(λ,h))ds]。"
     "路径辐亮度由源项沿路径积分得到：L_path(λ)=∫j(λ,s)·exp[−∫sRσext(λ,s′)ds′]ds；均匀路径下可简化为 L_path(λ)=B(λ,Tair)·[1−τ(λ)]。"
     "目标与背景的入瞳辐亮度为 L_app=L_int·τ+L_path；波段积分后得到 ΔL_app，再由 Planck 函数反演得到视在温差 ΔT_app。")
body("本报告采用“同路径地面背景”假设：目标与背景都是地面黑体，位于同一路径末端，故路径辐亮度对二者相同，在差分中抵消；ΔT_app 主要由 τ 与 Planck 反演的非线性决定。"
     "若背景为天空或远山，路径辐亮度项不能抵消，结果会显著不同。")

heading("4.2  简化模型与参数设置", 2)
body("气体吸收采用 HITRAN 逐线谱线，经 HAPI 在 283.15 K、1.01325 atm 下计算 H2O、CO2、CH4 的吸收截面；H2O 与 CO2 覆盖 3–5 μm 的主要吸收带，"
     "CH4 补充 3.3 μm 带。气溶胶按 Ångström 定律 σa(λ)=σa(550)(λ/0.55)^(−α) 叠加到路径消光。由于 HITRAN 服务器限速，N2O、O3、CO 在本次计算中暂缺，"
     "因此当前结果在 4.5–4.8 μm 的透过率偏高、ΔT_app 偏乐观。表 4 汇总了模型设置。")

table([
    ["项目", "设置"],
    ["波段 / 响应", "3–5 μm，平顶响应（简化）"],
    ["时间 / 场景", "夜间，无太阳散射；地面背景"],
    ["路径", "水平 2 km，近地面均匀 283.15 K、1 atm"],
    ["目标 / 背景", "15 °C / 10 °C；地面黑体 ε=1；同一路径"],
    ["气溶胶", "Ångström 消光，α=1.2；σa(550)=0.02–2.0 km⁻¹"],
    ["水汽", "PWV=0.2–1.8 cm；按 2 km 标高换算地面水汽密度"],
    ["气体吸收", "HITRAN 逐线：H2O、CO2、CH4（N2O/O3/CO 暂缺）"],
    ["未包含", "散射、水汽连续吸收、垂直廓线、传感器 NETD/MRTD"],
], [3.6, 12.4], "表 4  视在温差计算的简化模型设置", align_center=False)

heading("4.3  结果与解读", 2)
body("图 3 给出 (σa, PWV) 平面上的 ΔT_app 热力图。计算范围内 ΔT_app 约为 2.59–4.09 K，Planck 加权波段透过率约 0.50–0.81。"
     "低消光、低水汽的左上角接近 4.1 K；高消光、高水汽的右下角降到约 2.6 K。等值线显示：σa 是主要影响因素，PWV 的作用在高消光端更明显，"
     "但整体上 PWV 在 3–5 μm 的敏感性弱于长波红外，这与中波红外窗口相对较宽、水汽吸收线在该波段的分布有关。")
figure(os.path.join(ROOT, "视在温差热力图_3-5um_夜间.png"), 15.5,
       "图 3  3–5 μm 夜间地面背景视在温差热力图（简化模型；R=2 km，T_t=15 °C，T_bg=10 °C）")

body("路径辐亮度虽然显式进入 L_app，但在“同路径地面背景”假设下，它在目标与背景的差分中基本抵消，因此 ΔT_app 的平面结构主要由 τ 与 Planck 反演的非线性决定。"
     "这并不意味着路径辐亮度不重要：若背景为天空、远山或海面，目标与背景路径不同，L_path 差会直接改变对比度，甚至改变 ΔT_app 的符号与单调性。")

heading("4.4  局限与讨论", 2)
body("当前结果的主要局限包括：其一，N2O/O3/CO 与连续吸收缺失，使 4.5–4.8 μm 的透过率偏高，ΔT_app 偏乐观；其二，未考虑气溶胶散射，"
     "把气溶胶当作纯吸收介质会高估其对比度衰减作用；其三，采用水平均匀、单层温度廓线，未考虑垂直结构对路径辐亮度的影响；"
     "其四，10 °C 地面温度下饱和水汽限制 PWV 约不超过 1.9 cm，故纵轴仅取到 1.8 cm，更高 PWV 需更高地面温度另行计算；其五，未接入传感器 NETD/MRTD，"
     "因此这里给出的是大气层的视在温差，而不是成像系统最终可测的温差。")

# ---------------- 5 turbulence ----------------
page_break()
heading("5  湍流对分辨率的影响", 1)
heading("5.1  物理量与公式", 2)
body("湍流对成像的影响用 Fried 相干直径 r0 描述。对水平均匀路径，r0=[0.423k²∫Cn²dh]^(−3/5)，其中 k=2π/λ，∫Cn²dh=Cn²·R。"
     "r0 的物理含义是波前仍近似相干的有效口径尺度：口径 D≪r0 时接近衍射极限（θ≈λ/D）；D≫r0 时长曝光分辨率被限制在 θ≈λ/r0，"
     "此时继续增大口径基本无效（除非使用自适应光学）。r0 随波长按 λ^(6/5) 增大，因此同样湍流条件下 4 μm 的 r0 约是 0.55 μm 的 10.8 倍。")
body("进一步定义系统有效角分辨率 θeff=√[(λ/r0)²+(λ/D)²+IFOV²]（本报告把湍流、衍射与探测器瞬时视场按平方和近似），"
     "目标角尺寸 θt 与 θeff 的比值 Ne=θt/θeff 即目标上可分辨的单元数。Ne≈1 时目标只是一个模糊斑；Ne 越大，目标上可辨的细节越多。"
     "Johnson 判据使用的“周数”与 Ne 相差约 2 倍（一周≈两条线），正式使用时需统一口径。")

heading("5.2  结果与量级", 2)
body("图 4 左侧给出 r0(Cn², R)：路径越长、Cn² 越大，r0 越小；右侧给出 R=2 km 时 Ne(Cn², θt)：目标越小（θt 越小）或湍流越强，Ne 越小。"
     "表 5 列出 λ=4 μm、R=2 km、D=0.2 m 条件下的典型量级（Ne 仅含湍流与衍射，不含 IFOV）。")

table([
    ["Cn²（m⁻²/³）", "湍流状态", "r0 @2 km（cm）", "Ne（1 mrad，无 IFOV）", "限制类型"],
    ["1e-15", "弱", "≈65", "≈48", "接近衍射受限（λ/D=20 μrad）"],
    ["1e-14", "中", "≈16", "≈31", "湍流开始主导"],
    ["1e-13", "强", "≈4", "≈10", "湍流受限"],
    ["1e-12", "极强", "≈1", "≈2.5", "分辨率严重退化"],
], [3.2, 2.2, 3.4, 4.4, 5.0], "表 5  湍流量级（λ=4 μm，R=2 km，D=0.2 m）")

figure(os.path.join(ROOT, "湍流分辨率热力图_3-5um_夜间.png"), 15.8,
       "图 4  湍流对分辨率的影响：左为 r0(Cn²,R)，右为可分辨周数 Ne(Cn²,θt)")

body("需要强调：湍流与 σa、PWV 是相互独立的物理量，C_n² 主要由风切变、地形与温度梯度决定，不会随气溶胶或水汽变化。因此湍流图不能放在 (σa, PWV) 平面上，"
     "而应使用 Cn² 与路径长度/目标角尺寸作为坐标轴；这也是图 4 与图 3 坐标轴不同的原因。")

heading("5.3  局限", 2)
body("当前湍流计算采用水平均匀 Cn²、长曝光 Kolmogorov 统计，未考虑外尺度、风、闪烁、斜程与垂直廓线；θeff 的平方和组合是近似，严格评估应使用 MTF 积分或实测 r0。"
     "此外 D=0.2 m 是假设口径，实际系统需替换为真实口径与光学/探测器 MTF。")

# ---------------- 6 Pd ----------------
page_break()
heading("6  探测概率演示", 1)
heading("6.1  假设与模型", 2)
body("为演示 P_d 的计算流程，假设一套典型中波红外传感器与目标：口径 D=0.2 m、焦距 f=0.4 m、像元间距 15 μm（IFOV=37.5 μrad）、NETD=25 mK、波段 3–5 μm；"
     "目标临界尺寸 2 m、温度 15 °C，背景 10 °C；大气取上一节典型值 ΔT_app≈3.5 K，Cn²=1e-14。任务门限按 Johnson 周数 2/8/13（对应分辨单元约 4/16/26），"
     "用 logistic 函数近似任务概率；对比度门限按 3 倍 NETD 计。由于本场景 ΔT_app/NETD≈140，对比度门限恒满足，P_d 主要由分辨率与任务等级决定。")

heading("6.2  结果", 2)
body("图 5 左侧给出 R=2 km 时探测概率随 Cn² 与目标角尺寸的变化：参考点（Cn²=1e-14、θt=1 mrad，即 2 m@2 km）的 Ne≈20（含 IFOV），探测概率接近 1；"
     "当湍流极强（Cn²=1e-12）且目标很小（θt=0.1 mrad）时，探测概率降到约 0.04。右侧给出目标 2 m 时探测、识别、辨认概率随距离的变化，"
     "50% 距离分别约为 7.3、2.5、1.7 km。表 6 汇总了假设与结果。")
figure(os.path.join(ROOT, "Pd演示_3-5um_夜间.png"), 15.8,
       "图 5  探测概率演示：左为 P_d(Cn²,θt)，右为探测/识别/辨认概率随距离变化")

table([
    ["项目", "设定 / 结果"],
    ["传感器", "D=0.2 m，f=0.4 m，像元 15 μm，IFOV=37.5 μrad，NETD=25 mK"],
    ["目标 / 背景", "2 m 临界尺寸，15 °C / 10 °C，地面黑体、同路径"],
    ["大气", "ΔT_app≈3.5 K，Cn²=1e-14，R=2 km"],
    ["判据", "Johnson 周数 2/8/13 ↔ 分辨单元 4/16/26；logistic 近似"],
    ["结果", "50% 探测/识别/辨认距离 ≈7.3 / 2.5 / 1.7 km"],
    ["备注", "参考点 Ne≈20（含 IFOV）；强湍流小目标 P_d≈0.04；(σa,PWV) 平面上 P_d 基本饱和"],
], [3.2, 12.8], "表 6  探测概率演示的假设与结果", align_center=False)

body("一个重要的结论是：在“15 °C 目标 / 10 °C 地面背景”的假设下，目标-背景固有温差达 5 K，远高于典型 MWIR 传感器的 NETD，因此探测概率对大气对比度变化不敏感，"
     "在 (σa, PWV) 平面上基本饱和为 1。此时限制来自分辨率、任务等级与背景杂波，而不是大气透过率。若要区分不同大气工况，应关注识别/辨认任务、更远距离、"
     "更小目标或引入杂波模型；这也说明 P_d 不能仅由大气参数决定，必须与传感器、目标和任务判据联合计算。")

heading("6.3  局限与待确认参数", 2)
body("当前 P_d 演示采用 Johnson 型 logistic 近似，不是严格 ROC；未考虑背景杂波、平台抖动、固定图案噪声与大气闪烁；传感器参数为典型假设值；"
     "对比度门限被简化为 3×NETD 且恒满足。正式计算需要以下输入（表 7）。")

table([
    ["类别", "待确认项"],
    ["任务 / 判据", "任务等级（探测/识别/辨认）、虚警率 Pfa、判据形式（Johnson/MRTD/ROC）"],
    ["传感器", "口径 D、F#、像元/IFOV、NETD、积分时间、帧率、实测 MTF、读出噪声"],
    ["目标", "实际尺寸/形状/朝向、临界尺寸方向、发射率、温度"],
    ["背景", "地面/海面/天空、温度、发射率、杂波强度与空间结构"],
    ["几何", "距离范围、传感器高度、俯仰/方位角、目标与背景是否同路径"],
    ["大气", "目标区 PWV 气候态、气溶胶类型/α、Cn² 廓线或 HV 参数、昼夜"],
    ["验证", "外场红外图像、目标/背景测温、能见度/湍流观测、传感器 MTF/NETD 测试"],
], [3.0, 13.0], "表 7  P_d 正式计算需要的输入清单", align_center=False)

# ---------------- 7 conclusions ----------------
heading("7  结论与下一步", 1)
body("本阶段完成了大气参数化与成像效果检验的流程搭建和初步参数扫描，主要结论如下：")
_lead = doc.paragraphs[-1]
_lead.paragraph_format.keep_with_next = True
bullet("（1）三层参数体系与“三条大气链 + 湍流链”的流程可复现，路径辐亮度、r0 与视在温差的物理地位明确；两通道（辐射/对比度、空间/分辨率）在 P_d 处汇合。")
bullet("（2）工况范围宜用“二维范围框 + 第三维 α”表达；α 是气溶胶类型属性，把 α 当作连续场做空间插值会在工况重叠区产生歧义，最终采用无插值范围框更稳妥。")
bullet("（3）在 3–5 μm、夜间地面、R=2 km 的简化模型下，ΔT_app 约 2.59–4.09 K，σa 是主控因素，PWV 影响次要；路径辐亮度在同路径差分中抵消，若背景为天空/远山则不能忽略。")
bullet("（4）湍流方面，λ=4 μm、R=2 km 时，弱/中/强 Cn² 对应 r0≈65/16/4 cm，1 mrad 目标的 Ne≈48/31/10（不含 IFOV）；湍流与 σa、PWV 独立，需单独参数化。")
bullet("（5）P_d 演示表明，在 15/10 °C 场景下探测概率对大气对比度不敏感、基本饱和；50% 探测/识别/辨认距离约 7.3/2.5/1.7 km，瓶颈在分辨率、任务等级与杂波。")

body("下一步工作建议按以下顺序推进：")
_lead = doc.paragraphs[-1]
_lead.paragraph_format.keep_with_next = True
bullet("（1）接入正式辐射传输模型（MODTRAN 或 libRadtran），补齐 N2O/O3/CO、水汽连续吸收、气溶胶散射与垂直廓线，替换当前简化模型；")
bullet("（2）用实测传感器参数（口径、IFOV、NETD、MTF、积分时间）替换假设值，建立 MRTD/MTF 与 ROC 的严格任务模型；")
bullet("（3）建立背景杂波模型（地面/海面/天空），把 P_fa 与 P_d 一起评估，避免“探测概率饱和”掩盖实际问题；")
bullet("（4）用目标区域 PWV 气候态与当地气溶胶类型替换通用工况范围，形成区域化检验工况矩阵；")
bullet("（5）收集外场红外图像、目标/背景测温、湍流与能见度观测，开展模型验证与不确定性分析；")
bullet("（6）在以上基础上，把本报告流程固化为可自动运行的参数扫描与报告生成工具。")

# ---------------- appendix A ----------------
heading("附录 A  文件与脚本清单", 1)
table([
    ["文件", "说明"],
    ["fig_workflow.png", "图 1 流程框图"],
    ["工况分类图_无插值.png", "图 2 无插值工况分类图"],
    ["视在温差热力图_3-5um_夜间.png", "图 3 ΔT_app 参数扫描热力图"],
    ["湍流分辨率热力图_3-5um_夜间.png", "图 4 湍流 r0 / Ne 图"],
    ["Pd演示_3-5um_夜间.png", "图 5 P_d 演示图"],
    ["工况分类图_无插值 / 视在温差 / 湍流 / P_d 脚本", "make_scenario_clean.py、make_dtapp_heatmap.py、make_turbulence_heatmap.py、make_pd_demo.py"],
    ["典型观测区_MERRA2气候值.csv", "典型区气象/气溶胶气候值"],
    ["工况统计_多站汇总.csv", "多站汇总统计示例"],
    ["视在温差网格_3-5um_夜间.csv", "ΔT_app 网格数据"],
], [6.2, 9.8], "表 A1  报告相关文件与脚本", align_center=False)

heading("附录 B  数据来源与参考文献", 1)
refs = [
    "[1] Holben, B. N., et al. AERONET—A federated instrument network and data archive for aerosol characterization. Remote Sensing of Environment, 1998, 66(1): 1–16. doi:10.1016/S0034-4257(98)00031-5",
    "[2] Gelaro, R., et al. The Modern-Era Retrospective Analysis for Research and Applications, Version 2 (MERRA-2). Journal of Climate, 2017, 30(14): 5419–5454. doi:10.1175/JCLI-D-16-0758.1",
    "[3] Kochanov, R. V., et al. HITRAN Application Programming Interface (HAPI): A comprehensive approach to working with spectroscopic data. Journal of Quantitative Spectroscopy & Radiative Transfer, 2016, 177: 15–30. doi:10.1016/j.jqsrt.2016.03.005",
    "[4] Levy, R. C., et al. The Collection 6 MODIS aerosol products over land and ocean. Atmospheric Measurement Techniques, 2013, 6: 2989–3034. doi:10.5194/amt-6-2989-2013",
    "[5] NASA POWER — Prediction Of Worldwide Energy Resources. https://power.larc.nasa.gov/",
    "[6] AERONET site list (V3). https://aeronet.gsfc.nasa.gov/aeronet_locations_v3.txt",
    "[7] HITRAN online database. https://hitran.org/",
    "[8] East Asian Study of Tropospheric Aerosols: An International Regional Experiment (EAST-AIRE) 2005, JGR. https://agupubs.onlinelibrary.wiley.com/doi/full/10.1029/2006JD007592",
    "[9] Diurnal variability of dust aerosol optical thickness and Ångström exponent over dust source regions in China. Geophysical Research Letters, 2004. https://agupubs.onlinelibrary.wiley.com/doi/full/10.1029/2004GL019580",
    "[10] Advances in sunphotometer-measured aerosol optical properties and related topics in China: Impetus and perspectives. Atmospheric Research, 2021. https://www.sciencedirect.com/science/article/pii/S0169809520312230",
]
for ref in refs:
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(3)
    p.paragraph_format.line_spacing = 1.2
    p.paragraph_format.left_indent = Cm(0.0)
    r = p.add_run(ref)
    set_run_font(r, size=8.8, east=BODY_FONT)

body("说明：报告中的 MERRA-2/CERES 气候值经 NASA POWER API 获取（2015–2024 年逐日）；AERONET 站名与坐标取自 AERONET 站点列表；"
     "逐线吸收截面由 HAPI 基于 HITRAN 数据计算。受 HITRAN 服务器限速，N2O、O3、CO 暂未纳入本次计算。", indent=True, size=9)

doc.save(OUT)
print("saved:", OUT)
