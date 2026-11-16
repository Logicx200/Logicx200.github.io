# -*- coding: utf-8 -*-
"""v2 optimizer: consistent mass, guided stage 2. Finds a pitch schedule that inserts into a
circular orbit, then solves the payload so the insertion altitude is 550 km."""
import math
import numpy as np
from scipy.optimize import brentq, fsolve

R = 6371008.8
MU = 3.986004418e14
OMEGA = 7.2921159e-5
J2 = 1.08262668e-3
LAT0 = math.radians(38.849)
LON0 = math.radians(111.608)
T0 = 1795041870.0

BASE = dict(m0=232000.0, m1_prop=175000.0, m1_dry=11500.0, T1=2962e3, ve1=2650.0,
            m2_dry=4500.0, fairing=1500.0, T2=742e3, ve2=2900.0, CdA=12.0)


def gmst(unix):
    jd = unix / 86400.0 + 2440587.5
    T = (jd - 2451545.0) / 36525.0
    g = 280.46061837 + 360.98564736629 * (jd - 2451545.0) + 0.000387933 * T * T - T ** 3 / 38710000.0
    return math.radians(g % 360)


def unit(v):
    n = np.linalg.norm(v)
    return v / n if n else v


def accel(r, v, thrust, mass):
    rn = np.linalg.norm(r)
    g = -MU * r / rn ** 3
    z2 = r[2] * r[2]
    f = 1.5 * J2 * MU * R * R / rn ** 5
    g = g + np.array([f * r[0] * (5 * z2 / rn ** 2 - 1),
                      f * r[1] * (5 * z2 / rn ** 2 - 1),
                      f * r[2] * (5 * z2 / rn ** 2 - 3)])
    h = rn - R
    rho = 1.225 * math.exp(-max(h, 0.0) / 8500.0) if h < 200e3 else 0.0
    vrel = v - np.cross(np.array([0, 0, OMEGA]), r)
    drag = -0.5 * rho * BASE['CdA'] * np.linalg.norm(vrel) * vrel
    return g + thrust / mass + drag / mass


def rk4(r, v, m, thrust, mdot, dt):
    def f(r, v, m):
        return v, accel(r, v, thrust, m), mdot
    k1 = f(r, v, m)
    k2 = f(r + dt / 2 * k1[0], v + dt / 2 * k1[1], m + dt / 2 * k1[2])
    k3 = f(r + dt / 2 * k2[0], v + dt / 2 * k2[1], m + dt / 2 * k2[2])
    k4 = f(r + dt * k3[0], v + dt * k3[1], m + dt * k3[2])
    return (r + dt / 6 * (k1[0] + 2 * k2[0] + 2 * k3[0] + k4[0]),
            v + dt / 6 * (k1[1] + 2 * k2[1] + 2 * k3[1] + k4[1]),
            m + dt / 6 * (k1[2] + 2 * k2[2] + 2 * k3[2] + k4[2]))


def eci_to_geodetic(r, gm):
    x, y, z = r
    lon = math.degrees((math.atan2(y, x) - gm) % (2 * math.pi))
    if lon > 180:
        lon -= 360
    return math.degrees(math.asin(z / np.linalg.norm(r))), lon, np.linalg.norm(r) - R


def elements(r, v):
    rn = np.linalg.norm(r)
    hv = np.cross(r, v); hn = np.linalg.norm(hv)
    inc = math.degrees(math.acos(hv[2] / hn))
    n = np.cross(np.array([0, 0, 1.0]), hv); nn = np.linalg.norm(n)
    ev = np.cross(v, hv) / MU - r / rn
    e = np.linalg.norm(ev)
    energy = np.linalg.norm(v) ** 2 / 2 - MU / rn
    a = -MU / (2 * energy)
    return dict(a=a, e=e, inc=inc, rp=a * (1 - e), ra=a * (1 + e))


def state0():
    th = gmst(T0)
    r = np.array([R * math.cos(LAT0) * math.cos(LON0),
                  R * math.cos(LAT0) * math.sin(LON0),
                  R * math.sin(LAT0)])
    r = np.array([math.cos(th) * r[0] - math.sin(th) * r[1],
                  math.sin(th) * r[0] + math.cos(th) * r[1], r[2]])
    v = np.cross(np.array([0, 0, OMEGA]), r)
    return r, v, th


def sim(A0=188.2, k1=0.45, payload=1500.0, p_sched=1.5, s_sched=1.0, t_fair=190.0, dt=0.25,
        prop=None, record=False):
    """prop is stage-2 propellant mass; if None derived from mass budget."""
    m0 = BASE['m0']
    if prop is None:
        prop = m0 - BASE['m1_prop'] - BASE['m1_dry'] - BASE['m2_dry'] - payload - BASE['fairing']
    r, v, th = state0()
    m = m0
    t = 0.0
    mdot1 = BASE['T1'] / BASE['ve1']
    mdot2 = BASE['T2'] / BASE['ve2']
    # stage 1
    burnt = 0.0
    while burnt < BASE['m1_prop']:
        up = r / np.linalg.norm(r)
        east = unit(np.cross(np.array([0, 0, 1.0]), r)); north = unit(np.cross(up, east))
        pitch = math.radians(min(85.0, max(0.0, (t - 10.0) * k1)))
        az = math.radians(A0)
        d = math.cos(az) * north + math.sin(az) * east
        thrust = (math.cos(pitch) * up + math.sin(pitch) * d) * BASE['T1']
        r, v, m = rk4(r, v, m, thrust, -mdot1, dt)
        burnt += mdot1 * dt; t += dt
    t_sep = t
    m1_mass = m - BASE['m1_prop'] - BASE['m1_dry']  # not used
    # stage-1 debris
    r1, v1, t1 = r.copy(), v.copy(), t
    while np.linalg.norm(r1) > R and t1 < t + 1200:
        r1, v1, _ = rk4(r1, v1, BASE['m1_dry'], np.zeros(3), 0.0, dt)
        t1 += dt
    lat1, lon1, alt1 = eci_to_geodetic(r1, th + OMEGA * t1)
    imp1 = dict(t=t1, lat=lat1, lon=lon1)
    # stage 2
    m -= BASE['m1_dry']
    gamma0 = 90.0 - min(85.0, (t_sep - 10.0) * k1)
    t_burn2 = t_sep + prop / mdot2
    fair = None; fairing_done = False; cutoff = None
    while m > BASE['m2_dry'] + payload:
        up = r / np.linalg.norm(r)
        east = unit(np.cross(np.array([0, 0, 1.0]), r)); north = unit(np.cross(up, east))
        u = min(1.0, max(0.0, (t - t_sep) / max(1e-6, t_burn2 - t_sep)))
        gth = max(0.0, s_sched * gamma0 * (1.0 - u) ** p_sched)
        az = math.radians(A0)
        d = math.cos(az) * north + math.sin(az) * east
        thrust = (math.cos(math.radians(gth)) * d + math.sin(math.radians(gth)) * up) * BASE['T2']
        r, v, m = rk4(r, v, m, thrust, -mdot2, dt)
        t += dt
        if not fairing_done and t >= t_fair:
            fairing_done = True
            rf, vf, tf = r.copy(), v.copy(), t
            while np.linalg.norm(rf) > R and tf < t + 1500:
                rf, vf, _ = rk4(rf, vf, 600.0, np.zeros(3), 0.0, dt)
                tf += dt
            flat, flon, _ = eci_to_geodetic(rf, th + OMEGA * tf)
            fair = dict(t=t, alt=(np.linalg.norm(r) - R) / 1000, lat=flat, lon=flon, t_imp=tf)
            m -= BASE['fairing']
    el = elements(r, v)
    up = r / np.linalg.norm(r)
    vn = np.linalg.norm(v)
    fpa = math.degrees(math.asin(np.dot(v / vn, up)))
    lat, lon, alt = eci_to_geodetic(r, th + OMEGA * t)
    out = dict(f=dict(t=t, alt=alt / 1000, v=vn / 1000, fpa=fpa, lat=lat, lon=lon, m=m, el=el),
               sep=dict(t=t_sep, alt=(np.linalg.norm(r) - R) / 1000), imp1=imp1, fair=fair)
    if record:
        out['state'] = (t, r.copy(), v.copy(), m)
    return out


def solve_orbit(k1, payload, s=1.0):
    """Solve pitch-shape p (and scale) so final state is circular: fpa=0 and v=v_circ(r)."""
    def resid(x):
        p = x[0]
        o = sim(k1=k1, payload=payload, p_sched=p, s_sched=s)
        f = o['f']; el = f['el']
        vc = math.sqrt(MU / el['a']) if False else math.sqrt(MU / (R + f['alt'] * 1000))
        return [f['fpa'] / 1.0, (f['v'] - vc / 1000) / 0.01]
    x0 = [1.5]
    # 1-D: use fpa only, then report circularity
    try:
        p = brentq(lambda p: sim(k1=k1, payload=payload, p_sched=p)['f']['fpa'], 0.3, 4.0)
    except Exception as e:
        return None
    return p


if __name__ == '__main__':
    for k1 in (0.40, 0.45, 0.50, 0.55):
        o = sim(k1=k1, payload=1500.0, p_sched=1.5)
        f = o['f']
        print('k1=%.2f p=1.5: alt=%.1f v=%.3f fpa=%.2f e=%.3f i=%.2f a=%.0f' % (
            k1, f['alt'], f['v'], f['fpa'], f['el']['e'], f['el']['inc'], f['el']['a'] / 1000))
    print()
    for k1 in (0.40, 0.45, 0.50, 0.55):
        for p in (0.8, 1.2, 1.6, 2.0, 2.5):
            o = sim(k1=k1, payload=1500.0, p_sched=p)
            f = o['f']
            print('k1=%.2f p=%.1f: alt=%5.1f v=%.3f fpa=%5.2f e=%.3f' % (k1, p, f['alt'], f['v'], f['fpa'], f['el']['e']))
        print()
