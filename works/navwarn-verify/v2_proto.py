# -*- coding: utf-8 -*-
"""v2 prototype: physically consistent 3DOF ascent with a guided second stage.
Goal: consistent mass, real orbital insertion, computed debris impacts, no hard-coded points.
Scratch file for parameter exploration (final implementation goes to tools/trajectory3d.py)."""
import math
import numpy as np

R = 6371008.8
MU = 3.986004418e14
OMEGA = 7.2921159e-5
J2 = 1.08262668e-3
LAT0 = math.radians(38.849)
LON0 = math.radians(111.608)
T0 = 1795041870.0  # 2026-11-18T22:44:30Z

VEH = dict(m0=232000.0, m1_prop=175000.0, m1_dry=15000.0, T1=2962e3, ve1=2650.0,
           m2_prop=34500.0, m2_dry=4500.0, payload=1500.0, fairing=1500.0,
           T2=742e3, ve2=2900.0, CdA=12.0)


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
    # J2
    z2 = r[2] * r[2]
    f = 1.5 * J2 * MU * R * R / rn ** 5
    g = g + np.array([f * r[0] * (5 * z2 / rn ** 2 - 1),
                      f * r[1] * (5 * z2 / rn ** 2 - 1),
                      f * r[2] * (5 * z2 / rn ** 2 - 3)])
    h = rn - R
    rho = 1.225 * math.exp(-max(h, 0.0) / 8500.0) if h < 200e3 else 0.0
    vrel = v - np.cross(np.array([0, 0, OMEGA]), r)
    drag = -0.5 * rho * VEH['CdA'] * np.linalg.norm(vrel) * vrel
    return g + thrust / mass + drag / mass


def rk4(r, v, m, thrust, mdot, dt, cda=None):
    def f(r, v, m):
        return v, accel(r, v, thrust, m), mdot
    k1r, k1v, k1m = f(r, v, m)
    k2r, k2v, k2m = f(r + dt / 2 * k1r, v + dt / 2 * k1v, m + dt / 2 * k1m)
    k3r, k3v, k3m = f(r + dt / 2 * k2r, v + dt / 2 * k2v, m + dt / 2 * k2m)
    k4r, k4v, k4m = f(r + dt * k3r, v + dt * k3v, m + dt * k3m)
    return (r + dt / 6 * (k1r + 2 * k2r + 2 * k3r + k4r),
            v + dt / 6 * (k1v + 2 * k2v + 2 * k3v + k4v),
            m + dt / 6 * (k1m + 2 * k2m + 2 * k3m + k4m))


def eci_to_geodetic(r, gm):
    x, y, z = r
    lon = (math.atan2(y, x) - gm) % (2 * math.pi)
    lon_deg = math.degrees(lon)
    if lon_deg > 180.0:
        lon_deg -= 360.0
    lat = math.degrees(math.asin(z / np.linalg.norm(r)))
    return lat, lon_deg, np.linalg.norm(r) - R


def elements(r, v):
    rn = np.linalg.norm(r)
    hv = np.cross(r, v)
    hn = np.linalg.norm(hv)
    inc = math.degrees(math.acos(hv[2] / hn))
    n = np.cross(np.array([0, 0, 1.0]), hv)
    nn = np.linalg.norm(n)
    ev = np.cross(v, hv) / MU - r / rn
    e = np.linalg.norm(ev)
    energy = np.linalg.norm(v) ** 2 / 2 - MU / rn
    a = -MU / (2 * energy) if energy < 0 else float('inf')
    rp = a * (1 - e)
    ra = a * (1 + e)
    return dict(a=a, e=e, inc=inc, rp=rp, ra=ra)


def heading_vectors(r):
    up = unit(r)
    east = unit(np.cross(np.array([0, 0, 1.0]), r))
    north = unit(np.cross(up, east))
    return up, east, north


def simulate(A0=188.2, k1=0.28, t_kick=10.0, maxpitch=85.0, k2=0.4, gamma_min=0.0,
             t_fair=190.0, yaw_start=None, yaw_rate=0.0, yaw_max=0.0,
             dt=0.25, burn_all=True, target_alt=550.0, verbose=False):
    """Stage 1: pitch ramp k1 (deg/s from vertical), azimuth A0 (earth-relative).
    Stage 2: thrust pitch (from horizontal) starts at 90-(k1*(t_sep-t_kick)) and decreases at k2 deg/s.
    Optional yaw: A = A0 + yaw(t), yaw ramps after yaw_start at yaw_rate deg/s up to yaw_max."""
    th = gmst(T0)
    r = np.array([R * math.cos(LAT0) * math.cos(LON0),
                  R * math.cos(LAT0) * math.sin(LON0),
                  R * math.sin(LAT0)])
    r = np.array([math.cos(th) * r[0] - math.sin(th) * r[1],
                  math.sin(th) * r[0] + math.cos(th) * r[1], r[2]])
    v = np.cross(np.array([0, 0, OMEGA]), r)
    m = VEH['m0']
    t = 0.0
    mdot1 = VEH['T1'] / VEH['ve1']
    mdot2 = VEH['T2'] / VEH['ve2']
    log = []

    # ---------------- stage 1 ----------------
    burnt = 0.0
    while burnt < VEH['m1_prop']:
        up, east, north = heading_vectors(r)
        pitch = math.radians(min(maxpitch, max(0.0, (t - t_kick) * k1)))
        az = math.radians(A0)
        d = math.cos(az) * north + math.sin(az) * east
        thrust = (math.cos(pitch) * up + math.sin(pitch) * d) * VEH['T1']
        r, v, m = rk4(r, v, m, thrust, -mdot1, dt)
        burnt += mdot1 * dt
        t += dt
        if abs(t % 5) < dt:
            log.append((t, r.copy(), v.copy(), m))
    sep1 = dict(t=t, r=r.copy(), v=v.copy(), m=m)
    # stage-1 debris impact
    r1, v1, t1 = r.copy(), v.copy(), t
    while np.linalg.norm(r1) > R and t1 < t + 1200:
        r1, v1, _ = rk4(r1, v1, VEH['m1_dry'], np.zeros(3), 0.0, dt)
        t1 += dt
    lat1, lon1, alt1 = eci_to_geodetic(r1, th + OMEGA * t1)
    imp1 = dict(t=t1, lat=lat1, lon=lon1, alt=alt1 / 1000)

    # ---------------- stage 2 ----------------
    m -= VEH['m1_dry']
    m2_start = m
    gamma_thrust = 90.0 - min(maxpitch, (sep1['t'] - t_kick) * k1)  # deg above horizon
    fair = None
    fairing_done = False
    cutoff = None
    a_target = R + target_alt * 1000.0
    while m > VEH['m2_dry'] + VEH['payload']:
        up, east, north = heading_vectors(r)
        # yaw schedule
        yaw = 0.0
        if yaw_start is not None and t > yaw_start:
            yaw = min(yaw_max, yaw_rate * (t - yaw_start))
        az = math.radians(A0 + yaw)
        gth = max(gamma_min, gamma_thrust - k2 * (t - sep1['t']))
        d = math.cos(az) * north + math.sin(az) * east
        thrust = (math.cos(math.radians(gth)) * d + math.sin(math.radians(gth)) * up) * VEH['T2']
        r, v, m = rk4(r, v, m, thrust, -mdot2, dt)
        t += dt
        if abs(t % 5) < dt:
            log.append((t, r.copy(), v.copy(), m))
        # fairing
        if (not fairing_done) and t >= t_fair:
            fairing_done = True
            rf, vf, tf = r.copy(), v.copy(), t
            while np.linalg.norm(rf) > R and tf < t + 1500:
                rf, vf, _ = rk4(rf, vf, 600.0, np.zeros(3), 0.0, dt)
                tf += dt
            flat, flon, falt = eci_to_geodetic(rf, th + OMEGA * tf)
            fair = dict(t=t, alt=(np.linalg.norm(r) - R) / 1000, lat=flat, lon=flon, t_imp=tf)
            m -= VEH['fairing']
        # cutoff check: circular near target
        if burn_all is False:
            el = elements(r, v)
            if abs(el['rp'] - a_target) < 3e3 and abs(el['ra'] - a_target) < 3e3:
                cutoff = dict(t=t, m=m, el=el)
                break
    alt = (np.linalg.norm(r) - R) / 1000
    el = elements(r, v)
    res = dict(sep1=sep1, imp1=imp1, fair=fair, cutoff=cutoff,
               final=dict(t=t, alt=alt, v=np.linalg.norm(v) / 1000, m=m, el=el,
                          lat=eci_to_geodetic(r, th + OMEGA * t)[0],
                          lon=eci_to_geodetic(r, th + OMEGA * t)[1]),
               log=log)
    if verbose:
        s = sep1
        print('sep1 t=%.1f alt=%.1f v=%.3f m=%.0f' % (s['t'], (np.linalg.norm(s['r']) - R) / 1000,
                                                      np.linalg.norm(s['v']) / 1000, s['m']))
        print('imp1 t=%.1f %.4fN %.4fE alt=%.1f' % (imp1['t'], imp1['lat'], imp1['lon'], imp1['alt']))
        if fair:
            print('fair sep t=%.1f alt=%.1f -> imp %.4fN %.4fE t=%.1f' % (fair['t'], fair['alt'], fair['lat'], fair['lon'], fair['t_imp']))
        print('final t=%.1f alt=%.1f v=%.3f m=%.0f' % (t, alt, np.linalg.norm(v) / 1000, m))
        print('elements a=%.0f e=%.4f i=%.3f rp=%.0f ra=%.0f' % (el['a'] / 1000, el['e'], el['inc'], el['rp'] / 1000, el['ra'] / 1000))
    return res


if __name__ == '__main__':
    print('--- scan stage-2 pitch rate k2 (burn all propellant, no yaw) ---')
    for k2 in (0.2, 0.3, 0.4, 0.5, 0.6, 0.8, 1.0):
        r = simulate(k2=k2, dt=0.25)
        f = r['final']
        print(' k2=%.2f  final t=%.1f alt=%.1f v=%.3f | a=%.0f e=%.3f i=%.2f rp=%.0f ra=%.0f' % (
            k2, f['t'], f['alt'], f['v'], f['el']['a'] / 1000, f['el']['e'], f['el']['inc'],
            f['el']['rp'] / 1000, f['el']['ra'] / 1000))
