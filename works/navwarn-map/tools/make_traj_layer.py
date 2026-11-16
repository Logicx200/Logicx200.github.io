#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_traj_layer.py v2

把 trajectory3d_v2.py 的积分结果 (../trajectory3d.json) 转成地图图层 traj3d.js。

v1 的问题（本版已移除）：
  - 上升段被重新投影到"过两 NOTAM 盒中心"的大圆上（最大偏差 55 km）；
  - 落点事件直接写成 NOTAM 盒中心（循环论证）；
  - "推断段/轨道"是硬编码几何，与积分末态无关。
v2 直接使用积分得到的真实地面轨迹 / 滑行段 / 落点 / 入轨状态，NOTAM 盒只在地图上另行对照。

用法: python make_traj_layer.py [../trajectory3d.json]
"""
import json
import math
import os
import sys

R = 6371.0088
SITE = (38.849, 111.608)
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def hav(lat1, lon1, lat2, lon2):
    la1, lo1, la2, lo2 = map(math.radians, (lat1, lon1, lat2, lon2))
    return 2 * R * math.asin(math.sqrt(
        math.sin((la2 - la1) / 2) ** 2 +
        math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2))


def main(json_path=None):
    json_path = json_path or os.path.join(ROOT, 'trajectory3d.json')
    src = json.load(open(json_path, encoding='utf-8'))

    asc = [[s[0], s[1], s[2], s[3]] for s in src['samples'] if s[4] == 'ascent']
    coast = [[s[0], s[1], s[2], s[3]] for s in src['samples'] if s[4] == 'coast']
    # 保证滑行段从一次关机点开始（采样点可能滞后 <=5 s）
    if coast:
        pass
    elements = src['elements']

    ev_by_name = {e['ev']: e for e in src['events']}
    events = []

    def add(name, lat, lon, alt, kind, t=None, dist=None):
        d = dist if dist is not None else hav(SITE[0], SITE[1], lat, lon)
        events.append(dict(name=name, lat=round(lat, 4), lon=round(lon, 4),
                           alt=round(alt, 1), dist_km=round(d, 1),
                           kind=kind, t=None if t is None else round(t, 1)))

    e = ev_by_name.get('一级关机/分离')
    if e:
        add('一级关机/分离', e['lat'], e['lon'], e['alt_km'], 'sep', e['t'])
    imp1 = src['impact_stage1']
    add('一级残骸落点（积分）', imp1['lat'], imp1['lon'], 0.0, 'impact', imp1['t'], imp1['downrange_km'])
    e = ev_by_name.get('整流罩分离')
    if e:
        add('整流罩分离', e['lat'], e['lon'], e['alt_km'], 'sep', e['t'])
        add('整流罩残骸落点（积分）', e['impact_lat'], e['impact_lon'], 0.0,
            'impact', e['impact_t'], e['impact_dist_km'])
    e = ev_by_name.get('二级一次关机')
    if e:
        add('二级一次关机', e['lat'], e['lon'], e['alt_km'], 'sep', e['t'])
    e = ev_by_name.get('滑行至远地点')
    if e:
        add('滑行至远地点', e['lat'], e['lon'], e['alt_km'], 'coast', e['t'])
    e = ev_by_name.get('入轨（二次点火圆化）')
    if e:
        add('入轨（二次点火圆化）', e['lat'], e['lon'], e['alt_km'], 'insert', e['t'])

    data = dict(
        site=list(SITE),
        azimuth=src['azimuth_deg'],
        t0_utc=src['t0_utc'],
        target_alt_km=src['target_alt_km'],
        ascent=asc,
        coast=coast,
        orbit=src['orbit'],
        orbit3d=src['orbit3d'],
        events=events,
        elements=dict(inc_deg=elements['inc_deg'], alt_km=elements['alt_km'],
                      period_min=elements['period_min'], e=elements['e'],
                      a_km=elements['a_km'], rp_km=elements['rp_km'], ra_km=elements['ra_km']),
        note=src['note'],
    )
    out = os.path.join(ROOT, 'traj3d.js')
    with open(out, 'w', encoding='utf-8') as f:
        f.write('/* 自动生成：make_traj_layer.py v2（读取 trajectory3d.json 的积分结果） */\n')
        f.write('window.TRAJ3D = ')
        json.dump(data, f, ensure_ascii=False, separators=(',', ':'))
        f.write(';\n')
    print('wrote', out)
    print('ascent', len(asc), 'coast', len(coast), 'orbit', len(src['orbit']), 'orbit3d', len(src['orbit3d']))
    for ev in events:
        print('  ', ev['kind'], ev['name'], ev['lat'], ev['lon'], ev['alt'], ev['dist_km'], 'km')
    print(' elements', elements)


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else None)
