#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从 NOTAM 危险区推算“发射事件”与发射窗口（T0）的粗略估计。

思路：
  1. 取同一时段内的若干面状危险区（notams.json）
  2. 求各区域几何中心，按时间排序，计算相邻中心连线方位角
  3. 若各中心近似共线（方位差 < 5°），且某已知发射场位于该连线延长线上、方位一致，
     则判定为“该发射场的级间/整流罩残骸落区”
  4. 发射窗口：
       - 硬边界 T0 ∈ [max(B_i), min(C_i)]（所有区域同时有效的时间段）
       - 若各窗口起点几乎相同（相差 ≤ 2 min），可认为起点即“预激活时刻”，
         估算 T0 ≈ 最早 B + 1~2 min（可在 --lead 调整）
  5. 输出 trajectory.js 供地图画“推测弹道轴”

用法:
    python launch_window.py ../notams.json ../
"""
import json, math, sys, datetime

R = 6371.0088
SITES = {
    '太原': (38.849, 111.608),
    '酒泉': (40.960, 100.298),
    '西昌': (28.246, 102.027),
    '文昌': (19.614, 110.951),
    '海阳': (36.688, 121.163),
}


def hav(a, b):
    la1, lo1, la2, lo2 = map(math.radians, [a[0], a[1], b[0], b[1]])
    return 2 * R * math.asin(math.sqrt(
        math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2))


def brg(a, b):
    la1, lo1, la2, lo2 = map(math.radians, [a[0], a[1], b[0], b[1]])
    y = math.sin(lo2 - lo1) * math.cos(la2)
    x = math.cos(la1) * math.sin(la2) - math.sin(la1) * math.cos(la2) * math.cos(lo2 - lo1)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def dest(a, bearing, dist_km):
    la1, lo1 = math.radians(a[0]), math.radians(a[1])
    br = math.radians(bearing)
    d = dist_km / R
    la2 = math.asin(math.sin(la1) * math.cos(d) + math.cos(la1) * math.sin(d) * math.cos(br))
    lo2 = lo1 + math.atan2(math.sin(br) * math.sin(d) * math.cos(la1),
                           math.cos(d) - math.sin(la1) * math.sin(la2))
    return [math.degrees(la2), (math.degrees(lo2) + 540) % 360 - 180]


def center(ring):
    return [sum(p[0] for p in ring) / len(ring), sum(p[1] for p in ring) / len(ring)]


def parse(s):
    return datetime.datetime.fromisoformat(s.replace('Z', '+00:00')) if s and s != 'PERM' else None


def main(notams_path, out_dir, lead_min=1.5):
    data = json.load(open(notams_path, encoding='utf-8'))
    areas = [n for n in data['notams']
             if n['geom']['kind'] == 'polygon' and n['status'] in ('active', 'upcoming')
             and n.get('begin_utc') and n.get('end_utc') and n['end_utc'] != 'PERM']
    if len(areas) < 2:
        print('有效面状危险区不足 2 条，无法推断'); return
    areas.sort(key=lambda x: x['begin_utc'])
    for n in areas:
        n['_c'] = center(n['geom']['coords'])

    bs = [brg(areas[i]['_c'], areas[i + 1]['_c']) for i in range(len(areas) - 1)]
    bearing = sum(bs) / len(bs)
    spread = max(abs(((b - bearing + 180) % 360) - 180) for b in bs)

    best = None
    for name, s in SITES.items():
        d = hav(s, areas[0]['_c'])
        b = brg(s, areas[0]['_c'])
        dev = abs(((b - bearing + 180) % 360) - 180)
        if best is None or dev < best[2]:
            best = (name, d, dev)
    site, dist0, dev = best

    B = max(parse(n['begin_utc']) for n in areas)
    C = min(parse(n['end_utc']) for n in areas)
    starts = sorted(parse(n['begin_utc']) for n in areas)
    same_start = (starts[-1] - starts[0]).total_seconds() <= 120
    t0 = starts[0] + datetime.timedelta(minutes=lead_min) if same_start else B

    print(f'危险区 {len(areas)} 个，连线方位 {bearing:.1f}°（最大偏差 {spread:.1f}°）')
    print(f'最佳匹配发射场：{site}，距第一落区 {dist0:.0f} km，方位偏差 {dev:.1f}°')
    print(f'T0 硬边界：[{B.isoformat()} , {C.isoformat()}]')
    print(f'T0 估算：{t0.isoformat()}（±{int((starts[0]-B).total_seconds()/60)+3} min，依据窗口起点 {"相同" if same_start else "不同"}）')

    path = [[*SITES[site]]] + [n['_c'] for n in areas]
    last = path[-1]
    path.append(dest(last, bearing, 700))

    traj = {
        'event_guess': f'{site} 发射（推测）',
        'bearing_deg': round(bearing, 1),
        'collinearity_max_dev_deg': round(spread, 1),
        'site': {'name': site, 'll': list(SITES[site]), 'distance_to_first_km': round(dist0)},
        'areas': [{'id': n['id'], 'begin_utc': n['begin_utc'], 'end_utc': n['end_utc'],
                   'center': [round(v, 5) for v in n['_c']],
                   'distance_km': round(hav(SITES[site], n['_c']))} for n in areas],
        't0_bound_utc': [B.isoformat(), C.isoformat()],
        't0_estimate_utc': t0.isoformat(),
        'path': [[round(p[0], 5), round(p[1], 5)] for p in path],
        'note': '仅根据危险区几何与时间推断，非官方发射窗口；精确 T0 需发射场 NOTAM 与弹道/历史样本。',
    }
    import os
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, 'trajectory.js'), 'w', encoding='utf-8') as f:
        f.write('/* 自动生成：launch_window.py */\nwindow.TRAJ = ')
        json.dump(traj, f, ensure_ascii=False, indent=1)
        f.write(';\n')
    print('已写', os.path.join(out_dir, 'trajectory.js'))
    for n in traj['areas']:
        print(' ', n['id'], n['distance_km'], 'km', n['center'])


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else '.')
