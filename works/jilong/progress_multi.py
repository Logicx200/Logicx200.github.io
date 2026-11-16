# -*- coding: utf-8 -*-
"""
生成多算例进度面板 progress.html（自包含，无 fetch）。
监控对象可配置；每 5 秒重写一次。
"""
import os
import re
import sys
import json
import time
import glob
from datetime import datetime

B = r'F:\DeepSeek工作区\jilong'
HTML = os.path.join(B, 'progress.html')

# (标签, 目录, 总时长 s, 网格描述)
RUNS = [
    ('收敛检验 40 m', 'cv_coarse40', 700, '450 x 48 = 21,600 格  (dx=40 m, dy=280 m)'),
    ('收敛检验 30 m', 'cv_mid30', 700, '600 x 68 = 40,800 格  (dx=30 m, dy=200 m)'),
    ('高精度 15 m', 'hi15', 1200, '1067 x 90 = 96,030 格  (dx=15 m, dy=135 m)'),
]

def read_log_text(path):
    """PowerShell *> 重定向可能是 UTF-16LE，也可能是 UTF-8/ANSI，自适应读取。"""
    try:
        raw = open(path, 'rb').read()
    except Exception:
        return ''
    if not raw:
        return ''
    if raw[:2] in (b'\xff\xfe', b'\xfe\xff'):
        return raw.decode('utf-16', errors='replace')
    if b'\x00' in raw[:200]:
        return raw.decode('utf-16-le', errors='replace')
    try:
        return raw.decode('utf-8')
    except UnicodeDecodeError:
        return raw.decode('gbk', errors='replace')


def read_run(d, total):
    log = os.path.join(B, d, 'stdout.log')
    st = dict(pct=None, sim=None, done=False, frames=0, mb=0.0, alive=False)
    if os.path.exists(log):
        txt = read_log_text(log)
        for ln in reversed(txt.split('\n')):
            m = re.search(r'([0-9]+\.[0-9]+)\s*%\s*$', ln)
            if m:
                st['pct'] = float(m.group(1))
                try:
                    st['sim'] = float(ln.split()[0])
                except Exception:
                    pass
                break
        st['done'] = 'Computation is done' in txt
    outs = glob.glob(os.path.join(B, d, 'output*.plt'))
    st['frames'] = len(outs)
    st['mb'] = sum(os.path.getsize(f) for f in outs) / 1048576.0
    if os.path.exists(log):
        st['alive'] = (time.time() - os.path.getmtime(log)) < 180 and not st['done']
    return st


def bar(pct, cls='fill'):
    p = max(0.0, min(100.0, pct or 0))
    return ('<div class="bar"><div class="%s" style="width:%.1f%%"></div></div>'
            % (cls, p))


TEMPLATE = """<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<title>MassFlow 计算进度 — 吉隆冰崩</title>
<meta http-equiv="refresh" content="5">
<style>
 :root{color-scheme:dark}
 *{box-sizing:border-box}
 body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;
   background:#0d1117;color:#e6edf3;font:15px/1.55 "Segoe UI","Microsoft YaHei",system-ui,sans-serif}
 .card{width:min(880px,94vw);padding:30px 34px;background:#161b22;border:1px solid #30363d;
   border-radius:14px;box-shadow:0 12px 44px rgba(0,0,0,.55)}
 h1{margin:0 0 4px;font-size:21px}
 .sub{color:#8b949e;font-size:13px;margin-bottom:22px}
 .run{border-top:1px solid #21262d;padding:16px 0 6px}
 .run:first-of-type{border-top:none}
 .row{display:flex;align-items:baseline;gap:12px;margin-bottom:6px}
 .name{font-weight:700;font-size:15.5px}
 .tag{font-size:11.5px;font-weight:700;padding:2px 9px;border-radius:999px;
   background:#1f6feb22;color:#58a6ff;border:1px solid #1f6feb55}
 .tag.done{background:#3fb95022;color:#3fb950;border-color:#3fb95055}
 .tag.stall{background:#d2992222;color:#d29922;border-color:#d2992255}
 .tag.wait{background:#8b949e22;color:#8b949e;border-color:#8b949e55}
 .pv{margin-left:auto;font-size:23px;font-weight:800;font-variant-numeric:tabular-nums}
 .grid{color:#6e7681;font-size:12px;margin-bottom:8px}
 .bar{height:14px;background:#21262d;border-radius:7px;overflow:hidden}
 .fill{height:100%;background:linear-gradient(90deg,#1f6feb,#58a6ff);transition:width .5s}
 .fill.done{background:linear-gradient(90deg,#238636,#3fb950)}
 .meta{color:#8b949e;font-size:12px;margin-top:7px}
 .foot{margin-top:22px;border-top:1px solid #21262d;padding-top:12px;color:#6e7681;font-size:12px}
</style></head><body>
<div class="card">
  <h1>吉隆冰崩数值模拟 — 计算进度</h1>
  <div class="sub">MassFlow 2.9 &nbsp;·&nbsp; 分辨率提升与收敛性检验 &nbsp;·&nbsp; 求解器单元格上限约 10 万</div>
  __ROWS__
  <div class="foot">最后更新 __UPDATED__ &nbsp;·&nbsp; 每 5 秒自动重载 &nbsp;·&nbsp; 数据内嵌，无需 fetch</div>
</div></body></html>
"""


def render():
    rows = []
    for label, d, total, grid in RUNS:
        st = read_run(d, total)
        pct = st['pct'] if st['pct'] is not None else 0.0
        if st['done']:
            tag, cls = '已完成', 'tag done'
        elif st['alive']:
            tag, cls = '计算中', 'tag'
        elif st['pct'] is None:
            tag, cls = '待运行', 'tag wait'
        else:
            tag, cls = '已中断', 'tag stall'
        fillcls = 'fill done' if st['done'] else 'fill'
        rows.append("""
    <div class="run">
      <div class="row">
        <span class="name">{label}</span>
        <span class="{cls}">{tag}</span>
        <span class="pv">{pct:.1f}%</span>
      </div>
      <div class="grid">{grid}</div>
      {bar}
      <div class="meta">模拟时间 {sim:.0f} / {total} s &nbsp;&middot;&nbsp; {frames} 帧 &nbsp;&middot;&nbsp; {mb:.0f} MB</div>
    </div>""".format(label=label, cls=cls, tag=tag, pct=pct, grid=grid,
                    bar=bar(pct, fillcls), sim=st['sim'] or 0,
                    total=total, frames=st['frames'], mb=st['mb']))
    return (TEMPLATE.replace('__ROWS__', ''.join(rows))
                    .replace('__UPDATED__', datetime.now().strftime('%H:%M:%S')))


if __name__ == '__main__':
    while True:
        try:
            open(HTML, 'w', encoding='utf-8').write(render())
        except Exception as e:
            sys.stderr.write('render fail: %s\n' % e)
        time.sleep(5)
