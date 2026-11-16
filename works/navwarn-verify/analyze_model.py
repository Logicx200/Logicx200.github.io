# -*- coding: utf-8 -*-
"""Instrumented replica of the project's run() (same physics helpers) to expose:
- mass bookkeeping at each event
- velocity components in ECEF ENU (earth-relative vs inertial)
- orbital plane inclination at staging/shutdown
- first-stage impact termination (real ground hit vs 900 s cap)
- sensitivity to pitch rate, fairing separation time, drag area
"""
import sys, types, json, math
import numpy as np

sys.path.insert(0, r'F:\DeepSeek工作区\_navwarn_verify\tools')
mpl = types.ModuleType('matplotlib'); mpl.use = lambda *a, **k: None
plt = types.ModuleType('matplotlib.pyplot'); plt.rcParams = {}
mpl.pyplot = plt
mpl_tk = types.ModuleType('mpl_toolkits'); mpl_tk.__path__ = []
m3d = types.ModuleType('mpl_toolkits.mplot3d'); m3d.Axes3D = object
sys.modules['matplotlib'] = mpl; sys.modules['matplotlib.pyplot'] = plt
sys.modules['mpl_toolkits'] = mpl_tk; sys.modules['mpl_toolkits.mplot3d'] = m3d

import trajectory3d as T

R = T.R; MU = T.MU; OMEGA = T.OMEGA
LAT0, LON0 = T.LAT0, T.LON0


def enu(r, v, t):
    """Return (v_rel_enu, v_eci_enu, heading_deg, pitch_from_horiz_deg) at state (r, v) and time t."""
    gm = T.gmst(1763505870.0) + OMEGA * t
    # local frame in ECI = earth-fixed local frame at time t
    up = r / np.linalg.norm(r)
    east = np.array([-r[1], r[0], 0.0]); east /= np.linalg.norm(east)
    north = np.cross(up, east)
    vrel = v - np.cross(np.array([0, 0, OMEGA]), r)
    def comps(vec):
        return vec @ east, vec @ north, vec @ up
    # horizontal heading clockwise from north
    def az(x):
        e, n, u = x
        return (math.degrees(math.atan2(e, n)) + 360) % 360
    def pitch(x):
        e, n, u = x
        h = math.hypot(e, n)
        return math.degrees(math.atan2(u, h))
    return dict(vrel=comps(vrel), veci=comps(v), az_rel=az(comps(vrel)), az_eci=az(comps(v)),
                pitch_rel=pitch(comps(vrel)))


def elem_inc(r, v):
    h = np.cross(r, v); hn = np.linalg.norm(h)
    return math.degrees(math.acos(max(-1, min(1, h[2] / hn)))), h


def simulate(rate=0.28, max_pitch=88.0, fairing_t=200.0, fairing_mass=600.0, fairing_cda=2.5,
             stage1_cda=6.0, stage2_cda=None, m0=None, dt=0.25, az_deg=188.2,
             target_alt_km=650.0, verbose=True):
    t0 = 1763505870.0
    th = T.gmst(t0)
    r0 = np.array([R * math.cos(LAT0) * math.cos(LON0),
                   R * math.cos(LAT0) * math.sin(LON0),
                   R * math.sin(LAT0)])
    r0 = np.array([math.cos(th) * r0[0] - math.sin(th) * r0[1],
                   math.sin(th) * r0[0] + math.cos(th) * r0[1], r0[2]])
    v0 = np.cross(np.array([0, 0, OMEGA]), r0)
    az = math.radians(az_deg)
    up = r0 / np.linalg.norm(r0)
    east = np.cross(np.array([0, 0, 1.0]), r0); east /= np.linalg.norm(east)
    north = np.cross(up, east)
    heading = math.cos(az) * north + math.sin(az) * east
    V = T.VEH
    m0 = V['m0'] if m0 is None else m0
    m = m0
    r, v = r0.copy(), v0.copy()
    CdA = V['CdA']
    t = 0.0
    mdot1 = V['T1'] / V['ve1']
    log = []
    # ---- stage 1 ----
    burnt = 0.0
    while burnt < V['m1_prop']:
        pitch = math.radians(min(max_pitch, max(0.0, (t - 10.0) * rate)))
        d = heading - up * np.dot(heading, up)
        d = d / np.linalg.norm(d) if np.linalg.norm(d) > 1e-9 else up
        dirv = math.cos(pitch) * up + math.sin(pitch) * d
        r, v, m = T.rk4(r, v, m, dirv * V['T1'], -mdot1, V['CdA'], dt)
        burnt += mdot1 * dt
        t += dt
        if abs(t % 5) < dt:
            log.append((t, r.copy(), v.copy(), m))
    sep_state = (t, r.copy(), v.copy(), m)
    inc_sep, _ = elem_inc(r, v)
    e1 = enu(r, v, t)
    # ---- stage 1 ballistic to ground ----
    m1 = V['m1_dry']
    r1, v1, t1, steps = r.copy(), v.copy(), t, 0
    while np.linalg.norm(r1) > R and t1 < t + 900:
        r1, v1, _ = T.rk4(r1, v1, m1, np.zeros(3), 0, stage1_cda, dt)
        t1 += dt; steps += 1
        if t1 > t + 800: break
    cap = (t1 >= t + 899.9)
    lat1, lon1, alt1 = T.eci_to_geodetic(r1, th + OMEGA * t1)
    dr1 = math.acos(min(1, np.dot(r1 / np.linalg.norm(r1), r0 / np.linalg.norm(r0)))) * R / 1000
    imp1 = dict(t=t1, lat=lat1, lon=lon1, alt_km=alt1 / 1000, downrange_km=dr1, cap=cap, steps=steps)
    # ---- stage 2 ----
    m -= V['m1_dry']
    m2_start = m
    mdot2 = V['T2'] / V['ve2']
    burnt2 = 0.0
    fairing_done = fairing_t is None
    fair = None
    sep2 = None
    shutdown = None
    while burnt2 < V['m2_prop']:
        alt_now = np.linalg.norm(r) - R
        vr = np.dot(v, r / np.linalg.norm(r))
        if alt_now > target_alt_km * 1000 * 0.92 and vr <= 0:
            shutdown = dict(reason='alt/vr break', t=t, alt=alt_now / 1000, v=np.linalg.norm(v) / 1000)
            break
        dirv = v / np.linalg.norm(v)
        r, v, m = T.rk4(r, v, m, dirv * V['T2'], -mdot2, V['CdA'], dt)
        burnt2 += mdot2 * dt
        t += dt
        if abs(t % 5) < dt:
            log.append((t, r.copy(), v.copy(), m))
        if (not fairing_done) and t >= fairing_t:
            m -= V['fairing']
            fairing_done = True
            rf, vf, tf = r.copy(), v.copy(), t
            while np.linalg.norm(rf) > R and tf < t + 1500:
                rf, vf, _ = T.rk4(rf, vf, fairing_mass, np.zeros(3), 0, fairing_cda, dt)
                tf += dt
            flat, flon, falt = T.eci_to_geodetic(rf, th + OMEGA * tf)
            fdr = math.acos(min(1, np.dot(rf / np.linalg.norm(rf), r0 / np.linalg.norm(r0)))) * R / 1000
            fair = dict(t=t, alt_km=(np.linalg.norm(r) - R) / 1000, v_kms=np.linalg.norm(v) / 1000,
                        impact_t=tf, lat=flat, lon=flon, alt_km_i=falt / 1000, downrange_km=fdr,
                        cap=(tf >= t + 1499.9))
    if shutdown is None:
        shutdown = dict(reason='prop exhausted', t=t, alt=(np.linalg.norm(r) - R) / 1000,
                        v=np.linalg.norm(v) / 1000, m=m)
    inc_sh, _ = elem_inc(r, v)
    e2 = enu(r, v, t)
    shutdown.update(m=m, inc=inc_sh, az_rel=e2['az_rel'], pitch_rel=e2['pitch_rel'])
    # coast to target altitude (same as project)
    t_coast = t
    while (np.linalg.norm(r) - R) / 1000 < target_alt_km and t < 3000:
        r, v, m = T.rk4(r, v, m, np.zeros(3), 0, V['CdA'], dt)
        t += dt
        if abs(t % 5) < dt:
            log.append((t, r.copy(), v.copy(), m))
    t_coast = t
    el = T.elements(r, v)
    lat_i, lon_i, alt_i = T.eci_to_geodetic(r, th + OMEGA * t)
    if verbose:
        print(f'--- rate={rate} fairing_t={fairing_t} m0={m0} dt={dt} ---')
        print(' stage1 burnout t=%.1f alt=%.1f v=%.3f m=%.0f inc=%.3f' %
              (sep_state[0], (np.linalg.norm(sep_state[1]) - R) / 1000,
               np.linalg.norm(sep_state[2]) / 1000, sep_state[3], inc_sep))
        ee = enu(sep_state[1], sep_state[2], sep_state[0])
        print('   vrel ENU=(%.3f,%.3f,%.3f) az_rel=%.1f pitch_rel=%.1f | veci ENU=(%.3f,%.3f,%.3f) az_eci=%.1f' %
              (*ee['vrel'], ee['az_rel'], ee['pitch_rel'], *ee['veci'], ee['az_eci']))
        print(' stage1 impact: t=%.1f lat=%.4f lon=%.4f alt=%.3f downrange=%.1f km cap=%s steps=%d' %
              (imp1['t'], imp1['lat'], imp1['lon'], imp1['alt_km'], imp1['downrange_km'], imp1['cap'], imp1['steps']))
        if fair:
            print(' fairing sep t=%.1f alt=%.1f v=%.3f -> impact t=%.1f lat=%.4f lon=%.4f alt=%.3f downrange=%.1f km cap=%s' %
                  (fair['t'], fair['alt_km'], fair['v_kms'], fair['impact_t'], fair['lat'], fair['lon'],
                   fair['alt_km_i'], fair['downrange_km'], fair['cap']))
        print(' stage2 shutdown %s t=%.1f alt=%.1f v=%.3f m=%.0f inc=%.3f az_rel=%.1f pitch_rel=%.1f' %
              (shutdown['reason'], shutdown['t'], shutdown['alt'], shutdown['v'], shutdown['m'], inc_sh,
               e2['az_rel'], e2['pitch_rel']))
        print(' coast to target t=%.1f alt=%.1f v=%.3f | elements a=%.0f e=%.4f i=%.2f rp=%.0f ra=%.0f' %
              (t, (np.linalg.norm(r) - R) / 1000, np.linalg.norm(v) / 1000,
               el['a_km'], el['e'], el['inc_deg'], el['rp_km'], el['ra_km']))
        print(' mass check: m0=%.0f  stage2 start=%.0f  final=%.0f  (dry+payload=%.0f)' %
              (m0, m2_start, m, T.VEH['m2_dry'] + T.VEH['payload']))
    return dict(sep=sep_state, imp1=imp1, fair=fair, shutdown=shutdown, elements=el,
                log=log, t_coast=t_coast, m2_start=m2_start)


if __name__ == '__main__':
    print('=== baseline: current make_traj_layer settings (rate 0.28, fairing 200 s, target 650) ===')
    simulate()
    print('\n=== trajectory3d.py defaults (rate 0.30, target 550) ===')
    simulate(rate=0.30, target_alt_km=550.0)
    print('\n=== convergence: dt 0.5 / 0.25 / 0.1 (rate 0.28) ===')
    for dt in (0.5, 0.25, 0.1):
        simulate(dt=dt, verbose=False)
        # print compact
    for dt in (0.5, 0.25, 0.1):
        r = simulate(dt=dt, verbose=False)
        print(' dt=%.2f  sep(t=%.2f alt=%.2f v=%.3f)  imp1=%.1fkm %.4f,%.4f  fair=%.1fkm  shut(t=%.2f alt=%.1f v=%.3f i=%.2f)  elem e=%.3f a=%.0f' % (
            dt, r['sep'][0], (np.linalg.norm(r['sep'][1]) - R) / 1000, np.linalg.norm(r['sep'][2]) / 1000,
            r['imp1']['downrange_km'], r['imp1']['lat'], r['imp1']['lon'],
            r['fair']['downrange_km'], r['shutdown']['t'], r['shutdown']['alt'], r['shutdown']['v'],
            r['shutdown']['inc'], r['elements']['e'], r['elements']['a_km']))
