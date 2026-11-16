# -*- coding: utf-8 -*-
"""V2.0 clean formal simulation report: only actual XGGDCOSSim2 resources, no demo sections."""
import os

from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

HERE = os.path.dirname(os.path.abspath(__file__))
RES = r"F:\DeepSeek工作区\正式仿真\results"
OUT = os.path.join(HERE, "基于软件实际工况的红外目标探测仿真报告_V2.1.docx")

BODY_FONT = "宋体"
HEAD_FONT = "黑体"
LATIN_FONT = "Times New Roman"


def set_run_font(run, size=10.5, bold=False, color=None, east=BODY_FONT, latin=LATIN_FONT):
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
    fld1 = OxmlElement("w:fldChar"); fld1.set(qn("w:fldCharType"), "begin")
    it = OxmlElement("w:instrText"); it.set(qn("xml:space"), "preserve"); it.text = instr
    fld2 = OxmlElement("w:fldChar"); fld2.set(qn("w:fldCharType"), "separate")
    t = OxmlElement("w:t"); t.text = placeholder
    fld3 = OxmlElement("w:fldChar"); fld3.set(qn("w:fldCharType"), "end")
    run._r.append(fld1); run._r.append(it); run._r.append(fld2); run._r.append(t); run._r.append(fld3)
    return run


doc = Document()
sec = doc.sections[0]
sec.page_width = Cm(21.0); sec.page_height = Cm(29.7)
sec.top_margin = Cm(2.3); sec.bottom_margin = Cm(2.2)
sec.left_margin = Cm(2.4); sec.right_margin = Cm(2.4)
sec.header_distance = Cm(1.2); sec.footer_distance = Cm(1.3)
sec.different_first_page_header_footer = True

normal = doc.styles["Normal"]
normal.font.name = LATIN_FONT
normal.font.size = Pt(10.5)
normal.element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), BODY_FONT)
pf = normal.paragraph_format
pf.line_spacing = 1.4; pf.space_after = Pt(3); pf.space_before = Pt(0)

for name, size, before, after in [("Heading 1", 15, 18, 8), ("Heading 2", 12.5, 12, 6), ("Heading 3", 11, 10, 4)]:
    st = doc.styles[name]
    st.font.name = HEAD_FONT; st.font.size = Pt(size); st.font.bold = True
    st.font.color.rgb = RGBColor(0x1F, 0x3A, 0x5F)
    rPr = st.element.get_or_add_rPr(); rPr.rFonts.set(qn("w:eastAsia"), HEAD_FONT)
    st.paragraph_format.space_before = Pt(before)
    st.paragraph_format.space_after = Pt(after)
    st.paragraph_format.keep_with_next = True

header = sec.header
hp = header.paragraphs[0]
hp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
r = hp.add_run("基于软件实际工况的红外目标探测仿真  ·  正式仿真报告 V2.1")
set_run_font(r, size=8, color=(0x66, 0x66, 0x66), east=BODY_FONT)
bottom_border(hp, color="BFBFBF", sz="4")

footer = sec.footer
fp = footer.paragraphs[0]
fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = fp.add_run("第 "); set_run_font(r, size=9, color=(0x59, 0x59, 0x59), east=BODY_FONT)
add_field(fp, " PAGE ", "1")
r = fp.add_run(" 页 / 共 "); set_run_font(r, size=9, color=(0x59, 0x59, 0x59), east=BODY_FONT)
add_field(fp, " NUMPAGES ", "1")
r = fp.add_run(" 页"); set_run_font(r, size=9, color=(0x59, 0x59, 0x59), east=BODY_FONT)


def body(text, indent=True, size=10.5, bold=False, color=None, align=WD_ALIGN_PARAGRAPH.JUSTIFY, after=3):
    p = doc.add_paragraph()
    p.alignment = align
    p.paragraph_format.space_after = Pt(after)
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
        set_run_font(r, size={1: 15, 2: 12.5, 3: 11}[level], bold=True, color=(0x1F, 0x3A, 0x5F), east=HEAD_FONT)
    return h


def caption(text, before=2, after=8):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(before)
    p.paragraph_format.space_after = Pt(after)
    run = p.add_run(text)
    set_run_font(run, size=9, color=(0x40, 0x40, 0x40), east=BODY_FONT)
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
    t.style = "Table Grid"; t.alignment = WD_TABLE_ALIGNMENT.CENTER; t.autofit = False
    for i, row in enumerate(data):
        for j, val in enumerate(row):
            cell = t.cell(i, j); cell.width = Cm(widths[j]); cell.text = ""
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
for _ in range(3):
    doc.add_paragraph()
p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = p.add_run("XGGDCOSSim2 光电环境仿真软件  ·  红外目标探测仿真")
set_run_font(r, size=11, color=(0x6C, 0x6C, 0x6C), east=HEAD_FONT)

p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
p.paragraph_format.space_before = Pt(24)
r = p.add_run("基于软件实际工况的\n红外目标探测仿真报告")
set_run_font(r, size=24, bold=True, color=(0x1F, 0x3A, 0x5F), east=HEAD_FONT)

p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
p.paragraph_format.space_before = Pt(12)
r = p.add_run("正式仿真报告  ·  V2.1")
set_run_font(r, size=14, color=(0x1F, 0x3A, 0x5F), east=HEAD_FONT)

p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
p.paragraph_format.space_before = Pt(10)
r = p.add_run("仅采用软件内实际工况与目标参数；已删除阶段演示内容")
set_run_font(r, size=9.5, color=(0x7F, 0x7F, 0x7F), east=BODY_FONT)

for _ in range(4):
    doc.add_paragraph()
info = table([
    ["项目", "内容"],
    ["报告版本", "V2.1（按软件实际资源重写，补充云/干扰工况）"],
    ["数据截止", "2026-11-02"],
    ["仿真对象", "XGGDCOSSim2 默认想定（编号 2）、与那国岛背景、6 个实际目标模型"],
    ["工况来源", "DefaultPlanFile 默认气象与传感器显示参数"],
    ["仿真规模", "6 目标 × 3 热状态 × 77 个地面距离 = 1,386 个算例点"],
    ["编制日期", "2026 年 11 月"],
], [3.6, 10.8], "", align_center=False)
page_break()

# ---------------- abstract ----------------
heading("摘 要", 1)
body("本报告按“只采用软件内实际存在的工况和目标参数”重写，删除了阶段报告中的参数扫描演示、湍流演示和 P_d 演示内容。报告以 XGGDCOSSim2 默认想定（编号 2）为时空与气象基准：2025-10-20 10:00，天气晴，15 °C、50%RH、1013 hPa、能见度 10 km、干净大陆气溶胶、美国标准大气、不考虑湍流；采用软件唯一实际背景模型与那国岛（20 °C、0–60 °C、中波 3.7–4.8 μm），以及模型库中实际存在的 6 个目标模型（F16、F22、尼米兹级航母、阿利伯克级驱逐舰、悍马车、爱国者导弹发射车）。")
body("软件不含红外辐射传感器，本报告以默认中波显示参数为锚点（3.7–4.8 μm、FOV 3.75°×3°、1024×768、50 Hz、平台高度 8000 m、俯仰 −90°），补充口径 0.15 m、焦距 0.45 m、像元 28.7 μm、IFOV 63.9 μrad、NETD 25 mK、积分时间 10 ms、MTF 链，形成辐射/分辨率传感器模型。")
body("基于上述实际资源完成 6 目标 × 3 热状态（20/40/60 °C）× 77 个地面距离（1–20 km）共 1,386 个算例点的仿真与数据处理。主要结果：3.7–4.8 μm 波段平均路径透过率约 0.62→0.45；F16 视在温差在 20/40/60 °C 热状态约 −0.9 K、12.8→9.9 K、28.1→22.3 K；识别/辨认 50% 距离 F16 约 10.95/3.24 km、F22 约 14.84/6.96 km、爱国者发射车约 18.53/9.50 km，航母/驱逐舰在 20 km 内均接近 1，悍马车识别/辨认概率在全距离内低于 0.5。")
body("软件默认实际工况为晴天、无云（EnvCloud.CloudClass=0），默认干扰类型为直射阳光（JamParam.JamClass=1）；软件同时提供 10 类云、雨/雪/雾参数和 18 类干扰参数块。1,386 点主算例的基线为“无云、无定量干扰”；为避免只列不用，第 4.7 节从本地干扰 XML 的粒子率、密度、激光功率/曝光量构造筛选指数，把 10 类云、18 类干扰、雨/雪/雾全部纳入 15,708 点筛选矩阵，并给出各干扰项 10 km 识别概率。")
body("软件当前仍缺少默认想定的桃园机场背景模型、ah64 目标模型、RT 大气卡片和实测传感器参数；Q2 大气样本的条件与默认想定不一致，只用于字段与量级核对。上述缺口在报告第 5 章逐项列明，补齐后再开展最终定型报告。")
p = doc.add_paragraph(); p.paragraph_format.space_before = Pt(6)
r = p.add_run("关键词："); set_run_font(r, size=10.5, bold=True, east=HEAD_FONT)
r = p.add_run("红外目标探测；软件实际工况；与那国岛；视在温差；分辨单元；任务概率")
set_run_font(r, size=10.5, east=BODY_FONT)
page_break()

# ---------------- 1 ----------------
heading("1  任务与重写原则", 1)
heading("1.1  任务背景", 2)
body("红外目标探测的成像效果由目标与背景的固有温差、大气路径的透过与自身辐射、传感器分辨率与噪声、以及目标尺寸/形状共同决定。为使仿真结果与软件内部设置一致，本报告不再使用任何软件外的假设工况或背景类型，而是直接从 XGGDCOSSim2 的默认想定、模型库、模型 Config.ini 和模型包围盒中提取参数，建立可复现的仿真算例。")
heading("1.2  重写原则", 2)
body("本版遵循以下原则：")
bullet("（1）只使用软件内实际存在的工况和目标参数；不再构造 14 类背景×6 类目标的假设矩阵，不再使用阶段报告的演示图。")
bullet("（2）默认想定作为时空与气象基准；默认想定中无法直接使用的占位项（桃园机场背景模型、ah64 目标）在报告中明确标注，不伪造资源。")
bullet("（3）大气路径按默认气象参数计算；Q2 大气样本仅用于核对软件数据字段与量级，不作为主算例输入。")
bullet("（4）传感器只采用软件默认显示参数作为锚点，缺失的辐射参数由本报告明确设定，并逐项列出假设。")
heading("1.3  报告结构", 2)
body("第 2 章给出软件实际工况与目标参数；第 3 章给出仿真方法、传感器模型与实验设计；第 4 章给出 1,386 个算例点的数据处理结果；第 5 章给出数据质量、假设与不确定度；第 6 章总结结论和后续数据补充工作；附录给出文件、脚本与参考文献。图 1 给出 V2.1 的仿真流程。")
figure(os.path.join(RES, "v2_workflow.png"), 16.0,
       "图 1  V2.1 仿真流程：仅采用软件内实际工况与目标参数")

# ---------------- 2 ----------------
heading("2  软件实际工况与目标参数", 1)
heading("2.1  默认想定", 2)
body("默认想定（编号 2）是软件内唯一完整的想定配置。其时空原点、背景设置、目标实体与气象参数如表 1。默认想定的背景名称为“桃园机场”，BgType=1（沙漠）、BgClass=1（地面）、背景范围 300 m×300 m，但背景模型文件路径为空，属于占位配置；默认目标实体为 ah64 直升机（地面运动目标，坐标 0,0,10 m，发动机停车），但模型库中不存在 ah64 模型。因此本报告不直接使用该占位背景/目标，改用软件实际可加载的与那国岛背景和 6 个目标模型。")
table([
    ["参数", "软件内实际取值", "说明"],
    ["想定编号 / 零点", "编号 2 / 2025-10-20 10:00", "默认想定"],
    ["坐标原点", "126.1234567°E，45.1234567°N，123.45 m", "地面坐标系原点"],
    ["背景设置", "桃园机场；BgType=1 沙漠；BgClass=1 地面；300 m×300 m", "占位配置，模型路径为空"],
    ["默认目标实体", "ah64直升机；地面运动目标；0,0,10 m；发动机停车", "模型库无 ah64，改用现有 6 个模型"],
    ["天气类型", "晴天（WeatherType=0）", "无云、无雨、无雪"],
    ["大气温度 / 湿度", "15 °C / 50%", "WeatherBase"],
    ["气压 / 能见度", "1013 hPa / 10000 m", "能见度 10 km"],
    ["气溶胶 / 大气模式", "干净大陆（AtmAerosol=0）/ 美国标准大气（AtmMode=0）", "WeatherBase"],
    ["湍流设置", "TurImagSimFlag=0，AtmCn2=0", "默认想定不考虑湍流"],
], [4.0, 8.0, 4.0], "表 1  默认想定的时空、背景与气象参数", align_center=False)

heading("2.2  实际背景模型：与那国岛", 2)
body("与那国岛是软件唯一实际可加载的背景模型（地图模型，海岛类）。其 Config.ini 给出的波段与温度参数如表 2；模型范围为 220 km×220 km×215.7 m。本报告取背景温度 20 °C、发射率 0.95 作为基线。")
table([
    ["参数", "取值", "说明"],
    ["模型名称 / 类型", "与那国岛 / 地图模型", "ModelCategory=地图模型"],
    ["中心坐标 / 高程", "122.987568°E，24.456214°N，0 m", "Config.ini"],
    ["模型范围", "220 km × 220 km × 215.7 m", "OSG 顶点包围盒"],
    ["红外叠加比例", "InfraredRatio=0.25", "可见光 0.3"],
    ["中波 / 长波", "3.7–4.8 μm / 8.000–12.000 μm", "Config.ini"],
    ["环境温度 / 温度范围", "20 °C / 0–60 °C", "Config.ini"],
    ["中波辐亮度范围", "0.42917987377–3.763490011 W/(m²·sr)", "Config.ini"],
], [4.0, 8.0, 4.0], "表 2  与那国岛背景模型的实际参数", align_center=False)

heading("2.3  实际目标模型", 2)
body("模型库中实际存在 6 个目标模型，覆盖空中、海面、地面三类。表 3 给出型号、类别、目标类型与 OSG 顶点包围盒尺寸（软件局部坐标，按 1 单位 = 1 m 解释，需实测标定）。6 个模型的 Config.ini 波段/温度参数完全相同：中波 3.7–4.8 μm、长波 8–12 μm、环境温度 20 °C、温度范围 0–60 °C；算例中目标差异主要来自几何尺寸与目标类型。")
table([
    ["型号名称", "类别", "目标类型", "包围盒尺寸（m）", "本报告取目标高度"],
    ["F16战斗机", "空中模型", "空中飞机目标", "9.66 × 14.85 × 4.57", "500 m"],
    ["F22战斗机", "空中模型", "空中飞机目标", "13.50 × 18.60 × 4.00", "500 m"],
    ["尼米兹级航空母舰", "海洋模型", "海上运动目标", "85.73 × 340.66 × 75.22", "0 m"],
    ["阿利伯克级驱逐舰", "海洋模型", "海上运动目标", "20.27 × 151.32 × 47.74", "0 m"],
    ["悍马车", "陆地模型", "地面运动目标", "2.81 × 5.09 × 3.20", "10 m"],
    ["爱国者导弹发射车", "陆地模型", "地面静止/运动目标", "10.24 × 22.57 × 11.07", "10 m"],
], [4.2, 2.6, 4.2, 3.6, 1.4], "表 3  软件模型库中的 6 个实际目标模型", align_center=False)

heading("2.4  默认气象与大气数据说明", 2)
body("正式算例采用默认想定的实际气象：晴天、15 °C、50%RH、1013 hPa、能见度 10 km、干净大陆气溶胶、美国标准大气、不考虑湍流。软件未随安装包提供 RT 大气卡片，大气路径按本报告第 3 章方法计算；水汽由 15 °C/50%RH/2 km 标高推得 PWV≈1.28 cm。")
body("软件自带 Q2 大气数据样本的条件为：洛阳城市、10 °C、50%RH、能见度 25（软件单位存疑）、沙漠型气溶胶、美国标准大气、白天 10:00。该条件与默认想定（15 °C、10 km、干净大陆）不一致，且 RT 卡片缺失；因此 Q2 只用于核对软件大气数据的字段、网格与量级，不作为本报告主算例输入。")

_h = heading("2.5  传感器显示参数", 2)
_h.paragraph_format.page_break_before = True
body("默认想定的传感器为显示/注入链路参数：中波红外、3.7–4.8 μm、FOV 3.75°×3°、1024×768、50 Hz、平台高度 8000 m、俯仰 −90°。软件不含 NETD、口径、焦距、像元尺寸、积分时间与噪声模型；这些参数由本报告在第 3 章明确设定。")
table([
    ["参数", "软件内实际取值", "本报告处理"],
    ["传感器类型", "中波红外（SensorClass=1）", "采用"],
    ["工作波段", "3.7–4.8 μm", "采用"],
    ["视场 / 分辨率", "3.75° × 3° / 1024 × 768", "采用"],
    ["帧率 / 位宽", "50 Hz / 8 bit", "采用帧率"],
    ["平台高度 / 俯仰", "8000 m / −90°", "采用"],
    ["显示响应", "ResCoefficient=1746，ResBias=1733", "显示映射，不作辐射定标"],
], [4.2, 7.4, 4.4], "表 4  软件默认传感器显示参数及本报告处理方式", align_center=False)

heading("2.6  软件实际大气条件的参数定位", 2)
body("软件内实际存在的大气条件只有两个：默认想定（15 °C/50%RH/10 km/干净大陆）与 Q2 样本（洛阳城市/10 °C/50%/25/沙漠型）。按能见度换算 550 nm 气溶胶消光、按温湿度和 2 km 标高换算柱水汽，二者在 (σa, PWV) 平面的位置如图 2；颜色表示 Ångström 指数 α（默认想定 α≈1.30，Q2 沙漠型按 α≈0.30 示意）。图 2 只用于参数定位，不引入软件外工况。")
figure(os.path.join(RES, "v2_scenario_map.png"), 13.6,
       "图 2  软件内实际大气条件在 (σa, PWV) 参数平面上的位置（颜色为 α）")

heading("2.7  云、雨、雪、雾等环境参数", 2)
body("云和降水/雾属于软件实际工况的一部分，前一版漏列，本版补入。默认想定的环境云类型为 0（无云），但软件同时给出云高、云厚、云密度、透明度/亮度修正以及独立云块、雨、雪、雾的完整参数，可在想定中直接修改。表 4A 给出默认想定中的实际取值。")
table([
    ["参数", "默认想定实际值", "说明"],
    ["天气类型", "晴天（WeatherType=0）", "无云、无雨、无雪"],
    ["环境云类型", "0：无云（CloudClass=0）", "软件支持 0–9 共 10 类云"],
    ["环境云高度 / 厚度", "5000 m / 1000 m", "EnvCloud"],
    ["环境云密度", "5", "相对密度参数"],
    ["透明度 / 亮度修正", "1 / 1 / 0", "波段 1、2 修正系数与偏置"],
    ["独立云块", "CloudMassType=0（无云）；高度 1000 m；厚度 300 m；粒子数 100–100", "StandCloud"],
    ["雨", "雨量 10；雨云高 1000 m；生成方式 0（无）", "Rain"],
    ["雪", "雪量 0；生成方式 0（无）", "Snow"],
    ["雾", "强度 0.5；距离 5000 m；雾高 500 m；天空盒可见 1", "Fog"],
], [4.2, 7.0, 4.8], "表 4A  默认想定的云、雨、雪、雾实际参数", align_center=False)

heading("2.8  干扰模型的实际设置", 2)
body("软件支持 18 类干扰，默认想定实际选择的是第 1 类“阳光干扰-直射阳光”，仿真方式为场景贴图模拟。表 4B 给出默认干扰设置及软件支持的干扰类型；需要注意，默认干扰的型号名称却显示为“点源诱饵弹干扰”，与 JamClass=1 不一致，应属软件配置遗留，使用前需核实。")
table([
    ["参数", "默认想定实际值", "说明"],
    ["干扰类型", "1：阳光干扰-直射阳光", "JamClass=1"],
    ["干扰型号 / 显示名", "点源诱饵弹干扰 / 点源诱饵弹干扰", "与类型 1 不一致，需核实"],
    ["仿真方式", "1：场景贴图模拟", "JamSimMode=1"],
    ["出现方式 / 持续时间", "人工控制 / 10000 ms", "ReflectLight"],
    ["关联目标 / 运动状态", "不关联 / 静止", "位置 0,0,0"],
    ["软件支持的干扰类型", "1 直射阳光；2 镜面反射；3 爆炸强光；4 火焰；5 强光干扰弹；6 战场扬尘；7 烟幕弹；8 烟幕喷射；9 水幕；10 点源诱饵弹；11 面源诱饵弹；12 点面结合诱饵弹；13 激光压制；14 激光角度欺骗；15 激光高重频；16 假目标；17 本体伪装遮蔽；18 非本体伪装遮蔽", "参数块齐全，实际只选中第 1 类"],
    ["参数块", "反射阳光、强光、战场扬尘、烟幕弹、烟幕喷射、水幕、诱饵弹、激光压制、激光角度欺骗、激光高重频、假目标、伪装遮蔽", "均有默认占位参数"],
], [4.2, 9.4, 2.4], "表 4B  默认想定的干扰实际设置与软件支持类型", align_center=False)
body("云/雨/雪/雾与干扰在软件中都是“效果/渲染参数”，没有给出光学厚度、粒子消光系数、激光到达功率等物理量；因此 1,386 点基线主算例仍为“无云、无定量干扰”。为避免只列不用，第 4.7 节用本地 XML 参数构造筛选指数，把 10 类云、18 类干扰、雨/雪/雾全部纳入 15,708 点筛选矩阵；筛选结果用于排序，严格辐射耦合仍需第 5.3 节的物理系数。")

# ---------------- 3 ----------------
heading("3  仿真方法与实验设计", 1)
heading("3.1  大气辐射传输", 2)
body("大气路径按斜程均匀近似计算。3.7–4.8 μm 内的光谱透过率为")
body("τ(λ) = exp{−[σ_a(λ) + k_H2O(λ)·C_H2O + k_CO2(λ)·C_CO2 + k_CH4(λ)·C_CH4 + σ_mol(λ)]·R}", indent=True)
body("其中 σ_a(λ)=σ_a(550)(λ/0.55)^(−α)，α=1.30，550 nm 气溶胶消光由能见度 10 km 按 Koschmieder 关系推得；H2O/CO2/CH4 截面来自 HITRAN/HAPI；R 为斜程长度。路径辐亮度为")
body("L_path = ∫ B_λ(T_air)[1−exp(−τ(λ))] dλ", indent=True)
body("T_air 取默认气象 15 °C。受 HITRAN 服务器限速，N2O、O3、CO 未纳入本次计算；缺少这三类气体对 3.7–4.8 μm 宽波段结果的影响有限，但在 4.3 μm 附近 CO2 强吸收带边缘会带来一定不确定度。")

heading("3.2  目标/背景辐亮度与视在温差", 2)
body("目标与背景的波段辐亮度为")
body("L_t = ∫ ε_t B_λ(T_t) exp[−τ(λ)] dλ + L_path", indent=True)
body("L_b = ∫ ε_b B_λ(T_b) exp[−τ(λ)] dλ + L_path", indent=True)
body("取目标发射率 ε_t=0.90、背景 ε_b=0.95；目标热状态 20/40/60 °C，背景 20 °C。由波段辐亮度反演等效黑体温度，得到视在温度 T_app；视在温差 ΔT_app=T_app(L_t)−T_app(L_b)。")

heading("3.3  传感器模型", 2)
body("软件显示参数给出 FOV 3.75°、1024 像元，因此 IFOV=3.75°/1024=63.9 μrad。为使像元与 IFOV 匹配，取口径 0.15 m、焦距 0.45 m、像元 28.7 μm；NETD 取 25 mK，积分时间 10 ms，光学透过率 0.8，MTF 链包含衍射、像元、光学与平台抖动。传感器模型参数如表 5。")
table([
    ["参数", "取值", "来源"],
    ["波段", "3.7–4.8 μm", "软件默认"],
    ["视场 / 分辨率", "3.75° × 3° / 1024 × 768", "软件默认"],
    ["平台高度 / 俯仰", "8000 m / −90°", "软件默认"],
    ["口径 / 焦距", "0.15 m / 0.45 m", "本报告设定"],
    ["像元 / IFOV", "28.7 μm / 63.9 μrad", "本报告设定"],
    ["NETD / 积分时间", "25 mK / 10 ms", "本报告设定"],
    ["光学透过率 / MTF", "0.8 / 衍射×像元×光学×抖动", "本报告设定"],
], [4.4, 7.2, 4.4], "表 5  传感器模型参数", align_center=False)

heading("3.4  分辨单元与任务概率", 2)
body("目标角尺寸 θ_t=D_t/R（D_t 取模型最大尺寸，R 为斜距）；系统角分辨率 θ_eff=√[(λ/D)²+IFOV²+（λ/r0)²]。默认想定不考虑湍流（Cn²=0），故 r0 项为 0。分辨单元数 N_e=θ_t/θ_eff。识别/辨认采用 Johnson 周数门限 16/26 的 logistic 近似；探测概率用对比度门限的误差函数近似。该模型用于相对比较，不是严格 ROC。")

heading("3.5  实验设计", 2)
body("实验矩阵为 6 个目标 × 3 个热状态 × 77 个地面距离（1–20 km，步长 0.25 km），共 1,386 个算例点。目标高度：F16/F22 取 500 m，航母/驱逐舰取 0 m，悍马/爱国者取 10 m；传感器高度 8000 m、俯仰 −90°；背景取与那国岛 20 °C；大气按默认气象 15 °C/50%/10 km/干净大陆计算；不考虑湍流。该 1,386 点为无云/无定量干扰基线；云、雨/雪/雾与 18 类干扰在 4.7 节以筛选矩阵另行计算（共 15,708 点）。每个算例点输出路径透过率、路径辐亮度、视在温差、分辨单元数、探测/识别/辨认概率。")
table([
    ["维度", "取值", "说明"],
    ["目标", "6 个实际模型", "F16、F22、尼米兹、阿利伯克、悍马、爱国者"],
    ["热状态", "20/40/60 °C", "软件目标温度范围 0–60 °C"],
    ["地面距离", "1–20 km，77 点", "步长 0.25 km"],
    ["目标高度", "0/10/500 m", "按目标类别"],
    ["传感器", "8000 m，−90°", "软件默认"],
    ["大气", "15 °C/50%/10 km/干净大陆/美国标准", "默认想定"],
    ["算例点", "6×3×77=1,386", "全部完成"],
], [3.6, 6.0, 6.4], "表 6  正式仿真实验矩阵", align_center=False)

# ---------------- 4 ----------------
heading("4  数据处理与结果", 1)
heading("4.1  大气路径", 2)
body("图 3 给出默认气象下 3.7–4.8 μm 波段平均路径透过率与路径辐亮度。地面距离 1–20 km 时，海面/地面目标的波段平均透过率约从 0.62 降到 0.45，空中目标因斜程略短而高约 0.01–0.02；路径辐亮度从约 0.31 增至 0.45 W/(m²·sr)。该量级与 10 km 能见度、1.28 cm 水汽的干净大陆条件一致。")
figure(os.path.join(RES, "software_actual_atmos.png"), 15.5,
       "图 3  默认气象（15 °C/50%RH/10 km/干净大陆/美国标准大气）下 3.7–4.8 μm 路径透过率与路径辐亮度")

heading("4.2  视在温差", 2)
body("图 4 给出 F16 目标在 20/40/60 °C 三档热状态下的视在温差。背景取与那国岛 20 °C、ε=0.95，目标 ε=0.90；大气按默认气象计算。20 °C 低热状态与背景同温，视在温差约 −0.9 K（目标略冷于背景，来自路径/发射率差异）；40 °C 中热状态约 12.8→9.9 K；60 °C 高热状态约 28.1→22.3 K。目标热状态是视在温差的主因，距离次之；对同一高度的不同目标模型，视在温差基本一致，差异主要来自目标高度与背景路径。")
figure(os.path.join(RES, "software_actual_dt.png"), 14.8,
       "图 4  软件实际目标 F16 在 20/40/60 °C 热状态下的视在温差（与那国岛背景 20 °C）")
body("为与上一版报告的图类型对应，图 5 进一步给出 F16 在 1–20 km、0–60 °C 目标温度范围内的视在温差热力图。图中 0 K 等值线约在 21 °C 附近；目标温度每升高 10 °C，近距离段 ΔT_app 约增加 5 K，距离越远增加量略小（大气路径衰减）。")
figure(os.path.join(RES, "v2_dt_heatmap.png"), 13.6,
       "图 5  F16 目标视在温差随地面距离与目标温度变化的热力图（与那国岛背景 20 °C）")

heading("4.3  分辨单元数", 2)
body("图 6 给出 6 个实际目标在 40 °C 热状态下的分辨单元数随地面距离变化（对数坐标），并标出 Johnson 探测/识别/辨认门限 4/16/26。航母与驱逐舰的分辨单元数在全距离内远高于门限；F16/F22 在 10 km 附近分别约 17/21，识别门限附近；爱国者发射车约 25，辨认门限附近；悍马车在 10 km 处仅约 5.7，低于识别门限。")
figure(os.path.join(RES, "software_actual_ne.png"), 15.0,
       "图 6  6 个实际目标的分辨单元数随地面距离变化（40 °C 热状态）")
body("默认想定不考虑湍流（Cn²=0），主算例不含湍流项。为保持与上一版报告同类型的分析，图 7 给出 F16 目标在 Cn²=1e-16–1e-13、1–20 km 范围内的 r0 与 Ne 敏感性热力图。该图只用于说明“若实际大气存在湍流”时的量级，不改变默认想定 Cn²=0 的基线结论。")
figure(os.path.join(RES, "v2_turbulence_heatmap.png"), 15.5,
       "图 7  湍流敏感性热力图（默认想定 Cn²=0；本图仅为同类型敏感性分析）")

heading("4.4  任务概率", 2)
body("图 8 给出 6 个实际目标在 40 °C 热状态下的识别/辨认概率。由于目标尺寸差异极大，曲线分层明显：航母/驱逐舰在 20 km 内识别/辨认概率均接近 1；F16 识别 50% 距离约 10.95 km、辨认约 3.24 km；F22 约 14.84/6.96 km；爱国者发射车约 18.53/9.50 km；悍马车因尺寸最小，识别/辨认概率在全距离内低于 0.5，其探测 50% 距离约 16.35 km。")
figure(os.path.join(RES, "software_actual_pd.png"), 15.5,
       "图 8  6 个实际目标 + 默认气象：识别/辨认概率随地面距离变化（40 °C 热状态）")

_h = heading("4.5  结果汇总", 2)
_h.paragraph_format.page_break_before = True
body("表 7 汇总 6 个实际目标在 40 °C 热状态、10 km 地面距离处的分辨单元数、视在温差与任务概率，以及识别/辨认的 50% 距离。表中“>20 km”表示在 20 km 范围内未降到 0.5；“无（<0.5）”表示全距离内概率低于 0.5。")
table([
    ["目标", "类别", "最大尺寸（m）", "Ne@10 km", "ΔT_app@10 km（K）", "10 km 探测/识别/辨认", "识别 50%（km）", "辨认 50%（km）"],
    ["F16", "空中", "14.85", "16.99", "11.59", "1.000 / 0.696 / 0.001", "10.95", "3.24"],
    ["F22", "空中", "18.60", "21.28", "11.59", "1.000 / 0.988 / 0.019", "14.84", "6.96"],
    ["尼米兹级航母", "海面", "340.66", "380.48", "11.52", "1.000 / 1.000 / 1.000", ">20", ">20"],
    ["阿利伯克级驱逐舰", "海面", "151.32", "169.01", "11.52", "1.000 / 1.000 / 1.000", ">20", ">20"],
    ["悍马车", "地面", "5.09", "5.69", "11.52", "0.803 / 0.000 / 0.000", "无（<0.5）", "无（<0.5）"],
    ["爱国者发射车", "地面", "22.57", "25.22", "11.52", "1.000 / 1.000 / 0.343", "18.53", "9.50"],
], [3.2, 1.6, 2.0, 1.8, 2.6, 3.0, 1.9, 1.9], "表 7  6 个实际目标在 40 °C 热状态下的正式仿真结果")

heading("4.6  讨论", 2)
body("从 1,386 个算例点可以看出，目标尺寸/分辨单元数是任务概率分层的主因；视在温差由目标热状态决定，但在对比度远高于 NETD 时，任务概率对热状态不敏感。航母、驱逐舰等大目标在全距离内探测/识别/辨认均接近 1；F16/F22 处于识别门限附近；悍马车因尺寸过小，识别/辨认能力不足。该结论与软件实际目标模型的几何尺寸一致，未引入任何软件外目标参数。")

heading("4.7  云与 18 类干扰的筛选试验", 2)
body("本节不再只是列出云/干扰，而是把软件内的 10 类云、雨/雪/雾和 18 类干扰全部纳入试验矩阵。为覆盖所有干扰项，采用筛选级模型：由软件本地干扰 XML 的粒子率、流体密度、激光功率/曝光量和云型等级归一化得到干扰指数 I；遮蔽/云类同时降低到达对比度与可分辨单元数，强光/激光/诱饵类对任务概率施加饱和/虚警惩罚。该模型用于全项筛选排序，不是严格辐射传输计算。表 7A 给出试验矩阵与点数。")
table([
    ["试验组", "工况范围", "目标/状态", "距离", "点数", "状态"],
    ["基线", "无云、无定量干扰", "6 目标 × 3 热状态", "1–20 km，77 点", "1,386", "已完成"],
    ["云型", "软件 10 类云（0–9）", "6 目标 × 40 °C", "1–20 km，77 点", "4,620", "已完成"],
    ["干扰", "软件 18 类干扰（1–18）", "6 目标 × 40 °C", "1–20 km，77 点", "8,316", "已完成"],
    ["雨/雪/雾", "软件实际参数", "6 目标 × 40 °C", "1–20 km，77 点", "1,386", "已完成"],
    ["合计", "—", "—", "—", "15,708", "全部完成"],
], [2.6, 5.0, 4.0, 2.8, 1.6, 1.8], "表 7A  云/干扰筛选试验矩阵（含全部 18 类干扰）")

body("表 7B 给出 18 类干扰的本地来源、筛选指数和 10 km 识别概率（6 目标均值；无干扰基线为 0.781）。软件本地有独立模型目录的干扰项已直接读取其 XML 参数；无独立模型目录的 2、14、15、16、17、18 类按软件参数块和类别归一化取值，并在“本地来源”列明确标注。表 7C 给出 10 类云和雨/雪/雾的结果。")
table([
    ["ID", "干扰类型", "本地模型/来源", "筛选指数 I", "10 km 识别概率"],
    ["1", "直射阳光", "sunLight", "0.90", "0.219"],
    ["2", "镜面反射", "参数块（无独立模型目录）", "0.40", "0.531"],
    ["3", "爆炸强光", "baozha", "0.75", "0.312"],
    ["4", "火焰", "fire", "0.65", "0.375"],
    ["5", "强光干扰弹", "qggrd", "0.70", "0.343"],
    ["6", "战场扬尘", "yc", "0.45", "0.444"],
    ["7", "烟幕弹", "ymd", "0.65", "0.341"],
    ["8", "烟幕喷射", "ywps", "0.60", "0.350"],
    ["9", "水幕", "shuimu", "0.55", "0.368"],
    ["10", "点源诱饵弹", "dyyrd", "0.45", "0.500"],
    ["11", "面源诱饵弹", "myyrd", "0.50", "0.468"],
    ["12", "点面结合诱饵弹", "dmjh", "0.55", "0.437"],
    ["13", "激光压制", "jgyz", "0.90", "0.219"],
    ["14", "激光角度欺骗", "参数块（无独立模型目录）", "0.40", "0.531"],
    ["15", "激光高重频", "参数块（无独立模型目录）", "0.85", "0.250"],
    ["16", "假目标", "参数块（无独立模型目录）", "0.50", "0.468"],
    ["17", "伪装遮蔽-本体", "参数块（无独立模型目录）", "0.55", "0.368"],
    ["18", "伪装遮蔽-非本体", "参数块（无独立模型目录）", "0.55", "0.368"],
], [1.2, 4.0, 6.4, 2.2, 2.2], "表 7B  18 类干扰的筛选试验结果（40 °C，6 目标均值）")
table([
    ["云/天气", "筛选指数 I", "10 km 识别概率", "备注"],
    ["0 无云", "0.00", "0.781", "基线"],
    ["1 卷云", "0.10", "0.729", "EnvCloud"],
    ["2 积云", "0.18", "0.681", "EnvCloud"],
    ["3 层云", "0.26", "0.624", "EnvCloud"],
    ["4 卷积云", "0.34", "0.553", "EnvCloud"],
    ["5 中度积云", "0.42", "0.474", "EnvCloud"],
    ["6 高分辨率浓积云", "0.50", "0.400", "EnvCloud"],
    ["7 积雨云", "0.58", "0.356", "EnvCloud"],
    ["8 层积云", "0.66", "0.340", "EnvCloud"],
    ["9 高耸积云", "0.74", "0.335", "EnvCloud"],
    ["雨", "0.30", "0.590", "RainConcentration=10"],
    ["雪", "0.00", "0.781", "SnowConcentration=0"],
    ["雾", "0.30", "0.590", "FogIntensity=0.5"],
], [4.4, 3.2, 4.0, 4.4], "表 7C  10 类云与雨/雪/雾的筛选结果")
figure(os.path.join(RES, "v2_jam_matrix.png"), 15.8,
       "图 9  18 类软件干扰下 10 km 识别概率（40 °C，筛选模型）")
figure(os.path.join(RES, "v2_cloud_matrix.png"), 15.8,
       "图 10  软件 10 类云型下 10 km 识别概率（40 °C，筛选模型）")
body("结果显示：直射阳光、激光压制、激光高重频、爆炸强光/强光弹对任务概率影响最大；烟幕弹/烟幕喷射/水幕/扬尘对 F16/F22 与爱国者等中等目标影响显著，但对航母/驱逐舰等超大目标仍不足以使其降到 0.5 以下；诱饵与假目标类为中等影响；云型越强，识别概率越低。该结果已把全部 18 类干扰纳入同一试验矩阵，后续只需用软件/实测的物理系数替换筛选模型即可。")

# ---------------- 5 ----------------
heading("5  数据质量、假设与不确定度", 1)
heading("5.1  软件资源完整性", 2)
body("本版只采用软件实际资源后，发现以下完整性问题：")
bullet("（1）默认想定的背景“桃园机场”无模型文件，BgType=1（沙漠）与名称不一致，不能直接成像；实际可加载背景只有与那国岛。")
bullet("（2）默认想定的目标 ah64 不在模型库，无法直接按想定运行；本报告改用 6 个实际目标模型。")
bullet("（3）软件未交付 RT 大气卡片，Q2 样本条件（洛阳/10 °C/25/沙漠型）与默认气象（15 °C/10 km/干净大陆）不一致。")
bullet("（4）Q2 能见度标为 25（单位存疑，疑为 25 km）；城市地点配沙漠型气溶胶；长波 7.7–10.3 μm 与 Config.ini 的 8–12 μm 不一致。")
bullet("（5）软件无辐射传感器参数（NETD、口径、焦距、像元、积分时间、噪声模型）。")

heading("5.2  模型假设", 2)
body("本报告的假设包括：目标/背景温度取 20/40/60 °C 与 20 °C；发射率取 0.90/0.95；目标高度按类别取 0/10/500 m；大气按斜程均匀近似，未纳入 N2O/O3/CO 与湍流；目标尺寸取 OSG 局部坐标最大尺寸，按 1 单位=1 m 解释；任务概率采用 Johnson logistic 近似，不是严格 ROC；未考虑背景杂波、虚警率、平台抖动与固定图案噪声。")

heading("5.3  待补数据与不确定度", 2)
table([
    ["缺口", "对结果的影响", "建议"],
    ["桃园机场背景模型缺失", "默认想定不能直接成像", "补齐模型或正式改用与那国岛想定"],
    ["ah64 目标模型缺失", "默认想定目标不可用", "补齐模型或改用现有 6 个目标"],
    ["RT 大气卡片缺失、Q2 条件不一致", "大气路径为自算，非软件 RT 结果", "按默认气象重新生成 RT 卡片"],
    ["能见度单位/气溶胶类型/长波口径存疑", "路径透过率与气溶胶类型不确定", "核对软件单位与波段定义"],
    ["无实测传感器参数", "NETD/口径/IFOV/MTF 为本报告假设", "用实测参数替换表 5"],
    ["目标包围盒按 1 单位=1 m", "目标尺寸/角尺寸存在标定不确定度", "几何标定/人工核定"],
    ["未考虑湍流、杂波、ROC", "结果偏乐观/任务概率为相对值", "补充 Cn²、杂波与 ROC 数据"],
    ["云/雨/雪/雾缺光学厚度与粒子消光系数", "无法定量云层衰减/云自身辐射", "补云粒子谱、消光系数、云温"],
    ["干扰缺辐射强度/激光到达功率/消光系数", "无法定量干扰对 P_d 的影响", "补干扰辐射与激光参数"],
], [5.4, 5.4, 5.2], "表 8  数据缺口、影响与建议", align_center=False)

heading("5.4  对结论的影响", 2)
body("本报告结论的“相对排序”是稳健的：目标尺寸越大，识别/辨认距离越远；悍马车因尺寸小，识别/辨认能力不足；视在温差随目标热状态显著变化。但“绝对距离”受传感器假设、大气路径与目标尺寸标定影响，需在实测参数到位后重新计算。报告不把当前结果作为装备定型依据。")

# ---------------- 6 ----------------
heading("6  结论与后续", 1)
heading("6.1  结论", 2)
body("本报告按“只采用软件内实际工况和目标参数”完成重写，删除阶段演示内容，处理了 1,386 个正式算例点，主要结论如下：")
bullet("（1）软件实际可用资源为：默认想定 1 个（编号 2）、背景模型 1 个（与那国岛）、目标模型 6 个、默认气象 1 组、传感器显示参数 1 组；默认想定的桃园机场背景与 ah64 目标为占位/缺失项。")
bullet("（2）默认气象（15 °C/50%RH/10 km/干净大陆/美国标准大气、无湍流）下，3.7–4.8 μm 波段平均路径透过率约 0.62→0.45，路径辐亮度约 0.31→0.45 W/(m²·sr)。")
bullet("（3）F16 在 60 °C 高热状态下的视在温差约 28.1→22.3 K，40 °C 约 12.8→9.9 K，20 °C 约 −0.9 K；目标热状态是视在温差的主因。")
bullet("（4）6 个实际目标的识别/辨认能力由目标尺寸决定：航母/驱逐舰在 20 km 内接近 1；F16 识别/辨认 50% 距离约 10.95/3.24 km，F22 约 14.84/6.96 km，爱国者发射车约 18.53/9.50 km；悍马车识别/辨认概率在全距离内低于 0.5。")
bullet("（5）软件实际资源仍存在背景/目标占位、Q2 条件不一致、RT 卡片缺失、无辐射传感器参数、无湍流等问题；云/雨/雪/雾与 18 类干扰已用本地参数纳入筛选试验，但严格辐射耦合仍缺光学/辐射系数，表 8 已逐项列出。")
bullet("（6）全部 10 类云、18 类干扰、雨/雪/雾已纳入 15,708 点筛选矩阵：直射阳光、激光压制、激光高重频、爆炸强光/强光弹影响最大；烟幕/水幕/扬尘对中等目标显著，对超大目标仍不足以降到 0.5 以下；诱饵/假目标为中等影响。")
heading("6.2  后续工作", 2)
body("待软件方补齐桃园机场背景模型、ah64 目标模型、按默认气象生成的 RT 大气卡片，以及实测传感器参数后，重新运行 1,386 个算例点并出最终定型报告。在此之前，本报告只作为“基于软件现有数据的正式仿真报告”，不把缺失数据下的结果作为最终结论。")

# ---------------- appendix A ----------------
heading("附录 A  文件与脚本清单", 1)
table([
    ["文件", "说明"],
    ["正式仿真\\make_software_actual_case.py", "V2.1 主算例脚本（1,386 点）"],
    ["正式仿真\\make_v2_extra_figures.py", "V2.1 同类型新图脚本（图 1/2/5/7）"],
    ["正式仿真\\make_interference_screening.py", "云/18 类干扰筛选脚本（15,708 点）"],
    ["正式仿真\\results\\software_actual_case_results.csv", "全算例点结果（1,386 行）"],
    ["正式仿真\\results\\software_actual_summary.csv", "10 km 与 50% 距离汇总"],
    ["正式仿真\\results\\v2_workflow.png", "图 1 仿真流程"],
    ["正式仿真\\results\\v2_scenario_map.png", "图 2 实际大气条件参数定位"],
    ["正式仿真\\results\\software_actual_atmos.png", "图 3 大气路径"],
    ["正式仿真\\results\\software_actual_dt.png", "图 4 视在温差曲线"],
    ["正式仿真\\results\\v2_dt_heatmap.png", "图 5 视在温差热力图"],
    ["正式仿真\\results\\software_actual_ne.png", "图 6 分辨单元数"],
    ["正式仿真\\results\\v2_turbulence_heatmap.png", "图 7 湍流敏感性热力图"],
    ["正式仿真\\results\\software_actual_pd.png", "图 8 任务概率"],
    ["正式仿真\\results\\v2_jam_matrix.png", "图 9 18 类干扰筛选矩阵"],
    ["正式仿真\\results\\v2_cloud_matrix.png", "图 10 10 类云筛选矩阵"],
    ["正式仿真\\results\\interference_jam_summary.csv", "18 类干扰筛选结果"],
    ["正式仿真\\results\\interference_cloud_summary.csv", "10 类云筛选结果"],
    ["软件参数提取\\models.json / 模型与想定参数.md", "模型库、枚举、默认想定与包围盒"],
    ["软件参数提取\\Q2解析\\atmosphere_index.csv", "Q2 大气样本索引（仅核对）"],
    ["进度看板\\index.html / progress.json", "实时进度看板"],
], [7.0, 9.0], "表 A1  报告相关文件与脚本", align_center=False)

heading("附录 B  数据来源与参考文献", 1)
refs = [
    "[1] Kochanov, R. V., et al. HITRAN Application Programming Interface (HAPI): A comprehensive approach to working with spectroscopic data. Journal of Quantitative Spectroscopy & Radiative Transfer, 2016, 177: 15–30.",
    "[2] HITRAN online database. https://hitran.org/",
    "[3] Johnson, J. Analysis of image forming systems. Proceedings of the Image Intensifier Symposium, 1958.",
    "[4] XGGDCOSSim2 光电环境仿真软件数据目录（Data\\AtomData、Data\\SystemBaseFile、Data\\ModelData），2025–2026。",
    "[5] Ångström, A. On the atmospheric transmission of sun radiation and on dust in the air. Geografiska Annaler, 1929, 11: 156–166.",
]
for ref in refs:
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(3)
    p.paragraph_format.line_spacing = 1.2
    r = p.add_run(ref)
    set_run_font(r, size=8.8, east=BODY_FONT)
body("说明：软件实际想定参数取自 DefaultPlanFile，模型尺寸取自 OSG 顶点包围盒，目标/背景波段与温度参数取自各自 Config.ini；Q2 大气数据仅用于字段、网格与量级交叉核对。逐线吸收截面由 HAPI 基于 HITRAN 数据计算；受服务器限速，N2O、O3、CO 暂未纳入本次计算。", indent=True, size=9)

doc.save(OUT)
print("saved:", OUT)
