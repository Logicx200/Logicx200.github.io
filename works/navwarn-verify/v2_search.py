# -*- coding: utf-8 -*-
"""Fast search for a consistent ascent profile (skips debris propagation during optimization)."""
import math, sys, time
import numpy as np
from scipy.optimize import minimize

R = 6371008.8
MU = 3.986004418e14
OMEGA = 7.2921159e-5
J2 = 1.08262668e-3
LAT0 = math.radians(38.849)
LON0 = math.radians(111.608)
T0 = 1795041870.0

V = dict(m0=232000.0, m1_prop=175000.0, m1_dry=10000.0, T1=2962e3, ve1=2650.0,
         m2_dry=4500.0, fairing=1500.0, T2=742e3, ve2=2900.0, CdA=12.0)


def gmst(unix):
    jd = unix / 86400.0 + 2440587.5
    T = (jd - 2451545.0) / 36525.0
    g = 280.46061837 + 360.98564736629 * (jd - 2451545.0) + 0.000387933 * T * T - T ** 3 / 38710000.0
    return math.radians(g % 360)


def unit(x):
    n = np.linalg.norm(x)
    return x / n if n else x


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
    drag = -0.5 * rho * V['CdA'] * np.linalg.norm(vrel) * vrel
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


def elements(r, v):
    rn = np.linalg.norm(r)
    hv = np.cross(r, v); hn = np.linalg.norm(hv)
    inc = math.degrees(math.acos(hv[2] / hn))
    ev = np.cross(v, hv) / MU - r / rn
    e = np.linalg.norm(ev)
    energy = np.linalg.norm(v) ** 2 / 2 - MU / rn
    a = -MU / (2 * energy)
    return dict(a=a, e=e, inc=inc, rp=a * (1 - e), ra=a * (1 + e))


def state0():
    th = gmst(T0)
    r = np.array([R * math.cos(LAT0) * math.cos(LON0),
                  R * math.cos(LAT0) * math.sin(LON0), R * math.sin(LAT0)])
    r = np.array([math.cos(th) * r[0] - math.sin(th) * r[1],
                  math.sin(th) * r[0] + math.cos(th) * r[1], r[2]])
    return r, np.cross(np.array([0, 0, OMEGA]), r), th


def sim(A0=188.2, k1=0.46, payload=1000.0, ctrl=None, dt=0.6, debris=False, t_fair=190.0):
    prop = V['m0'] - V['m1_prop'] - V['m1_dry'] - V['m2_dry'] - payload - V['fairing']
    r, v, th = state0()
    m = V['m0']; t = 0.0
    mdot1 = V['T1'] / V['ve1']; mdot2 = V['T2'] / V['ve2']
    burnt = 0.0
    while burnt < V['m1_prop']:
        up = r / np.linalg.norm(r)
        east = unit(np.cross(np.array([0, 0, 1.0]), r)); north = unit(np.cross(up, east))
        pitch = math.radians(min(85.0, max(0.0, (t - 10.0) * k1)))
        az = math.radians(A0)
        d = math.cos(az) * north + math.sin(az) * east
        thrust = (math.cos(pitch) * up + math.sin(pitch) * d) * V['T1']
        r, v, m = rk4(r, v, m, thrust, -mdot1, dt)
        burnt += mdot1 * dt; t += dt
    t_sep = t
    sep = dict(t=t, r=r.copy(), v=v.copy(), m=m)
    up0 = r / np.linalg.norm(r)
    vn0 = np.linalg.norm(v)
    gam0 = math.degrees(math.asin(np.clip(np.dot(v / vn0, up0), -1, 1)))
    imp1 = None
    if debris:
        r1, v1, t1 = r.copy(), v.copy(), t
        while np.linalg.norm(r1) > R and t1 < t + 1500:
            r1, v1, _ = rk4(r1, v1, V['m1_dry'], np.zeros(3), 0.0, dt)
            t1 += dt
        imp1 = (math.degrees(math.asin(r1[2] / np.linalg.norm(r1))),
                math.degrees((math.atan2(r1[1], r1[0]) - (th + OMEGA * t1)) % (2 * math.pi)))
        if imp1[1] > 180:
            imp1 = (imp1[0], imp1[1] - 360)
    m -= V['m1_dry']
    t_burn2 = t_sep + prop / mdot2
    fair = None; fairing_done = False
    while m > V['m2_dry'] + payload:
        up = r / np.linalg.norm(r)
        u = min(1.0, max(0.0, (t - t_sep) / max(1e-6, t_burn2 - t_sep)))
        # ctrl = (u1, th1, u2, th2, th_end) ; start = gam0
        u1, th1, u2, th2, the = ctrl
        if u <= u1:
            gth = gam0 + (th1 - gam0) * u / max(1e-6, u1)
        elif u <= u2:
            gth = th1 + (th2 - th1) * (u - u1) / max(1e-6, u2 - u1)
        else:
            gth = th2 + (the - th2) * (u - u2) / max(1e-6, 1 - u2)
        east = unit(np.cross(np.array([0, 0, 1.0]), r)); north = unit(np.cross(up, east))
        az = math.radians(A0)
        d = math.cos(az) * north + math.sin(az) * east
        thrust = (math.cos(math.radians(gth)) * d + math.sin(math.radians(gth)) * up) * V['T2']
        r, v, m = rk4(r, v, m, thrust, -mdot2, dt)
        t += dt
        if debris and (not fairing_done) and t >= t_fair:
            fairing_done = True
            rf, vf, tf = r.copy(), v.copy(), t
            while np.linalg.norm(rf) > R and tf < t + 1500:
                rf, vf, _ = rk4(rf, vf, 600.0, np.zeros(3), 0.0, dt)
                tf += dt
            fair = (math.degrees(math.asin(rf[2] / np.linalg.norm(rf))),
                    math.degrees((math.atan2(rf[1], rf[0]) - (th + OMEGA * tf)) % (2 * math.pi)))
            m -= V['fairing']
    el = elements(r, v)
    vn = np.linalg.norm(v); up = r / np.linalg.norm(r)
    fpa = math.degrees(math.asin(np.clip(np.dot(v / vn, up), -1, 1)))
    lat = math.degrees(math.asin(r[2] / np.linalg.norm(r)))
    lon = math.degrees((math.atan2(r[1], r[0]) - (th + OMEGA * t)) % (2 * math.pi))
    if lon > 180:
        lon -= 360
    return dict(f=dict(t=t, alt=(np.linalg.norm(r) - R) / 1000, v=vn / 1000, fpa=fpa, lat=lat, lon=lon, m=m, el=el),
                sep=dict(t=t_sep, alt=(np.linalg.norm(r) - R) / 1000, gamma=gam0, v=np.linalg.norm(v) / 1000),
                imp1=imp1, fair=fair, prop=prop)


def obj(x, payload, k1, target=550.0):
    ctrl = (min(max(x[0], 0.02), 0.6), x[1], min(max(x[2], x[0] + 0.03), 0.97), x[3], x[4])
    o = sim(payload=payload, k1=k1, ctrl=ctrl, dt=0.6)
    f = o['f']
    vc = math.sqrt(MU / (R + f['alt'] * 1000)) / 1000
    return ((f['alt'] - target) / 5.0) ** 2 + (f['fpa'] / 0.3) ** 2 + ((f['v'] - vc) / 0.02) ** 2


if __name__ == '__main__':
    target = float(sys.argv[1]) if len(sys.argv) > 1 else 550.0
    payload = float(sys.argv[2]) if len(sys.argv) > 2 else 1000.0
    t_start = time.time()
    best = None
    for x0 in ([0.30, 45, 0.70, 15, 2], [0.20, 60, 0.60, 25, 5], [0.40, 35, 0.85, 10, 0],
               [0.15, 75, 0.50, 30, 5], [0.25, 25, 0.75, 0, 0]):
        res = minimize(obj, x0, args=(payload, 0.46, target), method='Nelder-Mead',
                       options=dict(maxiter=250, xatol=2e-3, fatol=1e-3))
        print('start', x0, 'err', round(res.fun, 4), 'x', [round(v, 3) for v in res.x], 't=%.0fs' % (time.time() - t_start))
        sys.stdout.flush()
        if best is None or res.fun < best.fun:
            best = res
    ctrl = (min(max(best.x[0], 0.02), 0.6), best.x[1], min(max(best.x[2], best.x[0] + 0.03), 0.97), best.x[3], best.x[4])
    o = sim(payload=payload, k1=0.46, ctrl=ctrl, dt=0.6, debris=True)
    f = o['f']
    print('\nBEST payload=%.0f target=%.0f err=%.4f' % (payload, target, best.fun))
    print(' ctrl =', [round(c, 4) for c in ctrl])
    print(' sep t=%.1f alt=%.1f v=%.3f fpa=%.2f' % (o['sep']['t'], o['sep']['alt'], o['sep']['v'], o['sep']['gamma']))
    print(' final alt=%.1f v=%.3f fpa=%.2f a=%.1f e=%.4f i=%.2f rp=%.1f ra=%.1f' % (
        f['alt'], f['v'], f['fpa'], f['el']['a'] / 1000, f['el']['e'], f['el']['inc'],
        f['el']['rp'] / 1000, f['el']['ra'] / 1000))
    print(' imp1', o['imp1'], ' fair', o['fair'], ' prop', o['prop'])
