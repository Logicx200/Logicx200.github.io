# -*- coding: utf-8 -*-
"""
解析 MassFlow 输出的 Tecplot 文件，提取每帧的流体厚度场，
转成 GeoTIFF 并出图。
Tecplot ASCII 格式: 变量头 + ZONE + 数据块
"""
import os
import re
import sys
import numpy as np

W = r'F:\DeepSeek工作区\jilong'
RUN = os.path.join(W, 'mf_run')
OUT = os.path.join(W, 'results')
os.makedirs(OUT, exist_ok=True)


def parse_header(path, max_lines=200):
    """读取文件头，识别变量名、zone 数与每 zone 的节点数。"""
    vars_ = []
    zones = []
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        for i, line in enumerate(f):
            if i > max_lines:
                break
            ls = line.strip()
            if ls.upper().startswith('VARIABLES'):
                rest = ls.split('=', 1)[1] if '=' in ls else ls
                parts = re.findall(r'"([^"]+)"', rest)
                if not parts:
                    parts = rest.replace(',', ' ').split()
                vars_ = [p.strip() for p in parts]
            m = re.search(r'ZONE\s+.*?N\s*=\s*(\d+)', ls, re.I)
            if m:
                zones.append(int(m.group(1)))
            m2 = re.search(r'ZONE\s+.*?I\s*=\s*(\d+).*?J\s*=\s*(\d+)', ls, re.I)
            if m2:
                zones.append(int(m2.group(1)) * int(m2.group(2)))
    return vars_, zones


if __name__ == '__main__':
    files = sorted([f for f in os.listdir(RUN) if f.startswith('output') and f.endswith('.plt')])
    print('输出文件:', files)
    for fn in files:
        p = os.path.join(RUN, fn)
        sz = os.path.getsize(p) / 1e6
        v, z = parse_header(p)
        print()
        print('=== %s  (%.1f MB) ===' % (fn, sz))
        print('  变量 (%d): %s' % (len(v), v[:20]))
        print('  前若干 ZONE 节点数: %s' % z[:10])
