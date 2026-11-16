# -*- coding: utf-8 -*-
"""Search for a direct (single-burn) circular insertion with the consistent vehicle."""
import sys, math
import numpy as np
sys.path.insert(0, r'F:\DeepSeek工作区\navwarn-map\tools')
import trajectory3d_v2 as T

R, MU, OMEGA = T.R, T.MU, T.OMEGA


def sim(p=2.0, k1=0.48, tfair=206.0, dt=0.1, payload=None):
    V = T.VEH
    if payload is not None:
        V = dict(T.VEH); V['payload'] = payload
        V['m2_prop'] = V['m0'] - V['m1_prop'] - V['m1_dry'] - V['m2_dry'] - V['payload'] - V['fairing']
    r, v, th = T.state0()
    r_launch = r.copy()
    m = V['m0']; t = 0.0
    mdot1 = V['T1'] / V['ve1']; mdot2 = V['T2'] / V['ve2']
    burnt = 0.0
    while burnt < V['m1_prop']:
        up, east, north = T.heading_frame(r)
        pitch = math.radians(min(85.0, max(0.0, (t - 10.0) * k1)))
        az = math.radians(188.2)
        d = math.cos(az) * north + math.sin(az) * east
        thrust = (math.cos(pitch) * up + math.sin(pitch) * d) * V['T1']
        r, v, m = T.rk4(r, v, m, thrust, -mdot1, dt, V['CdA'])
        burnt += mdot1 * dt; t += dt
    t_sep = t
    sep_r, sep_v = r.copy(), v.copy()
    # stage-1 impact
    r1, v1, t1 = r.copy(), v.copy(), t
    while np.linalg.norm(r1) > R and t1 < t + 1800:
        r1, v1, _ = T.rk4(r1, v1, V['m1_dry'], np.zeros(3), 0.0, 0.5, T.CDA_STAGE1_DEBRIS)
        t1 += 0.5
    imp1 = T.eci_to_geodetic(r1, th + OMEGA * t1)
    m -= V['m1_dry']
    up0, _, _ = T.heading_frame(r)
    gam0 = math.degrees(math.asin(np.clip(np.dot(v / np.linalg.norm(v), up0), -1, 1)))
    t_full = V['m2_prop'] / mdot2
    fair = None; fairing_done = False
    best = None
    while m > V['m2_dry'] + V['payload']:
        up, east, north = T.heading_frame(r)
        u = min(1.0, (t - t_sep) / t_full)
        gth = max(0.0, gam0 * (1.0 - u) ** p)
        az = math.radians(188.2)
        d = math.cos(az) * north + math.sin(az) * east
        thrust = (math.cos(math.radians(gth)) * d + math.sin(math.radians(gth)) * up) * V['T2']
        r, v, m = T.rk4(r, v, m, thrust, -mdot2, dt, V['CdA'])
        t += dt
        if not fairing_done and t >= tfair:
            fairing_done = True
            rf, vf, tf = r.copy(), v.copy(), t
            while np.linalg.norm(rf) > R and tf < t + 1800:
                rf, vf, _ = T.rk4(rf, vf, T.M_FAIRING_DEBRIS, np.zeros(3), 0.0, 0.5, T.CDA_FAIRING)
                tf += 0.5
            fair = T.eci_to_geodetic(rf, th + OMEGA * tf)
            m -= V['fairing']
        rn = np.linalg.norm(r)
        vc = math.sqrt(MU / rn)
        up = r / rn
        gam = math.degrees(math.asin(np.clip(np.dot(v / np.linalg.norm(v), up), -1, 1)))
        err = abs(np.linalg.norm(v) - vc) / 1.0 + abs(gam) / 0.1
        if best is None or err < best[0]:
            best = (err, t, (rn - R) / 1000, np.linalg.norm(v) / 1000, gam, m, T.elements(r, v),
                    T.eci_to_geodetic(r, th + OMEGA * t))
    return dict(imp1=imp1, fair=fair, best=best, sep_alt=(np.linalg.norm(sep_r) - R) / 1000,
                sep_v=np.linalg.norm(sep_v) / 1000, t_sep=t_sep)


if __name__ == '__main__':
    for p in (0.6, 0.8, 1.0, 1.2, 1.5, 1.8, 2.2, 2.6):
        o = sim(p=p)
        err, t, alt, v, gam, m, el, (la, lo, al) = o['best']
        print('p=%.1f | sep alt=%.1f v=%.3f | best circ: t=%.1f alt=%.1f v=%.3f gam=%.2f err=%.3f | e=%.4f a=%.0f i=%.2f @ (%.2f,%.2f)' % (
            p, o['sep_alt'], o['sep_v'], t, alt, v, gam, err, el['e'], el['a_km'], el['inc_deg'], la, lo))
