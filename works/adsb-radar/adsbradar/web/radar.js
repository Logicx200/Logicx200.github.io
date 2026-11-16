/* ADS-B radar PPI renderer — phosphor/CRT aesthetic.
 *
 * Data contract (from GET /api/state):
 *   { station:{lat,lon,set}, origin:{lat,lon}|null, range_km,
 *     source, stats:{aircraft,with_pos,msg_per_s,pos_per_s,crc_bad,max_range_km},
 *     aircraft:[ {icao,callsign,lat,lon,alt_ft,gs_kt,track_deg,vs_fpm,on_ground,
 *                 dist_km,brg_deg,age_s,seen_s,trail:[[lon,lat,ts],...]} ] }
 * Map assets: /data/coastline.json ([[lon,lat],...] lines) and
 *             /data/airports.json ([{icao,iata,name,lat,lon},...]).
 * When the server is unreachable the page shows an offline indicator and
 * keeps retrying; it never fabricates traffic.
 */
"use strict";

const DEG = Math.PI / 180;
const TAU = Math.PI * 2;
const RE = 6371.0088;

const PALETTES = {
  green: {
    grid: "#0d4024", gridMid: "#1c7a41", ring: "#1d8a4a", map: "#1f8f4d",
    sweep: "#3dff86", blip: "#8cffc0", blipCore: "#eafff3", text: "#7dffb0",
    label: "#b8ffd8", trail: "#2e9c5f", cross: "#39ff88", panel: "#3dff86",
  },
  amber: {
    grid: "#40280d", gridMid: "#7a4a1a", ring: "#8a5a1d", map: "#8f5a1f",
    sweep: "#ffb84d", blip: "#ffd27d", blipCore: "#fff3df", text: "#ffb84d",
    label: "#ffe0b0", trail: "#9c6a2e", cross: "#ffc066", panel: "#ffb84d",
  },
};

const S = {
  center: null, stationSet: false, rangeKm: 250, rangeUser: false,
  aircraft: [], stats: {}, source: "—",
  selected: null,
  sweepOn: true, trailsOn: true, labelsOn: true, palette: "green",
  offline: false, lastPanel: 0,
  map: null, mapLoaded: false,
  radio: null, transit: null, transitByIcao: {},
};

const canvas = document.getElementById("radar");
const ctx = canvas.getContext("2d");
const hudStatus = document.getElementById("hud-status");
const targetsEl = document.getElementById("targets");
const controlsEl = document.getElementById("controls");
const receiverEl = document.getElementById("receiver");

/* ------------------------------------------------------------------ geo */

function hav(lat1, lon1, lat2, lon2) {
  const p1 = lat1 * DEG, p2 = lat2 * DEG;
  const dp = (lat2 - lat1) * DEG, dl = (lon2 - lon1) * DEG;
  const a = Math.sin(dp / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2;
  return 2 * RE * Math.asin(Math.min(1, Math.sqrt(a)));
}
function brg(lat1, lon1, lat2, lon2) {
  const p1 = lat1 * DEG, p2 = lat2 * DEG, dl = (lon2 - lon1) * DEG;
  const y = Math.sin(dl) * Math.cos(p2);
  const x = Math.cos(p1) * Math.sin(p2) - Math.sin(p1) * Math.cos(p2) * Math.cos(dl);
  return (Math.atan2(y, x) / DEG + 360) % 360;
}

let W = 0, H = 0, R = 0, CX = 0, CY = 0;

function resize() {
  const dpr = window.devicePixelRatio || 1;
  W = window.innerWidth; H = window.innerHeight;
  canvas.width = Math.round(W * dpr);
  canvas.height = Math.round(H * dpr);
  canvas.style.width = W + "px";
  canvas.style.height = H + "px";
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  // On mobile the bottom panel docks over the lower part; centre the PPI above it.
  const mobile = W < 700;
  const visH = mobile ? H * 0.58 : H;
  CX = W / 2;
  CY = visH / 2;
  R = Math.min(W, visH) / 2 - 30;
  rebuildMapCache();
}
window.addEventListener("resize", resize);

function proj(lat, lon) {
  const d = hav(S.center.lat, S.center.lon, lat, lon);
  const b = brg(S.center.lat, S.center.lon, lat, lon);
  const r = (d / S.rangeKm) * R;
  const x = CX + Math.sin(b * DEG) * r;
  const y = CY - Math.cos(b * DEG) * r;
  return { x, y, d, b };
}

/* -------------------------------------------------------------- map data */

function rebuildMapCache() {
  S.map.polylines = [];
  S.map.airports = [];
  S.map.cities = [];
  if (!S.center) return;
  const lines = S.map._rawLines || [];
  const apts = S.map._rawApts || [];
  const cities = S.map._rawCities || [];
  const lim = S.rangeKm * 1.5;
  for (const line of lines) {
    let near = false;
    for (const pt of line) {
      if (hav(S.center.lat, S.center.lon, pt[1], pt[0]) < lim) { near = true; break; }
    }
    if (!near) continue;
    S.map.polylines.push(line.map((p) => proj(p[1], p[0])));
  }
  for (const a of apts) {
    const d = hav(S.center.lat, S.center.lon, a.lat, a.lon);
    if (d < S.rangeKm) S.map.airports.push(Object.assign({}, a, proj(a.lat, a.lon)));
  }
  for (const c of cities) {
    const d = hav(S.center.lat, S.center.lon, c.lat, c.lon);
    if (d < S.rangeKm) S.map.cities.push(Object.assign({}, c, proj(c.lat, c.lon)));
  }
}

function loadMapData() {
  fetch("data/coastline.json")
    .then((r) => (r.ok ? r.json() : Promise.reject()))
    .then((lines) => { S.map._rawLines = lines; rebuildMapCache(); })
    .catch(() => {});
  fetch("data/airports.json")
    .then((r) => (r.ok ? r.json() : Promise.reject()))
    .then((apts) => { S.map._rawApts = apts; rebuildMapCache(); })
    .catch(() => {});
  fetch("data/cities.json")
    .then((r) => (r.ok ? r.json() : Promise.reject()))
    .then((cities) => { S.map._rawCities = cities; rebuildMapCache(); })
    .catch(() => {});
}

/* -------------------------------------------------------------- polling */

async function poll() {
  try {
    const r = await fetch("api/state", { cache: "no-store" });
    if (!r.ok) throw new Error("bad status");
    S.offline = false;
    applyState(await r.json());
  } catch (e) {
    S.offline = true;
  }
}

function applyState(st) {
  S.source = st.source || "—";
  S.stats = st.stats || {};
  if (!S.rangeUser) S.rangeKm = st.range_km || S.rangeKm;
  S.radio = st.radio || null;
  S.transit = st.transit || null;
  S.transitByIcao = {};
  if (S.transit && S.transit.upcoming) {
    for (const t of S.transit.upcoming) S.transitByIcao[t.icao] = t;
  }
  buildReceiver();
  if (st.station && st.station.set) {
    const c = { lat: st.station.lat, lon: st.station.lon };
    if (!S.center || S.center.lat !== c.lat || S.center.lon !== c.lon) {
      S.center = c; rebuildMapCache();
    }
    S.stationSet = true;
  } else if (st.origin) {
    const c = { lat: st.origin.lat, lon: st.origin.lon };
    if (!S.center) { S.center = c; rebuildMapCache(); }
  }
  // project every aircraft for rendering
  S.aircraft = (st.aircraft || []).map((a) => {
    const o = Object.assign({}, a);
    if (a.lat != null && S.center) {
      const p = proj(a.lat, a.lon);
      o._x = p.x; o._y = p.y; o._d = p.d; o._b = p.b;
    }
    return o;
  });
  updatePanel();
}

/* --------------------------------------------------------------- panel */

function buildReceiver() {
  const r = S.radio;
  if (S.offline) {
    receiverEl.innerHTML = '<div class="rx-title">接收机</div><div class="rx-status"><span class="dot off"></span>无法连接服务，正在重试…</div>';
    return;
  }
  if (!r) {
    receiverEl.innerHTML = '<div class="rx-title">接收机</div><div class="rx-status"><span class="dot off"></span>等待状态…</div>';
    return;
  }
  const conn = r.connected;
  const dotCls = conn ? "on" : "off";
  const dotTxt = conn ? (r.reading ? "已连接 · 正在读取" : "已连接（未读取）") : "未连接";
  const nf = r.noise_floor != null ? (+r.noise_floor).toFixed(3) : "—";
  const pk = r.peak != null ? (+r.peak).toFixed(2) : "—";
  const gain = r.gain != null ? String(r.gain) : "—";
  const tuner = r.tuner_type != null ? ` · tuner ${r.tuner_type}` : "";
  const status = `<span class="dot ${dotCls}"></span>${dotTxt}${tuner} · 底噪 ${nf} · 峰值 ${pk} · 增益 ${gain} dB`;
  let err = "";
  if (r.error) err = `<div class="err">⚠ ${r.error}</div>`;

  const gains = ["auto", "19.7", "28.0", "33.8", "40.2", "43.9", "49.6"];
  const cur = String(r.gain ?? "");
  const btns = gains.map((g) => {
    const label = g === "auto" ? "自动" : g;
    let active = "";
    if (g === "auto") active = (cur === "0.0" || cur === "0") ? "active" : "";
    else active = (Math.abs(parseFloat(cur) - parseFloat(g)) < 0.05) ? "active" : "";
    return `<button data-gain="${g}" class="${active}">${label}</button>`;
  }).join("");

  receiverEl.innerHTML =
    `<div class="rx-title">接收机 · ${S.source.toUpperCase()}</div>` +
    `<div class="rx-status">${status}</div>` + err +
    `<div class="gainrow"><span class="glabel">增益</span>${btns}</div>`;
}

async function setGain(g) {
  try {
    await fetch("api/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ gain: g }),
    });
    if (S.radio) S.radio.gain = g;
    buildReceiver();
  } catch (e) { /* ignore */ }
}

function buildControls() {
  const pal = S.palette;
  controlsEl.innerHTML = `
    <div class="row">
      ${[50, 100, 200, 400].map((r) =>
        `<button data-range="${r}" class="${r === S.rangeKm ? "active" : ""}">${r}km</button>`).join("")}
    </div>
    <div class="row">
      <button id="b-sweep" class="${S.sweepOn ? "active" : ""}">扫描线</button>
      <button id="b-trails" class="${S.trailsOn ? "active" : ""}">尾迹</button>
      <button id="b-labels" class="${S.labelsOn ? "active" : ""}">标签</button>
      <button id="b-pal">${pal === "green" ? "绿磷" : "琥珀"}</button>
    </div>
  `;
  controlsEl.querySelectorAll("[data-range]").forEach((b) =>
    b.addEventListener("click", () => { S.rangeKm = +b.dataset.range; S.rangeUser = true; rebuildMapCache(); buildControls(); }));
  document.getElementById("b-sweep").addEventListener("click", () => { S.sweepOn = !S.sweepOn; buildControls(); });
  document.getElementById("b-trails").addEventListener("click", () => { S.trailsOn = !S.trailsOn; buildControls(); });
  document.getElementById("b-labels").addEventListener("click", () => { S.labelsOn = !S.labelsOn; buildControls(); });
  document.getElementById("b-pal").addEventListener("click", () => {
    S.palette = S.palette === "green" ? "amber" : "green";
    applyPalette(); buildControls();
  });
}

function applyPalette() {
  const p = PALETTES[S.palette];
  const root = document.documentElement.style;
  root.setProperty("--c-grid", p.grid);
  root.setProperty("--c-dim", p.ring);
  root.setProperty("--c-mid", p.gridMid);
  root.setProperty("--c-bright", p.panel);
  root.setProperty("--c-text", p.text);
  document.body.style.color = p.text;
}

function updatePanel() {
  const now = performance.now();
  if (now - S.lastPanel < 400) return;
  S.lastPanel = now;
  const list = S.aircraft.slice().sort((a, b) => (a.dist_km ?? 1e9) - (b.dist_km ?? 1e9));
  const head = `目标 ${S.stats.aircraft ?? list.length} · 定位 ${S.stats.with_pos ?? 0}`;
  let html = `<div class="head">${head}</div>`;
  if (S.transit && S.transit.upcoming && S.transit.upcoming.length) {
    html += `<div class="head transit-head">凌日/月预测</div>`;
    for (const t of S.transit.upcoming.slice(0, 6)) {
      const cs = t.callsign || t.icao;
      const body = t.body === "sun" ? "☀ 凌日" : "☾ 凌月";
      const eta = t.eta_s < 60 ? Math.round(t.eta_s) + "s" : (t.eta_s / 60).toFixed(1) + "min";
      html += `<div class="trk transit">
        <div class="cs">${cs}</div>
        <div class="meta">${body} · ${eta}后 · 最近 ${t.dist_deg}°</div>
      </div>`;
    }
  }
  for (const a of list.slice(0, 40)) {
    if (a.lat == null) continue;
    const cs = a.callsign || a.icao;
    const fl = a.alt_ft != null ? "FL" + Math.round(a.alt_ft / 100).toString().padStart(3, "0") : "---";
    const spd = a.gs_kt != null ? Math.round(a.gs_kt) + "kt" : "---";
    const dist = a.dist_km != null ? Math.round(a.dist_km) + "km" : "";
    const br = a.brg_deg != null ? String(Math.round(a.brg_deg)).padStart(3, "0") + "°" : "";
    html += `<div class="trk ${a.icao === S.selected ? "sel" : ""}" data-icao="${a.icao}">
      <div class="cs">${cs}</div>
      <div class="meta">${fl} · ${spd}</div>
      <div class="meta">${dist} ${br}</div>
    </div>`;
  }
  targetsEl.innerHTML = html;
  targetsEl.querySelectorAll(".trk").forEach((el) =>
    el.addEventListener("click", () => {
      const icao = el.dataset.icao;
      S.selected = S.selected === icao ? null : icao;
      updatePanel();
    }));
}

/* -------------------------------------------------------------- drawing */

function scrang(b) { return (90 - b) * DEG; }

function drawScope(tMs) {
  const p = PALETTES[S.palette];
  ctx.clearRect(0, 0, W, H);
  ctx.fillStyle = "#020906";
  ctx.fillRect(0, 0, W, H);

  // range rings
  ctx.lineWidth = 1;
  for (let i = 1; i <= 4; i++) {
    const rr = (R * i) / 4;
    ctx.strokeStyle = i === 4 ? p.ring : p.grid;
    ctx.beginPath(); ctx.arc(CX, CY, rr, 0, TAU); ctx.stroke();
    ctx.fillStyle = p.ring;
    ctx.font = "10px Consolas, monospace";
    ctx.textAlign = "left"; ctx.textBaseline = "bottom";
    ctx.fillText(Math.round((S.rangeKm * i) / 4) + "km", CX + 4, CY - rr + 2);
  }

  // bearing spokes + ticks
  for (let a = 0; a < 360; a += 10) {
    const t = scrang(a);
    const major = a % 30 === 0;
    const r1 = R, r2 = R - (major ? 12 : 6);
    ctx.strokeStyle = major ? p.gridMid : p.grid;
    ctx.beginPath();
    ctx.moveTo(CX + Math.cos(t) * r1, CY + Math.sin(t) * r1);
    ctx.lineTo(CX + Math.cos(t) * r2, CY + Math.sin(t) * r2);
    ctx.stroke();
  }
  ctx.fillStyle = p.text;
  ctx.font = "bold 12px Consolas, monospace";
  ctx.textAlign = "center"; ctx.textBaseline = "middle";
  const cards = [[0, "N"], [90, "E"], [180, "S"], [270, "W"]];
  for (const [a, c] of cards) {
    const t = scrang(a), rr = R + 18;
    ctx.fillText(c, CX + Math.cos(t) * rr, CY + Math.sin(t) * rr);
  }

  // crosshair
  ctx.strokeStyle = p.grid;
  ctx.beginPath();
  ctx.moveTo(CX - 10, CY); ctx.lineTo(CX + 10, CY);
  ctx.moveTo(CX, CY - 10); ctx.lineTo(CX, CY + 10);
  ctx.stroke();
  ctx.strokeStyle = p.cross;
  ctx.beginPath(); ctx.arc(CX, CY, 2, 0, TAU); ctx.stroke();

  // map
  if (S.map) {
    ctx.strokeStyle = p.map;
    ctx.lineWidth = 1;
    for (const line of S.map.polylines) {
      ctx.beginPath();
      line.forEach((pt, i) => (i ? ctx.lineTo(pt.x, pt.y) : ctx.moveTo(pt.x, pt.y)));
      ctx.stroke();
    }
    ctx.fillStyle = p.map;
    for (const a of S.map.airports) {
      const s = 3;
      ctx.beginPath();
      ctx.moveTo(a.x - s, a.y); ctx.lineTo(a.x + s, a.y);
      ctx.moveTo(a.x, a.y - s); ctx.lineTo(a.x, a.y + s);
      ctx.stroke();
    }
    // cities: dot + label (decluttered)
    ctx.fillStyle = p.label;
    for (const c of S.map.cities) {
      ctx.beginPath(); ctx.arc(c.x, c.y, 1.8, 0, TAU); ctx.fill();
    }
    ctx.font = "10px Consolas, monospace";
    ctx.textAlign = "center"; ctx.textBaseline = "top";
    const placed = [];
    for (const c of S.map.cities) {
      let collide = false;
      for (const r of placed) if (Math.abs(c.x - r.x) < 48 && Math.abs(c.y - r.y) < 12) { collide = true; break; }
      if (collide) continue;
      placed.push({ x: c.x, y: c.y });
      ctx.fillStyle = p.map;
      ctx.fillText(c.name, c.x, c.y + 3);
    }
    // airports: IATA/ICAO code label
    ctx.textAlign = "left"; ctx.textBaseline = "alphabetic";
    for (const a of S.map.airports) {
      const code = a.iata || a.icao;
      if (!code) continue;
      let collide = false;
      for (const r of placed) if (Math.abs(a.x + 5 - r.x) < 48 && Math.abs(a.y - 5 - r.y) < 12) { collide = true; break; }
      if (collide) continue;
      placed.push({ x: a.x + 5, y: a.y - 5 });
      ctx.fillStyle = p.ring;
      ctx.fillText(code, a.x + 5, a.y - 4);
    }
  }

  drawBodies(p);
  drawSweep(tMs, p);
  drawAircraft(tMs, p);
}

function drawBodies(p) {
  if (!S.transit || !S.transit.bodies) return;
  const bodies = S.transit.bodies;
  const items = [
    ["sun", "太阳", bodies.sun, "#ffd24d"],
    ["moon", "月亮", bodies.moon, "#cfe0ff"],
  ];
  for (const [key, label, b, color] of items) {
    if (!b || b.az == null || b.el == null) continue;
    const t = b.az * DEG;
    const r = R - 6;
    const x = CX + Math.sin(t) * r;
    const y = CY - Math.cos(t) * r;
    // radial direction hint
    ctx.strokeStyle = color;
    ctx.globalAlpha = 0.18;
    ctx.lineWidth = 1;
    ctx.setLineDash([3, 5]);
    ctx.beginPath();
    ctx.moveTo(CX, CY);
    ctx.lineTo(CX + Math.sin(t) * R, CY - Math.cos(t) * R);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.globalAlpha = 1;
    // disc at the rim
    ctx.fillStyle = color;
    ctx.shadowColor = color; ctx.shadowBlur = 8;
    ctx.beginPath(); ctx.arc(x, y, 5, 0, TAU); ctx.fill();
    ctx.shadowBlur = 0;
    // label
    ctx.fillStyle = color;
    ctx.font = "bold 11px Consolas, monospace";
    ctx.textAlign = "left"; ctx.textBaseline = "alphabetic";
    const up = b.el >= 0;
    ctx.fillText(`${label} ${b.az.toFixed(0)}° ${up ? "+" : ""}${b.el.toFixed(0)}°`, x + 8, y + (up ? -6 : 12));
  }
}

function drawSweep(tMs, p) {
  if (!S.sweepOn) return;
  const period = 4.0;
  const sweep = ((tMs / 1000) * (360 / period)) % 360;
  const a0 = scrang(sweep);
  if (ctx.createConicGradient) {
    const g = ctx.createConicGradient(a0, CX, CY);
    const rgb = hexToRgb(p.sweep);
    const fade = 70 / 360;
    g.addColorStop(0, `rgba(${rgb},0.28)`);   // brightest right on the sweep line
    g.addColorStop(fade, `rgba(${rgb},0)`);   // fades away behind it
    g.addColorStop(1, `rgba(${rgb},0)`);
    ctx.fillStyle = g;
    ctx.beginPath(); ctx.arc(CX, CY, R, 0, TAU); ctx.fill();
  }
  const t = scrang(sweep);
  ctx.strokeStyle = p.sweep;
  ctx.lineWidth = 1.6;
  ctx.shadowColor = p.sweep; ctx.shadowBlur = 10;
  ctx.beginPath();
  ctx.moveTo(CX, CY);
  ctx.lineTo(CX + Math.cos(t) * R, CY + Math.sin(t) * R);
  ctx.stroke();
  ctx.shadowBlur = 0;
}

function hexToRgb(hex) {
  const n = parseInt(hex.slice(1), 16);
  return `${(n >> 16) & 255},${(n >> 8) & 255},${n & 255}`;
}

function drawAircraft(tMs, p) {
  if (!S.center) return;
  const period = 4.0;
  const sweep = ((tMs / 1000) * (360 / period)) % 360;
  const labels = [];

  for (const a of S.aircraft) {
    if (a.lat == null || a._x == null) continue;
    const x = a._x, y = a._y;
    const onScope = Math.hypot(x - CX, y - CY) <= R + 20;

    // trail
    if (S.trailsOn && a.trail && a.trail.length && S.center) {
      ctx.strokeStyle = p.trail;
      ctx.lineWidth = 1;
      ctx.globalAlpha = 0.5;
      ctx.beginPath();
      let started = false;
      for (const [lon, lat] of a.trail) {
        const q = proj(lat, lon);
        if (Math.hypot(q.x - CX, q.y - CY) > R + 30) continue;
        if (!started) { ctx.moveTo(q.x, q.y); started = true; }
        else ctx.lineTo(q.x, q.y);
      }
      ctx.stroke();
      ctx.globalAlpha = 1;
    }

    // phosphor brightness: painted bright as the sweep passes, then decays behind it
    const behind = (sweep - a._b + 360) % 360;
    const glow = Math.exp(-behind / 45);
    let alpha = 0.62 + 0.38 * glow;   // base 0.62 so targets stay clearly visible
    if (a.age_s > 30) alpha *= 0.7;
    if (!onScope) alpha *= 0.4;

    // velocity vector
    const hdg = a.track_deg != null ? a.track_deg : null;
    const vlen = hdg != null ? Math.min(24, 5 + (a.gs_kt || 0) / 22) : 0;

    ctx.save();
    ctx.globalAlpha = Math.max(0.06, alpha);
    ctx.translate(x, y);
    if (hdg != null) ctx.rotate(hdg * DEG);

    // chevron
    ctx.fillStyle = p.blip;
    ctx.beginPath();
    ctx.moveTo(0, -4);
    ctx.lineTo(3.4, 3);
    ctx.lineTo(0, 1);
    ctx.lineTo(-3.4, 3);
    ctx.closePath();
    ctx.fill();
    ctx.restore();

    // core dot + glow
    ctx.save();
    ctx.globalAlpha = alpha;
    ctx.shadowColor = p.sweep; ctx.shadowBlur = 8;
    ctx.fillStyle = p.blipCore;
    ctx.beginPath(); ctx.arc(x, y, 1.6, 0, TAU); ctx.fill();
    ctx.shadowBlur = 0;
    if (vlen && hdg != null) {
      const t = hdg * DEG;
      ctx.strokeStyle = p.blip;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(x, y);
      ctx.lineTo(x + Math.sin(t) * vlen, y - Math.cos(t) * vlen);
      ctx.stroke();
    }
    ctx.restore();

    // transit marker: a coloured ring + Sun/Moon glyph around aircraft that
    // are predicted to transit, so they stand out on the scope.
    const tr = S.transitByIcao[a.icao];
    if (tr && onScope) {
      const tcolor = tr.body === "sun" ? "#ffd24d" : "#cfe0ff";
      ctx.save();
      ctx.globalAlpha = Math.max(0.55, alpha);
      ctx.strokeStyle = tcolor;
      ctx.lineWidth = 1.6;
      ctx.shadowColor = tcolor; ctx.shadowBlur = 10;
      ctx.beginPath(); ctx.arc(x, y, 9, 0, TAU); ctx.stroke();
      ctx.shadowBlur = 0;
      ctx.fillStyle = tcolor;
      ctx.font = "bold 12px Consolas, monospace";
      ctx.textAlign = "center"; ctx.textBaseline = "middle";
      ctx.fillText(tr.body === "sun" ? "☀" : "☾", x, y - 16);
      ctx.restore();
    }

    if (S.labelsOn && onScope) labels.push(a);
  }

  drawLabels(labels, p);
}

function drawLabels(labels, p) {
  const placed = [];
  const sel = labels.find((a) => a.icao === S.selected);
  const order = sel ? [sel, ...labels.filter((a) => a !== sel)] : labels;
  for (const a of order) {
    if (!a.callsign && a.icao !== S.selected) continue;
    const x = a._x, y = a._y;
    const ox = x + 10, oy = y - 10;
    let collide = false;
    for (const r of placed) {
      if (Math.abs(ox - r.x) < 90 && Math.abs(oy - r.y) < 16) { collide = true; break; }
    }
    if (collide && a.icao !== S.selected) continue;
    placed.push({ x: ox, y: oy });

    const cs = a.callsign || a.icao;
    const fl = a.alt_ft != null ? "FL" + Math.round(a.alt_ft / 100).toString().padStart(3, "0") : "----";
    const spd = a.gs_kt != null ? Math.round(a.gs_kt) + "kt" : "---";
    const l2 = `${fl} ${spd} ${Math.round(a.dist_km ?? 0)}km ${String(Math.round(a.brg_deg ?? 0)).padStart(3, "0")}°`;

    ctx.strokeStyle = p.label;
    ctx.lineWidth = 1;
    ctx.globalAlpha = 0.5;
    ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(ox, oy); ctx.stroke();
    ctx.globalAlpha = 1;

    ctx.fillStyle = p.label;
    ctx.font = "11px Consolas, monospace";
    ctx.textAlign = "left"; ctx.textBaseline = "alphabetic";
    ctx.fillText(cs, ox, oy);
    ctx.fillStyle = p.text;
    ctx.fillText(l2, ox, oy + 12);
  }
}

/* ----------------------------------------------------------------- loop */

function frame(tMs) {
  drawScope(tMs);
  // HUD status
  const st = S.stats;
  hudStatus.textContent =
    `${S.source}  ·  ${st.aircraft ?? 0} 目标 / ${st.with_pos ?? 0} 定位` +
    `  ·  ${st.msg_per_s ?? 0} msg/s` +
    (S.offline ? "  ·  ⚠ 无法连接服务" : "");
  requestAnimationFrame(frame);
}

/* ----------------------------------------------------------------- boot */

function boot() {
  S.map = { _rawLines: [], _rawApts: [], _rawCities: [], polylines: [], airports: [], cities: [] };
  receiverEl.addEventListener("click", (e) => {
    const b = e.target.closest("[data-gain]");
    if (b) setGain(b.dataset.gain);
  });
  buildControls();
  applyPalette();
  loadMapData();
  resize();
  poll();
  setInterval(poll, 250);
  requestAnimationFrame(frame);
}

boot();
