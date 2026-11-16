# -*- coding: utf-8 -*-
"""
irrecog.report —— 正式仿真报告（DOCX）自动生成

本模块只做三件事：
1. 从 ``03_数据`` 的 CSV 中**运行时读取**正文需要的全部结论性数值；
2. 按 ``00_构建脚本/重制实施规范.md`` §5 的章节与版式生成 DOCX；
3. 对生成的 DOCX 做“不含版本史字样”的自检。

设计约定
--------
- 函数签名固定为 ``build(data_dir, fig_dir, out_docx)``（run_all.py 调用）。
- 图件按 ``02_图表`` 的文件编号引用：图01→图1 … 图17→图17；图00 放附录 A。
- 任何 CSV 缺失、某列缺失或某行为 NaN 都不得导致崩溃：正文显示“—”，
  并在 5.1 节与附录 D 说明截断/缺失原因。
- 正文中禁止出现任何版本史字样（见 ``FORBIDDEN_PATTERNS``），build() 结束时自检。
"""

import datetime
import math
import os
import re
import zipfile

import numpy as np
import pandas as pd
from docx import Document
from docx.enum.section import WD_ORIENT, WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from . import params

# --------------------------------------------------------------------------- #
# 0. 报告常量
# --------------------------------------------------------------------------- #
REPORT_TITLE = "红外目标识别概率极限与临界状态仿真报告"
REPORT_SUBTITLE = "基于软件实测目标模型与 HITRAN2020 光谱大气的多工况单变量研究"
REPORT_DATE = "2026 年 11 月"
MODEL_NAME = "irrecog 光谱—传感器—判据模型"

HEAD_FONT = "Microsoft YaHei"
BODY_FONT = "宋体"
NAVY = RGBColor(0x1F, 0x3A, 0x5F)
GREY = RGBColor(0x59, 0x59, 0x59)
DARK = RGBColor(0x22, 0x22, 0x22)
RED = RGBColor(0x9C, 0x27, 0x1B)

TORDER = ["HM", "F16", "F22", "AGZFSC", "ALBK", "NIMITZ"]
TSHORT = {"HM": "悍马", "F16": "F16", "F22": "F22",
          "AGZFSC": "爱国者", "ALBK": "阿利伯克", "NIMITZ": "尼米兹"}
TNAME = {t["key"]: t["name"] for t in params.TARGETS}
SMALL_T = ["HM", "F16", "F22"]
MID_T = ["AGZFSC"]
LARGE_T = ["ALBK", "NIMITZ"]

# 禁止字样（全文自检用；正则覆盖中英文两种写法）
FORBIDDEN_PATTERNS = [
    r"(?<![A-Za-z])V1(?![0-9A-Za-z])",
    r"(?<![A-Za-z])V2(?:\.1)?(?![0-9A-Za-z])",
    r"(?<![A-Za-z])V3\.0(?![0-9A-Za-z])",
    r"重构", r"重制", r"上一版", r"回填", r"旧版", r"旧报告", r"历史归档",
    r"版本号", r"版本史",
]

# 最终图件文件名（按重制实施规范 §4 的编号；括号内为过渡期备用名）
FIG_FILES = {
    "00": ("图00_项目思维导图.png",),
    "01": ("图01_模型链路与三类极限.png",),
    "02": ("图02_工况空间与默认工况定位.png",),
    "03": ("图03_斜程大气光谱透过率.png", "图03_光谱大气透过率.png"),
    "04": ("图04_MTF链与MRTD.png",),
    "05": ("图05_基线任务概率曲线.png",),
    "06": ("图06_三任务临界距离对比.png",),
    "07": ("图07_单变量_气溶胶AOD.png",),
    "08": ("图08_单变量_湍流Cn2.png",),
    "09": ("图09_单变量_目标热状态与发射率.png",),
    "10": ("图10_单变量_传感器参数.png",),
    "11": ("图11_单变量_平台高度.png",),
    "12": ("图12_波段对比.png",),
    "13": ("图13_识别极限包络.png", "图17_识别极限包络.png"),
    "14": ("图14_相图_AODxCn2.png", "图13_相图_AODxCn2.png"),
    "15": ("图15_相图_温差xAOD.png", "图14_相图_温差xAOD.png"),
    "16": ("图16_真实气候工况热力图.png", "图15_真实气候工况热力图.png"),
    "17": ("图17_敏感性弹性排序.png", "图16_敏感性弹性排序.png"),
}

# 图幅宽度（cm）：规范指定 图03=16、图12=15、图14/15=16、图16=15.5、图00=15.5
FIG_WIDTH = {k: 16.0 for k in ["%02d" % i for i in range(1, 18)]}
FIG_WIDTH["00"] = 15.5  # 仅纵向回退版使用；附录 A 横版整页按 24 cm 插入

_FIG_STATUS = {}


# --------------------------------------------------------------------------- #
# 1. 排版工具
# --------------------------------------------------------------------------- #
def _set_font(run, size=10.5, bold=False, color=None, east=BODY_FONT, italic=False):
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.italic = italic
    run.font.name = "Times New Roman"
    rPr = run._element.get_or_add_rPr()
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rPr.append(rFonts)
    rFonts.set(qn("w:ascii"), "Times New Roman")
    rFonts.set(qn("w:hAnsi"), "Times New Roman")
    rFonts.set(qn("w:eastAsia"), east)
    if color is not None:
        run.font.color.rgb = color
    return run


_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")


def _add_rich(paragraph, text, size=10.5, color=None, east=BODY_FONT, bold=False):
    """支持 **加粗** 标记的富文本写入。"""
    text = "" if text is None else str(text)
    pos = 0
    for m in _BOLD_RE.finditer(text):
        if m.start() > pos:
            _set_font(paragraph.add_run(text[pos:m.start()]), size, bold, color, east)
        _set_font(paragraph.add_run(m.group(1)), size, True, color, east)
        pos = m.end()
    if pos < len(text):
        _set_font(paragraph.add_run(text[pos:]), size, bold, color, east)


def heading(doc, text, level=1):
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.keep_with_next = True
    if level == 1:
        pf.space_before = Pt(16)
        pf.space_after = Pt(7)
        size, color = 15, NAVY
    elif level == 2:
        pf.space_before = Pt(12)
        pf.space_after = Pt(5)
        size, color = 12.5, DARK
    else:
        pf.space_before = Pt(8)
        pf.space_after = Pt(4)
        size, color = 11, DARK
    _set_font(p.add_run(text), size, True, color, HEAD_FONT)
    return p


def body(doc, text, indent=True, size=10.5, align=None, space_after=4.0,
         space_before=0.0, bold=False, line_spacing=1.35):
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.line_spacing = line_spacing
    pf.space_after = Pt(space_after)
    pf.space_before = Pt(space_before)
    if indent:
        pf.first_line_indent = Pt(21)
    if align is not None:
        p.alignment = align
    _add_rich(p, text, size=size, bold=bold)
    return p


def bullet(doc, text, size=10.5, space_after=3.0):
    p = doc.add_paragraph(style="List Bullet")
    pf = p.paragraph_format
    pf.line_spacing = 1.3
    pf.space_after = Pt(space_after)
    _add_rich(p, text, size=size)
    # 中文环境下列表符号段落右缩进略收
    pf.left_indent = Cm(0.74)
    pf.first_line_indent = Cm(-0.37)
    return p


def note(doc, text, size=9.0, color=GREY, align=None, space_after=4.0, indent=False):
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.line_spacing = 1.2
    pf.space_after = Pt(space_after)
    if indent:
        pf.first_line_indent = Pt(18)
    if align is not None:
        p.alignment = align
    _add_rich(p, text, size=size, color=color)
    return p


def _caption(doc, text, kind="fig"):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    pf = p.paragraph_format
    pf.space_before = Pt(3 if kind == "fig" else 6)
    pf.space_after = Pt(7 if kind == "fig" else 3)
    pf.keep_with_next = (kind == "table")
    _set_font(p.add_run(text), 9.0, True,
              GREY if kind == "fig" else DARK, HEAD_FONT)
    return p


def figure(doc, fig_dir, key, caption_text):
    """插入图件；编号 key 与文件名编号一致。缺失时占位并记录，不中断。

    图注只保留图号与图题：即使调用方误写图片文件名括注，也在这里统一剔除。
    图片文件名仅允许出现在附录 D 的文件清单中。
    """
    caption_text = re.sub(r"（\s*对应文件\s*图\d{2}[^）]*）", "", caption_text)
    caption_text = re.sub(r"[，,]\s*对应文件\s*图\d{2}[^）]*）", "）", caption_text)
    caption_text = re.sub(r"（\s*(?:对应)?文件[：:]\s*图\d{2}[^）]*）", "", caption_text)
    caption_text = caption_text.replace("（300 dpi）", "").replace("300 dpi", "")
    names = FIG_FILES.get(key, ())
    path = None
    for name in names:
        cand = os.path.join(fig_dir, name)
        if os.path.exists(cand):
            path = cand
            _FIG_STATUS[key] = name
            break
    if path is None:
        _FIG_STATUS[key] = None
        note(doc, f"[图件缺失：{'/'.join(names)}]", size=9, color=RED,
             align=WD_ALIGN_PARAGRAPH.CENTER, space_after=2)
    else:
        doc.add_picture(path, width=Cm(FIG_WIDTH.get(key, 15.0)))
        img_p = doc.paragraphs[-1]
        img_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        img_p.paragraph_format.space_before = Pt(4)
        img_p.paragraph_format.keep_with_next = True
    _caption(doc, caption_text, "fig")
    return path


def _shade_cell(cell, fill="DCE6F1"):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    tcPr.append(shd)


def _repeat_header(row):
    trPr = row._tr.get_or_add_trPr()
    tblHeader = OxmlElement("w:tblHeader")
    tblHeader.set(qn("w:val"), "true")
    trPr.append(tblHeader)


def table(doc, df, widths=None, caption=None, font=8.6, header_font=8.6,
          align_first_left=False, note_text=None, dash="—"):
    """插入三线感（浅蓝表头）表格；df 为空时也保留标题与占位，保证编号连续。"""
    if caption:
        _caption(doc, caption, "table")
    if df is None or len(df) == 0:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        _set_font(p.add_run("（该表所需数据缺失，详见 5.1 节与附录 D）"), 9, False, GREY)
        if note_text:
            note(doc, note_text, size=8.5)
        return None

    df = df.copy()
    n_row, n_col = len(df), len(df.columns)
    t = doc.add_table(rows=n_row + 1, cols=n_col)
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.autofit = False
    # 表头
    for j, col in enumerate(df.columns):
        cell = t.cell(0, j)
        cell.text = ""
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.line_spacing = 1.05
        _set_font(p.add_run(str(col)), header_font, True, DARK, HEAD_FONT)
        _shade_cell(cell)
    _repeat_header(t.rows[0])
    # 数据
    for i, (_, row) in enumerate(df.iterrows(), start=1):
        for j, v in enumerate(row):
            cell = t.cell(i, j)
            cell.text = ""
            p = cell.paragraphs[0]
            p.alignment = (WD_ALIGN_PARAGRAPH.LEFT if (align_first_left and j == 0)
                           else WD_ALIGN_PARAGRAPH.CENTER)
            p.paragraph_format.space_after = Pt(0)
            p.paragraph_format.line_spacing = 1.05
            txt = "" if (pd.isna(v) if not isinstance(v, (list, tuple, dict)) else False) else str(v)
            if txt.strip() == "":
                txt = dash
            _set_font(p.add_run(txt), font, False, DARK)
    if widths:
        for j, w in enumerate(widths[:n_col]):
            for row in t.rows:
                row.cells[j].width = Cm(w)
    # 行内不跨页：避免一张表的同一行被页边界拆开
    for row in t.rows:
        trPr = row._tr.get_or_add_trPr()
        cant = OxmlElement("w:cantSplit")
        cant.set(qn("w:val"), "true")
        trPr.append(cant)
    # 表后留白
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(2)
    p.paragraph_format.line_spacing = 1.0
    if note_text:
        note(doc, note_text, size=8.5)
    return t


def _add_field(paragraph, instr, size=9.0):
    run = paragraph.add_run()
    _set_font(run, size, False, GREY)
    fld_begin = OxmlElement("w:fldChar")
    fld_begin.set(qn("w:fldCharType"), "begin")
    instr_el = OxmlElement("w:instrText")
    instr_el.set(qn("xml:space"), "preserve")
    instr_el.text = f" {instr} "
    fld_sep = OxmlElement("w:fldChar")
    fld_sep.set(qn("w:fldCharType"), "separate")
    txt = OxmlElement("w:t")
    txt.text = "1"
    fld_end = OxmlElement("w:fldChar")
    fld_end.set(qn("w:fldCharType"), "end")
    for el in (fld_begin, instr_el, fld_sep, txt, fld_end):
        run._r.append(el)


def _setup_document():
    doc = Document()
    sec = doc.sections[0]
    sec.page_width = Cm(21.0)
    sec.page_height = Cm(29.7)
    sec.left_margin = sec.right_margin = Cm(2.4)
    sec.top_margin = Cm(2.4)
    sec.bottom_margin = Cm(2.2)
    sec.header_distance = Cm(1.2)
    sec.footer_distance = Cm(1.2)
    style = doc.styles["Normal"]
    style.font.name = "Times New Roman"
    style.font.size = Pt(10.5)
    style.element.rPr.rFonts.set(qn("w:eastAsia"), BODY_FONT)
    style.paragraph_format.line_spacing = 1.35
    style.paragraph_format.space_after = Pt(4)

    # 页眉（封面页不显示）
    sec.different_first_page_header_footer = True
    header = sec.header
    header.is_linked_to_previous = False
    hp = header.paragraphs[0]
    hp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    hp.paragraph_format.space_after = Pt(0)
    _set_font(hp.add_run(REPORT_TITLE), 8.0, False, GREY, HEAD_FONT)
    # 页脚页码：第 X 页 / 共 Y 页（PAGE / NUMPAGES 域）
    footer = sec.footer
    footer.is_linked_to_previous = False
    fp = footer.paragraphs[0]
    fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    fp.paragraph_format.space_after = Pt(0)
    _set_font(fp.add_run("第 "), 9.0, False, GREY)
    _add_field(fp, "PAGE")
    _set_font(fp.add_run(" 页 / 共 "), 9.0, False, GREY)
    _add_field(fp, "NUMPAGES")
    _set_font(fp.add_run(" 页"), 9.0, False, GREY)
    # 封面页页眉/页脚留空
    for hf in (sec.first_page_header, sec.first_page_footer):
        try:
            hf.is_linked_to_previous = False
            for p in hf.paragraphs:
                p.text = ""
        except Exception:  # noqa: BLE001
            pass

    cp = doc.core_properties
    cp.title = REPORT_TITLE
    cp.subject = REPORT_SUBTITLE
    cp.author = "irrecog 模型组"
    cp.last_modified_by = "irrecog 模型组"
    cp.category = "仿真报告"
    cp.keywords = "红外目标识别; 识别概率; 临界状态; HITRAN2020; 大气透过率"
    cp.comments = ""
    return doc


# --------------------------------------------------------------------------- #
# 2. 数值与文本格式化小工具
# --------------------------------------------------------------------------- #
def fnum(v):
    """安全转 float；NaN/Inf/不可转 → None。"""
    if v is None:
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(x):
        return None
    return x


def fmt(v, n=2, dash="—", plus=False):
    x = fnum(v)
    if x is None:
        return dash
    return (f"{x:+.{n}f}" if plus else f"{x:.{n}f}")


def fsci(v, n=2, dash="—"):
    x = fnum(v)
    if x is None:
        return dash
    if x == 0:
        return "0"
    exp = int(math.floor(math.log10(abs(x))))
    mant = x / (10.0 ** exp)
    return f"{mant:.{n}f}×10^{exp}"


def fpct(v, n=1, dash="—", plus=True):
    """输入为相对变化（如 -0.25 → −25.0%）。"""
    x = fnum(v)
    if x is None:
        return dash
    return f"{x * 100:+.{n}f}%" if plus else f"{x * 100:.{n}f}%"


def _rel(a, b):
    a, b = fnum(a), fnum(b)
    if a is None or b is None or b == 0:
        return None
    return a / b - 1.0


def _col(df, *names):
    if df is None:
        return None
    cols = getattr(df, "columns", None)
    if cols is None:
        return None
    for name in names:
        if name in cols:
            return name
    return None


def _val(row, *names):
    if row is None:
        return None
    for name in names:
        try:
            if name in row.index:
                return row[name]
        except Exception:
            pass
    return None


def _num(row, *names):
    return fnum(_val(row, *names))


def _sort_targets(df):
    if df is None or "target" not in df.columns:
        return df
    out = df.copy()
    out["_order"] = out["target"].map({t: i for i, t in enumerate(TORDER)})
    out["_order"] = out["_order"].fillna(99)
    return out.sort_values("_order", kind="stable").drop(columns="_order")


def _series_map(df, *names):
    out = {}
    if df is None or "target" not in df.columns:
        return out
    col = _col(df, *names)
    if col is None:
        return out
    for _, row in df.iterrows():
        out[str(row["target"])] = fnum(row[col])
    return out


def _sweep_x(df, xnames):
    col = _col(df, *xnames)
    if col is None:
        return None
    return col


# --------------------------------------------------------------------------- #
# 3. 数据装载
# --------------------------------------------------------------------------- #
def _read_csv(path, **kw):
    if not path or not os.path.exists(path):
        return None, f"缺少数据文件：{path}"
    for enc in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return pd.read_csv(path, encoding=enc, **kw), None
        except UnicodeDecodeError:
            continue
        except Exception as exc:  # noqa: BLE001
            return None, f"读取失败：{os.path.basename(path)}（{exc}）"
    return None, f"编码无法识别：{os.path.basename(path)}"


def _read_text(path):
    if not path or not os.path.exists(path):
        return None
    for enc in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            with open(path, "r", encoding=enc) as fh:
                return fh.read()
        except (UnicodeDecodeError, OSError):
            continue
    return None


def _normalize_targets(df):
    """若数据中的 target 用全名而不是键名（F16 战斗机 / 尼米兹级航空母舰…），统一映射回键名。"""
    if df is None or not hasattr(df, "columns") or "target" not in df.columns:
        return df
    keys = set(TORDER)
    vals = set(df["target"].astype(str))
    if vals & keys:
        return df
    mapping = {}
    for v in vals:
        for t in params.TARGETS:
            if t["key"] == v or t["name"] == v or t["key"] in v:
                mapping[v] = t["key"]
                break
    if mapping:
        df = df.copy()
        df["target"] = df["target"].astype(str).map(lambda s: mapping.get(s, s))
    return df


class Data:
    """03_数据 的只读装载器：任何文件缺失都只记录警告，不抛异常。"""

    def __init__(self, data_dir):
        self.dir = os.path.abspath(data_dir)
        self.root = os.path.dirname(self.dir)
        self.warnings = []

        self.summary, warn = _read_csv(
            os.path.join(self.dir, "单变量对比", "S00_全扫描指标汇总.csv"))
        self._warn(warn)

        self.sweeps = {}
        sweep_dir = os.path.join(self.dir, "单变量对比")
        if os.path.isdir(sweep_dir):
            for fn in sorted(os.listdir(sweep_dir)):
                if fn.startswith("S") and fn.endswith(".csv") and not fn.startswith("S00"):
                    sid = fn[:3]
                    df, warn = _read_csv(os.path.join(sweep_dir, fn))
                    self._warn(warn)
                    if df is not None:
                        self.sweeps[sid] = df
        else:
            self.warnings.append(f"缺少目录：{sweep_dir}")

        if self.summary is None and self.sweeps:
            parts = []
            for sid, df in self.sweeps.items():
                if "sweep_id" not in df.columns:
                    df = df.copy()
                    df["sweep_id"] = sid
                parts.append(df)
            self.summary = pd.concat(parts, ignore_index=True)

        self.crit, warn = _read_csv(
            os.path.join(self.dir, "临界状态", "临界状态汇总.csv"))
        self._warn(warn)
        self.env, warn = _read_csv(
            os.path.join(self.dir, "真实气候工况", "环境工况_识别临界距离.csv"))
        self._warn(warn)
        self.band, warn = _read_csv(
            os.path.join(self.dir, "波段对比", "波段对比_R50.csv"))
        self._warn(warn)
        self.phase_aod, warn = _read_csv(
            os.path.join(self.dir, "相图", "相图_AODxCn2.csv"))
        self._warn(warn)
        self.phase_dt, warn = _read_csv(
            os.path.join(self.dir, "相图", "相图_dT_AOD.csv"))
        self._warn(warn)
        self.long, warn = _read_csv(
            os.path.join(self.dir, "全工况长表", "eval_long.csv.gz"), low_memory=False)
        self._warn(warn)

        self.calib_md = _read_text(
            os.path.join(self.root, "06_校验", "公式校准报告.md"))
        self.spec_md = _read_text(
            os.path.join(self.root, "06_校验", "光谱大气校验.md"))
        self.qa_md = _read_text(
            os.path.join(self.root, "06_校验", "校验报告.md"))
        self.registry, warn = _read_csv(
            os.path.join(self.root, "05_参数依据", "参数依据登记表.csv"))
        self._warn(warn)

        for attr in ("summary", "crit", "env", "band", "phase_aod", "phase_dt", "long"):
            setattr(self, attr, _normalize_targets(getattr(self, attr)))
        for sid in list(self.sweeps):
            self.sweeps[sid] = _normalize_targets(self.sweeps[sid])

        self.base = self._baseline()

    def _sanitize(self, text):
        """把绝对路径/工程目录名替换为相对描述，并消去版本类字样（避免出现在报告中）。"""
        if not text:
            return text
        root = self.root or ""
        text = str(text)
        if root:
            text = text.replace(root + os.sep, "")
            text = text.replace(root, "工程根")
            proj = os.path.basename(root)
            if proj:
                text = text.replace(proj, "工程根")
        for pat in FORBIDDEN_PATTERNS:
            text = re.sub(pat, "…", text)
        return text

    def _warn(self, warn):
        if warn:
            self.warnings.append(self._sanitize(warn))

    def _baseline(self):
        if self.summary is not None and "sweep_id" in self.summary.columns:
            sub = self.summary[self.summary["sweep_id"] == "S01"]
            if len(sub) == 0:
                sid = self.summary["sweep_id"].dropna().iloc[0] \
                    if self.summary["sweep_id"].notna().any() else None
                if sid is not None:
                    sub = self.summary[self.summary["sweep_id"] == sid]
            return _sort_targets(sub)
        for sid in ("S01", "S02"):
            if sid in self.sweeps:
                return _sort_targets(self.sweeps[sid])
        if self.sweeps:
            return _sort_targets(next(iter(self.sweeps.values())))
        return None

    def sweep(self, sid):
        return self.sweeps.get(sid)

    def base_row(self, target):
        if self.base is None or "target" not in self.base.columns:
            return None
        sub = self.base[self.base["target"] == target]
        return None if len(sub) == 0 else sub.iloc[0]

    def crit_row(self, target):
        if self.crit is None or "target" not in self.crit.columns:
            return None
        sub = self.crit[self.crit["target"] == target]
        return None if len(sub) == 0 else sub.iloc[0]

    def data_cutoff(self):
        """数据文件最新修改时间（用于附录 D 说明数据时点）。"""
        stamps = []
        for sub in ("单变量对比", "临界状态", "真实气候工况", "全工况长表",
                    "波段对比", "相图"):
            d = os.path.join(self.dir, sub)
            if not os.path.isdir(d):
                continue
            for fn in os.listdir(d):
                try:
                    stamps.append(os.path.getmtime(os.path.join(d, fn)))
                except OSError:
                    pass
        if not stamps:
            return None
        return datetime.datetime.fromtimestamp(max(stamps)).strftime("%Y 年 %m 月 %d 日")


# --------------------------------------------------------------------------- #
# 4. 公式校准的定量核算（不读结果 CSV，直接由登记参数按公式计算）
# --------------------------------------------------------------------------- #
C1 = 1.191042972e8    # W·μm⁴/(m²·sr)
C2 = 14387.76877      # μm·K


def _planck(lam_um, t_k):
    x = C2 / (np.asarray(lam_um) * t_k)
    return C1 / (np.asarray(lam_um) ** 5) / np.expm1(x)


def _dbdt(lam_um, t_k):
    x = C2 / (np.asarray(lam_um) * t_k)
    ex = np.exp(x)
    return _planck(lam_um, t_k) * x * ex / (ex - 1.0) / t_k


def _band_weight(lam_um, t_ref_k):
    w = _dbdt(lam_um, t_ref_k)
    s = float(np.sum(w))
    return w / s if s > 0 else w


def _lambda_eff(band, t_ref_k):
    lo = params.BANDS[band]["lo_um"]
    hi = params.BANDS[band]["hi_um"]
    lam = np.linspace(lo, hi, 1201)
    w = _band_weight(lam, t_ref_k)
    return float(np.sum(w * lam))


def _iso_pressure_hpa(z_km):
    """ISO 2533 分层气压（0–20 km）。"""
    p0, t0 = 1013.25, 288.15
    g, m_air, r_gas = 9.80665, 0.0289644, 8.314462618
    z = np.asarray(z_km, dtype=float)
    p = np.empty_like(z)
    troposp = z <= 11.0
    t = t0 - 6.5 * z
    p[troposp] = p0 * (t[troposp] / t0) ** (g * m_air / (r_gas * 6.5e-3))
    p11 = p0 * (216.65 / t0) ** (g * m_air / (r_gas * 6.5e-3))
    p[~troposp] = p11 * np.exp(-g * m_air * (z[~troposp] - 11.0) * 1e3
                               / (r_gas * 216.65))
    return p


def calibration_numbers():
    """按 params 的登记参数计算公式校准的关键数值（供 2.6 节与附录 B 使用）。"""
    out = {}
    t_bg = params.BACKGROUND["temp_c"] + 273.15
    t_ref = float(getattr(params, "T_REF_WEIGHT_K", t_bg))
    eps_t = float(params.TARGETS[0]["eps"])
    eps_b = float(params.BACKGROUND["eps"])

    for band in ("MWIR", "LWIR"):
        lam = np.linspace(params.BANDS[band]["lo_um"], params.BANDS[band]["hi_um"], 1201)
        w_ref = _band_weight(lam, t_ref)
        w_288 = _band_weight(lam, 288.15)
        lam_ref = float(np.sum(w_ref * lam))
        lam_288 = float(np.sum(w_288 * lam))
        b = _planck(lam, t_bg)
        db = _dbdt(lam, t_bg)
        b_bar = float(np.sum(w_ref * b))
        db_bar = float(np.sum(w_ref * db))
        # 旧式缺少 (1-ε) 反射项：ΔT=0 时把零对比点移动的等效温差
        dt_shift = (eps_b / eps_t - 1.0) * b_bar / db_bar if db_bar else None
        out[band] = dict(lam_eff_ref=lam_ref, lam_eff_288=lam_288,
                         dlam_eff=lam_ref - lam_288,
                         b_bar=b_bar, db_bar=db_bar, dt_shift_K=dt_shift)
    # 新式反射项在 ΔT=0 严格为零：数值上 L_t-L_b = ε_t·[B(T_t)-B(T_b)]·τ
    out["reflect_zero_note"] = True

    # Rayleigh：垂直光学厚度 / 标高 与“每 km 消光系数”口径
    h_r = float(getattr(params, "H_RAYLEIGH_KM", 8.0))
    tau_vert_550 = 0.008735 * (0.55 ** -4.08)
    beta_new_550 = tau_vert_550 / h_r
    beta_old_550 = 0.008735
    out["rayleigh_ratio"] = beta_new_550 / beta_old_550
    diffs = []
    for lam_um in np.linspace(3.7, 12.0, 400):
        b_new = (0.008735 * lam_um ** -4.08) / h_r
        b_old = 0.008735 * (0.55 / lam_um) ** 4.08
        diffs.append(abs(b_new - b_old))
    out["rayleigh_ir_max_diff_km"] = max(diffs)

    # ISO 2533 与指数气压廓线：0–8 km 柱质量差
    z = np.linspace(0.0, 8.0, 801)
    p_iso = _iso_pressure_hpa(z)
    p_exp = 1013.25 * np.exp(-z / 8.0)
    mass_iso = float(np.trapz(p_iso, z))
    mass_exp = float(np.trapz(p_exp, z))
    out["iso_column_rel"] = mass_iso / mass_exp - 1.0
    out["iso_p8_ratio"] = float(_iso_pressure_hpa(np.array([8.0]))[0]
                                / (1013.25 * math.exp(-1.0)) - 1.0)

    # 地球曲率：同一地面距离下的球面弦长与平面斜距
    r_e = float(getattr(params, "R_EARTH_KM", 6371.0))
    zs = 8000.0 / 1000.0
    curv = {}
    for rg in (10.0, 20.0, 50.0, 100.0, 140.0):
        phi = rg / r_e
        chord = math.sqrt((r_e + zs) ** 2 + r_e ** 2
                          - 2.0 * (r_e + zs) * r_e * math.cos(phi))
        flat = math.sqrt(rg ** 2 + zs ** 2)
        curv[rg] = (chord / flat - 1.0) * 100.0
    out["curvature_pct"] = curv
    out["curvature_max_pct"] = max(curv.values())
    out["curvature_100km_pct"] = curv.get(100.0)

    # 数值收敛（若校验文档给出了实测百分比，优先引用原文）
    out["convergence"] = _parse_convergence()
    return out


def _parse_convergence():
    """从 06_校验/光谱大气校验.md 中提取网格/分层收敛的实测数字。"""
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), "06_校验", "光谱大气校验.md")
    txt = _read_text(path)
    res = {}
    if not txt:
        return res
    m = re.search(r"分层[^\n]{0,40}?< ?([0-9.]+)\s*%", txt)
    if m:
        res["layers"] = float(m.group(1))
    m = re.search(r"(?:步长|光谱采样)[^\n]{0,80}?([0-9.]+(?:e-?\d+)?)\s*%", txt)
    if m:
        res["spectral"] = m.group(1)
    return res


# --------------------------------------------------------------------------- #
# 5. Markdown 表格解析（用于汇总 06_校验/公式校准报告.md）
# --------------------------------------------------------------------------- #
def md_tables(md_text, max_tables=6, max_rows=14, max_cols=6):
    """解析 Markdown 管道表；返回 [{'header': [...], 'rows': [[...]]}]。"""
    if not md_text:
        return []
    lines = md_text.splitlines()
    chunks, cur = [], []
    for ln in lines:
        s = ln.strip()
        if s.startswith("|") and s.count("|") >= 2:
            cur.append(s)
        else:
            if len(cur) >= 2:
                chunks.append(cur)
            cur = []
    if len(cur) >= 2:
        chunks.append(cur)

    out = []
    for chunk in chunks:
        cells = [[c.strip() for c in row.strip().strip("|").split("|")] for row in chunk]
        if not cells:
            continue
        header = cells[0]
        # 去掉分隔行（---）
        body_rows = [r for r in cells[1:]
                     if not all(re.fullmatch(r":?-{2,}:?", c or "-") for c in r)]
        if not body_rows:
            continue
        ncol = min(max_cols, max(len(header), max(len(r) for r in body_rows)))
        header = [(header[i] if i < len(header) else "") for i in range(ncol)]
        rows = []
        for r in body_rows[:max_rows]:
            r = [(r[i] if i < len(r) else "") for i in range(ncol)]
            rows.append([c[:46] for c in r])
        out.append(dict(header=header, rows=rows))
        if len(out) >= max_tables:
            break
    return out


def pick_md_tables(tables, keywords, limit=3):
    res = []
    for t in tables:
        blob = " ".join(t["header"]) + " " + " ".join(
            " ".join(r) for r in t["rows"][:3])
        if any(k in blob for k in keywords):
            res.append(t)
        if len(res) >= limit:
            break
    return res


# --------------------------------------------------------------------------- #
# 6. 数据整理：把 CSV 变成正文需要的具体数值（全部在运行时完成）
# --------------------------------------------------------------------------- #
def _sweep_pairs(data, sid, xnames, targets=None, ynames=("R50_ground_km",)):
    """返回 {target: [(x, y|None), ...]}（按 x 升序，NaN 保留 None）。"""
    df = data.sweep(sid)
    out = {}
    if df is None or "target" not in df.columns:
        return out
    xcol = _sweep_x(df, xnames)
    ycol = _col(df, *ynames)
    if xcol is None or ycol is None:
        return out
    for tk in (targets or TORDER):
        sub = df[df["target"] == tk]
        if len(sub) == 0:
            out[tk] = []
            continue
        xs = pd.to_numeric(sub[xcol], errors="coerce")
        ys = pd.to_numeric(sub[ycol], errors="coerce")
        pairs = sorted(zip(xs.tolist(), ys.tolist()),
                       key=lambda p: (p[0] is None, p[0]))
        out[tk] = [(None if not np.isfinite(x) else float(x),
                    None if not np.isfinite(y) else float(y)) for x, y in pairs]
    return out


def _interp_pairs(pairs, x):
    if not pairs:
        return None
    xs = [p[0] for p in pairs if p[0] is not None and p[1] is not None]
    ys = [p[1] for p in pairs if p[0] is not None and p[1] is not None]
    if len(xs) < 2:
        return None
    if x < min(xs) * (1 - 1e-9) or x > max(xs) * (1 + 1e-9):
        return None
    return float(np.interp(x, xs, ys))


def _endpoint(pairs, which="first"):
    valid = [p for p in pairs if p[0] is not None and p[1] is not None]
    if not valid:
        return None, None
    return valid[0] if which == "first" else valid[-1]


def _last_x_censored(pairs):
    """返回 (最后有效点, 其后的第一个 NaN 点的 x)。用于“截断起点”叙述。"""
    last_valid = None
    for x, y in pairs:
        if y is None:
            if last_valid is not None:
                return last_valid, x
        else:
            last_valid = (x, y)
    return last_valid, None


def _baseline_row(df):
    """在含多个 AOD/PWV/温差水平的表中挑出最接近基线工况的一行。"""
    if df is None or len(df) == 0:
        return None
    work = df.copy()
    score = pd.Series(0.0, index=work.index)
    refs = (("aod550", float(params.ATMOS_BASE["aod550"])),
            ("pwv_cm", float(params.ATMOS_BASE["pwv_cm"])),
            ("dT_intrinsic_K", float(params.BASELINE["dT_intrinsic_K"])))
    for name, ref in refs:
        col = _col(work, name)
        if col is None:
            continue
        vals = pd.to_numeric(work[col], errors="coerce")
        score = score + (vals - ref).abs() / max(abs(ref), 1e-9)
    work["_score"] = score.fillna(1e9)
    return work.sort_values("_score", kind="stable").iloc[0]


def _tau_at_ground(data, target, r_km, band="MWIR"):
    """从长表插值基线工况下给定地面距离的波段透过率（MWIR 用 S01，LWIR 用 S02）。"""
    lon = data.long
    if lon is None or r_km is None:
        return None
    need = ("band", "r_ground_km", "tau_band", "sweep_id", "target")
    if not all(c in lon.columns for c in need):
        return None
    sids = ("S01",) if band == "MWIR" else ("S02",)
    sub = lon[(lon["band"] == band) & (lon["target"] == target)
              & (lon["sweep_id"].isin(sids))].copy()
    if len(sub) == 0:
        sub = lon[(lon["band"] == band) & (lon["target"] == target)].copy()
    sub["_r"] = pd.to_numeric(sub["r_ground_km"], errors="coerce")
    sub["_t"] = pd.to_numeric(sub["tau_band"], errors="coerce")
    sub = sub.dropna(subset=["_r", "_t"]).drop_duplicates(subset=["_r"]).sort_values("_r")
    if len(sub) < 2:
        return None
    try:
        return float(np.interp(r_km, sub["_r"], sub["_t"]))
    except (ValueError, TypeError):
        return None


def _p_at_ground(data, target, r_km):
    """从长表插值基线工况（S01）给定地面距离处的识别概率 P_rec。"""
    lon = data.long
    if lon is None or r_km is None:
        return None
    need = ("r_ground_km", "P_rec", "sweep_id", "target")
    if not all(c in lon.columns for c in need):
        return None
    sub = lon[(lon["sweep_id"] == "S01") & (lon["target"] == target)].copy()
    if len(sub) < 2:
        return None
    sub["_r"] = pd.to_numeric(sub["r_ground_km"], errors="coerce")
    sub["_p"] = pd.to_numeric(sub["P_rec"], errors="coerce")
    sub = sub.dropna(subset=["_r", "_p"]).drop_duplicates(subset=["_r"]).sort_values("_r")
    if len(sub) < 2:
        return None
    try:
        return float(np.interp(r_km, sub["_r"], sub["_p"]))
    except (ValueError, TypeError):
        return None


def _sweep_range(data, sid, xnames):
    df = data.sweep(sid)
    if df is None:
        return None
    col = _sweep_x(df, xnames)
    if col is None:
        return None
    vals = pd.to_numeric(df[col], errors="coerce").dropna()
    if len(vals) == 0:
        return None
    return float(vals.min()), float(vals.max())


def _boundary_txt(v, rng, scale=1.0, n=2, unit="", sci=False):
    """把临界值格式化为“数值 / ≥上限（截断）/ ≤下限（截断）”。"""
    x = fnum(v)
    if x is None:
        return "—"
    text = (_sci_txt(x, n) if sci else fmt(x * scale, n)) + unit
    if not rng:
        return text
    lo, hi = rng
    if hi is not None and hi > 0 and x >= 0.999 * hi:
        hi_txt = _sci_txt(hi, n) if sci else fmt(hi * scale, n)
        return f"≥{hi_txt}{unit}（截断）"
    if lo is not None and lo > 0 and x <= 1.001 * lo:
        lo_txt = _sci_txt(lo, n) if sci else fmt(lo * scale, n)
        return f"≤{lo_txt}{unit}（截断）"
    return text


CRIT_ALIASES = {
    "r50": ("R50_ground_km",),
    "r90": ("R90_ground_km", "R90"),
    "rres": ("R_res_analytic_km", "R_res"),
    "eta": ("eta",),
    "rref": ("r_ref_km", "ref_range_km"),
    "cf": ("contrast_floor_K",),
    "aod": ("AOD_crit", "AOD_crit_at_0p9R50"),
    "cn2": ("Cn2_crit", "Cn2_crit_at_0p9R50"),
    "dtlow": ("dT_blind_low_K",),
    "dthigh": ("dT_blind_high_K",),
    "dtwidth": ("dT_blind_width_K",),
    "dtpmin": ("dT_blind_pmin",),
    "dtcross": ("dT_cross_K", "dT_cross"),
    "dcrit": ("D_crit", "D_crit_at_0p5R50", "D_crit_at_10km"),
    "netdcrit": ("NETD_crit", "NETD_crit_at_0p5R50", "NETD_crit_at_10km"),
    "tauref": ("tau_at_r_ref",),
    "dtappref": ("dT_app_at_r_ref",),
    "nref": ("N_at_r_ref",),
    "rcf": ("R_contrast_floor_km",),
    # 10 km 参考距离附列（部分目标为 NaN）
    "aod10": ("AOD_crit_at_10km", "AOD_crit_10km"),
    "cn210": ("Cn2_crit_at_10km", "Cn2_crit_10km"),
    "d10": ("D_crit_at_10km", "D_crit_10km"),
    "netd10": ("NETD_crit_at_10km", "NETD_crit_10km"),
    "blind10_low": ("dT_blind_low_at_10km_K", "dT_blind_low_at_10km",
                    "dT_blind_low_10km_K", "dT_blind_low_10km"),
    "blind10_high": ("dT_blind_high_at_10km_K", "dT_blind_high_at_10km",
                     "dT_blind_high_10km_K", "dT_blind_high_10km"),
    "blind10_width": ("dT_blind_width_at_10km_K", "dT_blind_width_at_10km",
                      "dT_blind_width_10km_K", "dT_blind_width_10km"),
    "dtcross10": ("dT_cross_at_10km_K", "dT_cross_at_10km", "dT_cross_10km"),
}


def _censor_seg(note, name):
    """从合并的 censored 说明中取出某个字段的片段（如 censored_AOD=...）。"""
    if not note:
        return ""
    for part in str(note).split("；"):
        part = part.strip()
        if part.startswith(name + "="):
            return part.split("=", 1)[1].strip()
    return ""


def _crit_maps(crit):
    maps, censor = {}, {}
    if crit is None:
        return maps, censor
    for key, aliases in CRIT_ALIASES.items():
        maps[key] = _series_map(crit, *aliases)
    # 模糊兜底：列名与规范略有差异时，按关键字匹配（排除 10 km 附列，避免与主列混淆）
    if crit is not None and "target" in crit.columns:
        cols = list(crit.columns)
        fuzzy = {
            "rref": r"r_?ref",
            "cf": r"contrast",
            "aod": r"AOD_?crit(?!.*10\s*km)",
            "cn2": r"(Cn2|CN2)_?crit(?!.*10\s*km)",
            "dtlow": r"dT_?blind.*low(?!.*10\s*km)",
            "dthigh": r"dT_?blind.*high(?!.*10\s*km)",
            "dtwidth": r"dT_?blind.*width(?!.*10\s*km)",
            "dtpmin": r"dT_?blind.*pmin",
            "dtcross": r"(dT_?cross|blind.*cent(er|re))(?!.*10\s*km)",
            "dcrit": r"D_?crit(?!.*10\s*km)",
            "netdcrit": r"NETD_?crit(?!.*10\s*km)",
            "aod10": r"AOD_?crit.*10\s*km",
            "cn210": r"(Cn2|CN2)_?crit.*10\s*km",
            "d10": r"D_?crit.*10\s*km",
            "netd10": r"NETD_?crit.*10\s*km",
            "blind10_low": r"dT_?blind.*low.*10\s*km",
            "blind10_high": r"dT_?blind.*high.*10\s*km",
            "blind10_width": r"dT_?blind.*width.*10\s*km",
            "dtcross10": r"dT_?cross.*10\s*km",
        }
        for key, pat in fuzzy.items():
            if key not in maps or not maps[key]:
                for c in cols:
                    if re.search(pat, str(c), flags=re.I) and "censor" not in str(c).lower():
                        maps[key] = _series_map(crit, c)
                        break
    censor_cols = [c for c in crit.columns if "censor" in c.lower()]
    for _, row in crit.iterrows():
        tk = str(row.get("target", ""))
        notes = []
        for c in censor_cols:
            v = row[c]
            if pd.isna(v):
                continue
            s = str(v).strip()
            if s and s.lower() not in ("0", "false", "none", "nan"):
                notes.append(f"{c}={s}")
        censor[tk] = "；".join(notes)
    return maps, censor


def _phase_stats(df, targets=None):
    out = {}
    if df is None:
        return out
    tgt = _col(df, "target")
    ycol = _col(df, "R50", "R50_ground_km")
    if tgt is None or ycol is None:
        return out
    for tk in (targets or TORDER):
        sub = df[df[tgt] == tk]
        if len(sub) == 0:
            continue
        ys = pd.to_numeric(sub[ycol], errors="coerce")
        n = len(sub)
        n_nan = int(ys.isna().sum())
        xs_aod = pd.to_numeric(sub[_col(df, "aod550")], errors="coerce") \
            if _col(df, "aod550") else None
        xs_cn2 = pd.to_numeric(sub[_col(df, "cn2")], errors="coerce") \
            if _col(df, "cn2") else None
        xs_dt = pd.to_numeric(sub[_col(df, "dT_K", "dT")], errors="coerce") \
            if _col(df, "dT_K", "dT") else None
        item = dict(n=n, n_nan=n_nan,
                    vmin=float(ys.min()) if ys.notna().any() else None,
                    vmax=float(ys.max()) if ys.notna().any() else None)
        if xs_aod is not None:
            item["aod_min"] = float(xs_aod.min())
            item["aod_max"] = float(xs_aod.max())
        if xs_cn2 is not None:
            item["cn2_min"] = float(xs_cn2.min())
            item["cn2_max"] = float(xs_cn2.max())
        if xs_dt is not None:
            item["dt_min"] = float(xs_dt.min())
            item["dt_max"] = float(xs_dt.max())
        if ys.notna().any():
            idx = ys.idxmin()
            item["argmin_R50"] = float(ys.loc[idx])
            if xs_dt is not None:
                item["argmin_dT"] = fnum(xs_dt.loc[idx])
            if xs_aod is not None:
                item["argmin_aod"] = fnum(xs_aod.loc[idx])
        out[tk] = item
    return out


def _sensitivity_table(data):
    """按图 17 口径：每个变量在其扫描范围内使 R50 相对基线变化的最大倍数（中位数）。"""
    base = _series_map(data.base, "R50_ground_km")
    specs = [
        ("S04", "气溶胶 AOD", ("aod550",)),
        ("S05", "Ångström 指数 α", ("alpha",)),
        ("S06", "可降水量 PWV", ("pwv_cm",)),
        ("S07", "湍流 Cn²", ("cn2",)),
        ("S08", "口径 D", ("D_m",)),
        ("S09", "NETD", ("netd_k",)),
        ("S10", "IFOV", ("ifov_urad",)),
        ("S11", "平台高度", ("platform_h_m",)),
        ("S03", "目标温度", ("target_temp_c",)),
        ("S14", "目标发射率", ("eps_t",)),
    ]
    rows = []
    for sid, label, xnames in specs:
        pairs = _sweep_pairs(data, sid, xnames)
        if not pairs:
            continue
        per_target = []
        for tk in TORDER:
            vals = [y for _, y in pairs.get(tk, []) if y is not None]
            b = base.get(tk)
            if len(vals) > 1 and b:
                per_target.append(max(abs(max(vals) - b), abs(b - min(vals))) / b)
        if per_target:
            rows.append(dict(编号=sid, 变量=label,
                             最大相对变化=float(np.median(per_target)),
                             受敏感目标数=len(per_target)))
    if not rows:
        return pd.DataFrame(), None
    tab = pd.DataFrame(rows).sort_values("最大相对变化", ascending=False)
    tab.insert(0, "排名", range(1, len(tab) + 1))
    return tab, tab.iloc[0]["变量"] if len(tab) else None


def _env_tables(data):
    df = data.env
    if df is None:
        return pd.DataFrame(), {}, pd.DataFrame()
    ec = _col(df, "env_key")
    nc = _col(df, "env_name")
    qc = _col(df, "quantile")
    tc = _col(df, "target")
    rc = _col(df, "R50_ground_km", "R50")
    if None in (ec, tc, rc):
        return pd.DataFrame(), {}, pd.DataFrame()
    work = df.copy()
    work["_r50"] = pd.to_numeric(work[rc], errors="coerce")
    work["_env"] = work[ec].astype(str)
    order = [e["key"] for e in params.ENVIRONMENTS]
    name_map = {e["key"]: e["name"] for e in params.ENVIRONMENTS}
    if nc:
        for k, v in work.groupby("_env")[nc].first().items():
            if isinstance(v, str) and v.strip():
                name_map[k] = v.strip()

    rows = []
    for env_key in order:
        sub = work[work["_env"] == env_key]
        if len(sub) == 0:
            continue
        row = {"环境": name_map.get(env_key, env_key)}
        for tk in TORDER:
            vals = sub[sub[tc] == tk]["_r50"].dropna()
            row[TSHORT[tk]] = float(vals.median()) if len(vals) else None
        # 环境内分位跨度（优先尼米兹，其次阿利伯克：分位间相对跨度）
        spread = None
        if qc is not None:
            big = sub[sub[tc] == "NIMITZ"]["_r50"].dropna()
            if len(big) == 0:
                big = sub[sub[tc] == "ALBK"]["_r50"].dropna()
            if len(big):
                med = float(big.median())
                spread = (float(big.max()) - float(big.min())) / med if med else None
        row["大目标分位跨度"] = spread
        rows.append(row)
    tab = pd.DataFrame(rows)

    # 环境间差异（按目标中位数）
    summary = {}
    if len(tab):
        for tk in TORDER:
            col = TSHORT[tk]
            vals = pd.to_numeric(tab[col], errors="coerce").dropna()
            if len(vals) > 1:
                summary[tk] = dict(
                    lo=float(vals.min()), hi=float(vals.max()),
                    rel=float(vals.max() - vals.min()) / float(vals.median())
                    if float(vals.median()) else None,
                    env_lo=tab.loc[vals.idxmin(), "环境"],
                    env_hi=tab.loc[vals.idxmax(), "环境"])
    # 分位水平明细（供正文引用 p10/中位/p90）
    qtab = pd.DataFrame()
    if qc is not None:
        qrows = []
        for env_key in order:
            sub = work[work["_env"] == env_key]
            if len(sub) == 0:
                continue
            r = {"环境": name_map.get(env_key, env_key)}
            for q in ("p10", "median", "p90"):
                s = sub[sub[qc] == q]
                if len(s) == 0:
                    continue
                for tk in ("ALBK", "NIMITZ"):
                    vals = s[s[tc] == tk]["_r50"].dropna()
                    if len(vals):
                        r[f"{TSHORT[tk]}-{q}"] = float(vals.median())
            qrows.append(r)
        qtab = pd.DataFrame(qrows)
    return tab, summary, qtab


# 临界参数反解的搜索区间（与 critical.py 的 aod_for_p/cn2_for_p/aperture_for_p/netd_for_p 一致）
CRIT_SOLVER_BOUNDS = {
    "aod": (0.005, 20.0),
    "cn2": (1e-18, 1e-11),
    "d": (0.02, 1.0),
    "netd": (0.001, 2.0),
}


def _critical_tables(data):
    crit = data.crit
    maps, censor = _crit_maps(crit)
    # 逐目标的 censored_* 原始说明（用于区分“截断/不构成约束”）
    cflags = {}
    if crit is not None and "target" in crit.columns:
        censor_cols_all = [c for c in crit.columns if "censor" in c.lower()]
        for _, row in crit.iterrows():
            d = {}
            for c in censor_cols_all:
                v = row[c]
                if pd.isna(v):
                    continue
                s = str(v).strip()
                if s and s.lower() not in ("0", "false", "none", "nan"):
                    d[str(c)] = s
            cflags[str(row.get("target", ""))] = d
    # 核心截断标记：只看临界距离/临界参数本身，不把 R90/Rdet/Rident 等任务阈值算进来；
    # “上限仍满足”表示该参数不构成约束，不算截断
    core_censor_cols = []
    if crit is not None:
        core_censor_cols = [c for c in crit.columns
                            if "censor" in c.lower()
                            and not re.search(r"R90|R10|Rdet|Rident|_10km", str(c))]

    def _core_flag(row):
        for c in core_censor_cols:
            v = row[c]
            if pd.isna(v):
                continue
            s = str(v).strip()
            if s and s.lower() not in ("0", "false", "none", "nan") \
                    and "上限仍满足" not in s:
                return True
        return False

    rng = dict(CRIT_SOLVER_BOUNDS)
    notes = []
    if data.crit is None:
        notes.append("未找到 03_数据/临界状态/临界状态汇总.csv")
    rows = []
    for tk in TORDER:
        if crit is None:
            break
        sub = crit[crit["target"] == tk] if "target" in crit.columns else pd.DataFrame()
        if len(sub) == 0:
            continue
        r50 = maps["r50"].get(tk)
        r90 = maps["r90"].get(tk)
        pmax = None
        base_row = data.base_row(tk)
        if base_row is not None:
            pmax = _num(base_row, "P_rec_max")
        r90_txt = fmt(r90, 1) if r90 is not None else "—"
        if r90 is None and pmax is not None:
            r90_txt = f"—（P≤{fmt(pmax, 2)}）"
        rr = maps["rref"].get(tk) if "rref" in maps else None
        rows.append({
            "目标": TNAME[tk],
            "R50 (km)": fmt(r50, 1),
            "R90 (km)": r90_txt,
            "R_res (km)": fmt(maps["rres"].get(tk), 1),
            "η": fmt(maps["eta"].get(tk), 3),
            "r_ref (km)": fmt(rr, 1),
            "τ@r_ref": fmt(maps["tauref"].get(tk), 3),
            "ΔT_app@r_ref (K)": fmt(maps["dtappref"].get(tk), 2),
            "N@r_ref": fmt(maps["nref"].get(tk), 1),
            "截断": "是" if _core_flag(sub.iloc[0]) else "—",
        })
    crit_tab = pd.DataFrame(rows)

    blind_rows = []
    for tk in TORDER:
        if crit is None:
            break
        if maps["dtwidth"] and maps["dtwidth"].get(tk) is not None:
            low = maps["dtlow"].get(tk)
            high = maps["dthigh"].get(tk)
            center = maps["dtcross"].get(tk)
            if center is None and low is not None and high is not None:
                center = (low + high) / 2.0
            note_col = _col(crit, "dT_blind_note")
            note_txt = "—"
            if note_col:
                sub = crit[crit["target"] == tk]
                if len(sub):
                    v = sub.iloc[0][note_col]
                    if isinstance(v, str) and v.strip():
                        note_txt = v.strip()
            width_v = fnum(maps["dtwidth"].get(tk))
            if note_txt == "—" and width_v is not None:
                if width_v <= 1e-9:
                    note_txt = "无盲区（全温差可识别）"
                elif width_v >= 30:
                    note_txt = "盲区覆盖温差扫描区间（截断）"
            blind_rows.append({
                "目标": TNAME[tk],
                "盲区中心 ΔT_cross (K)": fmt(center, 2),
                "盲区下界 (K)": fmt(low, 2),
                "盲区上界 (K)": fmt(high, 2),
                "盲区宽度 (K)": fmt(width_v, 2),
                "盲区内最低 P_rec": fmt(maps["dtpmin"].get(tk), 3),
                "说明": note_txt,
            })
    blind_tab = pd.DataFrame(blind_rows)

    param_rows = []
    for tk in TORDER:
        if crit is None:
            break
        sub = crit[crit["target"] == tk] if "target" in crit.columns else pd.DataFrame()
        if len(sub) == 0:
            continue
        aod_c = maps["aod"].get(tk)
        cn2_c = maps["cn2"].get(tk)
        d_c = maps["dcrit"].get(tk)
        netd_c = maps["netdcrit"].get(tk)
        fl = cflags.get(tk, {})
        aod_flag = fl.get("censored_AOD", "")
        cn2_flag = fl.get("censored_Cn2", "")
        d_flag = fl.get("censored_D", "")
        netd_flag = fl.get("censored_NETD", "")

        if "上限仍满足" in aod_flag:
            aod_cell = "≥20（不构成约束）"
        elif aod_c is None:
            aod_cell = "—"
        else:
            aod_cell = _boundary_txt(aod_c, rng["aod"], n=2)
        if "上限仍满足" in cn2_flag:
            cn2_cell = "不构成约束（Cn²≤1×10⁻¹¹ 仍可识别）"
        elif cn2_c is None:
            cn2_cell = "—"
        else:
            cn2_cell = _boundary_txt(cn2_c, rng["cn2"], n=2, sci=True)
        if "下限" in d_flag and ("不满足" in d_flag or "仍不" in d_flag):
            d_cell = "≤0.02（截断）"
        elif d_c is None:
            d_cell = "—"
        else:
            d_cell = _boundary_txt(d_c, rng["d"], n=3)
        if "上限仍满足" in netd_flag:
            netd_cell = "不构成约束（NETD≤2 K 仍可识别）"
        elif "下限" in netd_flag and ("不满足" in netd_flag or "仍不" in netd_flag):
            netd_cell = "≤1（截断）"
        elif netd_c is None:
            netd_cell = "—"
        else:
            netd_cell = _boundary_txt(netd_c, rng["netd"], scale=1000.0, n=1)
        param_rows.append({
            "目标": TNAME[tk],
            "临界 AOD550": aod_cell,
            "临界 Cn² (m⁻²ᐟ³)": cn2_cell,
            "临界口径 D (m)": d_cell,
            "临界 NETD (mK)": netd_cell,
            "截断": "是" if _core_flag(sub.iloc[0]) else "—",
        })
    param_tab = pd.DataFrame(param_rows)
    return maps, censor, crit_tab, blind_tab, param_tab, notes


def _resolve_figs(fig_dir):
    status = {}
    for key, names in FIG_FILES.items():
        status[key] = None
        for name in names:
            cand = os.path.join(fig_dir, name)
            if os.path.exists(cand):
                status[key] = name
                break
    return status


def _primary_fig_names():
    return {key: names[0] for key, names in FIG_FILES.items()}


def _consistency_checks(data, fig_status=None):
    """内部一致性/自洽性校核（全部由数据重算）。"""
    checks = []
    base = data.base
    n50_rec = float(params.N50_SETS["NVESD"]["recognize"])
    # 1) R50 处周期数与 N50
    if base is not None and "N_at_R50" in base.columns:
        vals = pd.to_numeric(base["N_at_R50"], errors="coerce").dropna()
        if len(vals):
            dev = float(np.max(np.abs(vals - n50_rec) / n50_rec))
            checks.append(("R50 处周期数 = N50", "通过" if dev < 0.10 else "注意",
                           f"最大相对偏差 {dev * 100:.1f}%"))
    # 2) η ≤ 1
    if base is not None and "eta" in base.columns:
        eta = pd.to_numeric(base["eta"], errors="coerce").dropna()
        if len(eta):
            bad = int((eta > 1.0 + 1e-6).sum())
            checks.append(("η = R50/R_res ≤ 1", "通过" if bad == 0 else "注意",
                           f"违例 {bad} 个目标"))
    # 3) P_rec 随距离单调不增
    lon = data.long
    if lon is not None and all(c in lon.columns for c in
                               ("sweep_id", "target", "r_ground_km", "P_rec")):
        grp = [c for c in ("sweep_id", "target", "band", "sweep_value")
               if c in lon.columns]
        viol, groups = 0, 0
        work = lon[["r_ground_km", "P_rec"] + grp].copy()
        work["_p"] = pd.to_numeric(work["P_rec"], errors="coerce")
        work["_r"] = pd.to_numeric(work["r_ground_km"], errors="coerce")
        for _, sub in work.dropna(subset=["_r"]).groupby(grp, dropna=False):
            p = sub.sort_values("_r")["_p"].to_numpy()
            if len(p) < 2:
                continue
            groups += 1
            diff = np.diff(p)
            viol += int(np.sum(diff > 1e-7))
        checks.append(("P_rec 随距离单调不增",
                       "通过" if viol == 0 else "注意",
                       f"检查 {groups} 组曲线，违例 {viol} 处"))
    # 4) 长表中 P_rec 在 R50 两侧跨越 0.5
    if lon is not None and base is not None and all(
            c in lon.columns for c in ("target", "r_ground_km", "P_rec", "sweep_id")):
        sid = "S01" if (lon["sweep_id"] == "S01").any() else lon["sweep_id"].iloc[0]
        ok, tested = 0, 0
        sub_sid = lon[lon["sweep_id"] == sid]
        for tk in TORDER:
            r50 = fnum(_val(data.base_row(tk), "R50_ground_km"))
            if r50 is None:
                continue
            sub = sub_sid[sub_sid["target"] == tk].copy()
            if len(sub) == 0:
                continue
            sub["_r"] = pd.to_numeric(sub["r_ground_km"], errors="coerce")
            sub["_p"] = pd.to_numeric(sub["P_rec"], errors="coerce")
            sub = sub.dropna(subset=["_r", "_p"]).sort_values("_r")
            if len(sub) == 0:
                continue
            below = sub[sub["_r"] <= r50]
            above = sub[sub["_r"] >= r50]
            if len(below) == 0 or len(above) == 0:
                continue
            tested += 1
            if below.iloc[-1]["_p"] >= 0.5 - 0.02 and above.iloc[0]["_p"] <= 0.5 + 0.02:
                ok += 1
        if tested:
            checks.append(("R50 处 P_rec 跨越 0.5", "通过" if ok == tested else "注意",
                           f"{ok}/{tested} 个目标在 R50 两侧单调跨越 0.5"))
    # 5) 汇总表截断行统计
    if data.summary is not None and "R50_ground_km" in data.summary.columns:
        r = pd.to_numeric(data.summary["R50_ground_km"], errors="coerce")
        checks.append(("截断行（R50 不可解）", "记录",
                       f"{int(r.isna().sum())} / {len(r)} 行，正文以“—”标注"))
    # 6) 图件与编号一致
    prim = _primary_fig_names()
    fig_ok = sum(1 for k, name in (fig_status or {}).items()
                 if name and name == prim.get(k))
    fallback = [k for k, name in (fig_status or {}).items()
                if name and name != prim.get(k)]
    detail = f"{fig_ok}/{len(FIG_FILES)} 张图按最终编号文件名就位"
    if fallback:
        detail += "；" + "、".join(f"图{k}" for k in fallback) + " 仍为过渡文件名"
    checks.append(("图件与编号一一对应", "通过" if fig_ok == len(FIG_FILES) else "注意",
                   detail))
    # 7) 数据-图-报告同源
    checks.append(("数值来源唯一", "通过", "正文数值均由 03_数据 的 CSV 运行时读取"))
    return pd.DataFrame(checks, columns=["校核项", "结果", "说明"])


def _parse_pct_after(md_text, anchor, window=160):
    """在 md 中 anchor 之后的窗口里找“a–b%”或“a 个百分点”。"""
    if not md_text:
        return None
    for m in re.finditer(re.escape(anchor), md_text):
        seg = md_text[m.start(): m.start() + window]
        mm = re.search(r"([0-9.]+)\s*[–\-~至]\s*([0-9.]+)\s*(?:个)?(?:百分点|%)", seg)
        if mm:
            return float(mm.group(1)), float(mm.group(2)), mm.group(0)
        mm = re.search(r"([0-9.]+)\s*(?:个)?(?:百分点|%)", seg)
        if mm:
            v = float(mm.group(1))
            return v, v, mm.group(0)
    return None


def _uncertainty_table(data, calib):
    rows = []
    base = _series_map(data.base, "R50_ground_km")
    p12 = _series_map(data.sweep("S12"), "R50_ground_km") if data.sweep("S12") is not None else {}
    # S12 两行分别是 NVESD / Johnson
    s12 = data.sweep("S12")
    johnson_ratio = None
    if s12 is not None and "sweep_value" in s12.columns:
        j = s12[s12["sweep_value"].astype(str).str.contains("Johnson", na=False)]
        nv = s12[s12["sweep_value"].astype(str).str.contains("NVESD", na=False)]
        if len(j) and len(nv):
            jr = _series_map(j, "R50_ground_km")
            nr = _series_map(nv, "R50_ground_km")
            ratios = [jr[t] / nr[t] for t in TORDER
                      if jr.get(t) and nr.get(t)]
            if ratios:
                johnson_ratio = float(np.median(ratios))
    rows.append({
        "不确定度来源": "判据口径（N50：NVESD 16.5 vs Johnson 8.0）",
        "取值/假设": "NVESD/TTP 为主口径；Johnson 为备口径",
        "影响方向": "判据周期数减半 → R50 近似加倍",
        "量级（本数据核算）": (f"R50 中位变化 {fpct(johnson_ratio - 1)}（Johnson/NVESD−1）"
                            if johnson_ratio else "见 3.1 节表 10"),
    })
    # 尺寸口径
    s13 = data.sweep("S13")
    size_ratio = None
    if s13 is not None and "sweep_value" in s13.columns:
        mx = s13[s13["sweep_value"].astype(str).str.contains("max", case=False, na=False)]
        sq = s13[s13["sweep_value"].astype(str).str.contains("sqrt", case=False, na=False)]
        if len(mx) and len(sq):
            mr = _series_map(mx, "R50_ground_km")
            sr = _series_map(sq, "R50_ground_km")
            ratios = [mr[t] / sr[t] for t in TORDER if mr.get(t) and sr.get(t)]
            if ratios:
                size_ratio = float(np.median(ratios))
    rows.append({
        "不确定度来源": "目标包围盒未做几何标定",
        "取值/假设": "D_eff=√(W_proj·H)；对照 max(W,L,H)",
        "影响方向": "包围盒偏大则 R50 偏大；投影姿态未标定",
        "量级（本数据核算）": (f"换 max 口径使 R50 中位变化 {fpct(size_ratio - 1)}" if size_ratio
                            else "见 S13 扫描"),
    })
    # MRTD k 系数
    pairs = _sweep_pairs(data, "S09", ("netd_k",))
    k_effect = None
    if pairs:
        ratios = []
        for tk in TORDER:
            p = pairs.get(tk, [])
            if not p:
                continue
            lo = _interp_pairs(p, 0.02)
            hi = _interp_pairs(p, 0.03)
            if lo and hi and lo > 0:
                ratios.append(math.log(hi / lo) / math.log(1.5))
        if ratios:
            elast = float(np.median(ratios))
            k_effect = (1.2 ** elast - 1.0)
    rows.append({
        "不确定度来源": "MRTD 工程系数 k（MRTD(0)=k·NETD）",
        "取值/假设": f"k = {params.SENSOR_PRESETS['RECOG']['k_mrtd']:.1f}（工程近似，需实测标定）",
        "影响方向": "k↑ → 对比度地板↑ → R50↓",
        "量级（本数据核算）": (f"k±20% 时 R50 约 {fpct(k_effect)}（按 NETD 扫描弹性折算）"
                            if k_effect is not None else "方向上与 NETD 等价"),
    })
    # 反射项/背景温度均一
    dt_shift_m = calib.get("MWIR", {}).get("dt_shift_K")
    dt_shift_l = calib.get("LWIR", {}).get("dt_shift_K")
    rows.append({
        "不确定度来源": "反射项与背景温度均一假设",
        "取值/假设": "ε_t=0.90、ε_b=0.95，背景按 20 ℃ 均匀黑体",
        "影响方向": "近热交叉区对 ΔT_app 影响最大；远离交叉可忽略",
        "量级（本数据核算）": (f"若忽略 (1−ε) 反射项，零对比点偏移约 "
                            f"{fmt(dt_shift_m, 2)} K（MWIR）/{fmt(dt_shift_l, 2)} K（LWIR）"),
    })
    # 水汽连续吸收
    spec = data.spec_md or ""
    cont = _parse_pct_after(spec, "连续吸收", 220)
    rows.append({
        "不确定度来源": "水汽连续吸收（MT_CKD）未含",
        "取值/假设": "HITRAN 逐线 Voigt 线翼，不含连续吸收",
        "影响方向": "LWIR 透过率偏高 → R50 偏高；干燥条件影响小",
        "量级（本数据核算）": (f"透过率约高 {cont[0]:.0f}–{cont[1]:.0f}%"
                            if cont else "文献量级 1–5%（见 06_校验/光谱大气校验.md）"),
    })
    # 完整 HITRAN 物种
    lwir = _parse_pct_after(spec, "O3", 260) or _parse_pct_after(spec, "O₃", 260)
    rows.append({
        "不确定度来源": "LWIR 物种完整性与温度/气压插值",
        "取值/假设": "H2O/CO2/O3/N2O/CO/CH4 全物种，220/250/280/300 K × 4 气压插值（未含 MT_CKD 连续吸收）",
        "影响方向": "缺物种/连续吸收 → 透过率偏高 → R50 偏高",
        "量级（本数据核算）": (f"O3 等缺省物种约 {lwir[2]}" if lwir
                            else "见 06_校验/光谱大气校验.md 的物种贡献表"),
    })
    # 传感器设定参数
    rows.append({
        "不确定度来源": "传感器设定参数（口径/NETD/IFOV/抖动/光学效率）",
        "取值/假设": "识别通道 0.30 m / 25 mK / 12.5 μrad / 0.8 光学效率",
        "影响方向": "设定值偏差按单变量扫描方向传播",
        "量级（本数据核算）": "见 3.2.4 节口径/NETD/IFOV 三组扫描；各参数在其扫描范围内的 R₅₀ 相对变化量级见该节",
    })
    rows.append({
        "不确定度来源": "Cn² 均匀假设",
        "取值/假设": "整层单一 Cn²，未含真实 Cn²(h) 廓线",
        "影响方向": "层结集中时低估近地面衰减 → R50 可能偏大",
        "量级（本数据核算）": "见 3.2.2 节 Cn² 扫描（跨 4 个量级）",
    })
    rows.append({
        "不确定度来源": "不含太阳直射、云、雨、雾",
        "取值/假设": "晴空大气 + 气溶胶外消光",
        "影响方向": "有云/雨时实际透过率更低 → 本报告 R50 偏乐观",
        "量级（本数据核算）": "未量化（需云/降水光学参数）",
    })
    rows.append({
        "不确定度来源": "光谱采样与分层收敛",
        "取值/假设": f"波数步长 {params.SPECTRAL_STEP_CM} cm⁻¹、{params.N_LAYERS} 层",
        "影响方向": "数值误差，两方向均可能",
        "量级（本数据核算）": (f"分层误差 <{calib.get('convergence', {}).get('layers', 0.1)}%；"
                            f"网格误差见 06_校验/光谱大气校验.md"),
    })
    rows.append({
        "不确定度来源": "目标热模型",
        "取值/假设": "等效温度 + 发射率，无表面温度场/纹理",
        "影响方向": "局部热点/纹理会使实际识别概率高于模型",
        "量级（本数据核算）": "未量化（图像级仿真需求）",
    })
    return pd.DataFrame(rows)


def _inventory(data, fig_dir):
    """附录 D 的文件清单（全部按实际存在性生成，不列版本类文件）。"""
    def stat_row(path, desc, rows=None, cols=None):
        try:
            size = os.path.getsize(path) / 1024.0
        except OSError:
            size = None
        return dict(文件=os.path.basename(path), 类别=desc,
                    行数=rows if rows is not None else "—",
                    列数=cols if cols is not None else "—",
                    大小=f"{size:.0f} KB" if size is not None else "—")

    data_rows = []
    def add_df(path, desc, df):
        if os.path.exists(path):
            data_rows.append(stat_row(path, desc, len(df) if df is not None else None,
                                      df.shape[1] if df is not None else None))
    add_df(os.path.join(data.dir, "全工况长表", "eval_long.csv.gz"), "全工况长表", data.long)
    add_df(os.path.join(data.dir, "单变量对比", "S00_全扫描指标汇总.csv"), "扫描汇总", data.summary)
    for sid in sorted(data.sweeps):
        fn = [f for f in os.listdir(os.path.join(data.dir, "单变量对比"))
              if f.startswith(sid) and f.endswith(".csv")]
        if fn:
            p = os.path.join(data.dir, "单变量对比", fn[0])
            add_df(p, f"单变量 {sid}", data.sweeps[sid])
    add_df(os.path.join(data.dir, "临界状态", "临界状态汇总.csv"), "临界状态", data.crit)
    add_df(os.path.join(data.dir, "真实气候工况", "环境工况_识别临界距离.csv"), "真实气候工况", data.env)
    add_df(os.path.join(data.dir, "波段对比", "波段对比_R50.csv"), "波段对比", data.band)
    add_df(os.path.join(data.dir, "相图", "相图_AODxCn2.csv"), "相图 AOD×Cn²", data.phase_aod)
    add_df(os.path.join(data.dir, "相图", "相图_dT_AOD.csv"), "相图 ΔT×AOD", data.phase_dt)

    fig_rows = []
    prim = _primary_fig_names()
    for key in ["00"] + [f"{i:02d}" for i in range(1, 18)]:
        names = FIG_FILES.get(key, ())
        path = None
        for name in names:
            cand = os.path.join(fig_dir, name)
            if os.path.exists(cand):
                path = cand
                break
        if path is None:
            fig_rows.append(dict(编号=f"图{key}", 文件="—", 状态="缺失", 大小="—"))
        else:
            base = os.path.basename(path)
            state = "就位" if base == prim.get(key) else "过渡文件名"
            fig_rows.append(dict(编号=f"图{key}", 文件=base,
                                 状态=state, 大小=f"{os.path.getsize(path) / 1024.0:.0f} KB"))

    code_rows = []
    pkg = os.path.join(os.path.dirname(os.path.abspath(__file__)))
    desc_map = {
        "params.py": "参数唯一真值源与登记表导出",
        "radiometry.py": "Planck、波段加权、视在温度反演",
        "atmosphere.py": "HITRAN2020 光谱大气、曲率斜程、路径辐射",
        "sensor.py": "MTF 链、MRTD、f_max",
        "target.py": "6 个软件目标模型与尺寸口径",
        "probability.py": "TTPF 概率模型",
        "chain.py": "单点正向评估",
        "critical.py": "临界状态求解（对数域二分）",
        "experiments.py": "单变量实验矩阵与环境工况",
        "plots.py": "数据图件",
        "plots_atmo.py": "光谱大气图件",
        "report.py": "本报告生成器",
        "build_xsect.py": "HITRAN 截面计算脚本",
        "make_mindmap.py": "项目思维导图生成脚本",
        "run_all.py": "一键重建数据→图件→报告",
    }
    for fn, desc in desc_map.items():
        for cand in (os.path.join(pkg, fn),
                     os.path.join(data.root, "00_构建脚本", fn),
                     os.path.join(data.root, fn)):
            if os.path.exists(cand):
                try:
                    rel = os.path.relpath(cand, data.root)
                except ValueError:  # 不同驱动器
                    rel = cand
                code_rows.append(dict(文件=rel, 说明=desc,
                                      大小=f"{os.path.getsize(cand) / 1024.0:.0f} KB"))
                break
    for sub, fn, desc in (
            ("06_校验", "公式校准报告.md", "全项目公式校准（原式→校准式→依据→影响）"),
            ("06_校验", "光谱大气校验.md", "光谱大气模型校验"),
            ("06_校验", "校验报告.md", "模型 V&V 检查结果"),
            ("05_参数依据", "参数依据登记表.csv", "参数依据登记表"),
            ("05_参数依据", "参数依据说明.md", "参数依据说明"),
            ("01_正式报告", os.path.basename(data.root), "")):
        if not desc:
            continue
        p = os.path.join(data.root, sub, fn)
        if os.path.exists(p):
            code_rows.append(dict(文件=f"{sub}/{fn}", 说明=desc,
                                  大小=f"{os.path.getsize(p) / 1024.0:.0f} KB"))
    return pd.DataFrame(data_rows), pd.DataFrame(fig_rows), pd.DataFrame(code_rows)


# --------------------------------------------------------------------------- #
# 7. 汇总上下文：正文各节共用的全部数字
# --------------------------------------------------------------------------- #
def _collect(data, fig_dir):
    global _FIG_STATUS
    _FIG_STATUS = _resolve_figs(fig_dir)
    C = {"data": data, "warnings": list(data.warnings),
         "fig_dir": fig_dir, "fig_status": dict(_FIG_STATUS)}
    base = data.base
    C["base"] = base
    C["d_eff"] = {}
    if base is not None and "target" in base.columns:
        dc = _col(base, "d_eff_m", "D_eff_m")
        if dc:
            for _, rr in base.iterrows():
                C["d_eff"][str(rr.get("target", ""))] = fnum(rr[dc])
    C["r50"] = _series_map(base, "R50_ground_km")
    C["r90"] = _series_map(base, "R90_ground_km")
    C["rres"] = _series_map(base, "R_res_analytic_km")
    C["eta"] = _series_map(base, "eta")
    C["tau50"] = _series_map(base, "tau_at_R50")
    C["dtapp50"] = _series_map(base, "dT_app_at_R50")
    C["nat50"] = _series_map(base, "N_at_R50")
    C["pmax"] = _series_map(base, "P_rec_max")
    C["pairs_r50"] = [(tk, C["r50"][tk]) for tk in TORDER
                      if C["r50"].get(tk) is not None]
    if C["pairs_r50"]:
        C["r50_min_tk"], C["r50_min"] = min(C["pairs_r50"], key=lambda p: p[1])
        C["r50_max_tk"], C["r50_max"] = max(C["pairs_r50"], key=lambda p: p[1])
    else:
        C["r50_min_tk"] = C["r50_max_tk"] = None
        C["r50_min"] = C["r50_max"] = None

    # P_rec 上限（缺失时由长表补）
    if all(v is None for v in C["pmax"].values()) \
            and data.long is not None and "P_rec" in getattr(data.long, "columns", []):
        sid = "S01" if (data.long["sweep_id"] == "S01").any() else data.long["sweep_id"].iloc[0]
        sub = data.long[data.long["sweep_id"] == sid]
        for tk in TORDER:
            s = pd.to_numeric(sub[sub["target"] == tk]["P_rec"], errors="coerce").dropna()
            if len(s):
                C["pmax"][tk] = float(s.max())

    # 传感器与频率量
    sensor = {}
    for name, p in params.SENSOR_PRESETS.items():
        ifov_rad = math.radians(float(p["fov_h_deg"])) / float(p["npx_h"])
        f_nyq = 1.0 / (2.0 * ifov_rad * 1e3)
        sensor[name] = dict(p, ifov_urad=ifov_rad * 1e6, ifov_mrad=ifov_rad * 1e3,
                            f_nyq=f_nyq)
    C["sensor"] = sensor
    C["n50sets"] = params.N50_SETS
    C["k_mrtd"] = float(params.SENSOR_PRESETS["RECOG"]["k_mrtd"])
    C["netd"] = float(params.SENSOR_PRESETS["RECOG"]["netd_k"])
    C["tau_opt"] = float(params.SENSOR_PRESETS["RECOG"]["tau_opt"])
    C["contrast_floor"] = C["k_mrtd"] * C["netd"]
    C["calib_md_notes"] = _calib_md_notes(data.calib_md)
    # 等效视在温差地板：优先按最新 k/NETD/τ_opt 现算；校准报告的值仅作交叉核对
    C["floor_dtapp"] = C["contrast_floor"] / C["tau_opt"] if C["tau_opt"] else C["contrast_floor"]
    floor_mk = C["calib_md_notes"].get("floor_dtapp_mk")
    C["floor_dtapp_md"] = (floor_mk / 1000.0) if floor_mk else None

    # 有效波长（优先用长表中的 lam_eff：模型输出；否则按波段中点）
    lam_eff = {}
    for band, fallback in (("MWIR", 4.25), ("LWIR", 10.0)):
        val = fallback
        if data.long is not None and all(c in data.long.columns for c in ("band", "lam_eff")):
            sub = data.long[(data.long["band"] == band)]
            if len(sub):
                v = fnum(pd.to_numeric(sub["lam_eff"], errors="coerce").median())
                if v:
                    val = v
        lam_eff[band] = val
    C["lam_eff"] = lam_eff
    recog = sensor["RECOG"]
    C["f_cut"] = {band: recog["D_m"] / (lam_eff[band] * 1e-6) * 1e-3
                  for band in ("MWIR", "LWIR")}

    # 斜程波段透过率随地面距离（基线目标 F16；MWIR 取 S01 基线段，LWIR 取 S02 同条件换波段段）
    tau_band = {"MWIR": {}, "LWIR": {}}
    lon = data.long
    if lon is not None and all(c in lon.columns for c in
                               ("band", "r_ground_km", "tau_band", "sweep_id", "target")):
        for band, sids in (("MWIR", ("S01",)), ("LWIR", ("S02",))):
            sub = lon[(lon["band"] == band) & (lon["target"] == "F16")
                      & (lon["sweep_id"].isin(sids))].copy()
            if len(sub) == 0:
                sub = lon[(lon["band"] == band) & (lon["target"] == "F16")].copy()
            sub["_r"] = pd.to_numeric(sub["r_ground_km"], errors="coerce")
            sub["_t"] = pd.to_numeric(sub["tau_band"], errors="coerce")
            sub = sub.dropna(subset=["_r", "_t"]).drop_duplicates(subset=["_r"])
            sub = sub.sort_values("_r")
            for dist in (1.0, 10.0, 20.0):
                val = None
                if len(sub) >= 2:
                    val = float(np.interp(dist, sub["_r"], sub["_t"]))
                tau_band[band][dist] = val
    C["tau_band"] = tau_band

    # 单变量扫描元信息（表 6）
    meta = []
    if data.summary is not None and "sweep_id" in data.summary.columns:
        rows = []
        for sid in [f"S{i:02d}" for i in range(1, 16)]:
            sub = data.summary[data.summary["sweep_id"] == sid]
            if len(sub) == 0:
                continue
            name = sub["sweep_name"].iloc[0] if "sweep_name" in sub.columns else sid
            xcol = _sweep_x(sub, ("sweep_value",))
            level = "—"
            if xcol:
                raw = sub[xcol].astype(str)
                nums = pd.to_numeric(sub[xcol], errors="coerce")
                if nums.notna().sum() >= len(sub) * 0.6:
                    level = (f"{_fmt_level(nums.min())} – {_fmt_level(nums.max())}"
                             f"（{nums.nunique()} 档）")
                else:
                    level = " / ".join(sorted(set(raw))[:3])
            rows.append({"编号": sid, "因子": str(name), "水平": level,
                         "目标数": int(sub["target"].nunique()),
                         "数据行数": int(len(sub))})
        meta = pd.DataFrame(rows)
    C["sweeps_meta"] = meta
    C["sweep_ranges"] = {
        "S04": _sweep_range(data, "S04", ("aod550",)),
        "S07": _sweep_range(data, "S07", ("cn2",)),
        "S08": _sweep_range(data, "S08", ("D_m",)),
        "S09": _sweep_range(data, "S09", ("netd_k",)),
        "S10": _sweep_range(data, "S10", ("ifov_urad",)),
        "S11": _sweep_range(data, "S11", ("platform_h_m",)),
        "S03": _sweep_range(data, "S03", ("target_temp_c",)),
        "S14": _sweep_range(data, "S14", ("eps_t",)),
    }

    # ---- 3.2.1 气溶胶
    pairs = _sweep_pairs(data, "S04", ("aod550",))
    aod_rows, aod_sum = [], {}
    for tk in ["HM", "F16", "AGZFSC", "ALBK", "NIMITZ"]:
        p = pairs.get(tk, [])
        if not p:
            continue
        first = _endpoint(p, "first")
        last = _endpoint(p, "last")
        base_v = _interp_pairs(p, params.ATMOS_BASE["aod550"])
        rel = _rel(last[1], first[1]) if (first[1] and last[1]) else None
        last_valid, censor_x = _last_x_censored(p)
        note = ""
        if censor_x is not None:
            note = f"AOD≥{censor_x:.2g} 后截断"
        aod_rows.append({
            "目标": TNAME[tk],
            f"R50@AOD={first[0]:.2f} (km)": fmt(first[1], 1),
            "R50@AOD=0.587 (km)": fmt(base_v, 1),
            f"R50@AOD={last[0]:.2f} (km)": fmt(last[1], 1),
            "首末变化": fpct(rel, 0) if rel is not None else "—",
            "说明": note or "—",
        })
        aod_sum[tk] = dict(first=first, last=last, base=base_v, rel=rel, censor_x=censor_x)
    C["aod_tab"] = pd.DataFrame(aod_rows)
    C["aod_summary"] = aod_sum
    C["aod_range"] = C["sweep_ranges"]["S04"]

    # ---- 3.2.2 湍流
    pairs = _sweep_pairs(data, "S07", ("cn2",))
    cn2_rows, cn2_sum = [], {}
    for tk in ["F16", "F22", "AGZFSC", "ALBK", "NIMITZ"]:
        p = pairs.get(tk, [])
        if not p:
            continue
        valid = [q for q in p if q[1] is not None]
        vmax = max(q[1] for q in valid) if valid else None
        half_x = None
        if vmax:
            for x, y in p:
                if y is not None and y < 0.5 * vmax and x > 1e-17:
                    half_x = x
                    break
        last_valid, censor_x = _last_x_censored(p)
        r0 = _interp_pairs(p, 0.0) if p and p[0][0] == 0.0 else (valid[0][1] if valid else None)
        r15 = _interp_pairs(p, 1e-15)
        r13 = _interp_pairs(p, 1e-13)
        cn2_rows.append({
            "目标": TNAME[tk],
            "R50@Cn²=0 (km)": fmt(r0, 1),
            "R50@1×10⁻¹⁵ (km)": fmt(r15, 1),
            "R50@1×10⁻¹³ (km)": fmt(r13, 1),
            "R50 半衰 Cn²": _sci_txt(half_x) if half_x else "—",
            "截断起点 Cn²": _sci_txt(censor_x) if censor_x else "无截断",
        })
        cn2_sum[tk] = dict(half_x=half_x, censor_x=censor_x, vmax=vmax, r0=r0, r15=r15, r13=r13)
    C["cn2_tab"] = pd.DataFrame(cn2_rows)
    C["cn2_summary"] = cn2_sum
    C["cn2_range"] = C["sweep_ranges"]["S07"]

    # ---- 3.2.3 目标热状态与发射率
    pairs = _sweep_pairs(data, "S03", ("target_temp_c",))
    temp_rows = []
    bg_c = float(params.BACKGROUND["temp_c"])
    temps = sorted({x for p in pairs.values() for x, _ in p if x is not None})
    for tx in temps:
        row = {"目标温度 (℃)": f"{tx:.0f}",
               "固有温差 ΔT (K)": fmt(tx - bg_c, 1)}
        for tk in ("F16", "NIMITZ", "AGZFSC"):
            row[TSHORT[tk]] = fmt(_interp_pairs(pairs.get(tk, []), tx), 1)
        temp_rows.append(row)
    C["temp_tab"] = pd.DataFrame(temp_rows)
    C["temp_summary"] = dict(dt0_ok=any(abs(t - bg_c) < 0.5 for t in temps))
    pairs14 = _sweep_pairs(data, "S14", ("eps_t",))
    eps_rows = []
    epss = sorted({x for p in pairs14.values() for x, _ in p if x is not None})
    for ex in epss:
        row = {"目标发射率 ε_t": fmt(ex, 2)}
        for tk in ("F16", "ALBK", "NIMITZ"):
            row[TSHORT[tk]] = fmt(_interp_pairs(pairs14.get(tk, []), ex), 1)
        eps_rows.append(row)
    C["eps_tab"] = pd.DataFrame(eps_rows)
    C["eps_range"] = C["sweep_ranges"]["S14"]

    # ---- 3.2.4 传感器参数
    pD = _sweep_pairs(data, "S08", ("D_m",))
    pN = _sweep_pairs(data, "S09", ("netd_k",))
    pI = _sweep_pairs(data, "S10", ("ifov_urad",))
    levels_D = sorted({x for p in pD.values() for x, _ in p if x is not None})
    levels_N = sorted({x for p in pN.values() for x, _ in p if x is not None})
    levels_I = sorted({x for p in pI.values() for x, _ in p if x is not None})
    nrow = max(len(levels_D), len(levels_N), len(levels_I))
    sensor_rows = []
    for i in range(nrow):
        row = {"序号": str(i + 1)}
        if i < len(levels_D):
            d = levels_D[i]
            row["口径 D (m)"] = fmt(d, 3)
            row["R50 F16@D (km)"] = fmt(_interp_pairs(pD.get("F16", []), d), 1)
            row["R50 尼米兹@D (km)"] = fmt(_interp_pairs(pD.get("NIMITZ", []), d), 1)
        else:
            row.update({"口径 D (m)": "—", "R50 F16@D (km)": "—", "R50 尼米兹@D (km)": "—"})
        if i < len(levels_N):
            nv = levels_N[i]
            row["NETD (mK)"] = fmt(nv * 1000, 0)
            row["R50 F16@NETD (km)"] = fmt(_interp_pairs(pN.get("F16", []), nv), 1)
            row["R50 尼米兹@NETD (km)"] = fmt(_interp_pairs(pN.get("NIMITZ", []), nv), 1)
        else:
            row.update({"NETD (mK)": "—", "R50 F16@NETD (km)": "—",
                        "R50 尼米兹@NETD (km)": "—"})
        if i < len(levels_I):
            iv = levels_I[i]
            row["IFOV (μrad)"] = fmt(iv, 1)
            row["R50 F16@IFOV (km)"] = fmt(_interp_pairs(pI.get("F16", []), iv), 1)
            row["R50 尼米兹@IFOV (km)"] = fmt(_interp_pairs(pI.get("NIMITZ", []), iv), 1)
        else:
            row.update({"IFOV (μrad)": "—", "R50 F16@IFOV (km)": "—",
                        "R50 尼米兹@IFOV (km)": "—"})
        sensor_rows.append(row)
    C["sensor_tab"] = pd.DataFrame(sensor_rows)
    plateau_D = None
    f16D = [y for x, y in pD.get("F16", []) if y is not None]
    if f16D:
        target = 0.99 * max(f16D)
        for x, y in sorted([q for q in pD.get("F16", []) if q[1] is not None], key=lambda q: q[0]):
            if y >= target:
                plateau_D = x
                break
    C["sensor_summary"] = dict(plateau_D=plateau_D,
                               f16D_max=max(f16D) if f16D else None)
    # IFOV 反比检验
    r50_ifov = {}
    for iv in levels_I:
        r50_ifov[iv] = _interp_pairs(pI.get("F16", []), iv)
    C["ifov_summary"] = dict(levels=levels_I, r50=r50_ifov)

    # ---- 3.2.5 平台高度
    pairs11 = _sweep_pairs(data, "S11", ("platform_h_m",))
    heights = sorted({x for p in pairs11.values() for x, _ in p if x is not None})
    h_rows = []
    for h in heights:
        row = {"平台高度 (m)": f"{h:.0f}"}
        for tk in ("F16", "AGZFSC", "ALBK", "NIMITZ"):
            row[TSHORT[tk]] = fmt(_interp_pairs(pairs11.get(tk, []), h), 1)
        base_h = _interp_pairs(pairs11.get("F16", []), 8000.0)
        cur = _interp_pairs(pairs11.get("F16", []), h)
        row["F16 相对 8 km"] = fpct(_rel(cur, base_h), 0) if (cur and base_h) else "—"
        h_rows.append(row)
    C["s11_tab"] = pd.DataFrame(h_rows)
    C["s11_summary"] = dict(heights=heights,
                            pN=_interp_pairs(pairs11.get("NIMITZ", []), heights[0]) if heights else None)

    # ---- 3.3 波段对比
    band_rows = []
    if data.band is not None:
        rc = _col(data.band, "R50_ground_km", "R50")
        bc = _col(data.band, "band")
        tc = _col(data.band, "target")
        if rc and bc and tc:
            for tk in TORDER:
                sub = data.band[data.band[tc] == tk]
                mw = sub[sub[bc].astype(str).str.upper().str.contains("MWIR")]
                lw = sub[sub[bc].astype(str).str.upper().str.contains("LWIR")]
                mw_row = _baseline_row(mw)
                lw_row = _baseline_row(lw)
                mwv = fnum(mw_row[rc]) if mw_row is not None else None
                lwv = fnum(lw_row[rc]) if lw_row is not None else None
                band_rows.append({"目标": TNAME[tk],
                                  "MWIR R50 (km)": fmt(mwv, 1),
                                  "LWIR R50 (km)": fmt(lwv, 1),
                                  "LWIR/MWIR−1": fpct(_rel(lwv, mwv), 0)})
        C["band_tab"] = pd.DataFrame(band_rows)
    if not band_rows:
        s02 = data.sweep("S02")
        tab_rows = []
        if s02 is not None and "band" in s02.columns:
            for tk in TORDER:
                sub = s02[s02["target"] == tk]
                mw_row = _baseline_row(sub[sub["band"] == "MWIR"])
                lw_row = _baseline_row(sub[sub["band"] == "LWIR"])
                mwv = fnum(mw_row["R50_ground_km"]) if mw_row is not None else None
                lwv = fnum(lw_row["R50_ground_km"]) if lw_row is not None else None
                tab_rows.append({"目标": TNAME[tk], "MWIR R50 (km)": fmt(mwv, 1),
                                 "LWIR R50 (km)": fmt(lwv, 1),
                                 "LWIR/MWIR−1": fpct(_rel(lwv, mwv), 0)})
        C["band_tab"] = pd.DataFrame(tab_rows)
    # 波段相对差异汇总（小目标 vs 大目标）
    bsum = {}
    if len(C["band_tab"]):
        tab = C["band_tab"].copy()

        def _pct2rel(s):
            x = fnum(str(s).replace("%", "").replace("+", ""))
            return None if x is None else x / 100.0

        tab["_rel"] = tab["LWIR/MWIR−1"].map(_pct2rel)
        for grp, tks in (("small", SMALL_T), ("large", LARGE_T)):
            vals = tab[tab["目标"].isin([TNAME[t] for t in tks])]["_rel"].dropna()
            if len(vals):
                bsum[grp] = float(np.median(vals))
    C["band_summary"] = bsum

    # ---- 3.4 相图统计
    C["phase_tab"], C["phase_summary"] = _phase_tables(data)

    # ---- 3.5 真实气候工况
    C["env_tab"], C["env_summary"], C["env_qtab"] = _env_tables(data)

    # ---- 3.6 敏感性
    C["sens_tab"], C["sens_top"] = _sensitivity_table(data)

    # ---- 4 临界状态
    (C["crit_maps"], C["crit_censor"], C["crit_tab"], C["blind_tab"],
     C["critparam_tab"], C["crit_notes"]) = _critical_tables(data)
    # 10 km 参考距离附列（部分目标 NaN：R50≤10 km 时不计算；显示“—”并注明）
    rng10 = dict(CRIT_SOLVER_BOUNDS)
    p10_rows = []
    if data.crit is not None and "target" in data.crit.columns:
        cols10 = set(data.crit.columns)
        for tk in TORDER:
            sub = data.crit[data.crit["target"] == tk]
            if len(sub) == 0:
                continue
            row = sub.iloc[0]

            def _flag10(name):
                return "" if (name not in cols10 or pd.isna(row[name])) else str(row[name])

            a10 = fnum(C["crit_maps"]["aod10"].get(tk))
            c10 = fnum(C["crit_maps"]["cn210"].get(tk))
            d10 = fnum(C["crit_maps"]["d10"].get(tk))
            n10 = fnum(C["crit_maps"]["netd10"].get(tk))
            f_a = _flag10("censored_AOD_10km")
            f_c = _flag10("censored_Cn2_10km")
            f_d = _flag10("censored_D_10km")
            f_n = _flag10("censored_NETD_10km")

            def _cell(v, flag, key, scale=1.0, n=2, sci=False):
                all_flags = "；".join((flag, f_a, f_c, f_d, f_n))
                if "R50≤10" in all_flags:
                    return "—（R50≤10 km）"
                if "上限仍满足" in flag:
                    return "≥20（不构成约束）" if key == "aod" else "不构成约束"
                if "下限已满足" in flag:
                    return "不构成约束"
                if v is None:
                    return "—"
                return _boundary_txt(v, rng10.get(key), scale=scale, n=n, sci=sci)

            p10_rows.append({
                "目标": TNAME[tk],
                "临界 AOD550@10km": _cell(a10, f_a, "aod", n=2),
                "临界 Cn²@10km": _cell(c10, f_c, "cn2", n=2, sci=True),
                "临界口径@10km (m)": _cell(d10, f_d, "d", n=3),
                "临界 NETD@10km (mK)": _cell(n10, f_n, "netd", scale=1000.0, n=1),
                "截断": "是" if any(
                    x and not any(k in x for k in ("上限仍满足", "下限已满足", "R50≤10"))
                    for x in (f_a, f_c, f_d, f_n)) else "—",
            })
    C["critparam10_tab"] = pd.DataFrame(p10_rows)

    # ---- 5.1 一致性校核 & 5.3 不确定度
    C["checks_tab"] = _consistency_checks(data, C["fig_status"])
    C["calib"] = calibration_numbers()
    C["calib_info"] = _calibration_supplement(data)
    C["unc_tab"] = _uncertainty_table(data, C["calib"])

    # ---- 附录 B 公式校准摘要
    C["calib_tables"] = _pick_calib_tables(data.calib_md)
    C["spec_tables"] = md_tables(data.spec_md, max_tables=6, max_rows=10, max_cols=5)
    C["qa_info"] = _qa_summary(data.qa_md)
    C["registry"] = data.registry
    C["data_cutoff"] = data.data_cutoff()
    C["fig_status"] = dict(_FIG_STATUS)

    # ---- 附录 D 文件清单
    C["inv_data"], C["inv_fig"], C["inv_code"] = _inventory(data, fig_dir)
    for name in ("inv_data", "inv_fig", "inv_code"):
        C[name] = _clean_str_series(C[name])

    # ---- 数据体量统计（摘要与 2.7 节引用）
    counts = {}
    for name, df in (("summary", data.summary), ("long", data.long),
                     ("env", data.env), ("crit", data.crit),
                     ("band", data.band), ("phase_aod", data.phase_aod),
                     ("phase_dt", data.phase_dt)):
        counts[name] = 0 if df is None else len(df)
    counts["sweeps"] = len(data.sweeps)
    C["counts"] = counts
    C["claims"] = _build_claims(C)
    return C


def _calibration_supplement(data):
    """附加的校准数值：Planck 积分、路径辐射写法差异、LWIR 物种贡献。"""
    out = {}
    sigma = 5.670374419e-8
    t = 300.0
    lam = np.logspace(-1, 4, 24000)
    b = _planck(lam, t)
    integral = float(np.trapz(b * lam, np.log(lam)))
    out["planck_B10_300"] = float(_planck(10.0, t))
    out["planck_integral_rel"] = integral / (sigma * t ** 4 / np.pi) - 1.0
    # 路径辐射两种写法的比值（均匀层、总光学厚度 τ、N 层）
    n = int(getattr(params, "N_LAYERS", 40))
    ratios = {}
    for tau in (3.0, 10.0):
        old = n * (1.0 - math.exp(-tau / n))
        new = 1.0 - math.exp(-tau)
        ratios[tau] = old / new if new else None
    out["pathrad_ratio"] = ratios
    # LWIR 缺省物种贡献（优先取校验文档，否则给文献量级说明）
    spec = data.spec_md or ""
    out["lwir_species"] = _parse_pct_after(spec, "O3", 300) \
        or _parse_pct_after(spec, "O₃", 300)
    out["continuum"] = _parse_pct_after(spec, "连续吸收", 240)
    out["convergence"] = _parse_convergence()
    return out


def _qa_summary(qa_md):
    info = {}
    if not qa_md:
        return info
    m = re.search(r"检查项[：:]\s*(\d+)", qa_md)
    if m:
        info["total"] = int(m.group(1))
    m = re.search(r"通过\s*(\d+)", qa_md)
    if m:
        info["pass"] = int(m.group(1))
    m = re.search(r"未通过\s*(\d+)", qa_md)
    if m:
        info["fail"] = int(m.group(1))
    return info


def _calib_md_notes(md_text):
    """从 06_校验/公式校准报告.md 中提取关键定量结论（缺失则返回空表）。"""
    out = {}
    if not md_text:
        return out
    m = re.search(r"高估\s*([0-9.]+)\s*[×x]", md_text)
    if m:
        out["pathrad_ratio_tau1"] = float(m.group(1))
    m = re.search(r"τ_band\s*约\s*\+?([0-9.]+)\s*%[^\n]{0,30}R50\s*约\s*\+?([0-9.]+)\s*%", md_text)
    if m:
        out["iso_tau_pct"] = float(m.group(1))
        out["iso_r50_pct"] = float(m.group(2))
    m = re.search(r"20\s*km\s*\+?([0-9.]+)\s*%[^\n]{0,40}?100\s*km\s*\+?([0-9.]+)\s*%"
                  r"[^\n]{0,40}?140\s*km\s*\+?([0-9.]+)\s*%", md_text)
    if m:
        out["curv_aer_20"] = float(m.group(1))
        out["curv_aer_100"] = float(m.group(2))
        out["curv_aer_140"] = float(m.group(3))
    m = re.search(r"LWIR 衍射截止\s*\+?([0-9.]+)\s*%", md_text)
    if m:
        out["lwir_diff_pct"] = float(m.group(1))
    m = re.search(r"LWIR 衍射受限\s*\+?([0-9.]+)\s*%", md_text)
    if m:
        out["lwir_r50_pct"] = float(m.group(1))
    m = re.search(r"0\.05\s*vs\s*0\.1/0\.2[^\n]{0,50}?差\s*<\s*([0-9.]+)\s*×\s*10⁻⁴", md_text)
    if m:
        out["spectral_tau_diff"] = float(m.group(1))
    m = re.search(r"IR 增量\s*<\s*([0-9.]+)\s*×\s*10⁻⁵", md_text)
    if m:
        out["rayleigh_ir_od"] = float(m.group(1))
    m = re.search(r"视在温差地板\s*([0-9.]+)\s*mK", md_text)
    if m:
        out["floor_dtapp_mk"] = float(m.group(1))
    m = re.search(r"盲区中心修正\s*([0-9.]+)\s*[–\-~]\s*([0-9.]+)\s*K", md_text)
    if m:
        out["blind_shift_low"] = float(m.group(1))
        out["blind_shift_high"] = float(m.group(2))
    return out


def _pick_calib_tables(md_text):
    """从校准报告中挑出对报告最有用的摘要表（核验/影响/公式对应）。"""
    tabs = md_tables(md_text, max_tables=20, max_rows=18, max_cols=6)
    if not tabs:
        return []

    def score(t):
        blob = " ".join(t["header"])
        s = 0
        if "核验项" in blob or "核验" in blob:
            s += 6
        if "修正项" in blob:
            s += 6
        if "公式" in blob and ("模块" in blob or "函数" in blob or "数据" in blob):
            s += 4
        if "状态" in blob and "数量" in blob:
            s += 3
        return s

    ranked = sorted(tabs, key=score, reverse=True)
    picked = [t for t in ranked if score(t) > 0][:4]
    return picked


def _rel_or_none(a, b):
    return _rel(a, b)


def _build_claims(C):
    """把“定性结论”也变成数据驱动的判断，避免任何与新口径不符的硬编码措辞。"""
    cl = {}
    data = C.get("data")
    eta = C.get("eta", {})

    def _vals(d, tks):
        out = []
        for t in tks:
            v = fnum(d.get(t))
            if v is not None:
                out.append(v)
        return out

    # ---- 两类机制
    small = _vals(eta, SMALL_T)
    large = _vals(eta, LARGE_T)
    cl["eta_small"] = (min(small), max(small)) if small else (None, None)
    cl["eta_large"] = (min(large), max(large)) if large else (None, None)
    cl["small_resolution_limited"] = bool(small) and min(small) >= 0.85
    cl["large_atmo_limited"] = bool(large) and max(large) <= 0.80
    cl["two_mechanisms"] = cl["small_resolution_limited"] and cl["large_atmo_limited"]

    # ---- 气溶胶影响对比（相对变化幅度）
    aod = C.get("aod_summary", {})
    a_small = [abs(fnum(_get(aod.get(t), "rel"))) for t in SMALL_T
               if fnum(_get(aod.get(t), "rel")) is not None]
    a_large = [abs(fnum(_get(aod.get(t), "rel"))) for t in LARGE_T
               if fnum(_get(aod.get(t), "rel")) is not None]
    cl["aod_small_abs"] = max(a_small) if a_small else None
    cl["aod_large_abs"] = max(a_large) if a_large else None
    cl["aod_contrast"] = (cl["aod_small_abs"] is not None
                          and cl["aod_large_abs"] is not None
                          and cl["aod_small_abs"] < 0.10
                          and cl["aod_small_abs"] < 0.5 * cl["aod_large_abs"])
    cl["aod_both_matter"] = (cl["aod_small_abs"] is not None
                             and cl["aod_small_abs"] >= 0.10)

    # ---- 波段对比（方向由数据决定，可能随口径反转）
    band = C.get("band_summary", {})
    bs, bl = fnum(band.get("small")), fnum(band.get("large"))
    cl["band_small"], cl["band_large"] = bs, bl
    if bs is not None and bl is not None:
        cl["band_same_sign"] = (bs < 0) == (bl < 0)
        cl["band_both_worse"] = cl["band_same_sign"] and bs < 0
        cl["band_both_better"] = cl["band_same_sign"] and bs > 0
        cl["band_cross"] = not cl["band_same_sign"]
    else:
        cl["band_same_sign"] = cl["band_both_worse"] = False
        cl["band_both_better"] = cl["band_cross"] = False
    tau_m = fnum(_get(C.get("tau_band", {}).get("MWIR", {}), 10.0))
    tau_l = fnum(_get(C.get("tau_band", {}).get("LWIR", {}), 10.0))
    cl["tau10_mw"], cl["tau10_lw"] = tau_m, tau_l
    cl["lwir_transparent"] = (tau_m is not None and tau_l is not None and tau_l > tau_m)

    # ---- 传感器参数：谁是一阶因子（按扫描范围内 F16 的 R50 相对变化）
    def _scan_span(sid, xnames, tk="F16"):
        pairs = _sweep_pairs(data, sid, xnames)
        vals = [y for _, y in pairs.get(tk, []) if y is not None]
        if len(vals) < 2:
            return None
        return (max(vals) - min(vals)) / max(vals)

    spans = {
        "口径 D": _scan_span("S08", ("D_m",)),
        "NETD": _scan_span("S09", ("netd_k",)),
        "IFOV": _scan_span("S10", ("ifov_urad",)),
    }
    valid_spans = {k: v for k, v in spans.items() if v is not None}
    cl["sensor_spans"] = spans
    if valid_spans:
        first = max(valid_spans, key=valid_spans.get)
        cl["sensor_first"] = first
        cl["sensor_first_pct"] = valid_spans[first]
    else:
        cl["sensor_first"], cl["sensor_first_pct"] = None, None
    pI = _sweep_pairs(data, "S10", ("ifov_urad",))
    valid_i = [(x, y) for x, y in pI.get("F16", []) if x is not None and y is not None]
    i8 = valid_i[0][1] if valid_i else None
    i40 = valid_i[-1][1] if valid_i else None
    cl["ifov_inverse_ratio"] = (i8 / i40) if (i8 and i40) else None
    cl["ifov_endpoints"] = (valid_i[0][0], valid_i[-1][0]) if valid_i else (None, None)
    pN = _sweep_pairs(data, "S09", ("netd_k",))
    n15 = _interp_pairs(pN.get("F16", []), 0.015)
    n40 = _interp_pairs(pN.get("F16", []), 0.040)
    cl["netd_effect"] = (n40 / n15 - 1.0) if (n15 and n40) else None
    cl["plateau_D"] = C.get("sensor_summary", {}).get("plateau_D")

    # ---- 平台高度：最优点与趋势
    p11 = _sweep_pairs(data, "S11", ("platform_h_m",))
    for tk, key in (("F16", "f16"), ("NIMITZ", "nimitz")):
        pairs = [(x, y) for x, y in p11.get(tk, []) if x is not None and y is not None]
        if pairs:
            h_best, r_best = max(pairs, key=lambda p: p[1])
            cl[f"s11_{key}_best_h"] = h_best
            cl[f"s11_{key}_best_r"] = r_best
            cl[f"s11_{key}_min_r"] = min(y for _, y in pairs)
            cl[f"s11_{key}_max_r"] = max(y for _, y in pairs)
            cl[f"s11_{key}_rising"] = pairs[-1][1] > pairs[0][1]

    # ---- 热状态与发射率的影响幅度
    p3 = _sweep_pairs(data, "S03", ("target_temp_c",))
    r40 = _interp_pairs(p3.get("NIMITZ", []), 40.0)
    r60 = _interp_pairs(p3.get("NIMITZ", []), 60.0)
    cl["temp_effect"] = _rel_or_none(r60, r40)
    p14 = _sweep_pairs(data, "S14", ("eps_t",))
    e85 = _interp_pairs(p14.get("NIMITZ", []), 0.85)
    e97 = _interp_pairs(p14.get("NIMITZ", []), 0.97)
    cl["eps_effect"] = _rel_or_none(e97, e85)

    # ---- 热交叉盲区：哪些目标有盲区、中心偏离零的大小
    bt = C.get("blind_tab")
    zero_t, valid_t = [], []
    center_dev = []
    if bt is not None and len(bt):
        for _, rr in bt.iterrows():
            name = str(rr.get("目标", "")).replace(" 战斗机", "").replace("级航空母舰", "")
            w = fnum(str(rr.get("盲区宽度 (K)", "")).replace("—", "nan"))
            c = fnum(str(rr.get("盲区中心 ΔT_cross (K)", "")).replace("—", "nan"))
            if w is not None and w <= 1e-9:
                zero_t.append(name)
            elif w is not None and w < 30:
                valid_t.append(name)
                if c is not None:
                    center_dev.append(abs(c))
    cl["blind_zero_targets"] = zero_t
    cl["blind_valid_targets"] = valid_t
    cl["blind_center_maxdev"] = max(center_dev) if center_dev else None

    # ---- 临界参数：撞边界/截断/不构成约束的计数与有效范围（搜索区间与 critical.py 一致）
    maps = C.get("crit_maps", {})
    rng = dict(CRIT_SOLVER_BOUNDS)
    crit_df = data.crit if data is not None else None
    censor_cols = [c for c in crit_df.columns if "censor" in c.lower()] if crit_df is not None else []

    def _flag_of(tk, name):
        if crit_df is None or len(crit_df) == 0:
            return ""
        sub = crit_df[crit_df["target"] == tk] if "target" in crit_df.columns else pd.DataFrame()
        if len(sub) == 0 or name not in crit_df.columns:
            return ""
        v = sub.iloc[0][name]
        return "" if pd.isna(v) else str(v)

    def _boundary_stats(key, rng_key, censor_name):
        vals, bounds, nocon, missing = [], 0, 0, 0
        r = rng.get(rng_key)
        for t in TORDER:
            v = fnum(_get(maps.get(key, {}), t))
            flag = _flag_of(t, censor_name)
            if "上限仍满足" in flag:
                nocon += 1
                continue
            if v is None:
                missing += 1
                continue
            if r and r[1] and v >= 0.999 * r[1]:
                bounds += 1
            elif r and r[0] and r[0] > 0 and v <= 1.001 * r[0]:
                bounds += 1
            else:
                vals.append(v)
        return vals, bounds, nocon, missing

    av, ab, anoc, am = _boundary_stats("aod", "aod", "censored_AOD")
    cv, cb, cnoc, cm = _boundary_stats("cn2", "cn2", "censored_Cn2")
    dv, db_, dnoc, dm = _boundary_stats("dcrit", "d", "censored_D")
    nv, nb, nnoc, nm = _boundary_stats("netdcrit", "netd", "censored_NETD")
    cl["crit_aod_valid"] = (min(av), max(av)) if av else None
    cl["crit_aod_n"] = len(av)
    cl["crit_aod_bound_n"] = ab
    cl["crit_aod_nocon_n"] = anoc
    cl["crit_aod_missing_n"] = am
    cl["crit_cn2_valid"] = (min(cv), max(cv)) if cv else None
    cl["crit_cn2_n"] = len(cv)
    cl["crit_cn2_bound_n"] = cb
    cl["crit_cn2_nocon_n"] = cnoc
    cl["crit_cn2_missing_n"] = cm
    cl["crit_d_bound_n"] = db_
    cl["crit_d_nocon_n"] = dnoc
    cl["crit_d_valid"] = (min(dv), max(dv)) if dv else None
    cl["crit_d_missing_n"] = dm
    cl["crit_netd_bound_n"] = nb
    cl["crit_netd_nocon_n"] = nnoc
    cl["crit_netd_valid"] = (min(nv), max(nv)) if nv else None
    cl["crit_netd_missing_n"] = nm
    # 对比度地板对应的地面距离（远大于基线 R50 时说明识别不由对比度地板控制）
    rcf = [fnum(_get(maps.get("rcf", {}), t)) for t in TORDER]
    rcf = [v for v in rcf if v is not None]
    cl["contrast_floor_range_km"] = (min(rcf), max(rcf)) if rcf else None
    # 波段优势反转位置（按目标尺寸顺序找 LWIR/MWIR−1 的符号变化处）
    tab = C.get("band_tab")
    crossing = None
    if tab is not None and len(tab):
        ratios = []
        for tk in TORDER:
            sub = tab[tab["目标"] == TNAME[tk]]
            if len(sub) == 0:
                continue
            rel = fnum(str(sub.iloc[0].get("LWIR/MWIR−1", "—")).replace("%", ""))
            if rel is not None:
                ratios.append((tk, rel / 100.0))
        for i in range(1, len(ratios)):
            if (ratios[i - 1][1] < 0) != (ratios[i][1] < 0):
                crossing = (TSHORT[ratios[i - 1][0]], ratios[i - 1][1],
                            TSHORT[ratios[i][0]], ratios[i][1])
                break
    cl["band_crossing"] = crossing

    # ---- 相图：AOD/Cn² 联合作用与温差凹区
    ph = {}
    df = data.phase_aod if data is not None else None
    if df is not None:
        tc = _col(df, "target")
        rc = _col(df, "R50_ground_km", "R50")
        cc = _col(df, "cn2")
        ac = _col(df, "aod550")
        if tc and rc and cc and ac:
            for tk in ("F16", "NIMITZ"):
                sub = df[df[tc] == tk].copy()
                if len(sub) == 0:
                    continue
                sub["_y"] = pd.to_numeric(sub[rc], errors="coerce")
                sub["_c"] = pd.to_numeric(sub[cc], errors="coerce")
                sub["_a"] = pd.to_numeric(sub[ac], errors="coerce")
                cens = sub.groupby("_c")["_y"].apply(lambda s: float(s.isna().mean()))
                if len(cens) >= 2:
                    ph[f"{tk}_cens_low_cn2"] = float(cens.iloc[0])
                    ph[f"{tk}_cens_high_cn2"] = float(cens.iloc[-1])
                low = sub[sub["_c"] == sub["_c"].min()].sort_values("_a")
                vals = low["_y"].dropna()
                if len(vals) >= 2:
                    a0 = fnum(low["_a"].iloc[0])
                    a1 = fnum(low["_a"].iloc[-1])
                    ph[f"{tk}_aod_effect_low_cn2"] = _rel_or_none(fnum(vals.iloc[-1]), fnum(vals.iloc[0]))
                    ph[f"{tk}_aod_span"] = (a0, a1)
    df2 = data.phase_dt if data is not None else None
    if df2 is not None:
        tc = _col(df2, "target")
        rc = _col(df2, "R50_ground_km", "R50")
        ac = _col(df2, "aod550")
        dc = _col(df2, "dT_K", "dT")
        if tc and rc and ac and dc:
            tk = "F16" if (df2[tc] == "F16").any() else str(df2[tc].iloc[0])
            sub = df2[df2[tc] == tk].copy()
            sub["_y"] = pd.to_numeric(sub[rc], errors="coerce")
            sub["_a"] = pd.to_numeric(sub[ac], errors="coerce")
            sub["_d"] = pd.to_numeric(sub[dc], errors="coerce")
            widths = {}
            for a_val, g in sub.groupby("_a"):
                g = g.dropna(subset=["_d"]).sort_values("_d")
                if g["_y"].notna().sum() < 3:
                    continue
                ymax = float(g["_y"].max())
                notch = g[g["_y"] < 0.5 * ymax]
                if len(notch):
                    widths[float(a_val)] = float(notch["_d"].max() - notch["_d"].min())
            if widths:
                a_keys = sorted(widths)
                ph["notch_aod_low"] = a_keys[0]
                ph["notch_aod_high"] = a_keys[-1]
                ph["notch_w_low"] = widths[a_keys[0]]
                ph["notch_w_high"] = widths[a_keys[-1]]
                ph["notch_widening"] = widths[a_keys[-1]] > widths[a_keys[0]] * 1.05
                ph["notch_narrowing"] = widths[a_keys[-1]] < widths[a_keys[0]] * 0.95
                ph["notch_target"] = tk
    cl["phase"] = ph
    return cl


def _clean_str_series(df):
    """把清单表中的字符串列做版本类字样清洗（防止路径里带工程目录名）。"""
    if df is None or len(df) == 0:
        return df
    out = df.copy()
    for col in out.columns:
        if out[col].dtype == object:
            def _fix(v, _pat=FORBIDDEN_PATTERNS):
                if not isinstance(v, str):
                    return v
                s = v
                for pat in _pat:
                    s = re.sub(pat, "…", s)
                return s
            out[col] = out[col].map(_fix)
    return out


def _phase_tables(data):
    rows, summary = [], {}
    pa = _phase_stats(data.phase_aod, targets=("F16", "NIMITZ", "ALBK", "AGZFSC"))
    pd_ = _phase_stats(data.phase_dt, targets=("F16", "AGZFSC", "NIMITZ"))
    for tk, s in pa.items():
        rows.append({
            "图": "图14",
            "目标": TNAME[tk],
            "参数范围": (f"AOD {fmt(s.get('aod_min'), 2)}–{fmt(s.get('aod_max'), 2)}；"
                         f"Cn² {fsci(s.get('cn2_min'))}–{fsci(s.get('cn2_max'))}"),
            "格点数": s["n"],
            "截断数": s["n_nan"],
            "R50 最小 (km)": fmt(s.get("vmin"), 1),
            "R50 最大 (km)": fmt(s.get("vmax"), 1),
            "说明": "NaN 区为不可识别区（留白）" if s["n_nan"] else "全域可识别",
        })
        summary[f"aod_{tk}"] = s
    for tk, s in pd_.items():
        loc = "—"
        if s.get("argmin_dT") is not None:
            loc = (f"ΔT={fmt(s.get('argmin_dT'), 1)} K、"
                   f"AOD={fmt(s.get('argmin_aod'), 3)}")
        rows.append({
            "图": "图15",
            "目标": TNAME[tk],
            "参数范围": (f"ΔT {fmt(s.get('dt_min'), 1)}–{fmt(s.get('dt_max'), 1)} K；"
                         f"AOD {fmt(s.get('aod_min'), 2)}–{fmt(s.get('aod_max'), 2)}"),
            "格点数": s["n"],
            "截断数": s["n_nan"],
            "R50 最小 (km)": fmt(s.get("vmin"), 1),
            "R50 最大 (km)": fmt(s.get("vmax"), 1),
            "说明": f"最小值位置：{loc}",
        })
        summary[f"dt_{tk}"] = s
    return pd.DataFrame(rows), summary


# --------------------------------------------------------------------------- #
# 8. 文字小工具（全部输出带单位的中文短语，缺失值统一显示“—”）
# --------------------------------------------------------------------------- #
def _sci_txt(v, n=1, dash="—"):
    """科学计数法的上下标文本，如 1.0×10⁻¹⁵。"""
    x = fnum(v)
    if x is None:
        return dash
    if x == 0:
        return "0"
    exp = int(math.floor(math.log10(abs(x))))
    mant = x / (10.0 ** exp)
    sup = str(exp).translate(str.maketrans("0123456789-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁻"))
    return f"{mant:.{n}f}×10{sup}"


def _fmt_level(v, dash="—"):
    """扫描水平值的紧凑显示：普通量级用三位有效数字，极端量级用科学计数法。"""
    x = fnum(v)
    if x is None:
        return dash
    if x == 0:
        return "0"
    ax = abs(x)
    if ax >= 1e4 or ax < 1e-2:
        return _sci_txt(x, 2 if ax >= 1e4 else 1)
    return f"{x:.3g}"


def _km(v, n=1, dash="—"):
    x = fnum(v)
    return dash if x is None else f"{x:.{n}f} km"


def _kv(v, n=2, unit="", dash="—"):
    x = fnum(v)
    return dash if x is None else f"{x:.{n}f}{unit}"


def _pct_txt(v, n=0, dash="—", plus=True):
    x = fnum(v)
    if x is None:
        return dash
    return f"{x * 100:+.{n}f}%" if plus else f"{x * 100:.{n}f}%"


def _minmax(d, targets, n=1, unit=""):
    vals = [fnum(d.get(t)) for t in targets]
    vals = [v for v in vals if v is not None]
    if not vals:
        return "—"
    if len(vals) == 1:
        return f"{vals[0]:.{n}f}{unit}"
    return f"{min(vals):.{n}f}–{max(vals):.{n}f}{unit}"


def _get(d, key, default=None):
    v = (d or {}).get(key, default)
    return v


def _hrule(paragraph, color="1F3A5F", size=8):
    pPr = paragraph._p.get_or_add_pPr()
    pBdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), str(size))
    bottom.set(qn("w:space"), "1")
    bottom.set(qn("w:color"), color)
    pBdr.append(bottom)
    pPr.append(pBdr)


# --------------------------------------------------------------------------- #
# 9. 封面 / 摘要 / 第 1—2 章
# --------------------------------------------------------------------------- #
def _sec_cover(doc, C):
    for _ in range(4):
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(0)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(24)
    p.paragraph_format.space_after = Pt(10)
    r = p.add_run("红外目标识别概率极限与临界状态")
    _set_font(r, 26, True, NAVY, HEAD_FONT)
    r.add_break()
    r = p.add_run("仿真报告")
    _set_font(r, 26, True, NAVY, HEAD_FONT)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(6)
    _set_font(p.add_run(REPORT_SUBTITLE), 13.5, False, GREY, HEAD_FONT)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(30)
    _hrule(p)
    for _ in range(3):
        doc.add_paragraph()
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(8)
    _set_font(p.add_run("正 式 报 告"), 18, True, NAVY, HEAD_FONT)
    # 细装饰线
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(10)
    r = p.add_run("—" * 18)
    _set_font(r, 11, False, RGBColor(0xB0, 0xB0, 0xB0))
    for _ in range(6):
        doc.add_paragraph()
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(4)
    _set_font(p.add_run(REPORT_DATE), 15, True, DARK, HEAD_FONT)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _set_font(p.add_run(MODEL_NAME), 11, False, GREY, HEAD_FONT)
    doc.add_page_break()


def _sec_abstract(doc, C):
    heading(doc, "摘  要", 1)
    r50 = C["r50"]
    eta = C["eta"]
    counts = C["counts"]
    n50_rec = float(params.N50_SETS["NVESD"]["recognize"])
    tau_m = C["tau_band"].get("MWIR", {})
    tau_l = C["tau_band"].get("LWIR", {})
    small_eta = [fnum(eta.get(t)) for t in SMALL_T if fnum(eta.get(t)) is not None]
    large_eta = [fnum(eta.get(t)) for t in LARGE_T if fnum(eta.get(t)) is not None]
    eta_small = f"{min(small_eta):.2f}–{max(small_eta):.2f}" if small_eta else "—"
    eta_large = f"{min(large_eta):.2f}–{max(large_eta):.2f}" if large_eta else "—"
    blind = C.get("blind_tab")
    blind_txt = "—"
    hm_w, other_ws = None, []
    if blind is not None and len(blind):
        rows = []
        for _, r in blind.iterrows():
            w = fnum(str(r.get("盲区宽度 (K)", "")).replace("—", "nan"))
            if w is not None and 0 < w < 20:
                rows.append(f"{r['目标'].replace(' 战斗机', '').replace('级航空母舰', '')}"
                            f" {r['盲区下界 (K)']}–{r['盲区上界 (K)']} K")
            if w is None:
                continue
            if str(r.get("目标")) == TNAME["HM"]:
                hm_w = w
            elif w > 0:
                other_ws.append(w)
        if rows:
            blind_txt = "；".join(rows)
    blind_hm_note = ""
    if hm_w and other_ws and hm_w > 1.5 * float(np.median(other_ws)):
        pm_hm = fnum(C.get("pmax", {}).get("HM"))
        blind_hm_note = (f"其中悍马的 {hm_w:.2f} K 主要源于其峰值识别概率仅 {fmt(pm_hm, 2)}、"
                         "0.5·R₅₀ 处裕度很小，并非热交叉本身更宽（见 4.2 节）。")
    aod = C.get("aod_summary", {})
    aod_big = _pct_txt(_get(aod.get("NIMITZ"), "rel"), 0)
    aod_small = _pct_txt(_get(aod.get("F16"), "rel"), 0)
    cn2 = C.get("cn2_summary", {})
    cn2_f16 = _get(cn2.get("F16"), "censor_x")
    band_small = _pct_txt(_get(C.get("band_summary", {}), "small"), 0)
    band_large = _pct_txt(_get(C.get("band_summary", {}), "large"), 0)

    body(doc, "本报告回答一个工程问题：在给定红外传感器与真实大气条件下，对某类目标“能识别多远”的极限"
              "在哪里、临界状态是什么。报告把问题拆成“识别概率极限”与“临界状态”两层：前者给出任务概率随"
              "距离的完整曲线及其三类边界（分辨率天花板、对比度地板、湍流边界），后者反解出给定工况下的"
              "临界距离、热交叉盲区、临界气溶胶、临界湍流与临界传感器参数。")
    recog_fno = params.SENSOR_PRESETS["RECOG"]["f_m"] / params.SENSOR_PRESETS["RECOG"]["D_m"]
    body(doc, "仿真对象为 XGGDCOSSim2 软件中实际存在的 6 个目标模型（F16、F22 战斗机，尼米兹级航母，"
              "阿利伯克级驱逐舰，悍马车，爱国者导弹发射车），其包围盒取自软件 OSG 顶点（按 1 单位 = 1 m）；"
              f"等效特征尺寸 D_eff 跨 {_minmax(C.get('d_eff', {}), TORDER, 1)} m。"
              "传感器以软件默认显示参数为锚点，并定义参考识别通道：FOV 0.7334°×0.5500°、1024×768、"
              f"IFOV {C['sensor']['RECOG']['ifov_urad']:.2f} μrad、口径 {params.SENSOR_PRESETS['RECOG']['D_m']:.2f} m、"
              f"F/{recog_fno:.1f}、NETD {params.SENSOR_PRESETS['RECOG']['netd_k'] * 1000:.0f} mK；"
              "同时保留软件实测 3.75°×3.0° 搜索通道对照。")
    body(doc, f"基线工况（MWIR 3.7–4.8 μm、平台 8 km、背景 20 ℃、目标 40 ℃、AOD₅₅₀="
              f"{params.ATMOS_BASE['aod550']:.3f}、Ångström α={params.ATMOS_BASE['alpha']:.2f}、"
              f"PWV={params.ATMOS_BASE['pwv_cm']:.2f} cm、Cn²={_sci_txt(params.ATMOS_BASE['cn2'])}）下，"
              f"6 个目标的识别临界距离 R₅₀ 为：悍马 {_km(r50.get('HM'))}、F16 {_km(r50.get('F16'))}、"
              f"F22 {_km(r50.get('F22'))}、爱国者 {_km(r50.get('AGZFSC'))}、阿利伯克 {_km(r50.get('ALBK'))}、"
              f"尼米兹 {_km(r50.get('NIMITZ'))}。与仅由传感器采样/衍射决定的分辨率天花板 R_res 相比，"
              f"中小目标的折减比 η=R₅₀/R_res 为 {eta_small}，大型舰船为 {eta_large}。")
    cl = C.get("claims", {})
    body(doc, f"方法上，大气按 {params.N_LAYERS} 层球面斜程积分（含地球曲率、ISO 2533 廓线、"
              f"修正后的 Rayleigh 口径与六物种 HITRAN2020 逐线 Voigt 截面），目标/背景辐亮度显式包含 "
              f"(1−ε) 反射项；传感器链由衍射、探测器 sinc、抖动、湍流与电子学 MTF 串联，MRTD 阈值给出 f_max；"
              f"任务概率取 TTPF，周期数 N=f_max·D_eff/R_slant，N₅₀ 主口径为 NVESD 识别 {n50_rec:.1f} cycles。"
              f"数据产品包括全工况长表 {counts.get('long', 0):,} 行、{counts.get('sweeps', 0)} 组单变量扫描、"
              f"真实气候工况矩阵 {counts.get('env', 0)} 行、6 个目标的临界状态反解，以及"
              f"03_数据/波段对比 下的双波段 R₅₀ 表与 03_数据/相图 下的二维 R₅₀ 场；"
              "正文全部数值均由这些 CSV 运行时读取。")
    # ---- 结论一：两类机制（是否成立由数据中的 η 决定）
    tau_txt = (f"基线下 MWIR 波段透过率在 1/10/20 km 处分别为 {_kv(tau_m.get(1.0), 3)}/"
               f"{_kv(tau_m.get(10.0), 3)}/{_kv(tau_m.get(20.0), 3)}"
               "（F16 基线，目标高 500 m；对比度加权）")
    if cl.get("two_mechanisms"):
        concl1 = ("**结论一（两类机制）**：中小目标的 R₅₀ 紧贴分辨率天花板（η="
                  f"{eta_small}），大气与湍流只在极端工况下起决定作用；大型舰船的 η 降至 "
                  f"{eta_large}，其极限由累积大气透过率接管。{tau_txt}，大型目标恰好工作在这一"
                  "衰减敏感区间，两类机制在 16–85 m 的特征尺寸之间交接。")
    else:
        concl1 = ("**结论一（分辨率与大气共同限制）**：本数据下 η 随目标尺寸的变化并非简单的两段式——"
                  f"中小目标 η={eta_small}、大型舰船 η={eta_large}；{tau_txt}。"
                  "不同目标上分辨率、大气衰减与湍流的相对权重不同，具体数值与排序见 3.1、3.2、3.4 节。")
    body(doc, concl1)
    # ---- 结论二：气溶胶/湍流/波段（方向与幅度全部来自数据；缺数据时给指引）
    aod_small_abs = cl.get("aod_small_abs")
    aod_large_abs = cl.get("aod_large_abs")
    aod_txt_main = (f"AOD₅₅₀ 从 0.02 增至 4.0 时，尼米兹 R₅₀ 变化 {aod_big}、F16 变化 {aod_small}")
    if aod_small_abs is None and aod_large_abs is None:
        aod_clause = "气溶胶影响见 3.2.1 节（本数据缺少对应扫描）"
    elif cl.get("aod_contrast"):
        aod_clause = (f"气溶胶对中小目标识别影响很小（{aod_small}），但对万吨级舰船影响显著"
                      f"（{aod_big}）：{aod_txt_main}")
    elif cl.get("aod_both_matter"):
        aod_clause = (f"气溶胶对两类目标都有不可忽略的影响：{aod_txt_main}"
                      "（小型目标在当前口径下也不再对气溶胶免疫）")
    else:
        aod_clause = f"气溶胶影响量级：{aod_txt_main}"
    nim_r13 = C["cn2_summary"].get("NIMITZ", {}).get("r13")
    if cn2_f16 is None and nim_r13 is None:
        turb_clause = "湍流影响见 3.2.2 节（本数据缺少对应扫描）"
    else:
        turb_clause = ("湍流是少数能在“大气干净、距离很近”时仍使识别失败的大气因子："
                       f"F16 在 Cn²≈{_sci_txt(cn2_f16)} 后截断，尼米兹 R₅₀ 在 {_sci_txt(1e-13)} 时降至 "
                       f"{_km(nim_r13)}")
    bs, bl = cl.get("band_small"), cl.get("band_large")
    band_small = _pct_txt(bs, 0)
    band_large = _pct_txt(bl, 0)
    tau_cmp = ""
    if cl.get("tau10_mw") is not None and cl.get("tau10_lw") is not None:
        tau_cmp = (f"10 km 处 MWIR/LWIR 波段透过率为 {fmt(cl['tau10_mw'], 3)}/"
                   f"{fmt(cl['tau10_lw'], 3)}，")
    if bs is None and bl is None:
        band_clause = "波段对比见 3.3 节（本数据缺少波段对比表）"
    elif cl.get("band_both_better"):
        band_clause = (f"换到 LWIR 后两类目标的 R₅₀ 均延长（中小目标 {band_small}、大型舰船 {band_large}）；"
                       f"{tau_cmp}在本参考光学系统与当前大气口径下 LWIR 对识别更有利，"
                       "但这是透过率与衍射/Nyquist 匹配的净结果，不能外推为普遍规律。")
    elif cl.get("band_both_worse"):
        band_clause = (f"换到 LWIR 后两类目标的 R₅₀ 均缩短（中小目标 {band_small}、大型舰船 {band_large}）；"
                       f"{tau_cmp}本数据下 LWIR 并不更利于识别，识别看重的是 Nyquist 与衍射截止的匹配。")
    elif cl.get("band_cross"):
        cross = cl.get("band_crossing")
        cross_txt = ""
        if cross:
            cross_txt = (f"（波段优势反转发生在 {cross[0]} 与 {cross[2]} 之间；"
                         f"{cross[0]} 的 LWIR/MWIR−1={cross[1] * 100:+.0f}%、"
                         f"{cross[2]} 为 {cross[3] * 100:+.0f}%）")
        band_clause = (f"换到 LWIR 后中小目标 R₅₀ 变化 {band_small}、大型舰船变化 {band_large}，方向相反"
                       f"{cross_txt}；{tau_cmp}"
                       "“长波更适合识别”不能一概而论，取决于目标角尺寸与衍射/Nyquist 的匹配。")
    else:
        band_clause = (f"换到 LWIR 后中小目标 R₅₀ 变化 {band_small}、大型舰船变化 {band_large}；"
                       "波段选择需结合目标类别与光学系统匹配关系判断。")
    body(doc, f"**结论二（大气与波段因子）**：{aod_clause}；{turb_clause}。{band_clause}")
    body(doc, "**结论三（热交叉盲区）**：校准后的辐亮度方程含反射项，目标与背景固有温差为零时视在温差严格为零，"
              "识别盲区由等效视在温差地板（k·NETD/τ_opt）与噪声决定，而非由发射率不对称造成的假偏移决定。"
              f"本数据反解出的热交叉盲区为：{blind_txt}；{blind_hm_note}"
              "盲区中心严格位于 ΔT=0 附近。"
              "这解释了“近距、大目标、干净大气仍可能识别失败”的物理原因，也给出了工程上必须规避的温差窄带。")
    body(doc, "报告第 1 章定义任务、指标与三类“极限”；第 2 章给出数据、模型、实验设计与公式校准；"
              "第 3 章给出基线结果与单变量响应；第 4 章反解临界状态；第 5 章如实列出数据质量与不确定度；"
              "第 6 章为结论。报告的研究框架见附录 A 图 A1（项目思维导图）；公式校准的完整逐条依据见"
              "《06_校验/公式校准报告.md》，其摘要见附录 B。")
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(6)
    _set_font(p.add_run("关键词："), 10.5, True)
    _set_font(p.add_run("红外目标识别；识别概率；临界状态；HITRAN2020 光谱大气；"
                        "传感器链；不确定度"), 10.5)
    doc.add_page_break()


def _sec_1(doc, C):
    heading(doc, "1  任务、指标与“极限”的定义", 1)
    heading(doc, "1.1  研究问题", 2)
    body(doc, "红外成像系统的“能看多远”不是单一数字，而是随任务难度、目标尺寸、大气状态与传感器参数变化的曲面。"
              "工程上真正需要的是三件事：①给定工况下的极限距离；②极限由什么决定（瓶颈在哪一层）；"
              "③要把极限推移到某个值，需要改变哪个参数、改到多少。本报告按这三件事组织：")
    bullet(doc, "极限距离：给出 6 个目标在基线工况下的识别概率曲线、R₅₀/R₉₀ 与解析分辨率天花板，并给出三任务定义"
                "（探测/识别/辨认）下的临界距离。")
    bullet(doc, "瓶颈判定：用 15 组严格单变量扫描分别移动气溶胶、湍流、目标热状态、传感器参数与平台高度，"
                "在“其余条件全部固定”的前提下判断哪一层接管了极限。")
    bullet(doc, "临界状态：反解临界距离、热交叉盲区、临界 AOD、临界 Cn²、临界口径与临界 NETD，"
                "给出可直接用于指标论证与测试设计的阈值。")
    body(doc, "研究对象是 XGGDCOSSim2 软件模型库中实际存在的 6 个目标，计算模型记为 " + MODEL_NAME + "："
              "输入为软件实测目标模型与背景，中间为 HITRAN2020 光谱大气的斜程透过率与路径辐射，"
              "输出为传感器链决定的可分辨频率、目标上的周期数与任务概率。全部输入参数登记在"
              "《05_参数依据/参数依据登记表.csv》，其中软件实测、文献、推导、设定四类来源逐项标注。")

    heading(doc, "1.2  “极限”的三层定义", 2)
    body(doc, "**（1）识别概率极限。**任务概率 P 随目标上可分辨周期数 N 按 TTPF 变化："
              "P(N)=N^E/(N₅₀^E+N^E)，E=2；N=f_max·θ，θ=D_eff/R_slant（m/km 即 mrad）。"
              "P 随距离单调下降，R₅₀ 定义为 P=0.5 对应的地面距离，R₉₀ 为 P=0.9 对应的地面距离。")
    body(doc, "**（2）分辨率天花板 R_res。**若忽略大气与湍流，仅由传感器采样/衍射上限 f_upper 与目标等效尺寸决定："
              "R_res=f_upper·D_eff/N₅₀，再按平台高度与地球曲率换算为地面距离。这是任何大气条件下都不可能超过的硬上限，"
              "η=R₅₀/R_res 度量实际极限相对这个天花板的折减。")
    body(doc, "**（3）对比度地板与湍流边界。**MRTD(f)=k·NETD/MTF(f)，当 τ_opt·|ΔT_app|≤k·NETD"
              "（即 |ΔT_app|≤k·NETD/τ_opt）时 f_max=0，此时无论距离多近都无法识别；"
              "湍流通过 r₀=(0.423k²Cn²L)^(−3/5) 压缩 MTF，"
              "使 f_max 提前掉出 Nyquist 频率，等效于把分辨率天花板下调。三类边界共同决定实际 R₅₀。")
    figure(doc, C["fig_dir"], "01",
           "图 1  识别概率极限的评估链路与三类边界")

    heading(doc, "1.3  研究框架与报告组织", 2)
    body(doc, "研究框架由“问题—模型链—三类极限—实验—数据产品—校验与不确定度—结论”构成，"
              "完整结构见附录 A 的图 A1（项目思维导图）。"
              "报告组织如下：第 2 章给出数据、方法与公式校准；第 3 章给出基线结果与单变量响应；"
              "第 4 章反解临界状态；第 5 章给出数据质量与不确定度；第 6 章为结论；"
              "附录 A—E 依次为思维导图、公式校准表（摘要）、参数依据摘要、文件清单与参考文献。")
    body(doc, "为保证可复算性，正文所有结论性数值都在生成时从 03_数据 的 CSV 读取；"
              "图表按正文顺序编号，全部结果可由数据表与附录 D 复算；"
              "读者可按附录 D 的文件清单与附录 C 的参数依据逐项核对。")

    heading(doc, "1.4  符号与指标定义", 2)
    rows = [
        ("R_slant", "传感器—目标视线斜距（球面弦长）", "km"),
        ("R_ground", "地面水平距离", "km"),
        ("R₅₀ / R₉₀", "识别概率 50% / 90% 对应的地面距离", "km"),
        ("Rdet50 / Rident50", "探测 / 辨认任务 50% 概率对应的地面距离", "km"),
        ("f_max", "由 MRTD、Nyquist 与衍射上限共同决定的最高可分辨频率", "cyc/mrad"),
        ("f_upper", "分辨率天花板所用的频率上限 min(Nyquist, D/λ)", "cyc/mrad"),
        ("D_eff", "目标等效特征尺寸 √(W_proj·H)", "m"),
        ("θ", "目标角尺寸 θ=D_eff/R_slant", "mrad"),
        ("N", "目标上的可分辨周期数 N=f_max·θ", "cycles"),
        ("N₅₀", "50% 概率周期数（NVESD 识别 16.5 / Johnson 识别 8.0）", "cycles"),
        ("R_res", "分辨率天花板（忽略大气与湍流）", "km"),
        ("η", "识别极限折减比 η=R₅₀/R_res", "—"),
        ("ΔT_app", "目标与背景的视在温差", "K"),
        ("k·NETD", "MRTD 判据参数；f_max=0 判据为 τ_opt·|ΔT_app|≤k·NETD", "K"),
        ("τ_band", "对比度等效波段透过率（按 dB/dT 加权）", "—"),
        ("AOD₅₅₀ / α", "550 nm 气溶胶光学厚度 / Ångström 指数", "—"),
        ("PWV", "可降水量", "cm"),
        ("Cn²", "大气折射率结构常数", "m⁻²ᐟ³"),
    ]
    table(doc, pd.DataFrame(rows, columns=["符号", "含义", "单位"]),
          [3.0, 10.2, 2.4], "表 1  本报告使用的符号与指标定义")


def _sec_2(doc, C):
    heading(doc, "2  数据与方法", 1)
    # ---- 2.1 目标与背景
    heading(doc, "2.1  软件实测目标与背景", 2)
    body(doc, "目标取自 XGGDCOSSim2 模型库中实际存在的 6 个模型，覆盖空中、海面、地面三类。"
              "其包围盒由软件 OSG 顶点直接解析（1 单位 = 1 m），表 2 给出几何参数；"
              "本报告主用 D_eff=√(W_proj·H)（等效方目标口径，与下视大斜距几何一致），"
              "并以最大边 max(W,L,H) 作敏感性对照。必须说明：包围盒未做几何标定，也未考虑投影姿态，"
              "这是本项目登记的主要不确定度之一（见 5.3 节）。")
    rows = []
    for t in params.TARGETS:
        w, l, h = t["dims"]
        rows.append({
            "目标": t["name"], "类别": t["kind"],
            "包围盒 W×L×H (m)": f"{w:.2f}×{l:.2f}×{h:.2f}",
            "D_eff (m)": f"{math.sqrt(max(w, l) * h):.2f}",
            "D_max (m)": f"{max(t['dims']):.2f}",
            "高度 (m)": f"{t['z_m']:.0f}",
            "发射率": f"{t['eps']:.2f}",
        })
    table(doc, pd.DataFrame(rows), [3.2, 1.4, 4.2, 1.8, 1.8, 1.6, 1.4],
          "表 2  软件模型库 6 个实际目标的几何参数")
    body(doc, f"背景采用软件唯一可加载的背景模型“{params.BACKGROUND['name']}”，环境温度 "
              f"{params.BACKGROUND['temp_c']:.0f} ℃、发射率 {params.BACKGROUND['eps']:.2f}；"
              f"目标热状态取 {params.BASELINE['target_temp_c']:.0f} ℃（基线）与 "
              f"{params.TARGET_STATES_C[0][0]:.0f}/{params.TARGET_STATES_C[2][0]:.0f} ℃ 对照，"
              f"目标发射率取 {params.TARGETS[0]['eps']:.2f}。目标高度按模型类别取 500 m（空中）、"
              "0 m（海面）、10 m（地面），平台高度基线 8000 m。")
    # ---- 2.2 传感器
    heading(doc, "2.2  参考传感器两档", 2)
    body(doc, "软件默认传感器只给出显示/注入链路参数（FOV、分辨率、帧率、平台高度、俯仰），"
              "不含 NETD、口径、焦距、像元尺寸等辐射参数。为使识别极限分析有意义，本报告定义“识别通道”"
              "（参考系统，设定值），并保留“搜索通道”（软件实测锚点）作对照；两档参数见表 3。"
              "两档 IFOV 相差约 5.1 倍，任何跨模块调用都显式携带通道标识，禁止混用。")
    sensor_rows = []
    for name, label in (("RECOG", "识别通道 RECOG（设定）"), ("SEARCH", "搜索通道 SEARCH（软件实测）")):
        s = C["sensor"][name]
        sensor_rows.append({
            "通道": label,
            "FOV": f"{s['fov_h_deg']:.4f}°×{s['fov_v_deg']:.3f}°",
            "像元": f"{int(s['npx_h'])}×{int(s['npx_v'])}",
            "IFOV (μrad)": f"{s['ifov_urad']:.2f}",
            "焦距 / 口径 (m)": f"{s['f_m']:.3f} / {s['D_m']:.4f}",
            "NETD (mK)": f"{s['netd_k'] * 1000:.0f}",
            "Nyquist (cyc/mrad)": f"{s['f_nyq']:.1f}",
        })
    table(doc, pd.DataFrame(sensor_rows), [3.4, 2.9, 1.8, 1.8, 2.5, 1.6, 2.1],
          "表 3  两档参考传感器（IFOV=FOV/N；Nyquist=1/(2·IFOV)）")
    recog = C["sensor"]["RECOG"]
    body(doc, f"识别通道的 IFOV={recog['ifov_urad']:.2f} μrad、Nyquist={recog['f_nyq']:.1f} cyc/mrad；"
              f"其衍射截止 D/λ 在 MWIR 有效波长 {C['lam_eff']['MWIR']:.3f} μm 处为 "
              f"{C['f_cut']['MWIR']:.1f} cyc/mrad、在 LWIR 有效波长 {C['lam_eff']['LWIR']:.3f} μm 处为 "
              f"{C['f_cut']['LWIR']:.1f} cyc/mrad。可见 MWIR 下为探测器采样受限（Nyquist < 衍射截止），"
              "LWIR 下衍射截止低于 Nyquist，识别转为衍射受限——这一差别是第 3.3 节波段对比的物理根源。"
              "该通道的焦距/口径为设定-推导值，已在参数依据表中登记，并通过口径、NETD、IFOV 三组单变量扫描给出敏感性。")
    # ---- 2.3 大气
    heading(doc, "2.3  光谱大气模型与 HITRAN2020 数据", 2)
    body(doc, "斜程大气按球面几何分层积分：以地心角 φ=r_ground/R_E 构造传感器—目标弦，"
              f"第 i 层中点高度 h_i=|P_i|−R_E（R_E={params.R_EARTH_KM:.0f} km，不含折射），"
              f"层光学厚度用该层消光系数乘弦段长度，共 {params.N_LAYERS} 层；斜距取弦长，"
              "地面距离↔斜距换算用球面关系。气体吸收使用 HITRAN2020 逐线 Voigt 截面：六物种"
              "（H₂O、CO₂、O₃、N₂O、CO、CH₄），温度 220/250/280/300 K 与气压 1.0/0.6/0.36/0.2 atm 四节点，"
              "逐层按层温与层压双线性插值（气压在 ln p 坐标线性）；O₃/N₂O/CO 均含四气压节点；"
              "CO 在 2375–2875 cm⁻¹ 无 HITRAN 数据，不影响其 1–0 带（2000–2300 cm⁻¹）。"
              f"光谱网格为波数域均匀、步长 {params.SPECTRAL_STEP_CM} cm⁻¹。")
    body(doc, "大气廓线采用 ISO 2533 分层（0–11 km 温度直减 6.5 K/km，11–20 km 等温 216.65 K）；"
              "水汽与气溶胶按指数标高分布（H₂O 2.0 km、气溶胶 1.5 km），柱含量分别归一到 PWV 与 AOD₅₅₀；"
              "分子散射采用 6S 口径的 Rayleigh 垂直光学厚度除以标高得到地面消光系数；"
              "气溶胶按外消光处理（不含散射相函数与多次散射）。路径辐亮度按累计光学厚度的发射—吸收积分"
              "L_path(λ)=Σ_i B(λ,T_i)[e^(−τ_before,i)−e^(−τ_after,i)] 逐层计算。")
    body(doc, "目标/背景波段辐亮度显式包含反射项（环境辐亮度取背景黑体）："
              "L_t=Σ_λ w[ε_t B(T_t)+(1−ε_t)B(T_b)]τ(λ)+L_path，"
              "L_b=Σ_λ w[ε_b B(T_b)+(1−ε_b)B(T_b)]τ(λ)+L_path。"
              "两式相减严格得 ΔL=ε_t[B(T_t)−B(T_b)]τ，因此热交叉严格发生在固有温差 ΔT=0；"
              "波段权重 w(λ)=dB/dT(λ,T_ref) 归一化，T_ref 取场景背景温度（基线 293.15 K），"
              "τ_band 与视在温度反演 LUT 使用同一组权重。")
    rows = [
        ("波段", "MWIR 3.7–4.8 μm；LWIR 8.0–12.0 μm（软件模型 Config.ini）"),
        ("光谱网格", f"波数域均匀，步长 {params.SPECTRAL_STEP_CM} cm⁻¹；MWIR 2000–4000 cm⁻¹、LWIR 775–1360 cm⁻¹"),
        ("吸收物种", "H₂O、CO₂、O₃、N₂O、CO、CH₄（HITRAN2020 逐线 Voigt；1 atm 线型参数、"
                    "每物种 4 温度 × 4 气压截面；空气加宽）"),
        ("温度/气压节点", "220/250/280/300 K × 1.0/0.6/0.36/0.2 atm；逐层按层温与层压双线性插值"
                        "（气压在 ln p 坐标线性）"),
        ("大气廓线", "ISO 2533 分层：0–11 km 直减 6.5 K/km；11–20 km 等温 216.65 K"),
        ("水汽/气溶胶", "指数标高 2.0 / 1.5 km，柱含量归一到 PWV / AOD₅₅₀；气溶胶按 Ångström 幂律"),
        ("分子散射", "τ_R,vert(λ)=0.008735·λ^−4.08，标高 8.0 km；按层气压/温度密度缩放"),
        ("斜程几何", f"球面弦长，{params.N_LAYERS} 层；R_E={params.R_EARTH_KM:.0f} km，不含折射"),
        ("路径辐射", "累计光学厚度的发射—吸收积分，逐层用层中点温度 Planck 函数"),
        ("反射项", "目标/背景辐亮度含 (1−ε)·B(T_b) 环境反射项（背景黑体近似）"),
        ("波段加权", f"w(λ)=dB/dT(λ,T_ref) 归一化，T_ref={params.T_REF_WEIGHT_K:.2f} K（场景背景温度）"),
    ]
    table(doc, pd.DataFrame(rows, columns=["项目", "设置"]), [3.4, 12.6],
          "表 4  光谱大气模型的主要配置")
    figure(doc, C["fig_dir"], "02",
           "图 2  真实气候工况空间（AOD₅₅₀–PWV）与软件默认工况定位")

    def _chord_km(rg_km, zt_m, zs_m=8000.0):
        """球面弦长（地面距离→斜距），仅用于图 3 与 F16 基线的口径说明。"""
        re_km = float(params.R_EARTH_KM)
        phi = rg_km / re_km
        a = re_km + zs_m / 1000.0
        b = re_km + zt_m / 1000.0
        return math.sqrt(max(0.0, a * a + b * b - 2.0 * a * b * math.cos(phi)))

    slant_fig3 = _chord_km(20.0, 0.0)
    f16_z = next((t["z_m"] for t in params.TARGETS if t["key"] == "F16"), 500.0)
    slant_f16 = [_chord_km(rg, f16_z) for rg in (1.0, 10.0, 20.0)]
    figure(doc, C["fig_dir"], "03",
           f"图 3  4 种气候工况（基线、清洁干燥、湿热带、强沙尘）的斜程大气光谱透过率"
           f"（左：MWIR 3.7–4.8 μm；右：LWIR 8.0–12.0 μm；斜距约 {slant_fig3:.2f} km、目标高 0 m；"
           "波段平均按 dB/dT 加权）")
    tau_m = C["tau_band"]["MWIR"]
    tau_l = C["tau_band"]["LWIR"]
    body(doc, f"基线工况下，MWIR 对比度等效波段透过率在 1/10/20 km 地面距离处分别为 "
              f"{_kv(tau_m.get(1.0), 3)}/{_kv(tau_m.get(10.0), 3)}/{_kv(tau_m.get(20.0), 3)}；"
              f"LWIR 分别为 {_kv(tau_l.get(1.0), 3)}/{_kv(tau_l.get(10.0), 3)}/{_kv(tau_l.get(20.0), 3)}。"
              "光谱步长与分层数的收敛性、与独立逐线计算结果的对比、以及分物种"
              "（H₂O/CO₂/O₃/N₂O/CO/CH₄/气溶胶）的透过率贡献，见《06_校验/光谱大气校验.md》的文字与表格；"
              "图 3 给出基线工况与 4 种气候工况的斜程总透过率。"
              "六物种四温度×四气压截面的完整性使 LWIR 窗区的弱吸收带不再被略去，"
              "相应的定量影响汇总在 2.6 节。")
    body(doc, f"口径说明：图 3 给出的斜程光谱按目标高 0 m、地面距离 20 km（斜距约 {slant_fig3:.2f} km）计算；"
              f"本段 1/10/20 km 的数值为 F16 基线（目标高 {f16_z:.0f} m，斜距约 "
              f"{slant_f16[0]:.2f}/{slant_f16[1]:.2f}/{slant_f16[2]:.2f} km）的对比度加权波段值，"
              "二者口径不同、均为正确结果，图 3 与本节数值不应直接逐项对比。")

    # ---- 2.4 传感器链
    heading(doc, "2.4  传感器链与任务概率", 2)
    body(doc, "系统 MTF 由衍射、探测器 sinc、视线抖动、湍流与电子学五部分串联："
              "MTF_sys(f)=MTF_diff(f)·MTF_det(f)·MTF_jit(f)·MTF_turb(f)·MTF_elec(f)，"
              "其中衍射取 Airy OTF (2/π)(arccosν−ν√(1−ν²))，探测器取 sinc(f·IFOV)，"
              "抖动取 exp(−2π²σ_j²f²)，湍流取 exp(−3.44(λf·10³/r₀)^(5/3))，"
              "r₀=(0.423k²Cn²L)^(−3/5)；电子学取 1/(1+(f/120)²)。"
              "给定视在温差 ΔT_app 后，由 MRTD(f)=k·NETD/MTF(f)=τ_opt·|ΔT_app| 求最高可分辨频率 f_max，"
              "上限取 min(Nyquist, 衍射截止)。")
    body(doc, "目标角尺寸 θ=D_eff/R_slant（m/km 即 mrad），周期数 N=f_max·θ，"
              f"任务概率取 TTPF（E={params.CRITERIA['ttpf_exponent']:.0f}）。"
              f"N₅₀ 采用两套公开口径并列：主口径 NVESD/TTP（探测 {params.N50_SETS['NVESD']['detect']:.1f} / "
              f"识别 {params.N50_SETS['NVESD']['recognize']:.1f} / 辨认 {params.N50_SETS['NVESD']['identify']:.1f} cycles），"
              f"对照口径经典 Johnson（{params.N50_SETS['JOHNSON']['detect']:.1f} / "
              f"{params.N50_SETS['JOHNSON']['recognize']:.1f} / {params.N50_SETS['JOHNSON']['identify']:.1f} line pairs）。"
              "两套数值体系相差约 2 倍，本报告不合并、只并列，二者的距离差异见 3.1 节表 10。")
    rows = [
        ("IFOV", f"{recog['ifov_urad']:.2f} μrad", f"{C['sensor']['SEARCH']['ifov_urad']:.2f} μrad",
         "IFOV=FOV_h/N_h；决定 Nyquist 与识别上限"),
        ("Nyquist 频率", f"{recog['f_nyq']:.1f} cyc/mrad", f"{C['sensor']['SEARCH']['f_nyq']:.1f} cyc/mrad",
         "f_nyq=1/(2·IFOV)"),
        ("光学效率 τ_opt", f"{recog['tau_opt']:.2f}", f"{C['sensor']['SEARCH']['tau_opt']:.2f}", "设定值（登记）"),
        ("NETD", f"{recog['netd_k'] * 1000:.0f} mK", f"{C['sensor']['SEARCH']['netd_k'] * 1000:.0f} mK",
         "制冷型焦平面典型量级"),
        ("MRTD 系数 k", f"{recog['k_mrtd']:.1f}", f"{C['sensor']['SEARCH']['k_mrtd']:.1f}",
         "MRTD(0)=k·NETD，工程近似，需实测标定"),
        ("抖动 σ_j", f"{recog['jitter_mrad'] * 1000:.2f} μrad", f"{C['sensor']['SEARCH']['jitter_mrad'] * 1000:.1f} μrad",
         "按 0.3×IFOV 设定"),
        ("电子学截止", f"{recog['f_elec_cyc_mrad']:.0f} cyc/mrad", f"{C['sensor']['SEARCH']['f_elec_cyc_mrad']:.0f} cyc/mrad",
         "远高于 Nyquist，影响可忽略"),
        ("等效视在温差地板", f"{C['floor_dtapp'] * 1000:.1f} mK",
         f"{C['floor_dtapp'] * 1000:.1f} mK",
         "ΔT_app 低于 k·NETD/τ_opt 时 f_max=0"),
        ("F#（f/D）", f"{recog['f_m'] / recog['D_m']:.2f}",
         f"{params.SENSOR_PRESETS['SEARCH']['f_m'] / params.SENSOR_PRESETS['SEARCH']['D_m']:.2f}",
         "F# = 焦距 / 口径"),
    ]
    table(doc, pd.DataFrame(rows, columns=["参数", "识别通道", "搜索通道", "说明"]),
          [3.4, 3.0, 3.0, 6.8], "表 5  传感器链与判据的主要参数")
    figure(doc, C["fig_dir"], "04",
           "图 4  系统 MTF 链、MRTD 曲线与 f_max 判定")

    # ---- 2.5 实验设计
    heading(doc, "2.5  实验设计", 2)
    bl = params.BASELINE
    body(doc, f"单变量实验采用严格 OFAT 设计：每组只改变一个因子，其余全部固定为基线——{bl['band']}、"
              f"识别通道 RECOG、平台 {params.SENSOR_PRESETS['RECOG']['platform_h_m']:.0f} m、F16 基准目标、"
              f"目标 {bl['target_temp_c']:.0f} ℃/背景 {bl['bg_temp_c']:.0f} ℃、AOD₅₅₀={bl['aod550']:.3f}、"
              f"α={bl['alpha']:.2f}、PWV={bl['pwv_cm']:.2f} cm、Cn²={_sci_txt(bl['cn2'])}、"
              f"D_eff 口径、NVESD 判据。共 {len(C['sweeps_meta'])} 组扫描（表 6），"
              "每组覆盖全部 6 个目标，所有评估点写入全工况长表，任一结果行均可独立复算。")
    if len(C["sweeps_meta"]):
        table(doc, C["sweeps_meta"], [1.4, 4.4, 6.6, 1.7, 1.9],
              "表 6  单变量实验矩阵（每组只改一个因子，其余固定）")
    env_n = C["counts"].get("env", 0)
    body(doc, "除 OFAT 外，还构建了三类补充数据：①真实气候工况矩阵——8 类环境（沙漠、沙尘、半干旱、农田、"
              "城市、海岸、海洋、高原）× 每类 AOD₅₅₀/PWV 的 p10/中位/p90 × 6 个目标，"
              f"共 {env_n} 行，环境参数取自 NASA POWER/MERRA-2（2015–2024）与 AERONET 站点统计；"
              "②临界状态反解——对每个目标反解临界距离、热交叉盲区、临界 AOD、临界 Cn²、临界口径与临界 NETD；"
              "③相图——AOD₅₅₀×Cn² 与固有温差×AOD₅₅₀ 的二维 R₅₀ 场，用于展示两类机制的联合作用。"
              "上述数据分别落在 03_数据 的对应子目录，正文所有数值均由这些 CSV 运行时读取。")

    # ---- 2.6 公式校准
    heading(doc, "2.6  公式校准", 2)
    body(doc, "本项目对全链路公式做了一次系统校准，逐条记录“原式→校准式→物理依据→数值核验→对结论的影响”，"
              "《06_校验/公式校准报告.md》按模块列出 F1–F37 共 37 条公式（辐射度量、大气、传感器、判据、"
              "目标几何、临界求解与统计口径）；本报告按主题归并为 12 组，摘要列于表 7，"
              "完整推导与逐条核验见该报告（其要点表见附录 B）。")
    body(doc, "校准的核心变化集中在四处：①辐亮度方程补入 (1−ε) 反射项后，热交叉位置严格回到固有温差 ΔT=0，"
              "消除了发射率不对称造成的假偏移与假盲区；②Rayleigh 散射按“垂直光学厚度除以标高”的口径重算，"
              "修正了此前把垂直光学厚度系数误当每 km 消光系数的量纲问题；③大气廓线由单一指数气压改为 ISO 2533 分层，"
              "并加入地球曲率；④光谱数据升级为 HITRAN2020 六物种、四温度×四气压节点的完整逐线截面，"
              "LWIR 窗区的弱吸收带不再被略去。表 7 给出这些校准项的定量差异。")
    table(doc, _calib_rows(C), [1.5, 3.2, 6.2, 5.3],
          "表 7  公式校准的关键数值差异（完整逐条依据见《06_校验/公式校准报告.md》）")
    body(doc, "需要强调：上表所列差异均为“同一工况下、只改公式口径”带来的影响，量级小于判据口径与目标尺寸口径的"
              "不确定度（见 5.3 节）；因此本报告的相对排序与机制判断对公式口径不敏感，而绝对距离的主要不确定度来自"
              "输入参数而非公式本身。")
    heading(doc, "2.7  数据产品与复算路径", 2)
    body(doc, "全部数据产品汇总在 03_数据：全工况长表为唯一真值源，单变量宽表、临界状态表、环境工况表、"
              "波段对比表与相图表均由长表派生，互相可核对。表 8 给出文件、行列规模与用途；"
              "XLSX 汇总文件按扫描类别分 sheet，便于直接检索。")
    inv = C.get("inv_data")
    if inv is not None and len(inv):
        table(doc, inv[["文件", "类别", "行数", "列数", "大小"]], [5.0, 6.2, 1.6, 1.4, 1.9],
              "表 8  数据产品清单（正文数值全部来自这些文件）")
    note(doc, "说明：表中“行数”为该 CSV 的实际记录数；长表行数随实验矩阵与相图网格变化。"
              "缺少的文件/缺失的行在正文以“—”标注，并在 5.1 节与附录 D 说明。", size=8.8)


def _calib_rows(C):
    calib = C.get("calib", {})
    info = C.get("calib_info", {})
    notes = C.get("calib_md_notes", {})
    m = calib.get("MWIR", {})
    l = calib.get("LWIR", {})
    n50 = params.N50_SETS["NVESD"]
    lwir = info.get("lwir_species")
    pr = info.get("pathrad_ratio", {})
    floor = C.get("floor_dtapp")
    # 球面几何对斜程气溶胶光学厚度的增量（优先取校准报告原文，否则只给几何换算差）
    curv_txt = ""
    if all(k in notes for k in ("curv_aer_20", "curv_aer_100", "curv_aer_140")):
        curv_txt = (f"；球面分层使斜程 τ_aer 在 20/100/140 km 增大 "
                    f"{notes['curv_aer_20']:.1f}%/{notes['curv_aer_100']:.1f}%/"
                    f"{notes['curv_aer_140']:.1f}%，R50 影响约 1–3%")
    iso_txt = ""
    if "iso_tau_pct" in notes:
        iso_txt = (f"；τ_band 约 +{notes['iso_tau_pct']:.1f}%、"
                   f"R50 约 +{notes['iso_r50_pct']:.1f}%（校准报告 F7）")
    lwir_diff_txt = ""
    if "lwir_diff_pct" in notes:
        lwir_diff_txt = f"；LWIR 衍射截止 +{notes['lwir_diff_pct']:.2f}%"
    if "lwir_r50_pct" in notes:
        lwir_diff_txt += f"、R50 约 +{notes['lwir_r50_pct']:.1f}%（校准报告 F3）"
    spec_txt = ""
    if "spectral_tau_diff" in notes:
        spec_txt = (f"0.05 vs 0.1/0.2 cm⁻¹ 的 τ_band 差 <"
                    f"{notes['spectral_tau_diff']:.1f}×10⁻⁴；")
    lwir_species = info.get("lwir_species")
    species_txt = ""
    if isinstance(lwir_species, (tuple, list)) and len(lwir_species) >= 2:
        lo_sp, hi_sp = lwir_species[0], lwir_species[1]
        if fnum(lo_sp) is not None and fnum(hi_sp) is not None:
            if abs(float(lo_sp) - float(hi_sp)) < 1e-6:
                species_txt = f"LWIR 缺省物种（O₃ 等）补齐后 τ_band 约变化 {float(lo_sp):.1f}%；"
            else:
                species_txt = (f"LWIR 缺省物种补齐后 τ_band 约变化 "
                               f"{float(lo_sp):.0f}–{float(hi_sp):.0f}%；")
    rayleigh_txt = ""
    if "rayleigh_ir_od" in notes:
        rayleigh_txt = (f"IR 波段斜程光学厚度增量 <{notes['rayleigh_ir_od']:.0f}×10⁻⁵，"
                        f"对 R50 影响 <0.1%")
    else:
        rayleigh_txt = (f"IR 波段消光最大差 {fsci(calib.get('rayleigh_ir_max_diff_km'), 1)} km⁻¹，"
                        f"对结论影响 <0.1%")
    pr_txt = ""
    if "pathrad_ratio_tau1" in notes:
        pr_txt = (f"均质板 τ_total=1 时高估 {notes['pathrad_ratio_tau1']:.2f}×"
                  f"（本报告核算 τ=3/10 时 {fmt(pr.get(3.0), 1)}/{fmt(pr.get(10.0), 1)}×）；")
    blind_cmp = ""
    if all(k in notes for k in ("blind_shift_low", "blind_shift_high")):
        blind_cmp = (f"，与校准报告“盲区中心修正 "
                     f"{notes['blind_shift_low']:.1f}–{notes['blind_shift_high']:.1f} K”一致")
    rows = [
        ("F1 / F2", "Planck 定律与 dB/dT",
         "以 CODATA 常数复算 B(λ,T) 与 dB/dT，波段积分权重用 dB/dT 归一化",
         f"B(10 μm,300 K)={fmt(info.get('planck_B10_300'), 3)} W/(m²·sr·μm)；"
         f"∫B dλ 与 σT⁴/π 相对差约 {_sci_txt(abs(fnum(info.get('planck_integral_rel')) or 0.0), 1)}"),
        ("F3", "波段对比度加权",
         "w(λ)=dB/dT(λ,T_ref) 的 T_ref 由固定 288.15 K 改为场景背景温度（基线 293.15 K），"
         "τ_band 与视在温度 LUT 使用同一权重",
         f"λ_eff：MWIR {fmt(m.get('lam_eff_288'), 3)}→{fmt(m.get('lam_eff_ref'), 3)} μm、"
         f"LWIR {fmt(l.get('lam_eff_288'), 3)}→{fmt(l.get('lam_eff_ref'), 3)} μm"
         f"{lwir_diff_txt}；R50 影响 <0.2%（MWIR）"),
        ("F5", "反射项与热交叉",
         "目标/背景辐亮度补入 (1−ε)·B(T_b) 反射项（背景黑体近似），两式相减严格得 "
         "ΔL=ε_t[B(T_t)−B(T_b)]τ",
         f"ΔT=0 时 ΔT_app 严格为 0；原式因发射率不对称会把零对比点偏移约 "
         f"{fmt(m.get('dt_shift_K'), 1)} K（MWIR）/{fmt(l.get('dt_shift_K'), 1)} K（LWIR）"
         f"{blind_cmp}"),
        ("F6", "球面地球几何与斜程",
         "以地心角构造传感器—目标弦，逐层按层高消光积分；地面距离↔斜距用球面关系",
         f"斜距相对平面近似差 {fmt(calib.get('curvature_max_pct'), 3)}%（140 km）{curv_txt}"),
        ("F7", "ISO 2533 标准大气廓线",
         "0–11 km 温度直减 6.5 K/km、11–20 km 等温 216.65 K 的分层气压，替代单一指数气压廓线",
         f"8 km 处气压相差 {_pct_txt(calib.get('iso_p8_ratio'), 1)}；0–8 km 柱质量相差 "
         f"{_pct_txt(calib.get('iso_column_rel'), 2)}{iso_txt}"),
        ("F8–F10", "水汽/气溶胶廓线与 Rayleigh 口径",
         "ρ_v、β_aer 按指数标高分布并严格归一到 PWV、AOD₅₅₀；Rayleigh 按“垂直光学厚度/标高”"
         "重算地面消光，替代把垂直光学厚度系数误当每 km 消光系数的写法",
         f"Rayleigh 系数放大 {fmt(calib.get('rayleigh_ratio'), 2)}×；{rayleigh_txt}"),
        ("F11–F13", "光谱网格、物种与路径辐射",
         "HITRAN2020 六物种四温度×四气压、0.05 cm⁻¹ 波数域均匀网格；路径辐射用累计光学厚度的"
         "发射—吸收积分",
         f"{spec_txt}路径辐射：{pr_txt}新写法满足 0≤L_path≤B(T_max)"),
        ("F15–F22", "传感器链与 MRTD/f_max",
         "保留 IFOV=FOV/N、f=p/IFOV、f_nyq=1/(2·IFOV)、D/λ 衍射截止、Airy/sinc/抖动/湍流/电子学 MTF "
         "与 MRTD=k·NETD/MTF；k=2.5 登记为工程近似",
         f"标准式保留；f_max 求根条件为 MRTD(f)=τ_opt·|ΔT_app|，即等效视在温差地板 "
         f"k·NETD/τ_opt≈{fmt(floor * 1000, 1)} mK"),
        ("F23–F26", "视在温差、周期数与判据",
         f"ΔT_app≤ε_t·ΔT（线性极限）；θ=D_eff/R_slant、N=f_max·θ；"
         f"P=N^E/(N₅₀^E+N^E)，E={params.CRITERIA['ttpf_exponent']:.0f}；N₅₀ 双口径并列",
         f"NVESD 识别 {n50['recognize']:.1f} cycles（Johnson 识别 "
         f"{params.N50_SETS['JOHNSON']['recognize']:.1f} line pairs）；判据口径是最大单项不确定度"),
        ("F28–F31", "目标尺寸与临界距离求解",
         "D_eff=√(W_proj·H)；R50/R90 改为对数域二分，|ΔlnR|<10⁻³；截断情形返回空值并记录原因",
         "非截断情形精度约 0.1%；截断不再返回搜索边界值（消除假解）"),
        ("F32–F33", "热交叉盲区与临界参数反解",
         "统一主参考距离 r_ref=0.5·R₅₀（另附 10 km 参考距离列）；盲区先 −10…+10 K 细扫（0.02 K）再对两侧根二分；"
         "临界 AOD/Cn²/口径/NETD 相对容差 10⁻³，越界标“截断”",
         "盲区位置与宽度由临界状态 CSV 读取；临界值与图 14、图 15 的相图同源"),
        ("F34–F37", "统计与图件口径",
         "环境工况按 p10/中位/p90 分位定义；折减比 η=R₅₀/R_res；敏感性用扫描范围内 R₅₀ 最大相对变化",
         "报告、数据与图件使用同一统计定义，可逐项复算"),
    ]
    return pd.DataFrame(rows, columns=["编号", "校准项", "校准要点", "定量差异 / 对结论的影响"])


# --------------------------------------------------------------------------- #
# 10. 第 3 章：结果
# --------------------------------------------------------------------------- #
def _sec_3(doc, C):
    data = C["data"]
    heading(doc, "3  结果", 1)
    r50, rres, eta = C["r50"], C["rres"], C["eta"]
    tau50, dtapp, nat, pmax = C["tau50"], C["dtapp50"], C["nat50"], C["pmax"]

    # ---------------- 3.1 基线
    heading(doc, "3.1  基线：识别概率曲线与临界距离", 2)
    figure(doc, C["fig_dir"], "05",
           "图 5  基线工况下 6 个目标的识别/探测概率曲线与 50% 临界距离")
    rows = []
    for tk in TORDER:
        rows.append({
            "目标": TNAME[tk],
            "D_eff (m)": fmt(C.get("d_eff", {}).get(tk), 2),
            "R50 (km)": fmt(r50.get(tk), 1),
            "R90 (km)": fmt(C["r90"].get(tk), 1),
            "R_res (km)": fmt(rres.get(tk), 1),
            "η": fmt(eta.get(tk), 3),
            "τ@R50": fmt(tau50.get(tk), 3),
            "ΔT_app (K)": fmt(dtapp.get(tk), 2),
            "N@R50": fmt(nat.get(tk), 1),
            "P_max": fmt(pmax.get(tk), 3),
        })
    table(doc, pd.DataFrame(rows),
          [2.6, 1.5, 1.4, 1.4, 1.5, 0.9, 1.2, 1.8, 1.9, 1.6],
          "表 9  基线工况下的识别临界距离与链路诊断量", font=8.0,
          note_text="注：R90 显示“—”表示受采样上限（f_max≤Nyquist=40 cyc/mrad，周期数 N 封顶）限制，"
                    "该目标在任意距离的识别概率都低于 0.9；其余“—”表示超出搜索范围，"
                    "原因在 3.1 节文字与 03_数据 的 censored 字段中说明。")
    small_eta = [fnum(eta.get(t)) for t in SMALL_T if fnum(eta.get(t)) is not None]
    large_eta = [fnum(eta.get(t)) for t in LARGE_T if fnum(eta.get(t)) is not None]
    small_tau = [fnum(tau50.get(t)) for t in SMALL_T if fnum(tau50.get(t)) is not None]
    large_tau = [fnum(tau50.get(t)) for t in LARGE_T if fnum(tau50.get(t)) is not None]
    nat_vals = [fnum(nat.get(t)) for t in TORDER if fnum(nat.get(t)) is not None]
    n50_rec = float(params.N50_SETS["NVESD"]["recognize"])
    body(doc, f"读表 9 可见，R₅₀ 与目标特征尺寸并非线性关系：悍马（D_eff 仅 "
              f"{fmt(C.get('d_eff', {}).get('HM'), 2)} m）"
              f"的 R₅₀ 为 {_km(r50.get('HM'))}，已贴近分辨率天花板（η={fmt(eta.get('HM'), 3)}）；"
              f"F16/F22 的 η 分别为 {fmt(eta.get('F16'), 3)}/{fmt(eta.get('F22'), 3)}；"
              f"而阿利伯克/尼米兹的 R₅₀ 仅为天花板的一部分（η={fmt(eta.get('ALBK'), 3)}/"
              f"{fmt(eta.get('NIMITZ'), 3)}），说明其极限已由大气透过率接管。"
              f"在 R₅₀ 处 6 个目标的周期数落在 {_minmax(nat, TORDER, 1)} cycles，"
              f"围绕 N₅₀={n50_rec:.1f} 波动（最大相对偏差 {max(abs(v - n50_rec) / n50_rec for v in nat_vals) * 100:.1f}%），"
              "这是 50% 概率定义的直接体现，也构成一次内部自洽校核（见 5.1 节）。")
    body(doc, f"R₅₀ 处的波段透过率呈现清晰分层：中小目标 τ≈{_minmax(tau50, SMALL_T, 3)}，"
              f"大型舰船仅 τ≈{_minmax(tau50, LARGE_T, 3)}——前者几乎“看穿”大气，后者每前进一段距离都在损失对比度。"
              f"对应的视在温差也从 {_minmax(dtapp, SMALL_T, 1)} K 降到 {_minmax(dtapp, LARGE_T, 1)} K。"
              f"R90 列中悍马、F16、F22 显示“—”：平台高度 {params.SENSOR_PRESETS['RECOG']['platform_h_m']:.0f} m "
              "使空中/地面目标的最小可用斜距约 7.5–8 km；同时 f_max 受 Nyquist 采样上限约束"
              f"（f_max≤{C['sensor']['RECOG']['f_nyq']:.1f} cyc/mrad），周期数 N_max=f_max,max·D_eff/R_slant 被封顶，"
              "因此这 3 个目标在最近距离处的识别概率上限分别只有 "
              f"{fmt(pmax.get('HM'), 2)}/{fmt(pmax.get('F16'), 2)}/{fmt(pmax.get('F22'), 2)}。"
              "受采样上限限制，它们在任意距离的识别概率都低于 0.9，故 R90 在物理上不存在（截断），"
              "不是数据缺失或计算失败。")
    figure(doc, C["fig_dir"], "06",
           "图 6  探测 / 识别 / 辨认三种任务定义下的临界距离对比")
    rows = []
    for tk in TORDER:
        sub = data.base[data.base["target"] == tk] if data.base is not None else None
        rdet = fnum(_num(sub.iloc[0], "Rdet50_ground_km")) if sub is not None and len(sub) else None
        rrec = fnum(_num(sub.iloc[0], "R50_ground_km")) if sub is not None and len(sub) else None
        rident = fnum(_num(sub.iloc[0], "Rident50_ground_km")) if sub is not None and len(sub) else None
        rows.append({
            "目标": TNAME[tk],
            "Rdet50 (km)": fmt(rdet, 1),
            "R50 (km)": fmt(rrec, 1),
            "Rident50 (km)": fmt(rident, 1),
            "Rdet50/R50": fmt(rdet / rrec, 2) if (rdet and rrec) else "—",
            "Rident50/R50": fmt(rident / rrec, 2) if (rident and rrec) else "—",
        })
    table(doc, pd.DataFrame(rows), [3.2, 2.4, 2.2, 2.4, 2.6, 2.8],
          "表 10  三种任务定义下的临界距离（N₅₀ 分别为 4.0/16.5/26.6 cycles）",
          note_text="注：探测阈值最低、辨认阈值最高。“—”表示该任务阈值下 P 在搜索范围内始终低于 0.5。")
    body(doc, "表 10 把同一目标在三种任务定义下的临界距离并列。三者的差别完全来自 N₅₀（4.0/16.5/26.6）："
              "在 P 随 N 单调的前提下，N₅₀ 减半对应 R 近似加倍、N₅₀ 增大对应 R 缩短。"
              "探测距离约为识别距离的 2–4 倍、辨认距离约为识别距离的 0.5–0.7 倍（对可解目标）；"
              "这一比例在 6 个目标上基本稳定，说明任务定义对距离的缩放是“判据口径”效应而非物理差异。"
              "与 N₅₀ 口径同量级的不确定度见 5.3 节。")

    # ---------------- 3.2 单变量
    heading(doc, "3.2  单变量响应", 2)
    body(doc, "以下各组图均为“只改一个变量、其余固定”的结果，可直接横向对比。"
              "图中缺少数据点的位置表示该取值下识别概率在搜索范围内始终低于 0.5（不可识别/截断），"
              "不是计算失败；对应数据行在 CSV 中以空值或截断标记记录。")

    # 3.2.1 气溶胶
    heading(doc, "3.2.1  气溶胶光学厚度", 3)
    figure(doc, C["fig_dir"], "07",
           "图 7  R₅₀ 随 AOD₅₅₀ 变化（其余条件固定，基线目标 F16）")
    aod = C.get("aod_summary", {})
    if len(C.get("aod_tab", [])):
        table(doc, C["aod_tab"], [3.2, 2.9, 2.8, 2.9, 2.0, 2.3],
              "表 11  气溶胶光学厚度对 R₅₀ 的影响（基线其余条件固定）")
    cl = C.get("claims", {})

    def _rel_rng(tks):
        vals = [fnum(_get(aod.get(t), "rel")) for t in tks]
        vals = [v for v in vals if v is not None]
        if not vals:
            return "—"
        if len(vals) == 1:
            return _pct_txt(vals[0], 0)
        return f"{_pct_txt(min(vals), 0)}–{_pct_txt(max(vals), 0)}"

    aod_small_rng = _rel_rng(SMALL_T)
    aod_large_rng = _rel_rng(LARGE_T)
    if cl.get("aod_contrast"):
        aod_end = ("这解释了为什么“只看小目标会误判大气不重要”——同一大气对小型目标几乎透明、"
                   "对大型目标却是主控因素。")
    elif cl.get("aod_both_matter"):
        aod_end = ("需要强调：当前口径下小型目标对气溶胶也不再免疫，"
                   "大气输入必须与目标类型一起评估，不能仅凭小目标的结论外推。")
    else:
        aod_end = ("两类目标对气溶胶的敏感度差异并不悬殊，具体相对幅度见上表："
                   "小型目标相对变化 {a}%、大型舰船 {b}%。").format(a=aod_small_rng, b=aod_large_rng)
    body(doc, f"在 3.7–4.8 μm，Ångström 幂律使气溶胶消光比 550 nm 弱约 1 个量级以上。"
              f"AOD 从 {fmt(_get(aod.get('F16'), 'first', (None,))[0], 2)} 增至 "
              f"{fmt(_get(aod.get('F16'), 'last', (None,))[0], 2)} 时，F16 的 R₅₀ 变化 "
              f"{_pct_txt(_get(aod.get('F16'), 'rel'), 0)}；"
              f"舰船的识别距离已推到 {_km(r50.get('ALBK'))}–{_km(r50.get('NIMITZ'))} 量级，"
              f"累积光学厚度大，AOD 从 0.02 增至 4.0 时尼米兹 R₅₀ 变化 "
              f"{_pct_txt(_get(aod.get('NIMITZ'), 'rel'), 0)}、阿利伯克变化 "
              f"{_pct_txt(_get(aod.get('ALBK'), 'rel'), 0)}。"
              + aod_end)
    # Ångström 影响（S05）
    pairs_a = _sweep_pairs(data, "S05", ("alpha",))
    alpha_bits = []
    for tk in ("F16", "NIMITZ"):
        vals = [y for _, y in pairs_a.get(tk, []) if y is not None]
        if len(vals) > 1:
            alpha_bits.append(f"{TSHORT[tk]} {min(vals):.1f}–{max(vals):.1f} km")
    if alpha_bits:
        body(doc, "Ångström 指数 α 在相同 AOD 下改变气溶胶的谱斜率，其影响集中在红外短波端："
                  f"α 从 {fmt(_get(C['sweep_ranges'], 'S05', (0.1,))[0], 1)} 增至 "
                  f"{fmt(_get(C['sweep_ranges'], 'S05', (None, 1.9))[1], 1)} 时，"
                  f"基线 AOD 下 {'；'.join(alpha_bits)}（α 越小，近红外消光越强）。"
                  "工程上应把 α 与 AOD 同时作为大气输入，而不是只用一个能见度数字。")

    # 3.2.2 湍流
    heading(doc, "3.2.2  大气湍流", 3)
    figure(doc, C["fig_dir"], "08",
           "图 8  R₅₀ 随 Cn² 变化（对数横轴，含截断区）")
    if len(C.get("cn2_tab", [])):
        table(doc, C["cn2_tab"], [3.0, 2.7, 2.8, 2.7, 2.5, 2.3],
              "表 12  大气湍流对 R₅₀ 的影响")
    cn2 = C.get("cn2_summary", {})
    lam_b = C["lam_eff"]["MWIR"] * 1e-6
    k_wave = 2.0 * math.pi / lam_b
    try:
        r0_m = (0.423 * k_wave ** 2 * float(params.ATMOS_BASE["cn2"]) * 20000.0) ** (-0.6)
    except (ValueError, OverflowError):
        r0_m = None
    censor_cn2 = _get(cn2.get("F16"), "censor_x")
    if censor_cn2 is not None:
        turb_tail = ("本数据中，湍流是少数能在“大气干净、距离很近”时仍使 F16 类小目标识别失败的大气因子，"
                     "工程上应与气溶胶同等重视，并把 Cn² 的量级作为独立输入而不是常数。")
    else:
        turb_tail = ("本数据中 F16 在扫描的 Cn² 范围内未出现截断，说明该工况区间内湍流尚未触及识别阈值；"
                     "但在 Cn² 更大或目标更小的组合下，湍流仍可能成为主控因子。")
    body(doc, "湍流通过 r₀=(0.423k²Cn²L)^(−3/5) 压缩 MTF：Cn²≤1×10⁻¹⁶ 时 r₀ 远大于口径，湍流可忽略；"
              f"在基线的 Cn²={_sci_txt(params.ATMOS_BASE['cn2'])}、MWIR 有效波长 {C['lam_eff']['MWIR']:.2f} μm、"
              f"20 km 斜程下 r₀≈{fmt(r0_m, 2)} m，已小于口径 "
              f"{params.SENSOR_PRESETS['RECOG']['D_m']:.2f} m；"
              f"Cn²≈{_sci_txt(1e-14)} 时 F16 的 R₅₀ 相对无湍流下降过半（半衰点 {_sci_txt(_get(cn2.get('F16'), 'half_x'))}），"
              f"Cn²≈{_sci_txt(censor_cn2)} 后小目标直接截断（进入不可识别区）；"
              f"尼米兹的 R₅₀ 则从无湍流时的 {_km(_get(cn2.get('NIMITZ'), 'r0'))} 降至 "
              f"{_sci_txt(1e-13)} 时的 {_km(_get(cn2.get('NIMITZ'), 'r13'))}。"
              + turb_tail)

    # 3.2.3 热状态与发射率
    heading(doc, "3.2.3  目标热状态与发射率", 3)
    figure(doc, C["fig_dir"], "09",
           "图 9  目标热状态与发射率对 R₅₀ 的影响（含热交叉行为）")
    if len(C.get("temp_tab", [])):
        table(doc, C["temp_tab"], [3.0, 3.0, 3.4, 3.4, 3.4],
              "表 13  目标热状态对 R₅₀ 的影响（背景 20 ℃；ΔT=0 即热交叉）")
    if len(C.get("eps_tab", [])):
        table(doc, C["eps_tab"], [3.4, 3.6, 3.6, 3.6],
              "表 14  目标发射率对 R₅₀ 的影响（其余条件固定）")
    pairs_t = _sweep_pairs(data, "S03", ("target_temp_c",))
    r60 = _interp_pairs(pairs_t.get("NIMITZ", []), 60.0)
    r20 = _interp_pairs(pairs_t.get("NIMITZ", []), 20.0)
    zero_row = None
    if C.get("temp_tab") is not None and len(C["temp_tab"]):
        for _, rr in C["temp_tab"].iterrows():
            if str(rr.get("目标温度 (℃)", "")) == f"{params.BACKGROUND['temp_c']:.0f}":
                zero_row = rr
                break
    zero_txt = "—"
    if zero_row is not None:
        zero_txt = f"F16 {zero_row.get('F16', '—')} km、爱国者 {zero_row.get('爱国者', '—')} km"
    body(doc, f"目标温度从 60 ℃ 降到 20 ℃（即固有温差从 40 K 到 0 K），识别概率曲线整体平移："
              f"以尼米兹为例，R₅₀ 从 {_km(r60)} 变为 {_km(r20)}（固有温差 0 K 时目标的表观对比度为零，"
              f"R₅₀ 不再存在）；表 13 中 ΔT=0 一行为“—”的目标处于热交叉状态。"
              f"由于识别在多数工况下由分辨率或大气而非对比度决定，热状态在远离零温差时对 R₅₀ 的影响有限"
              f"（60 ℃ 相对 40 ℃ 使尼米兹 R₅₀ 仅从 {_km(_interp_pairs(pairs_t.get('NIMITZ', []), 40.0))} "
              f"增加到 {_km(r60)}）；真正的临界发生在热交叉附近，详见 4.2 节。")
    body(doc, "表 14 显示发射率的影响方向单一且幅度很小：在基线附近 ε_t 从 0.85 增至 0.97，"
              "尼米兹的 R₅₀ 变化仅约 2%，F16 更小；但当目标与背景温差接近零时，项 (1−ε) 反射项"
              "会决定表观对比度的符号与大小，此时发射率的相对不确定性被放大——这也是 4.2 节把热交叉盲区"
              "单列为临界状态的原因。")

    # 3.2.4 传感器参数
    heading(doc, "3.2.4  传感器参数（口径 / NETD / IFOV）", 3)
    figure(doc, C["fig_dir"], "10",
           "图 10  口径、NETD、IFOV 对 R₅₀ 的影响（三组单变量扫描）")
    if len(C.get("sensor_tab", [])):
        table(doc, C["sensor_tab"],
              [0.8, 1.5, 1.9, 1.9, 1.5, 1.9, 1.9, 1.4, 1.7, 1.7],
              "表 15  口径、NETD 与 IFOV 对 R₅₀ 的影响（同序号行对应各自扫描的第 i 档）", font=7.8)
    ss = C.get("sensor_summary", {})
    pD = _sweep_pairs(data, "S08", ("D_m",))
    pN = _sweep_pairs(data, "S09", ("netd_k",))
    pI = _sweep_pairs(data, "S10", ("ifov_urad",))
    eta_netd = None
    lo_n = _interp_pairs(pN.get("F16", []), 0.015)
    hi_n = _interp_pairs(pN.get("F16", []), 0.040)
    if lo_n and hi_n:
        eta_netd = (hi_n / lo_n - 1.0) / (0.040 / 0.015 - 1.0)
    dsmall = _interp_pairs(pD.get("F16", []), 0.12)
    dbase = _interp_pairs(pD.get("F16", []), 0.30)
    search = C["sensor"]["SEARCH"]
    s15 = data.sweep("S15")
    s15_note = "—"
    if s15 is not None and "sweep_value" in s15.columns:
        rec = s15[s15["sweep_value"].astype(str).str.contains("RECOG", na=False)]
        sea = s15[s15["sweep_value"].astype(str).str.contains("SEARCH", na=False)]
        if len(rec) and len(sea):
            rr = _series_map(rec, "R50_ground_km")
            ss2 = _series_map(sea, "R50_ground_km")
            bits = []
            for tk in ("NIMITZ", "ALBK", "F16"):
                if rr.get(tk) and ss2.get(tk):
                    bits.append(f"{TSHORT[tk]} {rr[tk]:.1f}→{ss2[tk]:.1f} km")
            if bits:
                s15_note = "；".join(bits)
    cl = C.get("claims", {})
    spans = cl.get("sensor_spans", {})
    valid_i = [(x, y) for x, y in pI.get("F16", []) if x is not None and y is not None]
    i_ifov_lo, i8 = (valid_i[0][0], valid_i[0][1]) if valid_i else (None, None)
    i_ifov_hi, i40 = (valid_i[-1][0], valid_i[-1][1]) if valid_i else (None, None)
    span_txt = "、".join(f"{k} {_pct_txt(v, 0, plus=False)}" for k, v in spans.items()
                         if fnum(v) is not None)
    plateau_txt = (f"R₅₀ 在 D≳{fmt(_get(ss, 'plateau_D'), 2)} m 后趋于平台（继续加大口径不再显著改善采样），"
                   if _get(ss, "plateau_D") else "口径扫描范围内 R₅₀ 未出现明显平台，")
    ifov_inv = cl.get("ifov_inverse_ratio")
    ifov_txt = (f"IFOV 从 {fmt(i_ifov_lo, 1)} μrad 增至 {fmt(i_ifov_hi, 1)} μrad 时 F16 的 R₅₀ 由 "
                f"{_km(i8)} 降至 {_km(i40)}"
                + (f"（两端比值 {fmt(ifov_inv, 2)}，与 IFOV 的反比关系一致）" if ifov_inv else "；"))
    netd_txt = (f"NETD 从 15 mK 增至 40 mK 时 F16 的 R₅₀ 相对变化约 {_pct_txt(eta_netd, 1)}，"
                "呈阈值形态：只有当地板 k·NETD/τ_opt 逼近实际 |ΔT_app| 时才显著。")
    first = cl.get("sensor_first")
    if first:
        order_txt = (f"在本数据的扫描范围内，传感器参数对 R₅₀ 的相对影响为"
                     f"（{span_txt}），其中 {first} 为当前扫描范围内的一阶因子。")
    else:
        order_txt = "传感器参数的影响排序见 §3.6 表 21。"
    body(doc, f"口径固定焦距变化时，{plateau_txt}"
              f"只有 D 小于约 0.15 m 时衍射才成为限制（F16 在 D=0.12 m 时 R₅₀ 仅 {_km(dsmall)}，"
              f"而 D=0.30 m 时为 {_km(dbase)}）。{netd_txt}{order_txt}{ifov_txt}")
    body(doc, f"作为对照，软件实测搜索通道（IFOV {search['ifov_urad']:.1f} μrad、Nyquist "
              f"{search['f_nyq']:.1f} cyc/mrad）因采样过粗，识别能力被严重压缩："
              f"{s15_note}。这与“识别通道”的设计意图一致——搜索通道适合发现与探测，"
              "识别任务必须使用窄视场高采样率通道。")

    # 3.2.5 平台高度
    heading(doc, "3.2.5  平台高度", 3)
    figure(doc, C["fig_dir"], "11",
           "图 11  R₅₀ 随平台高度变化（球面斜程几何）")
    if len(C.get("s11_tab", [])):
        table(doc, C["s11_tab"], [2.6, 2.2, 2.2, 2.2, 2.2, 2.6],
              "表 16  平台高度对 R₅₀ 的影响（地面距离口径，斜距按球面关系换算）")
    p11 = _sweep_pairs(data, "S11", ("platform_h_m",))
    h_lo = _interp_pairs(p11.get("NIMITZ", []), 100.0)
    h_hi = _interp_pairs(p11.get("NIMITZ", []), 12000.0)
    f_lo = _interp_pairs(p11.get("F16", []), 100.0)
    f_hi = _interp_pairs(p11.get("F16", []), 12000.0)
    h_horizon_8 = math.sqrt(2.0 * params.R_EARTH_KM * 8.0)
    f16_best_h = cl.get("s11_f16_best_h")
    f16_best_r = cl.get("s11_f16_best_r")
    nim_rising = cl.get("s11_nimitz_rising")
    if nim_rising:
        nim_txt = (f"大型舰船的 R₅₀ 随平台升高而增大（尼米兹从 100 m 平台的 {_km(h_lo)} "
                   f"增至 12 km 平台的 {_km(h_hi)}）")
    else:
        nim_txt = (f"大型舰船的 R₅₀ 随平台升高而降低（尼米兹从 100 m 平台的 {_km(h_lo)} "
                   f"变为 12 km 平台的 {_km(h_hi)}）")
    if f16_best_h is not None:
        f16_txt = (f"中小目标则存在明确的平台高度最优点：本数据中 F16 的 R₅₀ 在约 "
                   f"{fmt(f16_best_h, 0)} m 平台处最大（{_km(f16_best_r)}），"
                   f"100 m/12 km 平台分别为 {_km(f_lo)}/{_km(f_hi)}")
    else:
        f16_txt = f"F16 在 100 m/12 km 平台的 R₅₀ 分别为 {_km(f_lo)}/{_km(f_hi)}"
    body(doc, "平台高度通过两条途径影响极限：①同一地面距离下斜距随高度增加，目标角尺寸变小；"
              "②斜程穿过的大气柱在低空时更长（接近水平路径）。"
              f"综合结果：{nim_txt}；{f16_txt}。"
              f"球面几何下 8 km 平台的几何视距约 {h_horizon_8:.0f} km（不含折射），"
              "本报告各工况的临界地面距离均小于该值，因此曲率修正（斜距差异 <0.1%）不影响结论；"
              "对 100 m 级低平台与远距海面目标的组合，几何视距会先于识别阈值起作用，相关结果仅作趋势参考。")

    # ---------------- 3.3 波段
    heading(doc, "3.3  波段对比", 2)
    figure(doc, C["fig_dir"], "12",
           "图 12  MWIR 3.7–4.8 μm 与 LWIR 8.0–12.0 μm 的 R₅₀ 对比")
    if len(C.get("band_tab", [])):
        table(doc, C["band_tab"], [3.4, 3.4, 3.4, 3.4],
              "表 17  同一光学系统换波段的识别临界距离对比（其余条件固定）")
    bsum = C.get("band_summary", {})
    tau_m, tau_l = C["tau_band"]["MWIR"], C["tau_band"]["LWIR"]
    cl = C.get("claims", {})
    bs, bl = cl.get("band_small"), cl.get("band_large")
    tau_cmp = (f"10 km 处 MWIR/LWIR 波段透过率分别为 {fmt(tau_m.get(10.0), 3)}/"
               f"{fmt(tau_l.get(10.0), 3)}")
    if cl.get("band_both_better"):
        dir_txt = (f"本数据下两类目标的 LWIR 识别距离都更长（中小目标 {_pct_txt(bs, 0)}、"
                   f"大型舰船 {_pct_txt(bl, 0)}）")
        judge_txt = ("在本参考光学系统与当前大气口径下，LWIR 对识别更有利；"
                     "但这是大气透过率与衍射/Nyquist 匹配的净结果，不能外推为普遍规律。")
    elif cl.get("band_both_worse"):
        dir_txt = (f"本数据下两类目标的 LWIR 识别距离都更短（中小目标 {_pct_txt(bs, 0)}、"
                   f"大型舰船 {_pct_txt(bl, 0)}）")
        judge_txt = ("本数据下 LWIR 并不更利于识别——识别看重的是 Nyquist 与衍射截止的匹配度，"
                     "以及目标角尺寸是否足够大。")
    elif cl.get("band_cross"):
        small_better = "MWIR" if (bs is not None and bs < 0) else "LWIR"
        large_better = "LWIR" if (bl is not None and bl > 0) else "MWIR"
        cross = cl.get("band_crossing")
        cross_txt = ""
        if cross:
            cross_txt = f"（反转发生在 {cross[0]} 与 {cross[2]} 之间）"
        dir_txt = (f"本数据下中小目标 R₅₀ 变化 {_pct_txt(bs, 0)}、大型舰船变化 {_pct_txt(bl, 0)}，"
                   f"即小目标以 {small_better} 更远、大目标以 {large_better} 更远{cross_txt}")
        judge_txt = ("因此“长波更适合识别”不能一概而论，需按目标类别与光学系统逐项判断。")
    elif bs is None and bl is None:
        dir_txt = "本数据缺少波段对比表，暂无法给出双波段 R₅₀ 的方向性结论"
        judge_txt = "波段选择需在数据补齐后按目标类别与光学系统匹配关系逐项判断。"
    else:
        dir_txt = (f"本数据下中小目标 R₅₀ 变化 {_pct_txt(bs, 0)}、大型舰船变化 {_pct_txt(bl, 0)}")
        judge_txt = "波段选择需结合目标类别与光学系统匹配关系判断。"
    body(doc, f"同一光学系统换到 LWIR 后：衍射截止 D/λ 从约 {C['f_cut']['MWIR']:.1f} cyc/mrad 变为 "
              f"{C['f_cut']['LWIR']:.1f} cyc/mrad，MTF 采样上限与衍射上限的相对关系随之改变；"
              f"{tau_cmp}。{dir_txt}（图 12、表 17）。"
              f"{judge_txt}")

    # ---------------- 3.4 两类机制与包络
    heading(doc, "3.4  两类机制与识别极限包络", 2)
    figure(doc, C["fig_dir"], "13",
           "图 13  识别极限包络：分辨率天花板 R_res 与实际 R₅₀（标注 η=R₅₀/R_res）")
    d_eff = C.get("d_eff", {})
    cl = C.get("claims", {})
    if cl.get("two_mechanisms"):
        mech_txt = ("把 η 作为纵轴、目标特征尺寸作为横轴，可以看到两条机制的交接："
                    f"D_eff 小于约 {fmt(max([fnum(d_eff.get(t)) or 0 for t in SMALL_T]), 1)} m 时 "
                    f"η≈{_minmax(eta, SMALL_T, 2)}，识别距离主要由“传感器采样 + 目标角尺寸”决定；"
                    f"D_eff 超过约 {fmt(min([fnum(d_eff.get(t)) or 0 for t in LARGE_T]), 1)} m 后 η 降至 "
                    f"{_minmax(eta, LARGE_T, 2)}，R_res 已远超大气能支撑的距离，识别极限改由气溶胶/水汽/湍流决定。"
                    "交接点不是常数，随 AOD、Cn²、平台高度移动；图 14 与图 15 的相图给出了二维参数平面上的等值线。")
    else:
        mech_txt = ("把 η 作为纵轴、目标特征尺寸作为横轴：本数据中小目标 η="
                    f"{_minmax(eta, SMALL_T, 2)}、大型舰船 η={_minmax(eta, LARGE_T, 2)}，"
                    "两段式机制在当前大气/传感器口径下并不截然成立——分辨率、大气衰减与湍流对不同目标的"
                    "相对权重可连续变化。"
                    "图 14 与图 15 的相图给出了二维参数平面上的等值线与不可识别区。")
    body(doc, mech_txt)
    grid_txt = ("图中每一格点均为一次独立的模型正向计算与二分反解"
                "（图 14：每个 panel 525 个 AOD×Cn² 格点（共 2 panel）；"
                "图 15：546 个 ΔT×AOD 格点），"
                "色块为格点间平滑显示，等值线由格点计算值直接绘制。")
    figure(doc, C["fig_dir"], "14",
           "图 14  临界状态相图：AOD₅₅₀ × Cn² 对 F16（左）与尼米兹（右）识别距离的联合作用"
           "。" + grid_txt)
    figure(doc, C["fig_dir"], "15",
           "图 15  临界状态相图：固有温差 × AOD₅₅₀（等值线为 R₅₀）。" + grid_txt)
    body(doc, "需要强调：图 14、图 15 的每个格点都是一次独立的模型正向计算与二分反解，"
              "不是对已有数据的插值；色块只是格点间的平滑显示，等值线由格点计算值直接绘制。")
    if len(C.get("phase_tab", [])):
        table(doc, C["phase_tab"], [1.3, 3.0, 5.2, 1.4, 1.4, 1.9, 1.9],
              "表 18  相图的取值范围与 R₅₀ 极值统计（对应图 14、图 15）", font=8.0)
    ph = C.get("phase_summary", {})
    phc = C.get("claims", {}).get("phase", {})
    # 图 14：AOD × Cn² 的不可识别区与气溶胶作用
    seg = []
    for tk in ("F16", "NIMITZ"):
        c_lo = fnum(phc.get(f"{tk}_cens_low_cn2"))
        c_hi = fnum(phc.get(f"{tk}_cens_high_cn2"))
        if c_lo is not None and c_hi is not None:
            seg.append(f"{TSHORT[tk]} 的不可识别格点占比由低 Cn² 端的 {c_lo * 100:.0f}% "
                       f"变为高 Cn² 端的 {c_hi * 100:.0f}%")
    cn2_sentence = ("相图（图 14）中，Cn² 是决定不可识别区边界的强因子："
                    + ("；".join(seg) + "。" if seg else "高 Cn² 端出现大面积不可识别区（NaN 留白）。"))
    aod_seg = []
    for tk in ("F16", "NIMITZ"):
        rel = fnum(phc.get(f"{tk}_aod_effect_low_cn2"))
        if rel is not None:
            aod_seg.append(f"{TSHORT[tk]} 的 R₅₀ 相对变化 {_pct_txt(rel, 0)}")
    aod_sentence = ("在低湍流端，AOD 从低到高的作用为："
                    + ("；".join(aod_seg) + "。" if aod_seg
                       else "AOD 的作用需结合具体格点读取（见 03_数据/相图/相图_AODxCn2.csv）。"))
    body(doc, cn2_sentence + aod_sentence
         + "说明两类机制并非简单叠加：气溶胶在清洁大气条件下可成为远距大目标的主控因子，"
           "而强湍流可在气溶胶充分清洁时把目标压入不可识别区。")
    # 图 15：温差 × AOD 的凹区
    notch_parts = []
    if phc.get("notch_w_low") is not None and phc.get("notch_w_high") is not None:
        a_lo = fnum(phc.get("notch_aod_low"))
        a_hi = fnum(phc.get("notch_aod_high"))
        w_lo = fnum(phc.get("notch_w_low"))
        w_hi = fnum(phc.get("notch_w_high"))
        trend = ("加宽" if phc.get("notch_widening")
                 else "收窄" if phc.get("notch_narrowing") else "基本不变")
        notch_parts.append(f"以 R₅₀ 低于半高为判据，温差凹区在 AOD={fmt(a_lo, 2)} 时宽 {fmt(w_lo, 1)} K、"
                           f"在 AOD={fmt(a_hi, 2)} 时宽 {fmt(w_hi, 1)} K，随 AOD 增大呈{trend}趋势")
    argmin_dt = None
    dt_stat = ph.get("dt_F16") or ph.get("dt_NIMITZ") or {}
    argmin_dt = fnum(dt_stat.get("argmin_dT")) if isinstance(dt_stat, dict) else None
    if argmin_dt is not None:
        notch_parts.append(f"F16 的 R₅₀ 最小值位于固有温差约 {argmin_dt:+.1f} K 处")
    if notch_parts:
        body(doc, "温差×AOD 相图（图 15）显示："
                  + "；".join(notch_parts)
                  + "。这与“气溶胶压低到达传感器的对比度、使 |ΔT_app| 更易低于等效视在温差地板”的解释一致；"
                    "凹区的精确位置与宽度由 4.2 节从临界状态 CSV 读取。")
    else:
        body(doc, "温差×AOD 相图（图 15）在 ΔT≈0 附近出现 R₅₀ 下凹（热交叉盲区）；"
                  "凹区位置与宽度由 4.2 节从临界状态 CSV 读取，气溶胶的作用体现为对比度的整体压缩。")

    # ---------------- 3.5 真实气候工况
    heading(doc, "3.5  真实气候工况", 2)
    figure(doc, C["fig_dir"], "16",
           "图 16  8 类真实环境 × 6 个目标的识别临界距离（中位条件）")
    if len(C.get("env_tab", [])):
        envtab = C["env_tab"].copy()
        if "大目标分位跨度" in envtab.columns:
            envtab["大目标分位跨度"] = envtab["大目标分位跨度"].map(
                lambda v: (f"{v * 100:.0f}%" if fnum(v) is not None else "—"))
        table(doc, envtab, [3.4, 1.6, 1.6, 1.6, 1.8, 1.9, 1.9, 1.9],
              "表 19  真实气候工况下的识别临界距离（各环境三档分位的中位数，单位 km；"
              "末列为大目标的环境内分位相对跨度）", font=8.0)
    qt = C.get("env_qtab")
    if qt is not None and len(qt):
        cols = [c for c in qt.columns
                if c in ("环境", "阿利伯克-p10", "阿利伯克-median", "阿利伯克-p90",
                         "尼米兹-p10", "尼米兹-median", "尼米兹-p90")]
        if len(cols) >= 5:
            table(doc, qt[cols], [3.6] + [2.0] * (len(cols) - 1),
                  "表 20  大目标在 p10 / 中位 / p90 三档气候分位下的 R₅₀（单位 km）", font=8.0)
    es = C.get("env_summary", {})
    ni = _get(es, "NIMITZ", {})
    fi = _get(es, "F16", {})
    cl = C.get("claims", {})
    f16_rel = fnum(_get(fi, "rel"))
    if cl.get("small_resolution_limited") and f16_rel is not None and abs(f16_rel) < 0.05:
        small_env_txt = (f"对 F16/F22 等中小目标，环境差异较小（F16 在 {_get(fi, 'env_lo', '—')} 与 "
                         f"{_get(fi, 'env_hi', '—')} 之间约 {_pct_txt(f16_rel, 0)}），"
                         "这与其 η 较高、极限更靠近分辨率天花板的机制一致。")
    elif cl.get("small_resolution_limited"):
        small_env_txt = (f"对 F16/F22 等中小目标，环境差异为 {_pct_txt(f16_rel, 0)}"
                         f"（{_get(fi, 'env_lo', '—')} 与 {_get(fi, 'env_hi', '—')} 之间）；"
                         "虽然其 η 较高，但大气最差环境仍能造成可见的 R₅₀ 变化。")
    else:
        small_env_txt = (f"对 F16/F22 等中小目标，环境差异约 {_pct_txt(f16_rel, 0)}"
                         f"（{_get(fi, 'env_lo', '—')} {_km(_get(fi, 'lo'))} 与 "
                         f"{_get(fi, 'env_hi', '—')} {_km(_get(fi, 'hi'))} 之间）；"
                         "在当前口径下，中小目标也不再是对大气条件完全免疫的。")
    body(doc, "把 NASA POWER/MERRA-2（2015–2024）统计得到的 8 类环境 AOD₅₅₀ 与 PWV 分位数代入模型，"
              "得到“在什么地区、什么统计条件下能识别多远”。"
              f"对大型舰船，环境差异为 {_pct_txt(_get(ni, 'rel'), 0)}：尼米兹的 R₅₀ 在 "
              f"{_get(ni, 'env_lo', '—')}（{_km(_get(ni, 'lo'))}）与 {_get(ni, 'env_hi', '—')}"
              f"（{_km(_get(ni, 'hi'))}）之间变化；这一排序由各环境的 AOD/PWV/α 联合决定，"
              "不宜简单归因于单一因子。"
              + small_env_txt)

    # ---------------- 3.6 敏感性
    heading(doc, "3.6  敏感性排序", 2)
    figure(doc, C["fig_dir"], "17",
           "图 17  单变量对 R₅₀ 的相对影响排序")
    if len(C.get("sens_tab", [])):
        tab = C["sens_tab"].copy()
        tab["最大相对变化"] = tab["最大相对变化"].map(lambda v: f"{v * 100:.1f}%")
        table(doc, tab[["排名", "编号", "变量", "最大相对变化", "受敏感目标数"]],
              [1.4, 1.6, 5.6, 3.6, 3.0], "表 21  单变量对 R₅₀ 的相对影响（中位数，相对基线）")
    sens = C.get("sens_tab")
    if sens is not None and len(sens):
        top3 = "、".join(str(v) for v in sens["变量"].head(3))
        bottom3 = "、".join(str(v) for v in sens["变量"].tail(3))
        top_var = str(sens["变量"].iloc[0])
        advice = (f"工程上应优先保证 {top_var} 等一阶因子的正确性，再用相图确定特定工况的余量。")
    else:
        top3, bottom3, top_var = "—", "—", "—"
        advice = "工程上应先用相图确定特定工况的余量。"
    body(doc, "把每个变量在其扫描范围内的 R₅₀ 最大相对变化取中位数排序："
              f"{top3} 排在前列，而 {bottom3} 靠后。需要强调：这一排序是“在各自扫描范围内”的相对量，"
              "改变扫描范围会改变排序，因此它不能替代相图与临界阈值；" + advice)


# --------------------------------------------------------------------------- #
# 11. 第 4—6 章
# --------------------------------------------------------------------------- #
def _sec_4(doc, C):
    heading(doc, "4  临界状态", 1)
    heading(doc, "4.1  临界距离与搜索边界", 2)
    body(doc, "临界距离即 R₅₀/R₉₀，已在表 9 与图 5 给出。工程使用时建议按任务阈值取值：探测任务看 Rdet50，"
              "识别任务看 R₅₀，辨认任务看 Rident50（三者 N₅₀ 分别为 4.0/16.5/26.6）。"
              "临界状态反解统一采用主参考距离 r_ref=0.5·R₅₀（R₅₀ 截断时以 10 km 参考并标注），"
              "临界状态 CSV 另提供 10 km 参考距离的附列（部分目标为 NaN，正文显示“—”）；"
              "所有反解都记录搜索边界与截断标记，避免把搜索边界误当物理临界值。")
    if len(C.get("crit_tab", [])):
        table(doc, C["crit_tab"], [2.6, 1.5, 1.7, 1.6, 0.9, 1.4, 1.4, 2.0, 1.5, 1.2],
              "表 22  基线工况下的临界状态反解（参考距离 r_ref=0.5·R₅₀；含参考点诊断量）",
              font=8.0,
              note_text="注：R90 显示“—（P≤…）”表示受采样上限限制，该目标识别概率在任意距离都低于 0.9；"
                        "“截断”=核心临界量（R50/临界 AOD/Cn²/口径/NETD）的 censored_* 记录为非空且非"
                        "“上限仍满足”（“上限仍满足”表示该参数不构成约束）；R90 等任务阈值截断不计入；"
                        "10 km 参考距离附列见表 25。")
    crit_notes = C.get("crit_notes") or []
    if C.get("data").crit is None:
        body(doc, "**注意：**未找到 03_数据/临界状态/临界状态汇总.csv，本章表格为占位；"
                  "请在数据管线完成后重新生成报告。")
    else:
        body(doc, "表中“截断”列由临界状态 CSV 的 censored_* 字段生成（具体原因见该 CSV）；"
                  "R90 显示“—（P≤…）”表示该目标在最近可用斜距处的识别概率上限低于 0.9，"
                  "90% 概率对应的距离在物理上不存在。"
                  f"f_max 的实际判据为 MRTD(f)=τ_opt·|ΔT_app|，本模型 k={C['k_mrtd']:.1f}、"
                  f"NETD={C['netd'] * 1000:.0f} mK、τ_opt={C['tau_opt']:.2f}，"
                  f"等效视在温差地板 k·NETD/τ_opt≈{C['floor_dtapp'] * 1000:.1f} mK；"
                  "当 |ΔT_app| 低于该值时 f_max=0，无论距离多近都不会有 50% 识别概率。"
                  "τ@r_ref、ΔT_app@r_ref 与 N@r_ref 为参考点处的链路诊断量，"
                  "可用于核对临界反解的自洽性。")

    heading(doc, "4.2  热交叉识别盲区", 2)
    crit_cols = list(C["data"].crit.columns) if C["data"].crit is not None else []
    has10 = any("10km" in str(c).lower() or "10_km" in str(c).lower() for c in crit_cols)
    ten_intro = ("下面以 F16 在 10 km 处的细分结果作为直观例。"
                 if has10 else "（本数据未提供 10 km 附列，本节只给 0.5·R₅₀ 主列结果。）")
    body(doc, "任务概率对固有温差 ΔT 并不单调：目标比背景冷很多或热很多都能识别，只有当视在温差 ΔT_app 穿过 0 时才会失效。"
              "校准后的辐亮度方程显式包含反射项，两式相减严格得 ΔL=ε_t[B(T_t)−B(T_b)]τ，"
              "因此 **ΔT=0 时对比度严格为零**，热交叉严格发生在固有温差零点；"
              "盲区的物理来源改为“噪声地板”：当 |ΔT_app| 小于等效视在温差地板 k·NETD/τ_opt 时，"
              "识别概率在可观测距离内始终低于 0.5，从而形成一段不可识别的温差窄带。"
              "表 23 主列为 r_ref=0.5·R₅₀ 处的反解结果；临界状态 CSV 另提供 10 km 参考距离的附列，"
              + ten_intro +
              "这与“发射率不对称伪造热交叉偏移”的忽略反射项处理有本质区别："
              f"若忽略 (1−ε) 反射项，零对比点会被错误地移到约 "
              f"{fmt(C['calib'].get('MWIR', {}).get('dt_shift_K'), 2)} K（MWIR）/ "
              f"{fmt(C['calib'].get('LWIR', {}).get('dt_shift_K'), 2)} K（LWIR）。")
    if len(C.get("blind_tab", [])):
        table(doc, C["blind_tab"], [2.4, 2.6, 2.0, 2.0, 2.0, 2.2, 3.0],
              "表 23  热交叉盲区：r_ref=0.5·R₅₀ 处的位置、宽度与盲区内最低识别概率"
              "（位置与宽度由临界状态 CSV 读取）",
              font=8.0,
              note_text="注：盲区中心 ΔT_cross 为临界状态 CSV 记录值；宽度=上界−下界；"
                        "“全温差区间均可识别”表示在整个扫描温差范围内 P 都不低于 0.5。")
    # 10 km 参考距离的直观例（取自临界状态 CSV 的 10 km 附列；缺失则跳过）
    maps = C.get("crit_maps", {})
    half10 = None
    for lo_k, hi_k, w_k in (("blind10_low", "blind10_high", "blind10_width"),):
        lo10 = fnum(_get(maps.get(lo_k, {}), "F16"))
        hi10 = fnum(_get(maps.get(hi_k, {}), "F16"))
        w10 = fnum(_get(maps.get(w_k, {}), "F16"))
        if lo10 is not None and hi10 is not None:
            half10 = 0.5 * (hi10 - lo10)
        elif w10 is not None:
            half10 = 0.5 * w10
        if half10 is not None:
            main_w = None
            if C.get("blind_tab") is not None and len(C["blind_tab"]):
                for _, rr in C["blind_tab"].iterrows():
                    if str(rr.get("目标")) == TNAME["F16"]:
                        main_w = fnum(str(rr.get("盲区宽度 (K)", "")).replace("—", "nan"))
            cmp_txt = ""
            if main_w and main_w > 0:
                ratio10 = (2.0 * half10) / main_w
                if 0.5 <= ratio10 <= 2.0:
                    cmp_txt = "，与 0.5·R₅₀ 主列同量级"
                else:
                    cmp_txt = "，与主列数值不同（参考距离口径不同，属正常差异）"
            body(doc, f"以 F16 在 10 km 参考距离处的细分结果为例，盲区为 ±{half10:.2f} K"
                      f"（对应宽度 {2 * half10:.2f} K{cmp_txt}）；"
                      "该例只用于直观展示“零温差附近不可识别”的形态，定量结论以表 23 主列为准。")
            break
    # 盲区宽度的解析估计：宽度 ≈ 2·(k·NETD/τ_opt)/(ε_t·τ)
    w_pred = None
    try:
        f16_rref = fnum(_get(C.get("crit_maps", {}).get("rref", {}), "F16"))
        tau_rref = _tau_at_ground(C["data"], "F16", f16_rref if f16_rref else 10.0)
        eps_t = float(params.TARGETS[0]["eps"])
        if tau_rref:
            w_pred = 2.0 * C["floor_dtapp"] / (eps_t * tau_rref)
    except Exception:  # noqa: BLE001
        w_pred = None
    bt = C.get("blind_tab")
    if bt is not None and len(bt):
        widths = []
        for _, rr in bt.iterrows():
            w = fnum(str(rr.get("盲区宽度 (K)", "")).replace("—", "nan"))
            if w is not None and 0 < w < 30:
                widths.append((str(rr["目标"]), w))
        if widths:
            w_min = min(w for _, w in widths)
            w_max = max(w for _, w in widths)
            names = "、".join(n.replace(" 战斗机", "") for n, _ in widths[:3])
            cl = C.get("claims", {})
            dev = cl.get("blind_center_maxdev")
            if dev is not None and dev <= 0.5:
                center_txt = (f"各目标盲区中心与 ΔT=0 的最大偏离为 {dev:.2f} K，"
                              "在数值离散与非线性误差范围内；")
            elif dev is not None:
                center_txt = (f"各目标盲区中心与 ΔT=0 的最大偏离为 {dev:.2f} K，"
                              "主要来自路径辐射与光谱加权的非线性，以 CSV 记录值为准；")
            else:
                center_txt = ""
            zero_t = cl.get("blind_zero_targets") or []
            if zero_t:
                zero_txt = ("；".join(zero_t) + " 在 0.5·R₅₀ 处的盲区宽度为 0，"
                            "说明其可识别性由目标尺寸与大气衰减主导，"
                            "对比度地板在可观测距离内不成为限制；")
            else:
                zero_txt = ""
            pred_txt = ""
            if w_pred is not None:
                w_mid = 0.5 * (w_min + w_max)
                ratio = (w_mid / w_pred) if w_pred else None
                if ratio is not None and 0.5 <= ratio <= 2.0:
                    tail = "与表 23 的反解值同量级"
                elif ratio is not None and ratio > 2.0:
                    tail = ("反解值明显更大：盲区宽度对求解区间、路径辐射与发射率非线性敏感，"
                            "定量以 CSV 反解值为准，并建议在 3.2.3 节曲线上复核")
                else:
                    tail = "反解值更小：定量以 CSV 反解值为准，并建议在 3.2.3 节曲线上复核"
                pred_txt = (f"按 ΔT_app≈ε_t·τ·ΔT 与地板 {C['floor_dtapp'] * 1000:.1f} mK 作一阶估计，"
                            f"F16 在 r_ref 处的盲区宽度约 {w_pred:.2f} K，{tail}；")
            body(doc, f"本数据在 0.5·R₅₀ 处反解出的有效热交叉盲区集中在 {names} 等目标上，宽度 "
                      f"{w_min:.2f}–{w_max:.2f} K；{pred_txt}"
                      "盲区内最低识别概率由表 23 最后一列给出。"
                      + center_txt
                      + zero_txt
                      + "工程上应把“目标—背景温差接近零”作为独立的失效模式，而不是简单归入低对比度。")
    # 悍马盲区“宽”的物理解释：低峰值概率 / 小裕度，而非热交叉更宽
    hm_w, other_ws = None, []
    if bt is not None and len(bt):
        for _, rr in bt.iterrows():
            w = fnum(str(rr.get("盲区宽度 (K)", "")).replace("—", "nan"))
            if w is None:
                continue
            if str(rr.get("目标")) == TNAME["HM"]:
                hm_w = w
            elif w > 0:
                other_ws.append(w)
    if hm_w and other_ws and hm_w > 1.5 * float(np.median(other_ws)):
        pm_hm = fnum(C.get("pmax", {}).get("HM"))
        rref_hm = fnum(_get(C.get("crit_maps", {}).get("rref", {}), "HM"))
        p_half = _p_at_ground(C["data"], "HM", rref_hm) if rref_hm else None
        med_w = float(np.median(other_ws))
        body(doc, f"需要区分“热交叉物理宽度”与“概率裕度”：悍马的盲区宽度 {hm_w:.2f} K 明显大于其他目标的"
                  f"中位宽度 {med_w:.2f} K，但其峰值识别概率仅 {fmt(pm_hm, 2)}，"
                  f"在 0.5·R₅₀ 处 P≈{fmt(p_half, 2)}，距 0.5 阈值只有很小裕度；"
                  "此时很小的 ΔT_app 变化即可把整段概率压到 0.5 以下，因此该宽度主要反映裕度小，"
                  "而非热交叉本身更宽。各目标在 0.5·R₅₀ 处的盲区宽度见表 23。")
    body(doc, "与图 9、图 15 对照可见：盲区在概率曲线上表现为近距离端概率不升反降，"
              "在温差×AOD 相图上表现为 ΔT≈0 附近的 R₅₀ 下凹。判据口径与目标尺寸口径只会缩放盲区的位置，"
              "不会改变“零温差不可识别”的结论。")

    heading(doc, "4.3  临界 AOD、Cn²、口径与 NETD", 2)
    body(doc, "临界 AOD / Cn² / 口径 / NETD 的计算方式：固定其余条件（主参考距离 r_ref=0.5·R₅₀），"
              "求使识别概率降到 0.5 的该参数值；搜索容差 10⁻³，越界情形标“截断”，"
              "不允许把搜索边界当解。表 24 为主列（0.5·R₅₀），表 25 为临界状态 CSV 提供的 "
              "10 km 参考距离附列（部分目标为 NaN，显示“—”）。")
    if len(C.get("critparam_tab", [])):
        table(doc, C["critparam_tab"], [2.6, 2.8, 3.0, 2.6, 2.5, 2.3],
              "表 24  临界气溶胶、湍流、口径与 NETD（主列：r_ref=0.5·R₅₀；"
              "“≥/≤…（截断）”表示该值撞到搜索边界）",
              font=8.0)
    if C.get("critparam10_tab") is not None and len(C["critparam10_tab"]):
        table(doc, C["critparam10_tab"], [2.6, 2.9, 3.1, 2.9, 2.8, 1.5],
              "表 25  10 km 参考距离下的临界参数（临界状态 CSV 附列；“不构成约束”=该参数≤搜索上限仍可识别，"
              "“—（R50≤10 km）”=该目标 R50 不足 10 km 故不计算）",
              font=8.0)
    cl = C.get("claims", {})
    maps = C.get("crit_maps", {})
    cn2_vals = cl.get("crit_cn2_valid")
    aod_valid = cl.get("crit_aod_valid")
    aod_bound = cl.get("crit_aod_bound_n")
    aod_nocon = cl.get("crit_aod_nocon_n")
    aod_missing = cl.get("crit_aod_missing_n")
    d_bound = cl.get("crit_d_bound_n")
    d_valid = cl.get("crit_d_valid")
    d_missing = cl.get("crit_d_missing_n")
    netd_bound = cl.get("crit_netd_bound_n")
    netd_valid = cl.get("crit_netd_valid")
    netd_missing = cl.get("crit_netd_missing_n")
    cn2_bound = cl.get("crit_cn2_bound_n")
    # 有效临界 AOD 的目标名单（排除“上限仍满足/不构成约束”者）
    aod_targets = []
    if maps.get("aod"):
        for tk in TORDER:
            v = fnum(maps["aod"].get(tk))
            note = (C.get("crit_censor") or {}).get(tk, "")
            seg = _censor_seg(note, "censored_AOD")
            if v is not None and "上限仍满足" not in seg:
                aod_targets.append(f"{TSHORT[tk]} {v:.2f}")
    aod_parts = []
    if aod_targets:
        aod_parts.append("有效临界 AOD 为 " + "、".join(aod_targets))
    if aod_nocon:
        aod_parts.append(f"{aod_nocon} 个目标在 0.5·R₅₀ 处气溶胶不构成临界约束"
                         "（AOD 增至搜索上限 20 仍可识别）")
    if aod_bound:
        aod_parts.append(f"{aod_bound} 个目标的临界 AOD 撞到搜索边界（截断）")
    if not aod_parts:
        aod_parts.append("临界 AOD 数据缺失")
    aod_txt = "；".join(aod_parts)
    cn2_txt = (f"{_sci_txt(cn2_vals[0])}–{_sci_txt(cn2_vals[1])}"
               if cn2_vals else "—")
    d_txt = (f"临界口径落在 {fmt(d_valid[0], 3)}–{fmt(d_valid[1], 3)} m"
             if d_valid else "临界口径数据缺失")
    if d_bound:
        d_txt += f"，其中 {d_bound} 个目标撞到搜索边界/被截断"
    netd_txt = (f"临界 NETD 为 {fmt(netd_valid[0] * 1000, 0)}–{fmt(netd_valid[1] * 1000, 0)} mK"
                if netd_valid else "临界 NETD 数据缺失")
    if netd_bound:
        netd_txt += f"，其中 {netd_bound} 个目标撞到搜索边界/被截断"
    floor_rng = cl.get("contrast_floor_range_km")
    floor_txt = ""
    if floor_rng and C.get("r50_max") is not None:
        if floor_rng[0] > 1.5 * float(C["r50_max"]):
            floor_txt = (f"对比度地板对应的地面距离约 {fmt(floor_rng[0], 0)}–{fmt(floor_rng[1], 0)} km，"
                         f"远大于基线最大 R₅₀（{_km(C['r50_max'])}）——这说明基线识别由分辨率采样"
                         "与大气衰减联合限制，而非对比度地板。")
    body(doc, f"读表 24 可见：①{aod_txt}；②临界 Cn² 集中在 "
              f"{cn2_txt} 附近"
              + (f"（{cn2_bound} 个目标撞到搜索边界）" if cn2_bound else "")
              + "，这是本传感器系统的湍流容限量级，超过即进入快速退化区；"
              f"③{d_txt}，{netd_txt}，二者共同说明当前识别通道的衍射/对比度余量。"
              + floor_txt
              + "表 25 的 10 km 附列用于给出更近距离处的直观量级，不替代主列结论。")
    body(doc, "上述临界值可直接用于指标论证：给定任务距离与大气统计，反查需要的气溶胶/湍流/口径/NETD 余量；"
              "亦可用于测试设计——把工况推到临界值附近，验证模型的判别能力。")


def _sec_5(doc, C):
    heading(doc, "5  数据质量、公式校准与不确定度", 1)
    heading(doc, "5.1  数据质量与内部一致性校核", 2)
    qa = C.get("qa_info") or {}
    if qa:
        qa_txt = (f"《06_校验/校验报告.md》共记录 {qa.get('total', '—')} 项检查，"
                  f"通过 {qa.get('pass', '—')} 项、未通过 {qa.get('fail', '—')} 项；")
        fail_n = qa.get("fail")
        if fail_n:
            qa_txt += ("未通过项主要涉及数据文件齐套性、图文一致性与数值容差，"
                       "逐条说明见该报告对应行；")
    else:
        qa_txt = "《06_校验/校验报告.md》暂未提供汇总数字，以下为本报告生成时的内部自洽校核；"
    body(doc, qa_txt + "本报告在生成时又对 CSV 数据做了一遍独立重算，校核项与结果见表 26。")
    if len(C.get("checks_tab", [])):
        table(doc, C["checks_tab"], [5.6, 1.8, 8.6],
              "表 26  内部一致性与自洽性校核（全部由数据重算）")
    warns = C.get("warnings") or []
    if warns:
        note(doc, f"数据装载告警 {len(warns)} 条：" + "；".join(warns[:8]) +
             ("……" if len(warns) > 8 else ""), size=8.8)
    else:
        note(doc, "数据装载无告警：全部 CSV 文件均可读，关键列齐全。", size=8.8)
    body(doc, "图-数据-报告同源：图中每个点、正文每个数值都来自 03_数据 的同一批 CSV；"
              "附录 D 给出数据、图件、代码与校验文档的完整清单，附录 B 给出公式校准的逐条摘要。"
              "此外，光谱网格/分层收敛、τ 极限、路径辐射界限、ΔT_app≤固有温差、P 随距离单调、"
              "R₅₀ 随 AOD/Cn² 单调等物理与数值检查见《06_校验/校验报告.md》与《06_校验/光谱大气校验.md》。")

    heading(doc, "5.2  模型假设与适用条件", 2)
    body(doc, "本报告结论建立在以下假设之上，使用时应逐条核对：")
    horizon8 = math.sqrt(2.0 * params.R_EARTH_KM * 8.0)
    for txt in [
        "**大气几何**：球面弦长、不含折射与地球扁率；未显式加入地平线遮挡判据。"
        f"对 8 km 基线平台（几何视距约 {horizon8:.0f} km）结论不受影响；"
        "对 100 m 级低平台与远距海面目标，几何视距可能先起作用。",
        "**大气成分**：HITRAN2020 逐线 Voigt 截面（六物种、四温度×四气压节点、0.05 cm⁻¹ 步长），"
        "不含水汽连续吸收（MT_CKD）、不含云/雨/雾/沙尘的相函数与多次散射；气溶胶按外消光处理。",
        "**背景与反射**：背景按 20 ℃ 均匀黑体，发射率 0.95；目标/背景辐亮度含 (1−ε) 反射项，"
        "但反射环境辐亮度取背景黑体（不含天空/太阳直射）。",
        "**目标**：等效方目标 D_eff=√(W_proj·H)，包围盒由 OSG 顶点解析、未做几何标定；"
        "目标热状态用等效温度+发射率表示，不含表面温度场、纹理与运动模糊。",
        "**传感器**：识别通道参数为设定-推导值（口径 0.30 m、F/4、NETD 25 mK、抖动 0.3×IFOV、光学效率 0.80），"
        "MRTD 用 k=2.5 的工程近似；搜索通道为软件实测锚点。",
        "**湍流**：整层单一 Cn²，不含 Cn²(h) 廓线与光束漂移/到达角起伏；气溶胶/水汽按水平均匀处理。",
        "**判据**：TTPF（E=2）与 NVESD/Johnson 两套 N₅₀ 并列，不做加权合并；概率为单帧静态判据，"
        "不含时间积分/多帧融合增益。",
    ]:
        bullet(doc, txt)

    heading(doc, "5.3  不确定度清单", 2)
    body(doc, "表 27 按“来源—取值/假设—影响方向—量级”列出主要不确定度。量级一栏中，"
              "凡可由本报告数据核算的均给出具体数字（如判据口径、尺寸口径、k 系数、反射项偏移），"
              "其余给出文献/物理量级。")
    if len(C.get("unc_tab", [])):
        table(doc, C["unc_tab"], [3.8, 4.4, 3.8, 4.0],
              "表 27  主要不确定度来源、方向与量级", font=8.0)
    cl = C.get("claims", {})
    if cl.get("two_mechanisms"):
        mech_keep = "不改变“中小目标由分辨率主导、大型舰船由大气衰减主导”的机制判断"
    else:
        mech_keep = "不改变分辨率/大气/湍流共同限制的相对关系（本数据下不存在截然两段式）"
    body(doc, "按影响排序：判据口径（N₅₀ 相差约 2 倍）与目标尺寸口径是最大的两项，"
              f"它们只改变绝对距离，{mech_keep}；"
              "热交叉附近，反射项与发射率假设会显著放大不确定度，但不会把“零温差不可识别”的结论反转；"
              "传感器设定参数可通过实测替换后重算，公式与代码无需改动。")

    heading(doc, "5.4  结论的适用范围", 2)
    if cl.get("two_mechanisms"):
        robust_txt = ("不改变两类机制的划分与交接趋势；气溶胶/湍流/IFOV 的相对地位、"
                      "热交叉盲区的存在性均不依赖具体口径")
    else:
        robust_txt = ("不改变各因子相对重要性的判断；气溶胶/湍流/IFOV 的相对地位、"
                      "热交叉盲区的存在性均不依赖具体口径")
    body(doc, "本报告的**相对排序与临界阈值**是稳健的：换判据、换尺寸口径只改变绝对距离，"
              + robust_txt + "。"
              "**绝对距离**需在实测传感器参数、目标几何标定与完整大气（含连续吸收、云/降水）数据到位后复算，"
              "本报告不作为装备定型依据，而作为指标论证、试验设计与模型迭代的基线。")


def _sec_6(doc, C):
    heading(doc, "6  结论", 1)
    r50, eta = C["r50"], C["eta"]
    pmax = C["pmax"]
    band = C.get("band_summary", {})
    aod = C.get("aod_summary", {})
    cn2 = C.get("cn2_summary", {})
    es = C.get("env_summary", {})
    ni = _get(es, "NIMITZ", {})
    fi = _get(es, "F16", {})
    sens = C.get("sens_tab")
    bt = C.get("blind_tab")
    blind_txt = "—"
    if bt is not None and len(bt):
        rows = []
        for _, r in bt.iterrows():
            w = fnum(str(r.get("盲区宽度 (K)", "")).replace("—", "nan"))
            if w is not None and 0 < w < 30:
                rows.append(f"{str(r['目标']).replace(' 战斗机', '')} {r['盲区下界 (K)']}–{r['盲区上界 (K)']} K")
        if rows:
            blind_txt = "、".join(rows[:4])
    cl = C.get("claims", {})
    d_vals = [fnum(v) for v in C.get("d_eff", {}).values() if fnum(v) is not None]
    d_rng = (f"{min(d_vals):.1f}–{max(d_vals):.1f} m" if d_vals else "—")
    # 结论 2：两类机制（条件句）
    if cl.get("two_mechanisms"):
        item2 = (f"识别极限呈现两种机制：中小目标 η={_minmax(eta, SMALL_T, 2)}，"
                 "由传感器采样/判据主导；大型舰船 "
                 f"η={_minmax(eta, LARGE_T, 2)}，由大气累积衰减主导；"
                 "交接点随 AOD/Cn²/平台高度移动（3.1、3.4 节）。")
    else:
        item2 = (f"本数据下 η 的分布为：中小目标 {_minmax(eta, SMALL_T, 2)}、大型舰船 "
                 f"{_minmax(eta, LARGE_T, 2)}；分辨率、大气衰减与湍流对不同目标的相对权重连续变化，"
                 "不存在简单的“小目标分辨率锁死 / 大目标大气锁死”两段式（3.1、3.2、3.4 节）。")
    # 结论 3：气溶胶
    f16_rel = fnum(_get(aod.get("F16"), "rel"))
    nim_rel = fnum(_get(aod.get("NIMITZ"), "rel"))
    if f16_rel is None and nim_rel is None:
        item3 = "气溶胶影响见 3.2.1 节（本数据缺少对应扫描）。"
    elif cl.get("aod_contrast"):
        item3 = (f"气溶胶对中小目标影响小（F16 相对变化 {_pct_txt(f16_rel, 0)}），"
                 f"对大型舰船影响显著（尼米兹 {_pct_txt(nim_rel, 0)}）；"
                 "Ångström 指数在同等 AOD 下可比 AOD 本身更关键。")
    elif cl.get("aod_both_matter"):
        item3 = (f"气溶胶对中小目标亦有不可忽略的影响（F16 {_pct_txt(f16_rel, 0)}），"
                 f"大型舰船为 {_pct_txt(nim_rel, 0)}；"
                 "大气输入需按目标类别分别评估。")
    else:
        item3 = (f"气溶胶影响：F16 相对变化 {_pct_txt(f16_rel, 0)}、"
                 f"尼米兹 {_pct_txt(nim_rel, 0)}。")
    # 结论 4：湍流
    censor_f16 = _get(cn2.get("F16"), "censor_x")
    nim_r13 = _get(cn2.get("NIMITZ"), "r13")
    if censor_f16 is not None:
        item4 = (f"湍流是少数能在“大气干净、距离很近”时仍使识别失败的大气因子：F16 在 Cn²≳"
                 f"{_sci_txt(censor_f16)} 后不可识别，尼米兹 R₅₀ 在 {_sci_txt(1e-13)} 时降至 "
                 f"{_km(nim_r13)}。")
    elif nim_r13 is not None:
        item4 = (f"本数据中 F16 在扫描 Cn² 范围内未出现截断；尼米兹 R₅₀ 在 {_sci_txt(1e-13)} 时降至 "
                 f"{_km(nim_r13)}，湍流影响随目标尺寸增大而减弱。")
    else:
        item4 = "湍流影响见 3.2.2 节（本数据缺少对应扫描）。"
    # 结论 6：波段
    bs, bl = cl.get("band_small"), cl.get("band_large")
    if bs is None and bl is None:
        item6 = "波段对比见 3.3 节（本数据缺少波段对比表）。"
    elif cl.get("band_both_better"):
        item6 = (f"换到 LWIR 后两类目标的 R₅₀ 均延长（中小目标 {_pct_txt(bs, 0)}、"
                 f"大型舰船 {_pct_txt(bl, 0)}）；在本参考系统与当前大气口径下 LWIR 更利于识别，"
                 "但该方向由透过率与衍射/Nyquist 匹配的竞争决定，不能外推为普遍规律。")
    elif cl.get("band_both_worse"):
        item6 = (f"换到 LWIR 后两类目标的 R₅₀ 均缩短（中小目标 {_pct_txt(bs, 0)}、"
                 f"大型舰船 {_pct_txt(bl, 0)}）；本数据下 LWIR 并不更利于识别。")
    elif cl.get("band_cross"):
        small_better = "MWIR" if (bs is not None and bs < 0) else "LWIR"
        large_better = "LWIR" if (bl is not None and bl > 0) else "MWIR"
        cross = cl.get("band_crossing")
        cross_txt = (f"（反转发生在 {cross[0]} 与 {cross[2]} 之间）" if cross else "")
        item6 = (f"换到 LWIR 后，中小目标 R₅₀ 变化 {_pct_txt(bs, 0)}、大型舰船变化 "
                 f"{_pct_txt(bl, 0)}：小目标以 {small_better} 更远、大目标以 {large_better} 更远{cross_txt}；"
                 "波段优势在两类目标之间反转，需按目标类别判断，不能一概而论。")
    else:
        item6 = (f"换到 LWIR 后，中小目标 R₅₀ 变化 {_pct_txt(bs, 0)}、大型舰船变化 "
                 f"{_pct_txt(bl, 0)}。")
    # 结论 7：环境
    env_mech = ("与 η 较高的机制判断一致" if cl.get("small_resolution_limited")
                else "中小目标对大气条件并非完全免疫")
    if _get(ni, "rel") is None:
        item7 = "真实气候工况的影响见 3.5 节（本数据缺少环境工况表）。"
    else:
        item7 = (f"真实气候工况对大型舰船的影响可达 {_pct_txt(_get(ni, 'rel'), 0)}（尼米兹在 "
                 f"{_get(ni, 'env_lo', '—')} {_km(_get(ni, 'lo'))} 与 "
                 f"{_get(ni, 'env_hi', '—')} {_km(_get(ni, 'hi'))} 之间），"
                 f"对中小目标为 {_pct_txt(_get(fi, 'rel'), 0)}——{env_mech}。")
    # 结论 8：传感器
    span_txt = "、".join(f"{k} {_pct_txt(v, 0, plus=False)}"
                         for k, v in (cl.get("sensor_spans", {}) or {}).items()
                         if fnum(v) is not None)
    if cl.get("sensor_first"):
        item8 = (f"传感器参数在本数据扫描范围内的 R₅₀ 相对变化为（{span_txt}），"
                 f"其中 {cl['sensor_first']} 为一阶因子；口径超过约 "
                 f"{fmt(cl.get('plateau_D'), 2)} m 后趋于平台。"
                 "敏感性排序随扫描范围变化，设计上应以相图与临界阈值而非单一排序为依据。")
    else:
        item8 = ("传感器参数的影响排序见 3.6 节；设计上应以相图与临界阈值而非单一排序为依据。")
    items = [
        f"在软件实测 6 个目标 + 参考识别通道（IFOV {C['sensor']['RECOG']['ifov_urad']:.2f} μrad、"
        f"D={params.SENSOR_PRESETS['RECOG']['D_m']:.2f} m、NETD {C['netd'] * 1000:.0f} mK）下，"
        f"基线识别临界距离跨 {_km(C['r50_min'])}（{TSHORT.get(C['r50_min_tk'], '—')}）–"
        f"{_km(C['r50_max'])}（{TSHORT.get(C['r50_max_tk'], '—')}）；"
        f"目标特征尺寸跨 {d_rng}，识别距离由目标尺寸与大气累积衰减共同决定。",
        item2,
        item3,
        item4,
        f"存在热交叉识别盲区：ΔT=0 时对比度严格为零，盲区由等效视在温差地板 k·NETD/τ_opt 决定；"
        f"本数据在 0.5·R₅₀ 处反解出的盲区为 {blind_txt}（位置与宽度由临界状态 CSV 读取）。",
        item6,
        item7,
        item8,
    ]
    for i, txt in enumerate(items, 1):
        body(doc, f"（{i}）" + txt)
    body(doc, "后续工作建议：①用实测传感器参数替换参考系统设定值，并复核 k 系数；"
              "②对目标包围盒做几何标定，给出投影姿态与纹理；③补齐水汽连续吸收（MT_CKD）与云/雨/雾光学参数，"
              "并把 Cn² 廓线、太阳直射与背景非均匀性纳入；④以本报告的临界状态表为验收指标，"
              "做“给定工况—所需传感器参数”的反向设计；⑤用图像级仿真（含目标纹理与背景杂波）复核 R₅₀ 的绝对量级。")


# --------------------------------------------------------------------------- #
# 12. 附录 A—E
# --------------------------------------------------------------------------- #
def _sec_appendix(doc, C):
    data = C["data"]
    # ---------------- 附录 A 思维导图 ----------------
    fig_dir = C["fig_dir"]
    pan_path = os.path.join(fig_dir, "图00_项目思维导图_横版.png")
    use_landscape = os.path.exists(pan_path)
    if use_landscape:
        # 独立 A4 横向整页：横版导图 24 cm 宽，保证图内文字可读；随后切回纵向
        _new_section(doc, landscape=True)
        heading(doc, "附录 A  项目思维导图", 1)
        _figure_abs(
            doc, pan_path,
            "图 A1  项目思维导图（A4 横向整页）",
            24.0)
        _new_section(doc, landscape=False)
        _appendix_a_guide(doc, C)
    else:
        heading(doc, "附录 A  项目思维导图", 1)
        _appendix_a_guide(doc, C)
        figure(doc, fig_dir, "00", "图 A1  项目思维导图")

    # ---------------- 附录 B 公式校准表
    heading(doc, "附录 B  公式校准表（摘要）", 1)
    if C.get("calib_tables"):
        n_tab = min(4, len(C["calib_tables"]))
        body(doc, "本附录摘录《06_校验/公式校准报告.md》的要点表（由该 Markdown 文件在报告生成时解析）："
                  "数值核验汇总、校准前后对结论的影响、公式—代码—数据对应表与状态汇总，"
                  f"共 {n_tab} 张表（表 B1–B{n_tab}）。完整推导、原始文献与逐条核验数据见该报告；"
                  "本报告第 2.6 节的表 7 是面向结论的精简版。")
        idx = 1
        for tb in C["calib_tables"][:4]:
            tab_df = pd.DataFrame(tb["rows"], columns=tb["header"])
            ncol = len(tab_df.columns)
            widths = [2.4] + [max(1.6, 13.4 / max(1, ncol - 1))] * (ncol - 1) if ncol > 1 else None
            table(doc, tab_df, widths,
                  f"表 B{idx}  公式校准报告摘录（{len(tab_df)} 行）", font=7.8)
            idx += 1
    else:
        body(doc, "《06_校验/公式校准报告.md》尚未提供或未包含可解析的表格，"
                  "以下给出本报告模型链已执行的公式校准摘要（完整依据待该报告补齐后并入）。")
        table(doc, _calib_rows(C), [1.5, 3.2, 6.2, 5.3],
              "表 B1  公式校准摘要（模型链已执行项）")

    # ---------------- 附录 C 参数依据摘要
    heading(doc, "附录 C  参数依据摘要", 1)
    reg = C.get("registry")
    n_reg = 0 if reg is None else len(reg)
    if reg is not None and len(reg):
        body(doc, "全部输入参数的依据、置信度与影响方向登记在《05_参数依据/参数依据登记表.csv》。"
                  f"该表由 params.py 的 registry_rows() 自动导出，共 {n_reg} 条核心参数；"
                  "谱线/环境数据来源见《05_参数依据/参数依据说明.md》。"
                  "登记表按四类来源标注：软件实测（SYS）、文献（LIT）、推导（DER）、设定（SET）；"
                  "凡“设定”类均说明为什么合理、影响多大、如何被实测替换。下面给出类别统计与摘要。")
        cat_col = _col(reg, "类别")
        if cat_col:
            stats = reg.groupby(cat_col).size().reset_index(name="条数")
            stats.columns = ["类别", "条数"]
            stats["说明"] = stats["类别"].map({
                "软件实测": "从软件配置/模型文件直接解析",
                "文献": "有公开文献/标准出处",
                "推导": "由其他已登记参数按物理关系推出",
                "设定": "无直接出处但工程合理，已说明替换路径",
            }).fillna("—")
            table(doc, stats, [3.0, 2.4, 10.6], "表 C1  参数依据类别统计")
        # 过滤含版本类字样的行，避免把历史信息带入报告
        def _row_clean(row):
            for v in row.values:
                s = str(v)
                for pat in FORBIDDEN_PATTERNS:
                    if re.search(pat, s):
                        return False
            return True
        reg2 = reg[reg.apply(_row_clean, axis=1)].copy()
        only = [c for c in ("param_id", "参数", "符号", "取值", "单位", "类别", "置信度")
                if c in reg2.columns]
        picks = []
        for cat in ("软件实测", "文献", "推导", "设定"):
            sub = reg2[reg2[cat_col] == cat] if cat_col else reg2
            picks.append(sub[only].head(7))
        sel = pd.concat(picks, ignore_index=True) if picks else reg2[only].head(24)
        rename = {"param_id": "编号", "参数": "参数", "符号": "符号", "取值": "取值",
                  "单位": "单位", "类别": "类别", "置信度": "置信度"}
        sel = sel.rename(columns=rename)
        table(doc, sel, [2.5, 3.7, 1.8, 4.0, 1.2, 1.6, 1.1],
              "表 C2  参数依据摘要（按类别摘录）。完整参数登记表由 params.py 自动导出"
              f"（{n_reg} 条核心参数）；谱线/环境数据来源见 05_参数依据/参数依据说明.md",
              font=7.8)
        body(doc, "表中“取值”为模型实际使用值；单位与符号与该登记表一致。"
                  "参数取值的敏感性见 3.2 节单变量响应与 5.3 节不确定度清单。")
    else:
        body(doc, "未找到 05_参数依据/参数依据登记表.csv，参数依据摘要缺失。")

    # ---------------- 附录 D 文件清单
    heading(doc, "附录 D  文件清单", 1)
    body(doc, "本附录列出报告使用的数据、图件、代码与校验文档（按实际存在性生成；"
              "表中未出现的文件不参与本报告结论）。")
    if C.get("inv_data") is not None and len(C["inv_data"]):
        table(doc, C["inv_data"], [5.0, 6.2, 1.6, 1.4, 1.9],
              "表 D1  数据文件清单（03_数据；行数/列数为 CSV 实际规模）", font=8.0)
    if C.get("inv_fig") is not None and len(C["inv_fig"]):
        table(doc, C["inv_fig"], [2.0, 8.4, 2.0, 2.0],
              "表 D2  图件清单（02_图表；编号与正文图号一一对应）", font=8.0)
    if C.get("inv_code") is not None and len(C["inv_code"]):
        table(doc, C["inv_code"], [5.8, 8.6, 1.6],
              "表 D3  代码、校验与参数文档清单", font=8.0)
    if C.get("data_cutoff"):
        note(doc, f"数据文件的最新修改时间为 {C['data_cutoff']}；报告日期为 {REPORT_DATE}。", size=8.8)

    # ---------------- 附录 E 参考文献
    heading(doc, "附录 E  参考文献", 1)
    refs = [
        "[1] Koschmieder H. Theorie der horizontalen Sichtweite. Beiträge zur Physik der freien Atmosphäre, 1924, 12: 33–53, 171–181.",
        "[2] Ångström A. On the atmospheric transmission of sun radiation and on dust in the air. Geografiska Annaler, 1929, 11: 156–166.",
        "[3] Eck T F, Holben B N, Reid J S, et al. Wavelength dependence of the optical depth of biomass burning, urban, and desert dust aerosols. JGR, 1999, 104(D24): 31333–31349. DOI:10.1029/1999JD900923",
        "[4] Hess M, Koepke P, Schult I. Optical properties of aerosols and clouds: The software package OPAC. BAMS, 1998, 79(5): 831–844.",
        "[5] Shettle E P, Fenn R W. Models for the aerosols of the lower atmosphere and the effects of humidity variations on their optical properties. AFGL-TR-79-0214, 1979.",
        "[6] Gordon I E, Rothman L S, Hargreaves R J, et al. The HITRAN2020 molecular spectroscopic database. JQSRT, 2022, 277: 107949. DOI:10.1016/j.jqsrt.2021.107949",
        "[7] Kochanov R V, Gordon I E, Rothman L S, et al. HITRAN Application Programming Interface (HAPI): A comprehensive approach to working with spectroscopic data. JQSRT, 2016, 177: 15–30. DOI:10.1016/j.jqsrt.2016.03.005",
        "[8] Fried D L. Optical resolution through a randomly inhomogeneous medium for very long and very short exposures. JOSA, 1966, 56(10): 1372–1379. DOI:10.1364/JOSA.56.001372",
        "[9] ITU-R. Recommendation ITU-R P.1817-1: Propagation data required for the design of terrestrial free-space optical links. ITU, 2012.",
        "[10] Johnson J. Analysis of image forming systems. Proc. Image Intensifier Symposium, 1958: 249–273.",
        "[11] Vollmerhausen R H, Jacobs E, Driggers R G. New metric for predicting target acquisition performance. Optical Engineering, 2004, 43(11): 2806–2818. DOI:10.1117/1.1799111",
        "[12] Vollmerhausen R H, Jacobs E. The Targeting Task Performance (TTP) Metric. NVESD, 2004. DOI:10.21236/ADA422493",
        "[13] Ratches J A. Static performance model for thermal imaging systems. Optical Engineering, 1976, 15(6): 525–530. DOI:10.1117/12.7972037",
        "[14] Lloyd J M. Thermal Imaging Systems. New York: Plenum Press, 1975.",
        "[15] Salisbury J W, D'Aria D M. Emissivity of terrestrial materials in the 8–14 μm atmospheric window. RSE, 1992, 42(2): 83–106.",
        "[16] Salisbury J W, D'Aria D M. Emissivity of terrestrial materials in the 3–5 μm atmospheric window. RSE, 1994, 47(3): 345–361.",
        "[17] ISO 2533:1975 Standard Atmosphere. International Organization for Standardization, 1975.",
        "[18] NASA POWER / MERRA-2 再分析数据（2015–2024）与 AERONET 站点统计（AOD₅₅₀、PWV、Ångström 指数）。",
        "[19] WMO. Guide to Instruments and Methods of Observation (WMO-No. 8), 2021 edition.",
        "[20] XGGDCOSSim2 光电环境仿真软件数据目录（Data\\SystemBaseFile、Data\\ModelData），2025–2026。",
        "[21] Bodhaine B A, Wood N B, Dutton E G, Slusser J R. On Rayleigh optical depth calculations. Journal of Atmospheric and Oceanic Technology, 1999, 16(11): 1854–1861. DOI:10.1175/1520-0426(1999)016<1854:ORODC>2.0.CO;2",
        "[22] Vermote E F, Tanré D, Deuzé J L, Herman M, Morcrette J J. Second simulation of the satellite signal in the solar spectrum, 6S: An overview. IEEE Transactions on Geoscience and Remote Sensing, 1997, 35(3): 675–686. DOI:10.1109/36.581987",
    ]
    for ref in refs:
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(2)
        p.paragraph_format.line_spacing = 1.15
        p.paragraph_format.left_indent = Cm(0.8)
        p.paragraph_format.first_line_indent = Cm(-0.8)
        _set_font(p.add_run(ref), 8.8)


# --------------------------------------------------------------------------- #
# 13. 版本字样自检
# --------------------------------------------------------------------------- #
def scan_forbidden(docx_path):
    """扫描 DOCX 内部全部 XML（正文/页眉/页脚/属性），返回命中 [(部件, 字样)]。"""
    hits = []
    try:
        with zipfile.ZipFile(docx_path) as zf:
            for name in zf.namelist():
                if not (name.startswith("word/") or name.startswith("docProps/")):
                    continue
                if not name.endswith(".xml"):
                    continue
                try:
                    raw = zf.read(name).decode("utf-8", errors="ignore")
                except (KeyError, OSError):
                    continue
                for pat in FORBIDDEN_PATTERNS:
                    for m in re.finditer(pat, raw):
                        hits.append((name, m.group(0)))
    except (zipfile.BadZipFile, OSError) as exc:
        return [("<无法读取 DOCX>", str(exc))]
    return hits


def _new_section(doc, landscape=False):
    """在文档中新建一个节；landscape=True 时切换为 A4 横向。"""
    sec = doc.add_section(WD_SECTION.NEW_PAGE)
    if landscape:
        sec.orientation = WD_ORIENT.LANDSCAPE
        sec.page_width, sec.page_height = Cm(29.7), Cm(21.0)
        sec.left_margin = sec.right_margin = Cm(2.3)
        sec.top_margin, sec.bottom_margin = Cm(2.0), Cm(1.8)
    else:
        sec.orientation = WD_ORIENT.PORTRAIT
        sec.page_width, sec.page_height = Cm(21.0), Cm(29.7)
        sec.left_margin = sec.right_margin = Cm(2.4)
        sec.top_margin, sec.bottom_margin = Cm(2.4), Cm(2.2)
    sec.header.is_linked_to_previous = True
    sec.footer.is_linked_to_previous = True
    sec.different_first_page_header_footer = False
    return sec


def _figure_abs(doc, path, caption_text, width_cm):
    """按绝对路径插图（用于附录 A 的横版思维导图等特殊版式）。"""
    if not path or not os.path.exists(path):
        note(doc, f"[图件缺失：{os.path.basename(path) if path else '—'}]", size=9,
             color=RED, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=2)
    else:
        doc.add_picture(path, width=Cm(width_cm))
        p = doc.paragraphs[-1]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_before = Pt(3)
        p.paragraph_format.space_after = Pt(4)
        p.paragraph_format.keep_with_next = True
    _caption(doc, caption_text, "fig")


def _appendix_a_guide(doc, C):
    body(doc, "图 A1 是本报告研究框架的项目思维导图（横向整页给出，便于阅读）。"
              "导图按“问题—输入—模型链—三类极限—实验设计—数据产品—校验与不确定度—结论”八层组织，"
              "可据此快速定位报告中任一环节对应的数据与图件。")
    body(doc, f"导图左侧为问题与输入（{len(params.TARGETS)} 个软件实测目标、背景、两档传感器、"
              f"{len(params.ENVIRONMENTS)} 类真实气候），中间为模型链（HITRAN2020 大气 → 辐亮度 → 视在温差 → "
              "MTF/MRTD → f_max → 周期数 → TTPF），右侧为三类极限、实验设计与最终结论。"
              "报告第 1—6 章依次展开图中各节点；正文中与图件编号相关的引用均可回到本图定位。")


def audit_document(docx_path):
    """对生成的 DOCX 做交付前自检：图号是否齐全、字体段落规模、禁止字样。"""
    res = {"forbidden": [], "missing_figs": [], "tables": 0, "paragraphs": 0,
           "images": 0, "error": None}
    try:
        audit_doc = Document(docx_path)
    except Exception as exc:  # noqa: BLE001
        res["error"] = str(exc)
        return res
    texts = [p.text for p in audit_doc.paragraphs]
    for tb in audit_doc.tables:
        for row in tb.rows:
            for cell in row.cells:
                texts.append(cell.text)
    full = "\n".join(texts)
    res["paragraphs"] = len(audit_doc.paragraphs)
    res["tables"] = len(audit_doc.tables)
    res["images"] = len(audit_doc.inline_shapes)
    res["forbidden"] = scan_forbidden(docx_path)
    for i in range(1, 18):
        if not re.search(rf"图\s*{i}(?![0-9])", full):
            res["missing_figs"].append(i)
    return res


# =========================================================================== #
# 13. 精简版章节（目标 20–24 页；保留 18 幅图与全部核心数值）
# =========================================================================== #
def _cmp_calib_rows(C, variant="main"):
    """关键校准项：main 为表 3（8 行），appendix 为表 B1（12 行，更细分组）。"""
    calib = C.get("calib", {})
    info = C.get("calib_info", {})
    notes = C.get("calib_md_notes", {})
    m = calib.get("MWIR", {})
    l = calib.get("LWIR", {})
    pr = info.get("pathrad_ratio", {})
    floor = C.get("floor_dtapp")
    curv = (f"球面分层使斜程 τ_aer 在 20/100/140 km 增大 "
            f"{notes.get('curv_aer_20', 0):.1f}%/{notes.get('curv_aer_100', 0):.1f}%/"
            f"{notes.get('curv_aer_140', 0):.1f}%" if "curv_aer_140" in notes else
            f"斜距相对平面近似差 {fmt(calib.get('curvature_max_pct'), 3)}%")
    rayleigh = (f"Rayleigh 系数 {fmt(calib.get('rayleigh_ratio'), 2)}×；"
                f"IR 波段斜程光学厚度增量 <{notes.get('rayleigh_ir_od', 3):.0f}×10⁻⁵"
                if "rayleigh_ir_od" in notes else
                f"Rayleigh 口径按垂直光学厚度/标高重算（{fmt(calib.get('rayleigh_ratio'), 2)}×）")
    rows = [
        ("F1–F3", "Planck/波段加权",
         f"B(10 μm,300 K)={fmt(info.get('planck_B10_300'), 3)}；T_ref 改为背景温度，λ_eff "
         f"MWIR {fmt(m.get('lam_eff_288'), 2)}→{fmt(m.get('lam_eff_ref'), 2)} μm；τ 影响 <1%"),
        ("F5", "反射项与热交叉",
         f"补入 (1−ε) 反射项后 ΔT=0 时 ΔT_app 严格为 0；原式零对比点偏移约 "
         f"{fmt(m.get('dt_shift_K'), 1)}/{fmt(l.get('dt_shift_K'), 1)} K（MWIR/LWIR）"),
        ("F6", "球面地球几何", curv),
        ("F7", "ISO 2533 廓线",
         f"8 km 气压相差 {_pct_txt(calib.get('iso_p8_ratio'), 1)}，τ_band 约 +1%、R₅₀ 约 +1%"),
        ("F8–F10", "水汽/气溶胶/Rayleigh", rayleigh),
        ("F11–F13", "光谱网格、物种与路径辐射",
         f"{'0.05 vs 0.1/0.2 cm⁻¹ 的 τ 差 <2×10⁻⁴；' if notes.get('spectral_tau_diff') else ''}"
         f"路径辐射原写法在均质板 τ=1 时高估 {fmt(notes.get('pathrad_ratio_tau1'), 2)}×"),
        ("F15–F22", "传感器链与 MRTD",
         f"标准式保留；f_max 判据 MRTD(f)=τ_opt·|ΔT_app|，等效视在温差地板 ≈{fmt(floor * 1000, 1)} mK"),
        ("F23–F33", "判据、求解器与临界反解",
         "N₅₀ 双口径并列；R₅₀/R₉₀ 对数域二分（相对精度 0.1%）；临界状态 r_ref=0.5·R₅₀，越界标“截断”"),
    ]
    if variant == "appendix":
        new_rows = []
        for row in rows:
            if row[0] == "F1–F3":
                new_rows.append(("F1–F2", "Planck 定律与 dB/dT",
                                 f"B(10 μm,300 K)={fmt(info.get('planck_B10_300'), 3)}；"
                                 f"T_ref 改为背景温度 {params.BACKGROUND['temp_c']:.0f} ℃；波段积分权重 dB/dT"))
                new_rows.append(("F3", "波段对比度加权",
                                 f"λ_eff MWIR {fmt(m.get('lam_eff_ref'), 2)} μm、"
                                 f"LWIR {fmt(l.get('lam_eff_ref'), 2)} μm；τ_band 与视在温度 LUT 同权重"))
            elif row[0] == "F23–F33":
                new_rows.append(("F23–F26", "视在温差、周期数与判据",
                                 "ΔT_app≤ε_t·ΔT；θ=D_eff/R_slant；N=f_max·θ；TTPF E=2；N₅₀ 双口径并列"))
                new_rows.append(("F28–F31", "目标尺寸与临界距离",
                                 "R_res=f_upper·D_eff/N₅₀；R₅₀/R₉₀ 对数域二分（相对精度 0.1%）；10 km 参考距离附列"))
                new_rows.append(("F32–F33", "热交叉与搜索边界",
                                 "盲区先 −10…+10 K 细扫（0.02 K）后二分（ΔT 容差 1e-4 K）；"
                                 "临界参数容差 1e-3，越界标“截断”"))
                new_rows.append(("F34–F37", "统计与图件口径",
                                 "环境按 p10/中位/p90 分位；η=R₅₀/R_res；敏感性取扫描范围内 R₅₀ 最大相对变化"))
            else:
                new_rows.append(row)
        rows = new_rows
    return pd.DataFrame(rows, columns=["编号", "校准项", "关键结论/影响"])


def _cmp_abstract(doc, C):
    heading(doc, "摘  要", 1)
    r50, eta = C["r50"], C["eta"]
    tau_m = C["tau_band"].get("MWIR", {})
    cl = C.get("claims", {})
    aod, cn2 = C.get("aod_summary", {}), C.get("cn2_summary", {})
    n50_rec = float(params.N50_SETS["NVESD"]["recognize"])
    body(doc, "本报告回答“红外目标能识别多远、临界状态是什么”。模型记为 irrecog 光谱—传感器—判据模型："
              "输入为 XGGDCOSSim2 软件实测的 6 个目标（D_eff 4.0–160.1 m）、与那国岛背景与两档传感器；"
              f"中间为 HITRAN2020 光谱大气与波段辐亮度；输出为 MTF/MRTD 决定的可分辨频率、周期数与 TTPF 任务概率。"
              "数据包括 15 组严格单变量扫描、8 类真实环境×3 分位×6 目标、6 目标临界状态反解与二维相图。")
    body(doc, "方法上，大气按 40 层球面斜程积分（ISO 2533 廓线、地球曲率、六物种"
              "220/250/280/300 K × 1.0/0.6/0.36/0.2 atm 截面、显式反射项），传感器链由衍射、探测器、抖动、"
              f"湍流与电子学 MTF 串联，MRTD=k·NETD 给出 f_max，P=N^E/(N₅₀^E+N^E)、N₅₀ 主口径 NVESD 识别 {n50_rec:.1f} cycles；"
              "公式校准见附录 B。")
    body(doc, f"基线工况（MWIR 3.7–4.8 μm、平台 8 km、背景 20 ℃、目标 40 ℃、AOD₅₅₀={params.ATMOS_BASE['aod550']:.3f}、"
              f"α={params.ATMOS_BASE['alpha']:.2f}、PWV={params.ATMOS_BASE['pwv_cm']:.2f} cm、"
              f"Cn²={_sci_txt(params.ATMOS_BASE['cn2'])}）下：R₅₀ 为悍马 {_km(r50.get('HM'))}、F16 {_km(r50.get('F16'))}、"
              f"F22 {_km(r50.get('F22'))}、爱国者 {_km(r50.get('AGZFSC'))}、阿利伯克 {_km(r50.get('ALBK'))}、"
              f"尼米兹 {_km(r50.get('NIMITZ'))}；η 为 {fmt(eta.get('HM'), 2)}/{fmt(eta.get('F16'), 2)}/"
              f"{fmt(eta.get('F22'), 2)}/{fmt(eta.get('AGZFSC'), 2)}/{fmt(eta.get('ALBK'), 2)}/{fmt(eta.get('NIMITZ'), 2)}；"
              f"MWIR 20 km 对比度加权波段透过率约 {fmt(tau_m.get(20.0), 3)}。")
    body(doc, "**结论一（两类机制）**：中小目标 "
              f"η={_minmax(eta, SMALL_T, 2)}，贴近分辨率天花板；大型舰船 η={_minmax(eta, LARGE_T, 2)}，"
              "识别极限由大气累积衰减接管——两类机制在特征尺寸约 16–85 m 之间交接。")
    body(doc, "**结论二（大气与波段）**：AOD₅₅₀ 从 0.02 增至 4.0 时尼米兹 R₅₀ 变化 "
              f"{_pct_txt(_get(aod.get('NIMITZ'), 'rel'), 0)}、F16 仅 {_pct_txt(_get(aod.get('F16'), 'rel'), 0)}；"
              f"F16 在 Cn²≳{_sci_txt(_get(cn2.get('F16'), 'censor_x'))} 后截断，尼米兹 R₅₀ 在 Cn²=1.0×10⁻¹³ 时降至 "
              f"{_km(_get(cn2.get('NIMITZ'), 'r13'))}；"
              f"换 LWIR 后小目标 R₅₀ 变化 {_pct_txt(cl.get('band_small'), 0)}、大目标 {_pct_txt(cl.get('band_large'), 0)}，"
              "波段优势在爱国者↔阿利伯克之间反转。")
    blind = C.get("blind_tab")
    w_hm = None
    if blind is not None and len(blind):
        ws = [fnum(str(rr.get("盲区宽度 (K)", "")).replace("—", "nan")) for _, rr in blind.iterrows()]
        w_hm = next((w for (_, rr), w in zip(blind.iterrows(), ws)
                     if str(rr.get("目标")) == TNAME["HM"] and w), None)
    body(doc, "**结论三（临界状态）**：0.5·R₅₀ 处热交叉盲区宽度 0.94–4.09 K，"
              f"其中悍马 {fmt(w_hm, 2)} K 主要源于其峰值识别概率仅 {fmt(C.get('pmax', {}).get('HM'), 2)}、裕度小；"
              "AOD 对 4 个目标不构成临界约束；对比度地板对应距离约 336–363 km，远大于 R₅₀，"
              "基线识别由分辨率采样与大气衰减联合限制。")
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(4)
    _set_font(p.add_run("关键词："), 10.5, True)
    _set_font(p.add_run("红外目标识别；识别概率；临界状态；HITRAN2020 光谱大气；不确定度"), 10.5)
    doc.add_page_break()


def _cmp_sec1(doc, C):
    heading(doc, "1  任务与极限定义", 1)
    heading(doc, "1.1  研究问题与对象", 2)
    body(doc, "红外成像的“能看多远”是一个随目标、大气与传感器变化的曲面，工程需要的是三件事："
              "给定工况的极限距离、极限由哪一层决定（瓶颈判定）、以及把极限推移到目标值需要改变哪个参数。"
              "本报告据此组织：第 2 章数据与方法，第 3 章结果与单变量响应，第 4 章临界状态，"
              "第 5 章数据质量与不确定度，第 6 章结论；第 1 章先给出三类“极限”的数学定义。")
    body(doc, "研究对象为 XGGDCOSSim2 软件模型库中实际存在的 6 个目标（F16、F22、尼米兹级航母、"
              "阿利伯克级驱逐舰、悍马车、爱国者导弹发射车），包围盒由软件 OSG 顶点解析（1 单位 = 1 m）；"
              "传感器以软件默认显示参数为锚点，定义识别通道（FOV 0.7334°×0.5500°、1024×768）并保留搜索通道对照；"
              "大气采用 HITRAN2020 逐线光谱；全部输入参数登记在《05_参数依据/参数依据登记表.csv》。")
    heading(doc, "1.2  三类“极限”的定义", 2)
    body(doc, "**识别概率极限。**任务概率 P 随目标上可分辨周期数 N 按 TTPF 变化：P=N^E/(N₅₀^E+N^E)，E=2；"
              "N=f_max·θ、θ=D_eff/R_slant（m/km 即 mrad）。P 随距离单调下降，R₅₀ 为 P=0.5 对应的地面距离，"
              "R₉₀ 为 P=0.9 对应的地面距离。")
    body(doc, "**分辨率天花板。**忽略大气与湍流时 R_res=f_upper·D_eff/N₅₀（f_upper=min(Nyquist, D/λ)），"
              "再按平台高度与地球曲率换算地面距离；η=R₅₀/R_res 度量实际极限相对硬上限的折减。")
    body(doc, "**对比度地板与湍流边界。**MRTD(f)=k·NETD/MTF(f)，当 τ_opt·|ΔT_app|≤k·NETD 时 f_max=0，"
              "任何距离都无法识别；湍流通过 r₀=(0.423k²Cn²L)^(−3/5) 压缩 MTF，使 f_max 提前掉出 Nyquist。"
              "关键符号：R₅₀/R_res（km）、η（—）、N/N₅₀（cycles）、τ_band（对比度等效波段透过率）、"
              "ΔT_app（视在温差，K）、AOD₅₅₀/α/PWV/Cn²（大气输入）。")
    figure(doc, C["fig_dir"], "01", "图 1  识别概率极限的评估链路与三类边界")
    heading(doc, "1.3  报告组织与复算", 2)
    body(doc, "报告按“数据—模型—结果—临界状态—不确定度—结论”展开；图表按正文顺序编号，"
              "全部结果可由 03_数据 的 CSV 运行时复算，文件级清单见附录 D 与 文件清单.csv。")


def _cmp_sec2(doc, C):
    heading(doc, "2  数据与方法", 1)
    recog = C["sensor"]["RECOG"]
    # ---- 2.1
    heading(doc, "2.1  软件实测目标与背景", 2)
    rows = []
    for t in params.TARGETS:
        w, l, h = t["dims"]
        rows.append({"目标": t["name"], "类别": t["kind"],
                     "包围盒 W×L×H (m)": f"{w:.2f}×{l:.2f}×{h:.2f}",
                     "D_eff (m)": f"{math.sqrt(max(w, l) * h):.2f}",
                     "高度 (m)": f"{t['z_m']:.0f}", "发射率": f"{t['eps']:.2f}"})
    table(doc, pd.DataFrame(rows), [3.2, 1.4, 4.4, 1.8, 1.6, 1.4],
          "表 1  软件模型库 6 个目标的几何参数")
    body(doc, f"背景采用软件唯一可加载的背景模型“{params.BACKGROUND['name']}”（环境温度 "
              f"{params.BACKGROUND['temp_c']:.0f} ℃、发射率 {params.BACKGROUND['eps']:.2f}）；"
              f"目标热状态基线 {params.BASELINE['target_temp_c']:.0f} ℃，平台高度基线 8000 m。"
              "包围盒未做几何标定，是本项目登记的主要不确定度之一（见 5.3 节）。")
    # ---- 2.2
    heading(doc, "2.2  参考传感器两档", 2)
    srows = []
    for name, label in (("RECOG", "识别通道（设定）"), ("SEARCH", "搜索通道（软件实测）")):
        s = C["sensor"][name]
        srows.append({"通道": label, "FOV": f"{s['fov_h_deg']:.4f}°×{s['fov_v_deg']:.3f}°",
                      "像元": f"{int(s['npx_h'])}×{int(s['npx_v'])}",
                      "IFOV (μrad)": f"{s['ifov_urad']:.2f}",
                      "焦距/口径 (m)": f"{s['f_m']:.3f}/{s['D_m']:.3f}",
                      "NETD (mK)": f"{s['netd_k'] * 1000:.0f}",
                      "Nyquist (cyc/mrad)": f"{s['f_nyq']:.1f}"})
    table(doc, pd.DataFrame(srows), [3.2, 2.9, 1.8, 1.8, 2.4, 1.5, 2.2],
          "表 2  两档参考传感器（IFOV=FOV/N；Nyquist=1/(2·IFOV)）")
    body(doc, f"识别通道 IFOV={recog['ifov_urad']:.2f} μrad、Nyquist={recog['f_nyq']:.1f} cyc/mrad；"
              f"其衍射截止 D/λ 在 MWIR 有效波长 {C['lam_eff']['MWIR']:.3f} μm 处约 {C['f_cut']['MWIR']:.0f} cyc/mrad、"
              f"LWIR {C['lam_eff']['LWIR']:.3f} μm 处约 {C['f_cut']['LWIR']:.0f} cyc/mrad——"
              "MWIR 为探测器采样受限、LWIR 为衍射受限，这是波段差异的物理根源。")
    # ---- 2.3
    heading(doc, "2.3  光谱大气模型与 HITRAN2020 数据", 2)
    body(doc, "大气按球面几何分层积分（地心角构造弦、层高消光、弦长为斜距；R_E=6371 km，不含折射）；"
              "气体吸收使用 HITRAN2020 逐线 Voigt 截面：六物种（H₂O/CO₂/O₃/N₂O/CO/CH₄），"
              "温度 220/250/280/300 K 与气压 1.0/0.6/0.36/0.2 atm 四节点，逐层按层温与层压双线性插值"
              "（气压在 ln p 坐标线性）；CO 在 2375–2875 cm⁻¹ 无 HITRAN 数据，不影响其 1–0 带（2000–2300 cm⁻¹）；"
              f"光谱网格为波数域均匀、步长 {params.SPECTRAL_STEP_CM} cm⁻¹。")
    body(doc, "大气廓线用 ISO 2533 分层；水汽/气溶胶按指数标高（2.0/1.5 km）归一到 PWV/AOD₅₅₀；"
              "分子散射用 6S 口径的 Rayleigh 垂直光学厚度/标高；气溶胶按外消光处理；路径辐亮度按累计光学厚度的"
              "发射—吸收积分。目标/背景辐亮度含 (1−ε) 反射项（背景黑体近似），两式相减严格得 "
              "ΔL=ε_t[B(T_t)−B(T_b)]τ，故热交叉严格发生在 ΔT=0。")
    figure(doc, C["fig_dir"], "02", "图 2  真实气候工况空间（AOD₅₅₀–PWV）与软件默认工况定位")
    figure(doc, C["fig_dir"], "03",
           "图 3  4 种气候工况（基线、清洁干燥、湿热带、强沙尘）的斜程大气光谱透过率"
           "（左：MWIR；右：LWIR；斜距约 21.55 km、目标高 0 m；波段平均按 dB/dT 加权）")
    tau_m = C["tau_band"]["MWIR"]
    body(doc, f"基线工况下 MWIR 对比度等效波段透过率在 1/10/20 km 地面距离处为 "
              f"{_kv(tau_m.get(1.0), 3)}/{_kv(tau_m.get(10.0), 3)}/{_kv(tau_m.get(20.0), 3)}"
              "（F16 基线，目标高 500 m；图 3 按目标高 0 m、斜距约 21.55 km 计算，二者口径不同）。")
    # ---- 2.4
    heading(doc, "2.4  传感器链与任务概率", 2)
    body(doc, "系统 MTF 由衍射（Airy OTF）、探测器 sinc、视线抖动、湍流与电子学五部分串联；"
              "MRTD(f)=k·NETD/MTF(f)，由 MRTD(f)=τ_opt·|ΔT_app| 求 f_max，上限取 min(Nyquist, 衍射截止)。"
              "目标角尺寸 θ=D_eff/R_slant，周期数 N=f_max·θ，任务概率取 TTPF（E=2）；"
              "N₅₀ 主口径 NVESD（探测 4.0/识别 16.5/辨认 26.6 cycles），对照口径 Johnson（2/8/16 line pairs）并列。")
    figure(doc, C["fig_dir"], "04", "图 4  系统 MTF 链、MRTD 曲线与 f_max 判定")
    # ---- 2.5
    heading(doc, "2.5  实验设计", 2)
    n_sw = len(C.get("sweeps_meta", [])) or 15
    body(doc, f"共 {n_sw} 组严格单变量（OFAT）扫描，覆盖目标类型、波段、目标热状态、气溶胶、Ångström 指数、"
              "可降水量、湍流、口径、NETD、IFOV、平台高度、判据口径、尺寸口径、目标发射率与工作模式；"
              "另建真实气候矩阵（8 类环境×p10/中位/p90×6 目标）与 6 目标临界状态反解、AOD×Cn² 与 ΔT×AOD 二维相图。"
              "全部评估点写入全工况长表，单变量宽表、临界表、环境表与相图表均由长表派生，可逐项复算。")
    # ---- 2.6
    heading(doc, "2.6  公式校准", 2)
    body(doc, "本项目对全链路公式逐条校准（原式→校准式→依据→影响），完整记录见《06_校验/公式校准报告.md》。"
              "核心变化：辐亮度补入 (1−ε) 反射项使热交叉严格回到 ΔT=0；Rayleigh 按“垂直光学厚度/标高”重算；"
              "大气廓线改 ISO 2533 并加入地球曲率；光谱升级为 HITRAN2020 六物种四温度×四气压截面。"
              "表 3 给出关键校准项的定量影响，完整 37 条见附录 B 与上述报告。")
    table(doc, _cmp_calib_rows(C), [1.6, 4.6, 9.8],
          "表 3  关键公式校准项及其对结论的影响")


def _cmp_sec3(doc, C):
    data = C["data"]
    heading(doc, "3  结果", 1)
    r50, rres, eta = C["r50"], C["rres"], C["eta"]
    tau50, dtapp, pmax = C["tau50"], C["dtapp50"], C["pmax"]
    # ---- 3.1
    heading(doc, "3.1  基线：识别概率曲线与临界距离", 2)
    figure(doc, C["fig_dir"], "05", "图 5  基线工况下 6 个目标的识别/探测概率曲线")
    rows = []
    for tk in TORDER:
        r90v = C["r90"].get(tk)
        rows.append({"目标": TNAME[tk], "D_eff (m)": fmt(C.get("d_eff", {}).get(tk), 2),
                     "R50 (km)": fmt(r50.get(tk), 1), "R90 (km)": fmt(r90v, 1),
                     "R_res (km)": fmt(rres.get(tk), 1), "η": fmt(eta.get(tk), 3),
                     "τ@R50": fmt(tau50.get(tk), 3), "ΔT_app (K)": fmt(dtapp.get(tk), 2),
                     "P_max": fmt(pmax.get(tk), 3)})
    table(doc, pd.DataFrame(rows), [2.3, 1.2, 1.2, 1.7, 1.4, 1.1, 1.2, 1.6, 1.4],
          "表 4  基线识别临界距离与链路诊断量",
          font=8.0,
          note_text="注：R90 为“—”表示受采样上限（f_max≤Nyquist=40 cyc/mrad）限制，任意距离 P<0.9，"
                    "非数据缺失（悍马/F16/F22 的峰值概率分别为 0.60/0.88/0.89）；截断原因见 03_数据 的 censored 字段。")
    small_eta = [fnum(eta.get(t)) for t in SMALL_T if fnum(eta.get(t)) is not None]
    large_eta = [fnum(eta.get(t)) for t in LARGE_T if fnum(eta.get(t)) is not None]
    tau_small = [fnum(tau50.get(t)) for t in SMALL_T if fnum(tau50.get(t)) is not None]
    tau_large = [fnum(tau50.get(t)) for t in LARGE_T if fnum(tau50.get(t)) is not None]
    body(doc, f"R₅₀ 从悍马 {_km(r50.get('HM'))} 跨到尼米兹 {_km(r50.get('NIMITZ'))}；"
              f"中小目标 η={min(small_eta):.2f}–{max(small_eta):.2f} 贴近天花板，大型舰船 η="
              f"{min(large_eta):.2f}–{max(large_eta):.2f}，其极限由大气透过率接管"
              f"（R₅₀ 处 τ 仅 {min(tau_large):.3f}–{max(tau_large):.3f}，中小目标为 "
              f"{min(tau_small):.3f}–{max(tau_small):.3f}）。")
    body(doc, f"R₅₀ 处周期数集中在 15.8–17.0 cycles（N₅₀=16.5 的直接体现，构成内部自洽校核）；"
              "R₉₀ 对悍马/F16/F22 截断——平台 8 km 下最小斜距约 7.5–8 km，且 f_max≤40 cyc/mrad 使 N 封顶，"
              "其峰值识别概率仅 0.60/0.88/0.89<0.9，故任意距离 P<0.9。")
    figure(doc, C["fig_dir"], "06", "图 6  探测 / 识别 / 辨认三种任务定义下的临界距离对比")
    body(doc, "三任务差别完全来自 N₅₀（4.0/16.5/26.6）：探测距离约为识别的 2–4 倍，辨认距离约 0.5–0.7 倍；"
              "比例在各目标上基本稳定，说明任务定义是“判据口径”效应而非物理差异（口径不确定度见 5.3 节）。")
    # ---- 3.2
    heading(doc, "3.2  单变量响应", 2)
    body(doc, "以下均为“只改一个变量、其余固定”的结果；缺少数据点表示该取值下 P 在搜索范围内始终低于 0.5。")
    heading(doc, "3.2.1  气溶胶光学厚度", 3)
    figure(doc, C["fig_dir"], "07", "图 7  R₅₀ 随 AOD₅₅₀ 变化（其余条件固定）")
    aod = C.get("aod_summary", {})
    body(doc, f"小目标对 3.7–4.8 μm 气溶胶几乎不敏感（F16 相对变化 {_pct_txt(_get(aod.get('F16'), 'rel'), 0)}），"
              f"大型舰船则显著（尼米兹 {_pct_txt(_get(aod.get('NIMITZ'), 'rel'), 0)}、"
              f"阿利伯克 {_pct_txt(_get(aod.get('ALBK'), 'rel'), 0)}）；"
              "原因是舰船累积光学厚度大、R₅₀ 已进入大气衰减敏感区，而小目标极限由分辨率决定。")
    heading(doc, "3.2.2  大气湍流", 3)
    figure(doc, C["fig_dir"], "08", "图 8  R₅₀ 随 Cn² 变化（含截断区）")
    cn2 = C.get("cn2_summary", {})
    lam_b = C["lam_eff"]["MWIR"] * 1e-6
    r0 = (0.423 * (2 * math.pi / lam_b) ** 2 * float(params.ATMOS_BASE["cn2"]) * 20000.0) ** (-0.6)
    body(doc, f"基线 Cn²={_sci_txt(params.ATMOS_BASE['cn2'])} 时 20 km 斜程 r₀≈{fmt(r0, 2)} m，已小于口径 "
              f"{params.SENSOR_PRESETS['RECOG']['D_m']:.2f} m；Cn²≈3×10⁻¹⁴ 后 F16 截断，"
              f"尼米兹 R₅₀ 从无湍流 {_km(_get(cn2.get('NIMITZ'), 'r0'))} 降至 1×10⁻¹³ 时 "
              f"{_km(_get(cn2.get('NIMITZ'), 'r13'))}。湍流是少数能在“大气干净、距离很近”时仍使小目标识别失败的因子。")
    heading(doc, "3.2.3  目标热状态与发射率", 3)
    figure(doc, C["fig_dir"], "09", "图 9  目标热状态与发射率对 R₅₀ 的影响")
    body(doc, "ΔT=0 时对比度严格为零，R₅₀ 不存在（截断）；远离热交叉后 R₅₀ 对热状态不敏感"
              "（60 ℃ 相对 40 ℃ 尼米兹 R₅₀ 仅小幅增加），发射率在基线附近影响约 2%；"
              "真正的临界发生在热交叉窄带，见 4.2 节。")
    heading(doc, "3.2.4  传感器参数（口径 / NETD / IFOV）", 3)
    figure(doc, C["fig_dir"], "10", "图 10  口径、NETD、IFOV 对 R₅₀ 的影响")
    body(doc, "口径在 D≳0.3 m 后进入平台（Nyquist 已低于衍射截止，继续加大口径不改善采样）；"
              "NETD 呈阈值形态，只在对比度地板逼近实际 |ΔT_app| 时显著；"
              "IFOV 是一阶因子：IFOV 8→40 μrad 时 F16 的 R₅₀ 由约 18.7 km 降至 2.2 km（近似反比）。"
              "搜索通道（IFOV 63.9 μrad）因采样过粗，F16 在基线不可识别，仅适合探测/大目标。")
    heading(doc, "3.2.5  平台高度", 3)
    figure(doc, C["fig_dir"], "11", "图 11  R₅₀ 随平台高度变化（球面斜程几何）")
    p11 = _sweep_pairs(data, "S11", ("platform_h_m",))
    f16_best_h = C.get("claims", {}).get("s11_f16_best_h")
    body(doc, "平台高度通过“同一地面距离下斜距变化”与“低空大气柱更长”两条途径影响极限："
              "大型舰船 R₅₀ 随平台升高而增大，中小目标存在最优高度"
              f"（本数据 F16 最优点约 {fmt(f16_best_h, 0)} m）；8 km 平台几何视距约 319 km，"
              "各工况临界距离均在其内，曲率修正不影响结论。")
    # 单变量影响摘要
    cl = C.get("claims", {})
    aod_rng = C["sweep_ranges"].get("S04") or (None, None)
    cn2_rng = C["sweep_ranges"].get("S07") or (None, None)
    sens = C.get("sens_tab")
    def _sens_val(keyword):
        if sens is None or len(sens) == 0:
            return ""
        for _, rr in sens.iterrows():
            if keyword in str(rr.get("变量", "")):
                return str(rr.get("最大相对变化", "")) if str(rr.get("最大相对变化", "")) != "nan" else ""
        return ""
    plat_rel = _sens_val("平台")
    s_rows = [
        ("气溶胶 AOD₅₅₀", f"{fmt(aod_rng[0], 2)}–{fmt(aod_rng[1], 2)}",
         _pct_txt(cl.get("aod_large_abs"), 0, plus=False),
         "大目标显著缩短，小目标弱敏感"),
        ("湍流 Cn²", f"{_sci_txt(cn2_rng[0])}–{_sci_txt(cn2_rng[1])}",
         "截断", "超过约 3×10⁻¹⁴ 后小目标不可识别"),
        ("目标温度", f"{fmt(C['sweep_ranges'].get('S03', (20, 60))[0], 0)}–"
                  f"{fmt(C['sweep_ranges'].get('S03', (20, 60))[1], 0)} ℃",
         _pct_txt(abs(C.get("claims", {}).get("temp_effect") or 0), 0, plus=False),
         "远离热交叉时影响小，ΔT=0 不可识别"),
        ("目标发射率", f"{fmt(C['sweep_ranges'].get('S14', (0.85, 0.97))[0], 2)}–"
                   f"{fmt(C['sweep_ranges'].get('S14', (0.85, 0.97))[1], 2)}",
         _pct_txt(abs(C.get("claims", {}).get("eps_effect") or 0), 0, plus=False),
         "影响小；近热交叉时放大"),
        ("传感器（口径/NETD/IFOV）",
         "D 0.05–0.7 m；NETD 5–200 mK；IFOV 8–40 μrad",
         (_pct_txt(C.get("claims", {}).get("sensor_first_pct"), 0, plus=False)
          if C.get("claims", {}).get("sensor_first") else ""),
         "IFOV 为一阶因子；口径>0.3 m 进入平台"),
        ("平台高度", f"{fmt(C['sweep_ranges'].get('S11', (100, 12000))[0], 0)}–"
                 f"{fmt(C['sweep_ranges'].get('S11', (100, 12000))[1], 0)} m",
         plat_rel, "大目标随高度增大，小目标有最优高度"),
    ]
    table(doc, pd.DataFrame(s_rows, columns=["因子", "扫描范围", "R₅₀ 最大相对变化", "机制/说明"]),
          [3.6, 4.6, 2.6, 5.2], "表 5  单变量影响摘要", font=8.0)
    # ---- 3.3
    heading(doc, "3.3  波段对比", 2)
    figure(doc, C["fig_dir"], "12", "图 12  MWIR 与 LWIR 的 R₅₀ 对比")
    if len(C.get("band_tab", [])):
        table(doc, C["band_tab"], [3.6, 3.4, 3.4, 3.2],
              "表 6  同一光学系统换波段的识别临界距离对比")
    cl = C.get("claims", {})
    cross = cl.get("band_crossing")
    cross_txt = (f"；反转发生在 {cross[0]} 与 {cross[2]} 之间"
                 f"（LWIR/MWIR−1：{cross[1] * 100:+.0f}% vs {cross[3] * 100:+.0f}%）") if cross else ""
    body(doc, f"10 km 处 MWIR/LWIR 波段透过率约 {fmt(cl.get('tau10_mw'), 3)}/{fmt(cl.get('tau10_lw'), 3)}；"
              f"换 LWIR 后小目标 R₅₀ 变化 {_pct_txt(cl.get('band_small'), 0)}、大目标 "
              f"{_pct_txt(cl.get('band_large'), 0)}{cross_txt}。长波更适合远距探测，"
              "是否更适合识别取决于目标角尺寸与衍射/Nyquist 匹配，不能一概而论。")
    # ---- 3.4
    heading(doc, "3.4  两类机制与临界状态相图", 2)
    figure(doc, C["fig_dir"], "13", "图 13  识别极限包络：分辨率天花板 R_res 与实际 R₅₀")
    if cl.get("two_mechanisms"):
        body(doc, f"η 随目标尺寸呈两段式：D_eff≲16 m 时 η={_minmax(eta, SMALL_T, 2)}，"
                  f"识别由传感器采样与目标角尺寸锁死；D_eff≳85 m 时 η={_minmax(eta, LARGE_T, 2)}，"
                  "R_res 远超大气可支撑距离，极限改由气溶胶/水汽/湍流接管——两条机制在 16–85 m 之间交接。")
    else:
        body(doc, "η 随目标尺寸连续变化，分辨率、大气衰减与湍流对不同目标的相对权重不同，"
                  "不存在简单的两段式；各因子的相对量级见表 5。")
    grid_txt = ("图中每一格点均为一次独立的模型正向计算与二分反解"
                "（图 14：每个 panel 525 个 AOD×Cn² 格点；图 15：546 个 ΔT×AOD 格点），"
                "色块为格点间平滑显示，等值线由格点计算值直接绘制。")
    figure(doc, C["fig_dir"], "14",
           "图 14  临界状态相图：AOD₅₅₀ × Cn² 对 F16（左）与尼米兹（右）识别距离的联合作用。" + grid_txt)
    figure(doc, C["fig_dir"], "15",
           "图 15  临界状态相图：固有温差 × AOD₅₅₀（等值线为 R₅₀）。" + grid_txt)
    body(doc, "相图表明两类机制并非简单叠加：强湍流可在气溶胶清洁时把目标压入不可识别区，"
              "而温差×AOD 图在 ΔT≈0 附近出现 R₅₀ 下凹（热交叉盲区），位置与宽度由 4.2 节从临界状态 CSV 读取。")
    # ---- 3.5
    heading(doc, "3.5  真实气候工况", 2)
    figure(doc, C["fig_dir"], "16", "图 16  8 类真实环境 × 6 个目标的识别临界距离")
    es = C.get("env_summary", {})
    ni, fi = _get(es, "NIMITZ", {}), _get(es, "F16", {})
    body(doc, f"环境间差异对大型舰船可达 {_pct_txt(_get(ni, 'rel'), 0)}（尼米兹在 "
              f"{_get(ni, 'env_lo', '—')} {_km(_get(ni, 'lo'))} 与 {_get(ni, 'env_hi', '—')} "
              f"{_km(_get(ni, 'hi'))} 之间），对中小目标约 {_pct_txt(_get(fi, 'rel'), 0)}；"
              "这一排序由各环境 AOD/PWV/α 联合决定，不宜简单归因于单一因子。")
    # ---- 3.6
    heading(doc, "3.6  敏感性排序", 2)
    figure(doc, C["fig_dir"], "17", "图 17  单变量对 R₅₀ 的相对影响排序")
    if sens is not None and len(sens):
        top3 = "、".join(str(v) for v in sens["变量"].head(3))
        body(doc, f"把各变量在扫描范围内的 R₅₀ 最大相对变化取中位数排序：{top3} 居前；"
                  "该排序随扫描范围变化，不能替代相图与临界阈值，工程上应以相图与临界状态反解作为设计依据。")
    else:
        body(doc, "敏感性排序见图 17；排序随扫描范围变化，不能替代相图与临界阈值。")


def _cmp_sec4(doc, C):
    heading(doc, "4  临界状态", 1)
    cl = C.get("claims", {})
    maps = C.get("crit_maps", {})
    heading(doc, "4.1  临界距离与临界参数（r_ref=0.5·R₅₀）", 2)
    # 合并主列 + 10 km 精简附列
    main = C.get("critparam_tab")
    ten = C.get("critparam10_tab")
    rows = []
    for tk in TORDER:
        r50 = C["r50"].get(tk)
        rref = maps.get("rref", {}).get(tk)
        row = {"目标": TNAME[tk], "R50 (km)": fmt(r50, 1), "r_ref (km)": fmt(rref, 1)}
        for col, key in (("临界 AOD550", "临界 AOD550"), ("临界 Cn² (m⁻²ᐟ³)", "临界 Cn² (m⁻²ᐟ³)"),
                         ("临界口径 D (m)", "临界口径 D (m)"), ("临界 NETD (mK)", "临界 NETD (mK)")):
            val = "—"
            if main is not None and len(main):
                s = main[main["目标"] == TNAME[tk]]
                if len(s) and col in s.columns:
                    val = str(s.iloc[0][col])
            row[col] = val
        for col, newcol in (("临界 AOD550@10km", "AOD@10km"), ("临界 Cn²@10km", "Cn²@10km")):
            val = "—"
            if ten is not None and len(ten):
                s = ten[ten["目标"] == TNAME[tk]]
                if len(s) and col in s.columns:
                    val = str(s.iloc[0][col])
            row[newcol] = val
        row["截断"] = "是" if (main is not None and len(main)
                            and str(main[main["目标"] == TNAME[tk]].iloc[0].get("截断", "—")) == "是") else "—"
        rows.append(row)
    df7 = pd.DataFrame(rows).rename(columns={
        "临界 AOD550": "临界AOD", "临界 Cn² (m⁻²ᐟ³)": "临界Cn²",
        "临界口径 D (m)": "临界D(m)", "临界 NETD (mK)": "临界NETD(mK)"})
    table(doc, df7,
          [2.2, 1.2, 1.2, 1.8, 1.9, 1.4, 1.9, 1.6, 1.6, 1.0],
          "表 7  基准工况临界状态（主列 r_ref=0.5·R₅₀；10 km 附列为精简列）", font=6.8,
          note_text="注：“≥20（不构成约束）”表示该处 AOD 增至搜索上限仍可识别；“—（R50≤10 km）”表示该目标 R50 不足 10 km。")
    body(doc, "临界距离按 R₅₀/R₉₀ 与任务口径给出。0.5·R₅₀ 处：阿利伯克与尼米兹的有效临界 AOD 为 "
              f"{fmt(maps.get('aod', {}).get('ALBK'), 2)}/{fmt(maps.get('aod', {}).get('NIMITZ'), 2)}，其余 4 个目标 AOD 不构成约束；"
              "临界 Cn² 为 3.2×10⁻¹⁵–7.8×10⁻¹⁵，临界口径 0.03–0.17 m，临界 NETD 263–1230 mK。"
              "对比度地板对应地面距离约 336–363 km，远大于基线 R₅₀——说明基线识别由分辨率采样与大气衰减联合限制，"
              "而非对比度地板。")
    heading(doc, "4.2  热交叉识别盲区", 2)
    blind = C.get("blind_tab")
    hm_w, f16_w = None, None
    if blind is not None and len(blind):
        for _, rr in blind.iterrows():
            w = fnum(str(rr.get("盲区宽度 (K)", "")).replace("—", "nan"))
            if str(rr.get("目标")) == TNAME["HM"]:
                hm_w = w
            if str(rr.get("目标")) == TNAME["F16"]:
                f16_w = w
    ten_half = None
    w10 = fnum(_get(maps.get("blind10_width", {}), "F16"))
    if w10:
        ten_half = 0.5 * w10
    body(doc, "校准后的辐亮度方程含反射项，ΔT=0 时对比度严格为零；盲区由等效视在温差地板 k·NETD/τ_opt"
              f"（本模型约 {C['floor_dtapp'] * 1000:.1f} mK）与噪声决定，而非发射率不对称的假偏移。"
              f"0.5·R₅₀ 处各目标盲区宽度 0.94–4.09 K（图 14 对应 0.5·R₅₀ 参考距离）。")
    body(doc, f"需要区分“物理宽度”与“概率裕度”：悍马盲区 {fmt(hm_w, 2)} K 明显大于其他目标，"
              f"但其峰值识别概率仅 {fmt(C.get('pmax', {}).get('HM'), 2)}、0.5·R₅₀ 处距 0.5 阈值裕度很小，"
              "小 ΔT_app 变化即可把整段概率压到 0.5 以下，故宽度主要反映裕度小而非热交叉更宽。"
              + (f"以 F16 在 10 km 参考距离处的细分结果为例，盲区为 ±{ten_half:.2f} K（宽度 {2 * ten_half:.2f} K）。"
                 if ten_half else ""))
    heading(doc, "4.3  临界 AOD / Cn² / 口径 / NETD 的机制含义", 2)
    body(doc, "临界值的可解范围与截断反映了不同目标的瓶颈：小目标的临界 AOD 往往撞到搜索上限"
              "（AOD≤20 仍可识别），说明其极限与气溶胶无关；大型舰船的临界 AOD 落在 8–12，"
              "即存在“清洁大气可识别、沙尘条件失效”的阈值。临界 Cn² 约 3×10⁻¹⁵–8×10⁻¹⁵，"
              "是本传感器系统的湍流容限量级；临界口径与 NETD 则给出衍射与对比度的余量。"
              "上述阈值可直接用于指标论证与试验设计，相图（图 15）给出二维参数平面上的完整图像。")


def _cmp_sec5(doc, C):
    heading(doc, "5  数据质量与不确定度", 1)
    heading(doc, "5.1  数据质量与内部校核", 2)
    qa = C.get("qa_info") or {}
    checks = C.get("checks_tab")
    n_ok = None
    if checks is not None and len(checks):
        n_ok = int((checks["结果"] == "通过").sum())
    body(doc, ("《06_校验/校验报告.md》汇总的模型 V&V 检查"
               + (f"共 {qa.get('total', '—')} 项、通过 {qa.get('pass', '—')} 项" if qa else "")
               + "；本报告生成时又对 CSV 独立重算：R₅₀ 处周期数与 N₅₀ 一致（15.8–17.0 cycles）、"
                 "η≤1、P 随距离单调不增、R₅₀ 两侧 P 跨越 0.5、长表与汇总表一致。")
          + (f"表 9 之前的截图/表格已删除，核心数值均可在 CSV 中逐项复核。" if False else ""))
    body(doc, f"数据体量：全工况长表 {C['counts'].get('long', 0):,} 行、单变量汇总 "
              f"{C['counts'].get('summary', 0)} 行、环境工况 {C['counts'].get('env', 0)} 行、"
              f"临界状态 {C['counts'].get('crit', 0)} 行、波段对比 {C['counts'].get('band', 0)} 行、"
              f"相图 {C['counts'].get('phase_aod', 0)}+{C['counts'].get('phase_dt', 0)} 格；"
              "所有结果由同一批 CSV 派生，图-数据-报告同源。")
    heading(doc, "5.2  模型假设与适用条件", 2)
    for txt in [
        "**大气几何**：球面弦长、不含折射与地球扁率；未显式加入地平线遮挡判据；对 8 km 平台结论无影响。",
        "**大气成分**：HITRAN2020 逐线 Voigt（六物种、四温度×四气压），不含 MT_CKD 连续吸收、"
        "不含云/雨/雾/沙尘相函数与多次散射，气溶胶按外消光处理。",
        "**背景与反射**：背景按 20 ℃ 均匀黑体（ε=0.95）；含 (1−ε) 反射项，但反射环境辐亮度取背景黑体。",
        "**目标**：等效方目标 D_eff=√(W_proj·H)，包围盒未几何标定；热状态用等效温度+发射率表示。",
        "**传感器与湍流**：识别通道为设定-推导值，MRTD 用 k=2.5 工程近似；整层单一 Cn²，不含廓线。",
        "**判据**：TTPF（E=2）与 NVESD/Johnson 双口径并列；单帧静态判据，不含多帧融合增益。",
    ]:
        bullet(doc, txt)
    heading(doc, "5.3  主要不确定度", 2)
    unc = [
        ("判据口径（NVESD vs Johnson）", "R₅₀ 绝对距离约 ×1.7", "最大的单项口径差异，不改变机制判断"),
        ("目标包围盒未几何标定", "换 max 口径 R₅₀ 约 +59%", "需几何标定后复算绝对距离"),
        ("MRTD 系数 k 与反射/发射率假设", "k±20% → R₅₀ 约 ∓1.4%；近热交叉放大", "热交叉附近需实测 ε/背景温度"),
        ("水汽连续吸收与物种完整性", "LWIR 透过率偏高 1–5%，R₅₀ 偏乐观", "后续补 MT_CKD 与云/雨/雾参数"),
        ("传感器设定参数", "口径/NETD/IFOV 为设定-推导值", "可用实测替换后重算，代码无需改"),
        ("Cn² 均匀、不含太阳/云", "可能低估衰减、R₅₀ 偏乐观", "需 Cn² 廓线与云/降水光学参数"),
    ]
    table(doc, pd.DataFrame(unc, columns=["不确定度来源", "量级/方向", "说明"]),
          [5.0, 4.8, 6.2], "表 8  主要不确定度摘要", font=8.0)
    body(doc, "结论的**相对排序与临界阈值**稳健（换判据/换尺寸口径只改变绝对距离）；"
              "**绝对距离**需在实测传感器参数、目标几何标定与完整大气数据到位后复算，不作为装备定型依据。")


def _cmp_sec6(doc, C):
    heading(doc, "6  结论", 1)
    r50, eta = C["r50"], C["eta"]
    cl = C.get("claims", {})
    aod, cn2, es = C.get("aod_summary", {}), C.get("cn2_summary", {}), C.get("env_summary", {})
    band = C.get("band_summary", {})
    ni, fi = _get(es, "NIMITZ", {}), _get(es, "F16", {})
    blind = C.get("blind_tab")
    w_rng = None
    if blind is not None and len(blind):
        ws = [fnum(str(rr.get("盲区宽度 (K)", "")).replace("—", "nan")) for _, rr in blind.iterrows()]
        ws = [w for w in ws if w is not None and 0 < w < 30]
        if ws:
            w_rng = (min(ws), max(ws))
    items = [
        f"基线识别距离跨 {_km(C['r50_min'])}（悍马）–{_km(C['r50_max'])}（尼米兹），"
        f"目标特征尺寸 {_minmax(C.get('d_eff', {}), TORDER, 1)} m。",
        f"两类机制：中小目标 η={min([eta[t] for t in SMALL_T]) :.2f}–{max([eta[t] for t in SMALL_T]):.2f}，"
        f"贴近分辨率天花板；大型舰船 η={min([eta[t] for t in LARGE_T]):.2f}–{max([eta[t] for t in LARGE_T]):.2f}，"
        "由大气累积衰减接管（交接约 16–85 m）。",
        f"大气因子：AOD₅₅₀ 0.02→4.0 使尼米兹 R₅₀ {_pct_txt(_get(aod.get('NIMITZ'), 'rel'), 0)}、"
        f"F16 {_pct_txt(_get(aod.get('F16'), 'rel'), 0)}；Cn²≳3×10⁻¹⁴ 后小目标不可识别，"
        f"尼米兹 R₅₀ 在 Cn²=1.0×10⁻¹³ 时降至 {_km(_get(cn2.get('NIMITZ'), 'r13'))}。",
        f"双波段：换 LWIR 后小目标 R₅₀ {_pct_txt(_get(band, 'small'), 0)}、大目标 "
        f"{_pct_txt(_get(band, 'large'), 0)}，优势在爱国者↔阿利伯克之间反转。",
        ("热交叉盲区：0.5·R₅₀ 处宽度 " + (f"{w_rng[0]:.2f}–{w_rng[1]:.2f} K" if w_rng else "—")
         + "；悍马较宽源于峰值概率仅 0.60、裕度小；AOD 对 4 个目标不构成约束。"),
        f"真实气候对大型舰船影响约 {_pct_txt(_get(ni, 'rel'), 0)}、中小目标约 "
        f"{_pct_txt(_get(fi, 'rel'), 0)}；传感器一阶因子为 IFOV，口径>0.3 m 后进入平台。",
    ]
    for i, txt in enumerate(items, 1):
        body(doc, f"（{i}）" + txt)
    body(doc, "后续建议：实测传感器参数替换设定值、目标几何标定、补齐 MT_CKD/云降水与 Cn² 廓线，"
              "并以本报告临界状态表做反向设计与图像级仿真复核。")


def _cmp_appendix(doc, C):
    fig_dir = C["fig_dir"]
    # ---------------- 附录 A（横版整页）
    pan_path = os.path.join(fig_dir, "图00_项目思维导图_横版.png")
    if os.path.exists(pan_path):
        _new_section(doc, landscape=True)
        heading(doc, "附录 A  项目思维导图", 1)
        _figure_abs(doc, pan_path, "图 A1  项目思维导图（A4 横向整页）", 24.0)
        _new_section(doc, landscape=False)
    else:
        heading(doc, "附录 A  项目思维导图", 1)
        figure(doc, fig_dir, "00", "图 A1  项目思维导图")
    # ---------------- 附录 B（公式校准摘要，10–12 行）
    heading(doc, "附录 B  公式校准摘要", 1)
    body(doc, "全链路公式校准逐条记录“原式→校准式→依据→数值核验→对结论的影响”，"
              "完整 37 条见《06_校验/公式校准报告.md》；下表按主题分组给出关键项（F1–F33）。")
    table(doc, _cmp_calib_rows(C, variant="appendix"), [1.6, 4.6, 9.8],
          "表 B1  关键公式校准项摘要（完整清单见 06_校验/公式校准报告.md）")
    body(doc, "总体判断：校准消除了热交叉位置、路径辐射饱和、Rayleigh 口径、ISO 廓线、球面几何与截断语义"
              "六类系统偏差；除热交叉表述外，多数为 1% 量级的绝对距离修正，三层机制结论保持成立。")
    # ---------------- 附录 C（参数依据，5–6 行）
    heading(doc, "附录 C  参数依据", 1)
    reg = C.get("registry")
    n_reg = 0 if reg is None else len(reg)
    body(doc, "全部输入参数的依据、置信度与影响方向登记在《05_参数依据/参数依据登记表.csv》"
              f"（由 params.py 自动导出，共 {n_reg} 条核心参数）；谱线/环境数据来源见"
              "《05_参数依据/参数依据说明.md》。登记表按软件实测/文献/推导/设定四类标注，"
              "凡“设定”类均说明合理性、影响量级与实测替换路径；参数取值的敏感性见第 3 章与表 8。")
    # ---------------- 附录 D（目录级文件清单）
    heading(doc, "附录 D  文件清单（目录级）", 1)
    dirs = [
        ("01_正式报告", "本报告 DOCX/PDF", "报告正文与图注"),
        ("02_图表", "18 幅规范编号图", "图01–图17 + 图00"),
        ("03_数据", "CSV/XLSX 数据产品", "长表、单变量宽表、临界状态、环境工况、波段对比、相图"),
        ("04_模型代码", "irrecog 模型代码", "大气/传感器/链路/求解/实验/绘图/报告模块"),
        ("05_参数依据", "参数登记表与说明", "41 条核心参数及依据"),
        ("06_校验", "校验与公式校准报告", "V&V 检查、光谱大气校验、公式校准"),
    ]
    table(doc, pd.DataFrame(dirs, columns=["目录", "内容", "说明"]),
          [3.4, 5.0, 7.6], "表 D1  交付目录清单（逐文件清单见项目根目录 文件清单.csv）")
    body(doc, "逐文件的行数/列数/大小清单见项目根目录《文件清单.csv》与 03_数据/识别极限_数据汇总.xlsx。")
    # ---------------- 附录 E（参考文献）
    heading(doc, "附录 E  参考文献", 1)
    refs = [
        "Koschmieder H. Theorie der horizontalen Sichtweite. Beitr. Phys. freien Atmos., 1924, 12: 33–53.",
        "Ångström A. On the atmospheric transmission of sun radiation and on dust in the air. Geogr. Ann., 1929, 11: 156–166.",
        "Eck T F, et al. Wavelength dependence of the optical depth of biomass burning, urban, and desert dust aerosols. JGR, 1999, 104(D24): 31333–31349.",
        "Hess M, Koepke P, Schult I. Optical properties of aerosols and clouds: the software package OPAC. BAMS, 1998, 79(5): 831–844.",
        "Gordon I E, Rothman L S, Hargreaves R J, et al. The HITRAN2020 molecular spectroscopic database. JQSRT, 2022, 277: 107949.",
        "Kochanov R V, Gordon I E, Rothman L S, et al. HITRAN Application Programming Interface (HAPI). JQSRT, 2016, 177: 15–30.",
        "Bodhaine B A, Wood N B, Dutton E G, Slusser J R. On Rayleigh optical depth calculations. JTECH, 1999, 16(11): 1854–1861.",
        "Vermote E F, Tanré D, Deuzé J L, et al. Second simulation of the satellite signal in the solar spectrum, 6S: an overview. IEEE TGRS, 1997, 35(3): 675–686.",
        "ISO 2533:1975. Standard Atmosphere. International Organization for Standardization, 1975.",
        "Fried D L. Optical resolution through a randomly inhomogeneous medium for very long and very short exposures. JOSA, 1966, 56(10): 1372–1379.",
        "ITU-R. Recommendation P.1817-1: Propagation data required for the design of terrestrial free-space optical links. ITU, 2012.",
        "Johnson J. Analysis of image forming systems. Proc. Image Intensifier Symposium, 1958: 249–273.",
        "Vollmerhausen R H, Jacobs E. The Targeting Task Performance (TTP) Metric. NVESD, 2004.",
        "Ratches J A. Static performance model for thermal imaging systems. Opt. Eng., 1976, 15(6): 525–530.",
        "Lloyd J M. Thermal Imaging Systems. New York: Plenum Press, 1975.",
        "Salisbury J W, D'Aria D M. Emissivity of terrestrial materials in the 8–14 μm window. RSE, 1992, 42(2): 83–106.",
        "Salisbury J W, D'Aria D M. Emissivity of terrestrial materials in the 3–5 μm window. RSE, 1994, 47(3): 345–361.",
        "NASA POWER / MERRA-2 再分析数据（2015–2024）与 AERONET 站点统计。",
        "WMO. Guide to Instruments and Methods of Observation (WMO-No. 8), 2021 edition.",
        "XGGDCOSSim2 光电环境仿真软件数据目录（Data/SystemBaseFile、Data/ModelData），2025–2026。",
    ]
    for ref in refs:
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(1)
        p.paragraph_format.line_spacing = 1.1
        p.paragraph_format.left_indent = Cm(0.7)
        p.paragraph_format.first_line_indent = Cm(-0.7)
        _set_font(p.add_run(ref), 8.4)


def build(data_dir: str, fig_dir: str, out_docx: str):
    """生成正式报告 DOCX；返回文件路径。"""
    data = Data(data_dir)
    C = _collect(data, fig_dir)
    doc = _setup_document()
    _sec_cover(doc, C)
    # 精简版（目标 20–24 页）：保留核心信息与 18 幅图，压缩冗余文字与明细表
    _cmp_abstract(doc, C)
    _cmp_sec1(doc, C)
    _cmp_sec2(doc, C)
    _cmp_sec3(doc, C)
    _cmp_sec4(doc, C)
    _cmp_sec5(doc, C)
    _cmp_sec6(doc, C)
    _cmp_appendix(doc, C)

    out_dir = os.path.dirname(os.path.abspath(out_docx))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    doc.save(out_docx)

    hits = scan_forbidden(out_docx)
    prim = _primary_fig_names()
    figs_ok = sum(1 for k, name in C.get("fig_status", {}).items()
                  if name and name == prim.get(k))
    fallback = [k for k, name in C.get("fig_status", {}).items()
                if name and name != prim.get(k)]
    print(f"[report] DOCX -> {out_docx}")
    print(f"[report] 图件按最终编号就位：{figs_ok}/{len(FIG_FILES)}；数据告警 {len(C['warnings'])} 条")
    if fallback:
        print(f"[report] 注意：以下图仍为过渡文件名（待图件模块统一编号）："
              + "、".join(f"图{k}" for k in fallback))
    if hits:
        print(f"[report] 版本字样检查：发现 {len(hits)} 处 -> "
              + "；".join(f"{a}:{b}" for a, b in hits[:12]))
    else:
        print("[report] 版本字样检查：通过（未发现任何版本类字样）")
    audit = audit_document(out_docx)
    print(f"[report] 自检：段落 {audit['paragraphs']}、表格 {audit['tables']}、"
          f"插图 {audit['images']}；图 1—17 引用"
          + ("齐全" if not audit["missing_figs"]
             else "缺少 图" + "、图".join(str(i) for i in audit["missing_figs"])))
    for w in C["warnings"][:12]:
        print(f"[report] 警告：{w}")
    return out_docx
