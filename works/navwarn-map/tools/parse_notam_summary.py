#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
解析中国民航局空管局情报中心（eAIP China）公开的《NOTAM Summary》月度汇总，
提取“临时危险区 / 特别限制区”等面状 NOTAM，输出 notams.json + notams.js（供地图直接 <script> 加载）。

数据源（免费、无需登录）：
    https://www.eaipchina.cn/eaip/homeFile/listPublish        （POST，列出已发布文件）
    https://www.eaipchina.cn/eaip/homeFile/NOTAM_SUMMARY/.../2026-11.zip  （月度汇总，含 A/E/F/G/L/M/U/W/Y 系列 PDF）

用法：
    python parse_notam_summary.py <txt目录> <输出目录>
"""
import sys, os, re, json, datetime

CST = datetime.timezone(datetime.timedelta(hours=8))
UTC = datetime.timezone.utc

HEAD = re.compile(r'^([A-Z])\s+(\d{4})/(\d{2})\s*$', re.M)
DMS_E = re.compile(r'N\s*(\d{2})\s*(\d{2})\s*(\d{2})?\s*E\s*(\d{3})\s*(\d{2})\s*(\d{2})?', re.I)
CIRCLE = re.compile(
    r'RADIUS OF\s*([\d.]+)\s*(KM|NM)\s+CENTERED AT\s*N\s*(\d{6})\s*E\s*(\d{6})', re.I)
TIME = re.compile(r'(\d{4})/(\d{2})/(\d{2})/(\d{2})(\d{2})')

KEEP_FROM = datetime.datetime(2026, 11, 1, tzinfo=UTC)   # 只保留 11 月仍有效/生效的区域


def blocks(text):
    ms = list(HEAD.finditer(text))
    for i, m in enumerate(ms):
        end = ms[i + 1].start() if i + 1 < len(ms) else len(text)
        yield m.group(1), m.group(2), m.group(3), text[m.start():end]


def fld(b, L):
    m = re.search(r'\b' + L + r'\)\s*(.*?)(?=\s[A-G]\)\s|$)', b, re.S)
    return re.sub(r'\s+', ' ', m.group(1)).strip() if m else ''


def parse_time(s):
    m = TIME.search(s or '')
    if not m:
        return None
    return datetime.datetime(*(int(x) for x in m.groups()), tzinfo=UTC)


def dms(deg, minu, sec):
    return int(deg) + int(minu) / 60 + (float(sec) / 3600 if sec else 0)


def extract_geometry(e):
    """返回 (geom, kind) —— geom 为 {'kind':'circle',...} 或 {'kind':'polygon',...}"""
    m = CIRCLE.search(e)
    if m:
        r = float(m.group(1)) * (1000 if m.group(2).upper() == 'KM' else 1852)
        lat = dms(m.group(3)[:2], m.group(3)[2:4], m.group(3)[4:6])
        lng = dms(m.group(4)[:3], m.group(4)[3:5], m.group(4)[5:7])
        return {'kind': 'circle', 'center': [round(lat, 6), round(lng, 6)],
                'radius_m': round(r)}, 'circle'
    pts = []
    for m in DMS_E.finditer(e):
        lat = dms(m.group(1), m.group(2), m.group(3))
        lng = dms(m.group(4), m.group(5), m.group(6))
        pts.append([round(lat, 6), round(lng, 6)])
    if len(pts) >= 3:
        return {'kind': 'polygon', 'coords': pts}, 'polygon'
    return None, None


def classify(e):
    t = e.upper()
    if 'DANGER AREA' in t:
        return '临时危险区'
    if 'PROHIBITED AREA' in t or 'PROHIBITED' in t:
        return '禁飞区'
    if 'RESTRICTED AREA' in t or 'SPECIAL RESTRICTION' in t:
        return '限制区'
    if 'TEMPORARY AREA' in t:
        return '临时区域'
    return None


def status(begin, end, now):
    if end == 'PERM' or end is None:
        return 'active' if (begin is None or begin <= now) else 'upcoming'
    if begin and begin > now:
        return 'upcoming'
    if end < now:
        return 'ended'
    return 'active'


def main(txt_dir, out_dir):
    now = datetime.datetime.now(UTC)
    out = []
    seen = set()
    for fn in sorted(os.listdir(txt_dir)):
        if not fn.lower().endswith('.txt'):
            continue
        text = open(os.path.join(txt_dir, fn), encoding='utf-8', errors='ignore').read()
        for series, num, yy, b in blocks(text):
            e = fld(b, 'E')
            kind_name = classify(e)
            if not kind_name:
                continue
            geom, gkind = extract_geometry(e)
            if not geom:
                continue
            begin = parse_time(fld(b, 'B'))
            craw = fld(b, 'C')
            perm = 'PERM' in craw.upper()
            end = 'PERM' if perm else parse_time(craw)
            nid = f'{series} {num}/{yy}'
            if nid in seen:
                continue
            seen.add(nid)
            if end != 'PERM' and end is not None and end < KEEP_FROM:
                continue
            out.append({
                'id': nid,
                'fir': fld(b, 'A'),
                'kind': kind_name,
                'status': status(begin, end, now),
                'begin_utc': begin.isoformat() if begin else None,
                'end_utc': end if end == 'PERM' else (end.isoformat() if end else None),
                'geom': geom,
                'e': e[:900],
            })
    # ---- 合并手工补充的 NOTAM（manual_notams.json，格式同上，可来自用户粘贴的原文） ----
    manual_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'manual_notams.json')
    if os.path.exists(manual_path):
        def iso(s):
            return datetime.datetime.fromisoformat(s.replace('Z', '+00:00')) if s else None
        for m in json.load(open(manual_path, encoding='utf-8')):
            if m['id'] in seen:
                continue
            b_, e_ = iso(m.get('begin_utc')), m.get('end_utc')
            e_ = 'PERM' if e_ == 'PERM' else iso(e_)
            m['status'] = m.get('status') or status(b_, e_, now)
            m.setdefault('source', 'manual')
            out.append(m)
            seen.add(m['id'])

    rank = {'active': 0, 'upcoming': 1, 'ended': 2}
    out.sort(key=lambda x: (rank.get(x['status'], 3), x['id']))
    payload = {
        'generated': datetime.datetime.now(CST).isoformat(),
        'source': 'CAAC AIS eAIP China · NOTAM Summary In Nov.2026（2026-11-02 00:06 UTC 快照）',
        'source_url': 'https://www.eaipchina.cn/',
        'count': len(out),
        'notams': out,
    }
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, 'notams.json'), 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    with open(os.path.join(out_dir, 'notams.js'), 'w', encoding='utf-8') as f:
        f.write('/* 自动生成：parse_notam_summary.py */\n')
        f.write('window.NOTAM_DATA = ')
        json.dump(payload, f, ensure_ascii=False, indent=1)
        f.write(';\n')
    print(f'NOTAM 面状区域 {len(out)} 条 -> {out_dir}/notams.json / notams.js')
    for n in out:
        print(' ', n['status'], n['id'], n['fir'], n['kind'], n['begin_utc'], n['end_utc'], n['geom']['kind'])


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else '.')
