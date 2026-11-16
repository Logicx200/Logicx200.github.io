// Validate the regenerated map data the same way index.html consumes it.
const fs = require('fs');
const vm = require('vm');
const path = require('path');
const root = 'F:\\DeepSeek工作区\\navwarn-map';
const ctx = { window: {}, console };
vm.createContext(ctx);
for (const f of ['trajectory.js', 'traj3d.js', 'notams.js']) {
  const p = path.join(root, f);
  if (fs.existsSync(p)) vm.runInContext(fs.readFileSync(p, 'utf8'), ctx, { filename: f });
}
const D = ctx.window.TRAJ3D;
const T = ctx.window.TRAJ;
const N = ctx.window.NOTAM_DATA;
const fail = [];
function chk(cond, msg) { if (!cond) fail.push(msg); }
chk(!!D, 'TRAJ3D missing');
chk(!!T, 'TRAJ missing');
chk(!!N, 'NOTAM_DATA missing');
if (D) {
  chk(Array.isArray(D.site) && D.site.length === 2, 'site');
  chk(Array.isArray(D.ascent) && D.ascent.length > 10, 'ascent');
  chk(Array.isArray(D.coast) && D.coast.length > 5, 'coast');
  chk(Array.isArray(D.orbit) && D.orbit.length > 100, 'orbit');
  chk(Array.isArray(D.orbit3d) && D.orbit3d.length > 50, 'orbit3d');
  chk(D.elements && ['inc_deg', 'alt_km', 'period_min', 'e', 'a_km', 'rp_km', 'ra_km'].every(k => k in D.elements), 'elements fields');
  chk(D.ascent.every(p => p.length >= 3 && isFinite(p[0]) && isFinite(p[1]) && isFinite(p[2])), 'ascent values');
  chk(D.coast.every(p => p.length >= 3 && isFinite(p[0]) && isFinite(p[1]) && isFinite(p[2])), 'coast values');
  chk(D.orbit.every(p => p.length >= 3 && isFinite(p[0]) && isFinite(p[1]) && isFinite(p[2])), 'orbit values');
  chk(D.orbit3d.every(p => p.length === 3 && isFinite(p[0]) && isFinite(p[1]) && isFinite(p[2])), 'orbit3d values');
  chk(Array.isArray(D.events) && D.events.length >= 6, 'events');
  for (const e of D.events) {
    if (!(typeof e.name === 'string' && isFinite(e.lat) && isFinite(e.lon) && isFinite(e.alt) && isFinite(e.dist_km))) {
      fail.push('bad event ' + JSON.stringify(e));
    }
  }
  // index.html uses e.dist_km, e.alt, e.lat, e.lon, e.kind
  chk(D.events.some(e => e.kind === 'impact'), 'impact event');
  chk(D.events.some(e => e.kind === 'insert'), 'insert event');
  // lat/lon ranges
  chk([...D.ascent, ...D.coast, ...D.orbit].every(p => p[0] >= -90 && p[0] <= 90 && p[1] >= -180 && p[1] <= 180), 'lat/lon range');
  console.log('elements', D.elements);
  console.log('ascent', D.ascent.length, 'coast', D.coast.length, 'orbit', D.orbit.length, 'events', D.events.length);
  console.log('events:', D.events.map(e => `${e.kind}:${e.name}@(${e.lat},${e.lon}) h=${e.alt} d=${e.dist_km}`).join('\n         '));
  console.log('ascent first/last', D.ascent[0], D.ascent[D.ascent.length - 1]);
  console.log('coast first/last', D.coast[0], D.coast[D.coast.length - 1]);
}
if (T) {
  chk(typeof T.bearing_deg === 'number', 'TRAJ bearing');
  chk(Array.isArray(T.path) && T.path.length >= 2, 'TRAJ path');
}
if (N) chk(Array.isArray(N.notams), 'notams');
console.log(fail.length ? 'FAIL:\n' + fail.join('\n') : 'ALL CHECKS PASSED');
