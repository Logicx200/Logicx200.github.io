# -*- coding: utf-8 -*-
"""Fixed independent 2D ballistic check + velocity-loss accounting for stage 1 (project model)."""
import sys, types, math
import numpy as np
sys.path.insert(0, r'F:\DeepSeek工作区\_navwarn_verify\tools')
mpl = types.ModuleType('matplotlib'); mpl.use = lambda *a, **k: None
plt = types.ModuleType('matplotlib.pyplot'); plt.rcParams = {}; mpl.pyplot = plt
mpl_tk = types.ModuleType('mpl_toolkits'); mpl_tk.__path__ = []
sys.modules['matplotlib'] = mpl; sys.modules['matplotlib.pyplot'] = plt
sys.modules['mpl_toolkits'] = mpl_tk
m3d = types.ModuleType('mpl_toolkits.mplot3d'); m3d.Axes3D = object
sys.modules['mpl_toolkits.mplot3d'] = m3d
import trajectory3d as T
from analyze_model import simulate, R

rr = simulate(rate=0.28, fairing_t=200.0, dt=0.5, verbose=False)
sep_t, sep_r, sep_v, sep_m = rr['sep']
alt0 = np.linalg.norm(sep_r) - T.R
v0 = np.linalg.norm(sep_v)
up = sep_r / np.linalg.norm(sep_r)
fpa = math.degrees(math.asin(np.dot(sep_v / v0, up)))
print('separation: t=%.1f alt=%.3f km v=%.4f km/s FPA=%.2f deg' % (sep_t, alt0/1000, v0/1000, fpa))

def ballistic2d(alt0_km, speed, fpa_deg, drag, cda=6.0, mass=15000.0, dt=0.05):
    r = T.R + alt0_km*1000
    th = 0.0
    vr = speed*math.sin(math.radians(fpa_deg)); vt = speed*math.cos(math.radians(fpa_deg))
    t = 0.0; vmin = speed
    while r > T.R and t < 5000:
        def d(r, th, vr, vt):
            v = math.hypot(vr, vt)
            ar = -T.MU/r**2
            at = 0.0
            if drag:
                h = r - T.R
                rho = 1.225*math.exp(-max(h, 0)/8500.0) if h < 200e3 else 0.0
                ad = 0.5*rho*cda*v*v/mass
                ar -= ad*vr/v
                at = -ad*vt/v
            return vr, vt/r, ar + vt*vt/r, at - vr*vt/r
        k1 = d(r, th, vr, vt)
        k2 = d(r+dt/2*k1[0], th+dt/2*k1[1], vr+dt/2*k1[2], vt+dt/2*k1[3])
        k3 = d(r+dt/2*k2[0], th+dt/2*k2[1], vr+dt/2*k2[2], vt+dt/2*k2[3])
        k4 = d(r+dt*k3[0], th+dt*k3[1], vr+dt*k3[2], vt+dt*k3[3])
        r += dt/6*(k1[0]+2*k2[0]+2*k3[0]+k4[0])
        th += dt/6*(k1[1]+2*k2[1]+2*k3[1]+k4[1])
        vr += dt/6*(k1[2]+2*k2[2]+2*k3[2]+k4[2])
        vt += dt/6*(k1[3]+2*k2[3]+2*k3[3]+k4[3])
        t += dt
        vmin = min(vmin, math.hypot(vr, vt))
    return th*T.R/1000, t, vmin/1000

for drag in (False, True):
    rng, t, vmin = ballistic2d(alt0/1000, v0, fpa, drag)
    print(('vacuum ' if not drag else 'w/drag '), '-> ground range from separation = %.1f km, flight time %.1f s' % (rng, t))
print('project first-stage impact: 633.4 km total downrange (separation point is already ~50 km downrange)')
print('flat-earth vacuum estimate v^2 sin(2g)/9.5 = %.1f km' % ((v0/1000)**2*math.sin(2*math.radians(fpa))/9.5))

print('\n=== stage-1 velocity-loss accounting (project model) ===')
# rerun stage 1 with the project's exact loop, accumulating gravity/drag losses along the velocity direction
t0 = 1763505870.0; th = T.gmst(t0)
r0 = np.array([T.R*math.cos(T.LAT0)*math.cos(T.LON0), T.R*math.cos(T.LAT0)*math.sin(T.LON0), T.R*math.sin(T.LAT0)])
r0 = np.array([math.cos(th)*r0[0]-math.sin(th)*r0[1], math.sin(th)*r0[0]+math.cos(th)*r0[1], r0[2]])
v0v = np.cross(np.array([0, 0, T.OMEGA]), r0)
az = math.radians(188.2); up = r0/np.linalg.norm(r0)
east = np.cross([0, 0, 1.0], r0); east /= np.linalg.norm(east); north = np.cross(up, east)
heading = math.cos(az)*north + math.sin(az)*east
V = T.VEH; m = V['m0']; r, v = r0.copy(), v0v.copy(); t = 0.0; dt = 0.5
mdot1 = V['T1']/V['ve1']; burnt = 0.0
grav_loss = drag_loss = 0.0
while burnt < V['m1_prop']:
    pitch = math.radians(min(88.0, max(0.0, (t-10.0)*0.28)))
    dvec = heading - up*np.dot(heading, up); dvec /= np.linalg.norm(dvec)
    dirv = math.cos(pitch)*up + math.sin(pitch)*dvec
    # instantaneous accelerations
    rn = np.linalg.norm(r); gvec = -T.MU*r/rn**3
    h = rn - T.R; rho = 1.225*math.exp(-max(h, 0)/8500.0) if h < 200e3 else 0.0
    vrel = v - np.cross(np.array([0, 0, T.OMEGA]), r)
    dragf = -0.5*rho*V['CdA']*np.linalg.norm(vrel)*vrel
    vhat = v/np.linalg.norm(v)
    grav_loss += -np.dot(gvec, vhat)*dt
    drag_loss += -np.dot(dragf/m, vhat)*dt
    r, v, m = T.rk4(r, v, m, dirv*V['T1'], -mdot1, V['CdA'], dt)
    burnt += mdot1*dt; t += dt; up = r/np.linalg.norm(r)
ideal = V['ve1']*math.log(V['m0']/m)
print(' ideal dv = ve*ln(m0/m) = %.1f m/s ; final inertial speed = %.1f m/s' % (ideal, np.linalg.norm(v)))
print(' gravity loss = %.1f m/s ; drag loss = %.1f m/s ; ideal - losses = %.1f m/s' % (grav_loss, drag_loss, ideal-grav_loss-drag_loss))
