# -*- coding: utf-8 -*-
"""渲染《V3.0 参数释义手册》docx + md。"""
import csv
import os
import sys

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import manual_data as MD  # noqa: E402

ROOT = r"F:\DeepSeek工作区\红外识别极限重构_V3.0"
CSV = os.path.join(ROOT, "05_参数依据", "参数依据登记表.csv")
OUT_DIR = os.path.join(ROOT, "05_参数依据")
os.makedirs(OUT_DIR, exist_ok=True)

BODY_FONT = "宋体"
HEAD_FONT = "微软雅黑"
MONO_FONT = "Consolas"
ACCENT = RGBColor(0x1F, 0x3B, 0x5C)
GREY = RGBColor(0x5A, 0x5A, 0x5A)


def load_rows():
    rows = list(csv.DictReader(open(CSV, encoding="utf-8-sig")))
    assert len(rows) == 106, len(rows)
    ids = [r["param_id"] for r in rows]
    missing = [i for i in ids if i not in MD.MEANING]
    assert not missing, f"缺少含义: {missing}"
    grouped = [pid for _, _, ids2 in MD.GROUPS for pid in ids2]
    assert sorted(grouped) == sorted(ids), (
        f"分组不一致: 多={set(grouped) - set(ids)}, 少={set(ids) - set(grouped)}")
    return rows, {r["param_id"]: r for r in rows}


def set_font(run, name, size=None, bold=None, color=None):
    run.font.name = name
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = rpr.makeelement(qn("w:rFonts"), {})
        rpr.append(rfonts)
    rfonts.set(qn("w:eastAsia"), name)
    rfonts.set(qn("w:ascii"), name)
    rfonts.set(qn("w:hAnsi"), name)
    if size is not None:
        run.font.size = Pt(size)
    if bold is not None:
        run.font.bold = bold
    if color is not None:
        run.font.color.rgb = color


def init_doc():
    doc = Document()
    sec = doc.sections[0]
    sec.page_width = Cm(21.0)
    sec.page_height = Cm(29.7)
    sec.top_margin = Cm(2.2)
    sec.bottom_margin = Cm(2.0)
    sec.left_margin = Cm(2.2)
    sec.right_margin = Cm(1.8)
    st = doc.styles["Normal"]
    st.font.name = BODY_FONT
    st.font.size = Pt(10.5)
    st.element.rPr.rFonts.set(qn("w:eastAsia"), BODY_FONT)
    st.paragraph_format.space_after = Pt(4)
    st.paragraph_format.line_spacing = 1.28
    for lvl, size in ((1, 15), (2, 12)):
        h = doc.styles[f"Heading {lvl}"]
        h.font.name = HEAD_FONT
        h.font.size = Pt(size)
        h.font.bold = True
        h.font.color.rgb = ACCENT
        h.element.rPr.rFonts.set(qn("w:eastAsia"), HEAD_FONT)
        h.paragraph_format.space_before = Pt(9 if lvl == 1 else 7)
        h.paragraph_format.space_after = Pt(3)
    return doc


def para(doc, text, size=10.5, bold=False, align=None, color=None, space_after=4):
    p = doc.add_paragraph()
    r = p.add_run(text)
    set_font(r, BODY_FONT, size=size, bold=bold, color=color)
    if align is not None:
        p.alignment = align
    p.paragraph_format.space_after = Pt(space_after)
    return p


def bullet(doc, text, size=10):
    p = doc.add_paragraph(style="List Bullet")
    r = p.add_run(text)
    set_font(r, BODY_FONT, size=size)
    p.paragraph_format.space_after = Pt(2)
    return p


def code_line(doc, text, size=9):
    p = doc.add_paragraph()
    r = p.add_run(text)
    set_font(r, MONO_FONT, size=size)
    p.paragraph_format.left_indent = Cm(0.6)
    p.paragraph_format.space_after = Pt(1)
    return p


def shade(cell, hexcolor):
    tcPr = cell._tc.get_or_add_tcPr()
    el = tcPr.makeelement(qn("w:shd"), {qn("w:val"): "clear",
                                        qn("w:color"): "auto",
                                        qn("w:fill"): hexcolor})
    tcPr.append(el)


def set_table_fixed(table, widths_cm):
    """强制固定表格布局并写入列宽（python-docx 单独设 cell.width 在 Word/LO 中常被忽略）。"""
    tbl = table._tbl
    tblPr = tbl.tblPr
    layout = OxmlElement("w:tblLayout")
    layout.set(qn("w:type"), "fixed")
    tblPr.append(layout)
    tblW = tblPr.find(qn("w:tblW"))
    if tblW is None:
        tblW = OxmlElement("w:tblW")
        tblPr.append(tblW)
    tblW.set(qn("w:type"), "dxa")
    tblW.set(qn("w:w"), str(int(sum(widths_cm) * 567)))
    grid = tbl.find(qn("w:tblGrid"))
    if grid is not None:
        cols = grid.findall(qn("w:gridCol"))
        for gc, w in zip(cols, widths_cm):
            gc.set(qn("w:w"), str(int(w * 567)))
    for row in table.rows:
        for i, w in enumerate(widths_cm):
            if i < len(row.cells):
                row.cells[i].width = Cm(w)


def make_table(doc, headers, rows, widths=None, font_size=8.3, header_fill="DCE6F1"):
    t = doc.add_table(rows=1, cols=len(headers))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.autofit = False
    hdr = t.rows[0].cells
    for i, h in enumerate(headers):
        hdr[i].text = ""
        p = hdr[i].paragraphs[0]
        r = p.add_run(h)
        set_font(r, HEAD_FONT, size=font_size, bold=True)
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        shade(hdr[i], header_fill)
    for row in rows:
        cells = t.add_row().cells
        for i, v in enumerate(row):
            cells[i].text = ""
            p = cells[i].paragraphs[0]
            r = p.add_run(str(v))
            set_font(r, BODY_FONT, size=font_size)
            p.paragraph_format.space_after = Pt(0)
    if widths:
        set_table_fixed(t, widths)
    return t


def build_markdown(rows, by_id):
    L = []
    L.append("# V3.0 参数释义手册\n")
    L.append("> 配套文档：《红外目标识别概率极限与临界状态 V3.0》正式报告与《参数依据登记表》106 项参数。")
    L.append("> 本手册回答一个问题：**报告里出现的每个参数，物理上是什么、为什么取这个值、它影响哪个结果。**\n")
    L.append("## 0 阅读说明\n")
    L.append("- 参数来源四分类（报告中每个参数都标注其一）：")
    L.append("  - `软件实测 SYS`：从 XGGDCOSSim2 安装目录的配置/模型文件解析得到，可直接溯源；")
    L.append("  - `文献 LIT`：给出文献编号（报告附录 C）；")
    L.append("  - `推导 DER`：由其他已登记参数按物理公式推出；")
    L.append("  - `设定 SET`：无直接出处但工程合理，必须写明理由与如何被实测替换。")
    L.append("- 置信度：高 / 中 / 低。低置信度项已在报告 §5.2 与《争议与不确定清单》单独登记。")
    L.append("- 参数唯一真值源是 `04_模型代码/irrecog/params.py`，`参数依据登记表.csv` 由其导出。\n")
    L.append("## 1 参数如何串起来：一条公式链\n")
    L.append("```")
    for name, formula, _ in MD.CHAIN:
        L.append(f"{name}: {formula}")
    L.append("```\n")
    L.append("## 2 参数分组详解（13 组，共 106 项）\n")
    for gi, (short, desc, ids) in enumerate(MD.GROUPS, 1):
        L.append(f"### 2.{gi} {short}\n")
        L.append(desc + "\n")
        L.append("| 符号 | 参数 | 取值 | 单位 | 含义 | 依据 | 置信度 |")
        L.append("|---|---|---|---|---|---|---|")
        for pid in ids:
            r = by_id[pid]
            L.append(f"| {r['符号']} | {r['参数']} | {r['取值']} | {r['单位']} | "
                     f"{MD.MEANING[pid]} | {r['类别']} | {r['置信度']} |")
        L.append("")
    L.append("## 14 报告里的结果量是什么意思（它们不是输入参数）\n")
    L.append("| 结果量 | 含义 | 典型值 |")
    L.append("|---|---|---|")
    for row in MD.RESULTS:
        L.append("| " + " | ".join(row) + " |")
    L.append("\n## 15 双轨口径与内部一致性\n")
    for s in MD.DUAL:
        L.append(f"- {s}")
    L.append("\n## 16 已登记的缺口与不确定度\n")
    L.append("| 缺口/假设 | 影响 | 对结论方向 |")
    L.append("|---|---|---|")
    for row in MD.GAPS:
        L.append("| " + " | ".join(row) + " |")
    L.append("\n## 附录 A 106 项参数速查表\n")
    L.append("| # | 编号 | 参数 | 符号 | 取值 | 单位 | 依据 | 置信度 |")
    L.append("|---|---|---|---|---|---|---|---|")
    for i, r in enumerate(rows, 1):
        L.append(f"| {i} | {r['param_id']} | {r['参数']} | {r['符号']} | {r['取值']} | "
                 f"{r['单位']} | {r['类别']} | {r['置信度']} |")
    L.append("\n## 附录 B 参数与代码/数据的对应\n")
    L.append("| 文件 | 作用 |")
    L.append("|---|---|")
    for name, desc in MD.MAPS:
        L.append(f"| `{name}` | {desc} |")
    return "\n".join(L)


def build_docx(rows, by_id):
    doc = init_doc()

    # ---------- 封面 ----------
    for _ in range(3):
        doc.add_paragraph()
    para(doc, "红外目标识别概率极限与临界状态仿真", size=19, bold=True,
         align=WD_ALIGN_PARAGRAPH.CENTER)
    para(doc, "V3.0 参数释义手册", size=27, bold=True,
         align=WD_ALIGN_PARAGRAPH.CENTER, color=ACCENT)
    para(doc, "——106 个参数：含义、取值、来源与影响——", size=12,
         align=WD_ALIGN_PARAGRAPH.CENTER, color=GREY)
    for _ in range(6):
        doc.add_paragraph()
    for line in ["配套报告：《红外目标识别概率极限与临界状态 V3.0》",
                 "数据来源：《参数依据登记表》106 项（SYS/LIT/DER/SET 四类）",
                 "参数真值源：04_模型代码/irrecog/params.py",
                 "版本：V3.0    日期：2026-11"]:
        para(doc, line, size=10.5, align=WD_ALIGN_PARAGRAPH.CENTER, color=GREY)
    doc.add_page_break()

    # ---------- 0 阅读说明 ----------
    doc.add_heading("0  阅读说明", level=1)
    para(doc, "本手册是 V3.0 正式报告与《参数依据登记表》的配套读物，回答一个问题："
              "报告里出现的每个参数，物理上是什么、为什么取这个值、它影响哪个结果。")
    para(doc, "参数按依据来源分为四类，这是本项目禁止无出处数值原则的落地方式：", bold=True)
    bullet(doc, "软件实测（SYS）：从 XGGDCOSSim2 安装目录的配置/模型文件直接解析，可溯源到具体文件与字段；")
    bullet(doc, "文献（LIT）：来自公开文献/标准，给出文献编号（见报告附录 C）；")
    bullet(doc, "推导（DER）：由其他已登记参数按物理公式推出，公式可在附录 B 的代码文件中核对；")
    bullet(doc, "设定（SET）：无直接出处但工程合理，必须写明为什么合理、如何被实测替换。")
    para(doc, "置信度分高/中/低三档；所有低置信度项、口径冲突项与已知缺口，均在报告 §5.2 与"
              "《争议与不确定清单》中单独登记，不隐藏在正文里。")
    para(doc, "参数唯一真值源是 04_模型代码/irrecog/params.py；《参数依据登记表.csv》由它自动导出；"
              "报告与图件只允许引用真值源中的值。")

    # ---------- 1 公式链 ----------
    doc.add_heading("1  参数如何串起来：一条公式链", level=1)
    para(doc, "把 106 个参数按计算顺序排列，可以看清每个参数在哪一步起作用。"
              "下面这条链就是报告第 2 章的模型主干：")
    for name, formula, note in MD.CHAIN:
        p = doc.add_paragraph()
        r = p.add_run(f"{name}：")
        set_font(r, HEAD_FONT, size=10.5, bold=True)
        p.paragraph_format.space_after = Pt(1)
        code_line(doc, "    " + formula)
        para(doc, "    " + note, size=9.5, color=GREY, space_after=6)

    # ---------- 2 分组详解 ----------
    doc.add_heading("2  参数分组详解（13 组，共 106 项）", level=1)
    for gi, (short, desc, ids) in enumerate(MD.GROUPS, 1):
        doc.add_heading(f"2.{gi}  {short}", level=2)
        para(doc, desc)
        trows = []
        for pid in ids:
            r = by_id[pid]
            trows.append([r["符号"], r["参数"], r["取值"], r["单位"],
                          MD.MEANING[pid], r["类别"], r["置信度"]])
        make_table(doc, ["符号", "参数", "取值", "单位", "含义（物理意义与用途）", "依据", "置信度"],
                   trows, widths=[1.8, 2.8, 2.2, 1.2, 6.0, 1.8, 1.2])

    # ---------- 14 结果量 ----------
    doc.add_heading("14  报告里的结果量是什么意思（它们不是输入参数）", level=1)
    para(doc, "报告表格中除了输入参数，还有一批结果量。它们由前面的参数链计算得到，"
              "是回答问题「能识别多远、临界在哪」的最终答案：")
    make_table(doc, ["结果量", "含义", "基线工况典型值"], MD.RESULTS,
               widths=[2.8, 8.6, 5.6])

    # ---------- 15 双轨口径 ----------
    doc.add_heading("15  双轨口径与内部一致性（读报告时必须注意）", level=1)
    for s in MD.DUAL:
        bullet(doc, s)

    # ---------- 16 缺口 ----------
    doc.add_heading("16  已登记的缺口与不确定度（详见报告 §5.2）", level=1)
    make_table(doc, ["缺口/假设", "影响", "对结论方向"], MD.GAPS,
               widths=[6.4, 6.2, 4.4])

    # ---------- 附录 A ----------
    doc.add_page_break()
    doc.add_heading("附录 A  106 项参数速查表", level=1)
    para(doc, "按参数登记表顺序列出；完整解释见第 2 章对应分组。", size=10, color=GREY)
    arows = []
    for i, r in enumerate(rows, 1):
        arows.append([i, r["param_id"], r["参数"], r["符号"], r["取值"],
                      r["单位"], r["类别"], r["置信度"]])
    make_table(doc, ["#", "编号", "参数", "符号", "取值", "单位", "依据", "置信度"],
               arows, widths=[0.8, 3.3, 3.1, 1.8, 3.3, 1.4, 1.7, 1.6], font_size=7.6)

    # ---------- 附录 B ----------
    doc.add_heading("附录 B  参数与代码/数据的对应", level=1)
    make_table(doc, ["文件", "作用"], MD.MAPS, widths=[7.4, 9.6])

    out = os.path.join(OUT_DIR, "参数释义手册_V3.0.docx")
    doc.save(out)
    return out


def main():
    rows, by_id = load_rows()
    print(f"[1/4] 登记表载入：{len(rows)} 项；释义齐全、13 组覆盖完整")

    md = build_markdown(rows, by_id)
    md_path = os.path.join(OUT_DIR, "参数释义手册_V3.0.md")
    open(md_path, "w", encoding="utf-8").write(md)
    print(f"[2/4] Markdown 已写：{md_path}（{len(md)/1024:.1f} KB）")

    docx_path = build_docx(rows, by_id)
    print(f"[3/4] Word 已写：{docx_path}（{os.path.getsize(docx_path)/1024:.1f} KB）")

    d = Document(docx_path)
    print(f"[4/4] 复核：段落 {len(d.paragraphs)}，表格 {len(d.tables)}")
    assert len(d.tables) == len(MD.GROUPS) + 4, len(d.tables)
    total = sum(len(t.rows) - 1 for t in d.tables[:len(MD.GROUPS)])
    print(f"     分组表数据行合计 = {total}（应为 106）")
    assert total == 106
    print("完成。")


if __name__ == "__main__":
    main()
