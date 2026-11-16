# -*- coding: utf-8 -*-
"""Find a physically consistent ascent that inserts into a circular 550 km orbit.
Flexible stage-2 pitch schedule: theta(u) piecewise-linear from staging FPA to horizontal.
Optimises insertion error; payload tuned separately."""
import math
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


def theta_sched(u, *ctrl):
    """Piecewise-linear thrust pitch from horizontal; ctrl = (u1,th1,u2,th2,th_end)."""
    u1, t1, u2, t2, te = ctrl
    if u <= u1:
        return t1 + (t1 - 0.0) * 0  # start value supplied separately
    if u <= u2:
        return t1 + (t2 - t1) * (u - u1) / max(1e-6, u2 - u1)
    return t2 + (te - t2) * (u - u2) / max(1e-6, 1 - u2)


def sim(A0=188.2, k1=0.46, payload=1000.0, ctrl=(0.3, 40.0, 0.7, 15.0, 2.0),
        t_fair=190.0, dt=0.5, gam0=None):
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
    r1, v1, t1 = r.copy(), v.copy(), t
    while np.linalg.norm(r1) > R and t1 < t + 1500:
        r1, v1, _ = rk4(r1, v1, V['m1_dry'], np.zeros(3), 0.0, dt)
        t1 += dt
    lat1, lon1, _ = eci_to_geodetic(r1, th + OMEGA * t1)
    imp1 = dict(t=t1, lat=lat1, lon=lon1)
    m -= V['m1_dry']
    t_burn2 = t_sep + prop / mdot2
    fair = None; fairing_done = False
    while m > V['m2_dry'] + payload:
        up = r / np.linalg.norm(r)
        u = min(1.0, max(0.0, (t - t_sep) / max(1e-6, t_burn2 - t_sep)))
        if gam0 is None:
            vn0 = np.linalg.norm(v); g0 = math.degrees(math.asin(np.clip(np.dot(v / vn0, up), -1, 1)))
        else:
            g0 = gam0
        if u <= ctrl[0]:
            gth = g0 + (ctrl[1] - g0) * u / max(1e-6, ctrl[0])
        elif u <= ctrl[2]:
            gth = ctrl[1] + (ctrl[3] - ctrl[1]) * (u - ctrl[0]) / max(1e-6, ctrl[2] - ctrl[0])
        else:
            gth = ctrl[3] + (ctrl[4] - ctrl[3]) * (u - ctrl[2]) / max(1e-6, 1 - ctrl[2])
        az = math.radians(A0)
        east = unit(np.cross(np.array([0, 0, 1.0]), r)); north = unit(np.cross(up, east))
        d = math.cos(az) * north + math.sin(az) * east
        thrust = (math.cos(math.radians(gth)) * d + math.sin(math.radians(gth)) * up) * V['T2']
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
            m -= V['fairing']
    el = elements(r, v)
    vn = np.linalg.norm(v); up = r / np.linalg.norm(r)
    fpa = math.degrees(math.asin(np.clip(np.dot(v / vn, up), -1, 1)))
    lat, lon, alt = eci_to_geodetic(r, th + OMEGA * t)
    return dict(f=dict(t=t, alt=alt / 1000, v=vn / 1000, fpa=fpa, lat=lat, lon=lon, m=m, el=el),
                sep=dict(t=t_sep, alt=(np.linalg.norm(r) - R) / 1000), imp1=imp1, fair=fair)


def objective(x, k1, payload):
    # x = (u1, th1, u2, th2, th_end)
    ctrl = (min(max(x[0], 0.05), 0.5), x[1], min(max(x[2], x[0] + 0.05), 0.95), x[3], x[4])
    o = sim(k1=k1, payload=payload, ctrl=ctrl, dt=0.5)
    f = o['f']
    vc = math.sqrt(MU / (R + f['alt'] * 1000)) / 1000
    return ((f['alt'] - 550.0) / 5.0) ** 2 + (f['fpa'] / 0.3) ** 2 + ((f['v'] - vc) / 0.02) ** 2


if __name__ == '__main__':
    for payload in (800.0, 1000.0, 1200.0):
        for k1 in (0.46, 0.50):
            best = None
            for x0 in ([0.3, 40, 0.7, 15, 2], [0.25, 55, 0.6, 25, 5], [0.35, 30, 0.8, 8, 0]):
                res = minimize(objective, x0, args=(k1, payload), method='Nelder-Mead',
                               options=dict(maxiter=600, xatol=1e-3, fatol=1e-4))
                if best is None or res.fun < best.fun:
                    best = res
            ctrl = (min(max(best.x[0], 0.05), 0.5), best.x[1], min(max(best.x[2], best.x[0] + 0.05), 0.95), best.x[3], best.x[4])
            o = sim(k1=k1, payload=payload, ctrl=ctrl, dt=0.5)
            f = o['f']
            print('payload=%.0f k1=%.2f -> err=%.4f alt=%.1f v=%.3f fpa=%.2f a=%.0f e=%.3f i=%.2f | ctrl=%s' % (
                payload, k1, best.fun, f['alt'], f['v'], f['fpa'], f['el']['a'] / 1000, f['el']['e'],
                f['el']['inc'], tuple(round(c, 2) for c in ctrl)))
