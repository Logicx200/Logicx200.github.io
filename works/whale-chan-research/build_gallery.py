# -*- coding: utf-8 -*-
"""生成自包含的鲸鱼娘 Q 版候选图库 HTML（缩略图内嵌 base64，无外部依赖）。"""
import base64
import io
import os
import re
import sys
from PIL import Image

BASE = os.getcwd()
IMG_DIR = os.path.join(BASE, "img")
OUT = os.path.join(BASE, "候选图库.html")

if not os.path.isdir(IMG_DIR):
    sys.exit("找不到图片目录: %s （请在该脚本所在目录运行）" % IMG_DIR)

THUMB_MAX = (460, 460)

# 候选分组：顺序即展示顺序
GROUPS = [
    ("B", "候选 1 · 大肥鱼（最推荐）", "YunYueSama / codex-deepseek-pet",
     "整只都是 2 头身 Q 版，而且已有完整动作序列帧——这是它最大的优势。",
     "https://github.com/YunYueSama/codex-deepseek-pet"),
    ("C", "候选 2 · 大肥鱼三视图 PNG", "1190fasheqi / dafeiyu-pet",
     "已经是透明背景 PNG，扔进桌宠框架几乎不用处理，但分辨率偏小（约 255×340）。",
     "https://github.com/1190fasheqi/dafeiyu-pet"),
    ("F", "候选 3 · 女仆鲸鱼娘图标", "Small-tailqwq / dsh-deep-whale",
     "画风干净、带透明通道，最适合做小尺寸图标或托盘宠物。",
     "https://github.com/small-tailqwq/dsh-deep-whale"),
    ("A", "候选 4 · Whale-chan 设定集", "Neko3000 / deepseek-whalechan",
     "主立绘偏美少女比例，但附带大量 Q 版素材，是设定最全的一套（三视图 + 配色 + 11 种表情）。",
     "https://github.com/Neko3000/deepseek-whalechan"),
    ("D", "候选 5 · Live2D 会动的", "Andersen216 / A8Chann",
     "带物理和 30+ 表情的 Live2D 模型。授权 CC BY-NC-SA 4.0，明确禁止商用。",
     "https://github.com/Andersen216/dsh-whale-girl-live2d"),
    ("E", "候选 6 · 表情包图库", "the-beating-light-of-the-nail / deepseek-chan-meme-pack",
     "474 张梗图，适合切图做贴纸和台词气泡。",
     "https://github.com/the-beating-light-of-the-nail/deepseek-chan-meme-pack"),
]

META = {
    "B1": ("角色标准与动作", "六视图 + 4 种表情 + 待机/走路/吃东西/哼歌", "最完整的 Q 版设定图"),
    "B2": ("角色标准图", "造型规范", ""),
    "B3": ("半身立绘", "Q 版半身", ""),
    "B4": ("动作分镜", "动作分解高清图", ""),
    "B5": ("正面待机（高清）", "睁眼 + 闭眼两态，透明底", "做桌宠待机帧的首选"),
    "B6": ("精灵图集 ★", "走路 16 帧循环 / 挥手 / 跳舞 / 偷吃 / 蜷睡 / 跳跃 23 帧", "直接可用于逐帧桌宠"),
    "B7": ("神态参考 · 眨眼", "社区参考", ""),
    "B8": ("神态参考 · 欢呼", "社区参考", ""),
    "B9": ("桌面陪伴面板实拍", "聊天、喂食、一起专注", "实际效果长这样"),
    "C1": ("正面", "透明底 PNG，约 255×340", ""),
    "C2": ("侧面", "透明底 PNG", ""),
    "C3": ("托盘图标", "小尺寸图标", ""),
    "F1": ("图标多尺寸预览", "开心/兴奋/傲娇 三表情 × 亮暗两版", "小尺寸下依然清晰"),
    "F2": ("512px 抠图", "带透明通道", "可直接当桌宠贴图"),
    "A1": ("角色全貌三视图", "正/侧/背 + 尾部结构，Q 版比例", ""),
    "A2": ("11 种 Q 版表情 ★", "温柔/开朗/得意/害羞/犯困/委屈/气鼓鼓…", "桌宠表情表的最佳参考"),
    "A3": ("配色材质规范", "色卡与材质", ""),
    "A4": ("一天的状态", "开机/专注/恢复/补给/休息/倦怠", ""),
    "A5": ("主视觉海报", "非 Q 版，作风格参考", ""),
    "A6": ("姿势指南", "姿势与动态", ""),
    "A7": ("表情潮汐（英文版）", "A2 的英文排版版", ""),
    "D1": ("趴桌待机（Q 版）", "带收起/归位按钮", ""),
    "D2": ("可换外观一览", "多套外观", ""),
    "D3": ("右键设置面板", "实际界面", ""),
    "D4": ("真实桌面效果", "在桌面上跑起来的样子", ""),
    "E1": ("梗图 · 点头认可", "Oh, so you ARE a premium model", ""),
    "E2": ("梗图 · 哭求", "用户别走，我上错模型了", ""),
    "E3": ("梗图 · 角色互换", "OK, now I'm the user", ""),
}


def thumb_b64(path):
    im = Image.open(path)
    im = im.convert("RGBA") if im.mode in ("P", "LA") else im.convert("RGB")
    im.thumbnail(THUMB_MAX, Image.LANCZOS)
    buf = io.BytesIO()
    if im.mode == "RGBA":
        im.save(buf, format="PNG", optimize=True)
        mime = "image/png"
    else:
        im.save(buf, format="JPEG", quality=82, optimize=True)
        mime = "image/jpeg"
    return "data:%s;base64,%s" % (mime, base64.b64encode(buf.getvalue()).decode("ascii"))


def esc(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


cards_html = []
missing = []
total = 0
for prefix, gtitle, gauthor, gdesc, glink in GROUPS:
    # 文件名形如 B1-xxx.png / B12-xxx.png：前缀后紧跟数字，再接连字符
    files = sorted(f for f in os.listdir(IMG_DIR)
                   if f.startswith(prefix) and re.match(r"^\d+-", f[len(prefix):]))
    if not files:
        continue
    items = []
    for fn in files:
        key = fn.split("-")[0]
        title, desc, note = META.get(key, (fn, "", ""))
        path = os.path.join(IMG_DIR, fn)
        try:
            data = thumb_b64(path)
        except Exception as exc:  # noqa: BLE001
            missing.append("%s: %s" % (fn, exc))
            continue
        w, h = Image.open(path).size
        total += 1
        badge = '<span class="badge">%s</span>' % esc(note) if note else ""
        items.append("""
      <figure class="card">
        <a class="thumb" href="img/{fn}" target="_blank" title="点击查看原图">
          <img src="{data}" alt="{alt}" loading="lazy">
        </a>
        <figcaption>
          <h4>{title}{badge}</h4>
          <p>{desc}</p>
          <span class="file">img/{fn} · {w}×{h}</span>
        </figcaption>
      </figure>""".format(
            fn=esc(fn), data=data, alt=esc(title),
            title=esc(title), badge=badge, desc=esc(desc), w=w, h=h,
        ))
    cards_html.append("""
  <section class="group">
    <header>
      <h2>{gtitle}</h2>
      <p class="src"><a href="{glink}" target="_blank" rel="noreferrer">{gauthor}</a></p>
      <p class="gdesc">{gdesc}</p>
    </header>
    <div class="grid">{items}
    </div>
  </section>""".format(gtitle=esc(gtitle), glink=esc(glink), gauthor=esc(gauthor),
                         gdesc=esc(gdesc), items="".join(items)))

HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>DeepSeek 鲸鱼娘 · Q 版桌宠候选图库</title>
<style>
  :root {{ --navy:#1b3a6b; --blue:#3b6fb5; --bg:#f4f7fc; --line:#d8e3f3; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; padding:32px 20px 64px; background:var(--bg); color:#22303f;
         font-family:"Microsoft YaHei","PingFang SC",system-ui,sans-serif; line-height:1.6; }}
  .wrap {{ max-width:1180px; margin:0 auto; }}
  h1 {{ color:var(--navy); font-size:30px; margin:0 0 8px; }}
  .lead {{ color:#5b6b80; margin:0 0 6px; }}
  .note {{ background:#fff8e6; border-left:4px solid #e6b23c; padding:10px 14px;
           border-radius:6px; font-size:14px; margin:18px 0 30px; }}
  .group {{ margin:0 0 44px; }}
  .group > header {{ border-bottom:2px solid var(--line); padding-bottom:10px; margin-bottom:18px; }}
  h2 {{ color:var(--navy); font-size:22px; margin:0 0 4px; }}
  .src {{ margin:0; font-size:13px; }}
  .src a {{ color:var(--blue); text-decoration:none; }}
  .src a:hover {{ text-decoration:underline; }}
  .gdesc {{ margin:6px 0 0; font-size:14px; color:#5b6b80; }}
  .grid {{ display:grid; gap:18px; grid-template-columns:repeat(auto-fill,minmax(250px,1fr)); }}
  .card {{ margin:0; background:#fff; border:1px solid var(--line); border-radius:12px;
           overflow:hidden; display:flex; flex-direction:column;
           box-shadow:0 1px 3px rgba(27,58,107,.06); }}
  .thumb {{ display:flex; align-items:center; justify-content:center; height:230px;
            background:repeating-conic-gradient(#eef3fa 0% 25%, #ffffff 0% 50%) 50%/18px 18px;
            overflow:hidden; }}
  .thumb img {{ max-width:100%; max-height:230px; object-fit:contain; transition:transform .18s; }}
  .thumb:hover img {{ transform:scale(1.05); }}
  figcaption {{ padding:10px 13px 13px; border-top:1px solid var(--line); }}
  h4 {{ margin:0 0 4px; font-size:15px; color:var(--navy); }}
  figcaption p {{ margin:0; font-size:13px; color:#5b6b80; }}
  .file {{ display:block; margin-top:7px; font-size:11px; color:#93a2b5;
           font-family:Consolas,monospace; word-break:break-all; }}
  .badge {{ display:inline-block; margin-left:6px; padding:1px 7px; border-radius:99px;
            background:#e8f1ff; color:var(--blue); font-size:11px; font-weight:400;
            vertical-align:middle; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>🐋 DeepSeek 鲸鱼娘 · Q 版桌宠候选图库</h1>
  <p class="lead">共 {total} 张图，全部为社区二创素材，已内嵌于本页，无需联网。</p>
  <p class="lead">搜集时间 2026-09-30　点击任意图片可查看原始分辨率大图。</p>
  <div class="note">
    <strong>授权提示：</strong>候选 5（Live2D）为 <strong>CC BY-NC-SA 4.0，明确禁止商用</strong>；
    候选 1、3 为自定义许可；候选 4、6 未声明许可。个人自用无妨，商用或公开分发前请逐个确认。
  </div>
  {cards}
</div>
</body>
</html>
""".format(total=total, cards="".join(cards_html))

with open(OUT, "w", encoding="utf-8") as fh:
    fh.write(HTML)

print("生成:", OUT)
print("内嵌图片:", total, "张")
print("输出大小: %.1f MB" % (os.path.getsize(OUT) / 1024 / 1024))
if missing:
    print("失败:", missing)
