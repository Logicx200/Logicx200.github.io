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
OUT = os.path.join(HERE, "红外大气参数化与成像效果评估_正式报告_V1.1.docx")

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
r = hp.add_run("红外目标探测大气参数化与成像效果评估  ·  正式报告 V1.1")
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


def page_break():
    doc.add_page_break()


# ---------------- cover ----------------
for _ in range(4):
    doc.add_paragraph()

p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = p.add_run("正 式 研 究 报 告")
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
    ("报告版本", "V1.1（正式报告，按软件实际资源重写）"),
    ("编制日期", "2026 年 11 月"),
    ("适用项目", "红外目标探测大气影响参数化与成像效果检验"),
    ("报告性质", "正式研究报告：方法、算例与数据质量评估"),
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

body("本报告按“采用软件内实际存在的工况和目标参数”重写。报告以 XGGDCOSSim2 默认想定（编号 2）为时空与气象基准，采用软件唯一实际背景模型与那国岛、模型库中实际存在的 6 个目标模型（F16、F22、尼米兹级航母、阿利伯克级驱逐舰、悍马车、爱国者导弹发射车），以及默认气象参数（晴天、15 °C、50%RH、1013 hPa、10 km、干净大陆、美国标准大气、不考虑湍流）；软件不含辐射传感器，报告以默认中波显示参数为锚点定义 3.7–4.8 μm 传感器模型（平台 8000 m、FOV 3.75°×3°、1024×768、IFOV 63.9 μrad、NETD 25 mK）。基于上述实际资源完成 3.7–4.8 μm 正式算例：路径波段平均透过率约 0.62→0.45；F16 视在温差在 20/40/60 °C 热状态约 −0.9/9.9–12.8/22.3–28.1 K；识别/辨认 50% 距离 F16 约 10.95/3.24 km、F22 约 14.84/6.96 km、爱国者发射车约 18.53/9.50 km，航母/驱逐舰 >20 km，悍马车识别/辨认 <0.5。报告同时说明默认想定背景/目标占位、Q2 大气样本条件不一致、RT 卡片缺失、无辐射传感器参数等数据质量问题及后续工作。")

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
r = p.add_run("报告说明：本版按软件内实际资源重写。第 3 节给出大气参数体系与工况范围；"
              "第 4–6 节为方法基线（视在温差、湍流分辨率、P_d 演示）；第 7 节给出软件实际想定、背景、目标模型、默认气象与传感器参数；"
              "第 8 节给出 6 个实际目标在 3.7–4.8 μm 下的正式算例；第 9 节总结结论、数据质量问题与后续工作。")
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
# ---------------- formal software settings & formal simulation ----------------
# ---------------- section 7 actual software resources ----------------
_h = heading("7  软件内实际工况与目标参数", 1)
_h.paragraph_format.page_break_before = True
heading("7.1  采用原则与资源清单", 2)
body("本版按“只采用软件内实际存在的工况和目标参数”的原则重写。解析对象为 XGGDCOSSim2 的默认想定（DefaultPlanFile）、模型库（ModelDatabase / DefaultModelDatabase）、6 个目标模型与 1 个背景模型的 Config.ini、OSG 模型包围盒，以及软件自带的 Q2 中波/长波大气数据样本。")
body("与前一版不同，本版不再构造 14 类背景×6 类目标的假设矩阵，也不把软件中并不存在的背景模型当作可用资源。软件内实际可用的资源只有：默认想定 1 个（编号 2）、可加载背景模型 1 个（与那国岛）、目标模型 6 个、默认想定气象参数 1 组、传感器显示参数 1 组、Q2 大气数据样本 1 组。表 8 给出资源清单及其在本报告中的使用方式。")
table([
    ["软件内资源", "位置/标识", "实际内容", "本报告使用方式"],
    ["默认想定", "DefaultPlanFile / ScenarioCode=编号2", "2025-10-20 10:00；原点 126.1234567°E、45.1234567°N、123.45 m", "作为时空与气象工况基准"],
    ["背景模型", "Data\\ModelData\\Background\\yngd", "与那国岛，地图模型，122.987568°E、24.456214°N、0 m", "作为唯一实际背景参与算例"],
    ["目标模型", "ModelDatabase 6 个目标", "F16、F22、尼米兹、阿利伯克、悍马、爱国者发射车", "作为 6 个实际目标参与算例"],
    ["默认气象", "DefaultPlanFile / WeatherParam", "晴天、15 °C、50%RH、1013 hPa、10 km、干净大陆、美国标准大气", "作为大气路径与背景温度输入"],
    ["传感器显示参数", "DefaultPlanFile / SensorParam", "中波红外、3.7–4.8 μm、3.75°×3°、1024×768、50 Hz、8000 m、−90°", "作为传感器模型锚点"],
    ["大气数据样本", "Data\\AtomData\\Q2_M.csv / Q2_L.csv", "洛阳城市、10 °C/50%/25/沙漠型、美国标准大气、中波 3.7–4.8 μm", "仅作结构与交叉核对，不作为主算例"],
], [3.4, 5.2, 4.8, 2.6], "表 8  软件内实际资源清单与本报告使用方式", align_center=False)

heading("7.2  默认想定的时空与气象参数", 2)
body("默认想定（编号 2）是软件内唯一完整的想定配置。其时空原点、背景设置、气象参数和传感器显示参数如表 9。需要特别说明：默认想定的背景名称为“桃园机场”，BgType=1（沙漠）、BgClass=1（地面），背景范围 300 m×300 m、重点区域 10 m×10 m，但背景模型文件路径为空，属于占位配置，不能直接用于成像计算；软件实际可加载的背景模型只有与那国岛。默认想定的目标实体为 ah64 直升机（地面运动目标，坐标 0,0,10 m，发动机停车），但模型库中不存在 ah64 模型，因此本报告改用模型库中实际存在的 6 个目标模型。")
table([
    ["参数", "软件内实际取值", "说明"],
    ["想定编号 / 零点", "编号 2 / 2025-10-20 10:00", "默认想定"],
    ["坐标原点", "126.1234567°E，45.1234567°N，123.45 m", "地面坐标系原点"],
    ["背景设置", "桃园机场；BgType=1 沙漠；BgClass=1 地面；300 m×300 m", "占位配置，背景模型路径为空"],
    ["默认目标实体", "ah64直升机；地面运动目标；0,0,10 m；发动机停车", "模型库无 ah64，改用 6 个实际模型"],
    ["天气类型", "晴天（WeatherType=0）", "无云、无雨、无雪"],
    ["大气温度 / 湿度", "15 °C / 50%", "WeatherBase"],
    ["气压 / 能见度", "1013 hPa / 10000 m", "能见度 10 km"],
    ["气溶胶 / 大气模式", "干净大陆（AtmAerosol=0）/ 美国标准大气（AtmMode=0）", "WeatherBase"],
    ["湍流设置", "TurImagSimFlag=0，AtmCn2=0", "默认想定不考虑湍流"],
], [4.0, 7.4, 4.6], "表 9  默认想定的时空、背景与气象参数", align_center=False)

heading("7.3  实际背景模型：与那国岛", 2)
body("与那国岛是软件唯一实际可加载的背景模型（地图模型，海岛类），其 Config.ini 给出的波段与温度参数如表 10。该模型的红外波段参数与目标模型一致：中波 3.7–4.8 μm、长波 8–12 μm、环境温度 20 °C、温度范围 0–60 °C；中波辐亮度范围 0.429–3.763 W/(m²·sr)，长波 23.824–62.905 W/(m²·sr)。本报告取背景温度 20 °C、发射率 0.95 作为基线。")
table([
    ["参数", "取值", "说明"],
    ["模型名称 / 类型", "与那国岛 / 地图模型", "ModelCategory=地图模型"],
    ["中心坐标 / 高程", "122.987568°E，24.456214°N，0 m", "Config.ini"],
    ["模型范围", "220 km × 220 km × 215.7 m", "OSG 顶点包围盒"],
    ["红外叠加比例", "InfraredRatio=0.25", "可见光 0.3"],
    ["中波 / 长波", "3.7–4.8 μm / 8.000–12.000 μm", "Config.ini"],
    ["环境温度 / 温度范围", "20 °C / 0–60 °C", "Config.ini"],
    ["中波辐亮度范围", "0.42917987377–3.763490011 W/(m²·sr)", "Config.ini"],
], [4.0, 8.0, 4.0], "表 10  与那国岛背景模型的实际参数", align_center=False)

heading("7.4  实际目标模型", 2)
body("模型库中实际存在 6 个目标模型，覆盖空中、海面、地面三类。表 11 给出型号、类别、目标类型与由 OSG 顶点直接计算的包围盒尺寸（软件局部坐标，按 1 单位 = 1 m 解释，需实测标定）。6 个模型的 Config.ini 波段/温度参数完全相同：中波 3.7–4.8 μm、长波 8–12 μm、环境温度 20 °C、温度范围 0–60 °C；因此算例中目标差异主要来自几何尺寸与目标类型，热状态按 0–60 °C 统一设定。")
table([
    ["型号名称", "类别", "目标类型", "包围盒尺寸（m）", "本报告取目标高度"],
    ["F16战斗机", "空中模型", "空中飞机目标", "9.66 × 14.85 × 4.57", "500 m"],
    ["F22战斗机", "空中模型", "空中飞机目标", "13.50 × 18.60 × 4.00", "500 m"],
    ["尼米兹级航空母舰", "海洋模型", "海上运动目标", "85.73 × 340.66 × 75.22", "0 m"],
    ["阿利伯克级驱逐舰", "海洋模型", "海上运动目标", "20.27 × 151.32 × 47.74", "0 m"],
    ["悍马车", "陆地模型", "地面运动目标", "2.81 × 5.09 × 3.20", "10 m"],
    ["爱国者导弹发射车", "陆地模型", "地面静止/运动目标", "10.24 × 22.57 × 11.07", "10 m"],
], [4.2, 2.6, 4.2, 3.6, 1.4], "表 11  软件模型库中的 6 个实际目标模型", align_center=False)

heading("7.5  实际气象工况与大气路径", 2)
body("正式算例采用默认想定的实际气象参数：晴天、15 °C、50%RH、1013 hPa、能见度 10 km、干净大陆气溶胶、美国标准大气、不考虑湍流。由于软件未随安装包提供 RT 大气卡片，大气路径由本报告第 4 章方法计算：HITRAN 逐线吸收（H2O/CO2/CH4）、Ångström 气溶胶消光（干净大陆 α=1.30，550 nm 消光由能见度 10 km 推得）与分子散射，路径按斜程均匀近似；水汽由 15 °C/50%RH/2 km 标高推得 PWV≈1.28 cm。图 6 给出 3.7–4.8 μm 路径透过率与路径辐亮度随地面距离的变化。")
body("软件自带 Q2 大气数据样本的条件为：洛阳城市、10 °C、50%RH、能见度 25（软件单位存疑）、沙漠型气溶胶、美国标准大气、白天 10:00，与默认想定（15 °C、10 km、干净大陆）不一致，且 RT 卡片缺失；因此 Q2 只用于核对软件大气数据的字段、网格与量级，不作为本报告主算例的输入。Q2 中波 3.7–4.8 μm、长波 7.7–10.3 μm 的波段设置与软件目标 Config.ini 的长波 8–12 μm 也不一致。")

heading("7.6  红外传感器模型", 2)
body("软件不含辐射传感器，只提供显示/注入链路参数。正式算例以软件默认传感器参数为锚点：中波 3.7–4.8 μm、FOV 3.75°×3°、1024×768、50 Hz、平台高度 8000 m、俯仰 −90°；由 FOV/分辨率得 IFOV=63.9 μrad。本报告补充口径 0.15 m、焦距 0.45 m、像元 28.7 μm、NETD 25 mK、积分时间 10 ms、光学透过率 0.8 与 MTF 链，形成可用于辐射/分辨率计算的传感器模型（表 12）。")
table([
    ["参数", "取值", "来源/说明"],
    ["波段", "3.7–4.8 μm", "软件默认"],
    ["视场 / 分辨率", "3.75° × 3° / 1024 × 768", "软件默认"],
    ["帧率 / 平台高度", "50 Hz / 8000 m", "软件默认"],
    ["口径 / 焦距", "0.15 m / 0.45 m", "本报告设定"],
    ["像元 / IFOV", "28.7 μm / 63.9 μrad", "本报告设定，匹配 FOV/分辨率"],
    ["NETD / 积分时间", "25 mK / 10 ms", "本报告设定"],
    ["光学透过率 / MTF", "0.8 / 衍射×像元×光学×抖动", "本报告设定"],
], [4.2, 6.4, 5.4], "表 12  软件显示参数锚点 + 本报告补充的红外传感器模型", align_center=False)

heading("7.7  正式算例定义", 2)
body("正式算例采用“软件实际资源”的最小组合：与那国岛背景（20 °C、ε=0.95）+ 6 个实际目标模型（ε=0.90、热状态 20/40/60 °C）+ 默认想定气象（15 °C/50%/10 km/干净大陆/美国标准大气、无湍流）+ 中波传感器（3.7–4.8 μm、8000 m、FOV 3.75°×3°、1024×768、IFOV 63.9 μrad、NETD 25 mK）。地面距离取 1–20 km；地面/海面目标高度分别取 10 m/0 m，空中目标取 500 m；传感器俯仰 −90°。由于默认想定不考虑湍流，基线算例的角分辨率由衍射与 IFOV 共同决定；湍流影响作为敏感性另行列出的条件不进入主表。")

# ---------------- section 8 actual results ----------------
heading("8  正式算例结果", 1)
heading("8.1  实际气象下的大气路径", 2)
body("图 6 给出实际气象条件下 3.7–4.8 μm 波段平均路径透过率与路径辐亮度。地面距离 1–20 km 时，海面/地面目标的波段平均透过率约从 0.62 降到 0.45，空中目标因斜程略短而高约 0.01–0.02；路径辐亮度从约 0.31 增至 0.45 W/(m²·sr)。这与 10 km 能见度、1.28 cm 水汽的干净大陆条件量级一致。")
figure(os.path.join(r"F:\DeepSeek工作区\正式仿真\results", "software_actual_atmos.png"), 15.5,
       "图 6  软件实际气象（15 °C/50%RH/10 km/干净大陆/美国标准大气）下 3.7–4.8 μm 路径透过率与路径辐亮度")

heading("8.2  视在温差", 2)
body("图 7 给出 F16 目标在 20/40/60 °C 三档热状态下的视在温差。背景取与那国岛 20 °C、ε=0.95，目标 ε=0.90；大气按 7.5 节实际气象计算。20 °C 低热状态与背景同温，视在温差约 −0.9 K（目标略冷于背景，来自路径/发射率差异）；40 °C 中热状态约 12.8→9.9 K；60 °C 高热状态约 28.1→22.3 K。目标热状态是主因，距离次之；对同一高度的不同目标模型，视在温差基本一致，差异主要来自目标高度与背景路径。")
figure(os.path.join(r"F:\DeepSeek工作区\正式仿真\results", "software_actual_dt.png"), 15.0,
       "图 7  软件实际目标 F16 在 20/40/60 °C 热状态下的视在温差（与那国岛背景 20 °C）")

heading("8.3  任务概率", 2)
body("图 8 给出 6 个实际目标模型在 40 °C 热状态下的识别/辨认概率随地面距离的变化。传感器按表 12；目标角尺寸取模型最大尺寸；基线不考虑湍流，角分辨率由 λ/D 与 IFOV 决定。由于目标尺寸差异极大，曲线分层明显：尼米兹级航母与阿利伯克级驱逐舰在 20 km 内识别/辨认概率均接近 1；F16 识别 50% 距离约 10.95 km、辨认约 3.24 km；F22 约 14.84 km / 6.96 km；爱国者发射车约 18.53 km / 9.50 km；悍马车尺寸最小，10 km 处分辨单元仅 5.69，识别/辨认概率在全距离内均低于 0.5（探测 50% 距离约 16.35 km）。")
figure(os.path.join(r"F:\DeepSeek工作区\正式仿真\results", "software_actual_pd.png"), 15.5,
       "图 8  软件实际目标模型 + 实际气象：识别/辨认概率随地面距离变化（40 °C 热状态）")

heading("8.4  结果汇总", 2)
body("表 13 汇总 6 个实际目标在 40 °C 热状态、10 km 地面距离处的分辨单元数、视在温差与任务概率，以及识别/辨认的 50% 距离。需要说明：识别/辨认概率采用 Johnson 周数门限（16/26 分辨单元）的 logistic 近似，不是严格 ROC；探测概率在对空/对海大目标上饱和，因此表中“>20 km”表示在本算例 20 km 范围内未降到 0.5。")
table([
    ["目标", "类别", "最大尺寸（m）", "Ne@10 km", "ΔT_app@10 km（K）", "10 km 探测/识别/辨认", "识别 50%（km）", "辨认 50%（km）"],
    ["F16", "空中", "14.85", "16.99", "11.59", "1.000 / 0.696 / 0.001", "10.95", "3.24"],
    ["F22", "空中", "18.60", "21.28", "11.59", "1.000 / 0.988 / 0.019", "14.84", "6.96"],
    ["尼米兹级航母", "海面", "340.66", "380.48", "11.52", "1.000 / 1.000 / 1.000", ">20", ">20"],
    ["阿利伯克级驱逐舰", "海面", "151.32", "169.01", "11.52", "1.000 / 1.000 / 1.000", ">20", ">20"],
    ["悍马车", "地面", "5.09", "5.69", "11.52", "0.803 / 0.000 / 0.000", "无（<0.5）", "无（<0.5）"],
    ["爱国者发射车", "地面", "22.57", "25.22", "11.52", "1.000 / 1.000 / 0.343", "18.53", "9.50"],
], [3.2, 1.6, 2.0, 1.8, 2.6, 3.0, 1.9, 1.9], "表 13  6 个实际目标在 40 °C 热状态下的正式算例结果")

heading("8.5  数据质量与适用性", 2)
body("本版严格采用软件内实际资源后，仍存在若干影响定量结论的问题（表 14）。这些问题不是通过建模可以消除的，需要在后续数据补充/实测中解决。")
table([
    ["问题", "影响", "建议"],
    ["默认想定背景“桃园机场”无模型文件，BgType=1 沙漠与名称不一致", "默认想定不能直接成像；实际背景只能使用与那国岛", "补齐桃园机场模型或改用实际背景模型重新想定"],
    ["默认想定目标 ah64 不在模型库", "想定目标与模型库不一致", "补齐 ah64 模型或改用 6 个现有模型"],
    ["Q2 样本条件（洛阳/10 °C/25/沙漠型）与默认气象（15 °C/10 km/干净大陆）不一致", "Q2 不能直接作为默认想定的 RT 输入", "按默认气象重新生成 RT 卡片"],
    ["Q2 能见度标为 25（单位存疑，疑为 25 km）；城市配沙漠型气溶胶", "路径透过率与气溶胶类型可信度不足", "核对软件单位与气溶胶模式后重算"],
    ["Q2 长波 7.7–10.3 μm 与 Config.ini 的 8–12 μm 不一致", "长波波段积分口径不一致", "统一波段定义"],
    ["RT 大气卡片文件未随软件交付", "大气结果不能独立复现", "索取 RT_...txt 或重新生成"],
    ["软件无辐射传感器；NETD/口径/焦距/像元/积分时间缺失", "传感器模型含本报告假设", "用实测传感器参数替换表 12"],
    ["目标包围盒为 OSG 局部坐标，按 1 单位=1 m 解释", "目标尺寸/角尺寸存在标定不确定度", "人工核定/几何标定"],
    ["默认想定不考虑湍流（Cn²=0）", "结果偏乐观，未含湍流模糊", "补充 Cn² 实测/廓线后做敏感性"],
], [5.2, 5.6, 5.2], "表 14  软件实际资源的数据质量与适用性问题", align_center=False)

# ---------------- conclusions ----------------
heading("9  结论与下一步", 1)
body("本版按“采用软件内实际存在的工况和目标参数”重写，完成了默认想定、实际背景、6 个实际目标模型、默认气象与传感器显示参数的统一建模，并给出 3.7–4.8 μm 的正式算例。主要结论如下：")
bullet("（1）软件内实际可用资源为：默认想定 1 个（编号 2）、背景模型 1 个（与那国岛）、目标模型 6 个、默认气象 1 组、Q2 大气样本 1 组；默认想定的背景“桃园机场”无模型文件、目标 ah64 不在模型库，不能直接用于成像计算。")
bullet("（2）按默认气象（15 °C/50%RH/10 km/干净大陆/美国标准大气、无湍流）与与那国岛 20 °C 背景，3.7–4.8 μm 波段平均路径透过率约 0.62→0.45（地面距离 1–20 km），路径辐亮度约 0.31→0.45 W/(m²·sr)。")
bullet("（3）F16 在 60 °C 高热状态下的视在温差约 28.1→22.3 K，40 °C 约 12.8→9.9 K，20 °C 低热状态约 −0.9 K；目标热状态是视在温差的主因。")
bullet("（4）6 个实际目标的识别/辨认能力由目标尺寸决定：航母/驱逐舰在 20 km 内接近 1；F16 识别/辨认 50% 距离约 10.95/3.24 km，F22 约 14.84/6.96 km，爱国者发射车约 18.53/9.50 km；悍马车因尺寸过小，识别/辨认概率在全距离内低于 0.5。")
bullet("（5）软件实际资源仍存在背景/目标占位、Q2 条件与默认气象不一致、RT 卡片缺失、无辐射传感器参数、无湍流等问题；表 14 已逐项列出，正式定型前需补齐。")
body("下一步工作建议：")
bullet("（1）补齐默认想定的桃园机场背景模型与 ah64 目标模型，或明确改用与那国岛 + 6 个现有目标的正式想定。")
bullet("（2）按默认气象重新生成 RT 大气卡片，核实能见度单位与气溶胶模式，统一长波 8–12 μm 波段口径。")
bullet("（3）用实测传感器参数（口径、焦距、像元、NETD、积分时间、MTF、光谱响应）替换表 12 的假设值。")
bullet("（4）补充 Cn² 实测/廓线、背景杂波与虚警率，建立 MRTD/MTF + ROC 的严格任务模型，并开展外场验证。")


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
    ["软件参数提取\\Q2解析\\atmosphere_index.csv", "Q2 大气数据块索引（软件内部参数）"],
    ["软件参数提取\\Q2解析\\atmosphere_data.parquet", "Q2 大气 44,010 行结构化数据"],
    ["软件参数提取\\models.json / 模型与想定参数.md", "模型库、枚举、默认想定与包围盒"],
    ["软件参数提取\\sensor_notes.md", "软件传感器参数与缺失项说明"],
    ["正式仿真\\make_formal_q2_case.py", "Q2 大气数据交叉核对脚本（非主算例）"],
    ["正式仿真\\results\\q2_*.png / q2_case_results.csv", "Q2 大气数据核对图与结果（非主算例）"],
    ["进度看板\\index.html / progress.json", "实时仿真进度看板"],
    ["正式仿真\\make_software_actual_case.py", "软件实际资源主算例脚本（图 6–8）"],
    ["正式仿真\\results\\software_actual_*.png", "图 6–8 实际资源算例图"],
    ["正式仿真\\results\\software_actual_case_results.csv", "6 个实际目标全距离结果"],
    ["正式仿真\\results\\software_actual_summary.csv", "10 km 与 50% 距离汇总"],
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
    "[11] XGGDCOSSim2 光电环境仿真软件数据目录（Data\\AtomData、Data\\SystemBaseFile、Data\\ModelData），2025–2026。",
    "[12] Johnson, J. Analysis of image forming systems. Proceedings of the Image Intensifier Symposium, 1958.",
]
for ref in refs:
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(3)
    p.paragraph_format.line_spacing = 1.2
    p.paragraph_format.left_indent = Cm(0.0)
    r = p.add_run(ref)
    set_run_font(r, size=8.8, east=BODY_FONT)

body("说明：软件实际想定参数取自 DefaultPlanFile，模型尺寸取自 OSG 顶点包围盒，目标/背景波段与温度参数取自各自 Config.ini；"
     "Q2 大气数据仅用于字段、网格与量级交叉核对。报告中的 MERRA-2/CERES 气候值经 NASA POWER API 获取（2015–2024 年逐日）；AERONET 站名与坐标取自 AERONET 站点列表；"
     "逐线吸收截面由 HAPI 基于 HITRAN 数据计算。受 HITRAN 服务器限速，N2O、O3、CO 暂未纳入本次计算。", indent=True, size=9)

doc.save(OUT)
print("saved:", OUT)
