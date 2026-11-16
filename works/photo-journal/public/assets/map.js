/**
 * 地图视图：内嵌世界底图 + GPS 光点
 *
 * 底图来自 scripts/build-atlas.mjs 烘焙的 Natural Earth 110m 海岸线，
 * 运行时不依赖任何在线地图服务（离线可用、不泄露访问行为）。
 * 如果你想要真实街道底图，见 README 的"接入在线地图"一节。
 *
 * 交互：滚轮缩放 / 拖拽平移 / 悬停显示 / 点击回调筛选
 */

import { WORLD_LAND } from './mapatlas.js';
import { encodePath } from './data.js';

const LAT_BOUND = 84;

export function createMap({ canvas, tip, onPick }) {
  const ctx = canvas.getContext('2d');
  let points = [];           // { lat, lng, count, items:[...] }
  let view = { scale: 1, x: 0, y: 0, w: 0, h: 0 };
  let base = { scale: 1, x: 0, y: 0 };
  let hover = null;
  let dragging = null;
  let dpr = Math.min(2, window.devicePixelRatio || 1);

  function resize() {
    const rect = canvas.getBoundingClientRect();
    if (!rect.width) return;
    dpr = Math.min(2, window.devicePixelRatio || 1);
    canvas.width = Math.round(rect.width * dpr);
    canvas.height = Math.round(rect.height * dpr);
    view.w = rect.width;
    view.h = rect.height;
    if (!base.w) fit();
    else draw();
  }

  function project(lng, lat) {
    const x = (lng + 180) / 360 * view.w;
    const clampedLat = Math.max(-LAT_BOUND, Math.min(LAT_BOUND, lat));
    const y = (90 - clampedLat) / (2 * LAT_BOUND * 180 / 180) * view.h;
    return [x, y];
  }

  function transform(lng, lat) {
    const [x, y] = project(lng, lat);
    return [x * view.scale + view.x, y * view.scale + view.y];
  }

  function fit() {
    if (!view.w) return;
    view.scale = 1;
    view.x = 0;
    // 让地图在垂直方向居中
    view.y = 0;
    base = { scale: 1, x: 0, y: 0, w: view.w, h: view.h };
    draw();
  }

  /** 根据数据范围自动缩放到有照片的区域（照片全在中国时不会显示整张世界地图） */
  function fitToPoints() {
    if (!points.length || !view.w) { fit(); return; }
    let minLat = 90; let maxLat = -90; let minLng = 180; let maxLng = -180;
    for (const p of points) {
      minLat = Math.min(minLat, p.lat); maxLat = Math.max(maxLat, p.lat);
      minLng = Math.min(minLng, p.lng); maxLng = Math.max(maxLng, p.lng);
    }
    const padLat = Math.max(2.5, (maxLat - minLat) * 0.35);
    const padLng = Math.max(2.5, (maxLng - minLng) * 0.35);
    minLat -= padLat; maxLat += padLat; minLng -= padLng; maxLng += padLng;

    const [x0, y0] = project(minLng, maxLat);
    const [x1, y1] = project(maxLng, minLat);
    const spanX = Math.max(1, x1 - x0);
    const spanY = Math.max(1, y1 - y0);
    const scale = Math.min(view.w / spanX, view.h / spanY, 40);
    view.scale = Math.max(1, scale);
    const cx = (x0 + x1) / 2;
    const cy = (y0 + y1) / 2;
    view.x = view.w / 2 - cx * view.scale;
    view.y = view.h / 2 - cy * view.scale;
    draw();
  }

  function draw() {
    if (!view.w) return;
    ctx.save();
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, view.w, view.h);

    const css = getComputedStyle(document.documentElement);
    const isLight = document.documentElement.dataset.theme === 'light'
      || (!document.documentElement.dataset.theme && window.matchMedia('(prefers-color-scheme: light)').matches);
    const landFill = isLight ? '#dbe6f0' : '#16202c';
    const landStroke = isLight ? '#b3c5d6' : '#2b3d52';
    const gridColor = isLight ? 'rgba(0,0,0,0.07)' : 'rgba(255,255,255,0.06)';

    // 经纬网
    ctx.lineWidth = 1;
    ctx.strokeStyle = gridColor;
    for (let lat = -60; lat <= 60; lat += 30) {
      const [, y] = transform(0, lat);
      ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(view.w, y); ctx.stroke();
    }
    for (let lng = -180; lng < 180; lng += 30) {
      const [x] = transform(lng, 0);
      ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, view.h); ctx.stroke();
    }

    // 陆地
    ctx.beginPath();
    for (const ring of WORLD_LAND) {
      for (let i = 0; i < ring.length; i++) {
        const [x, y] = transform(ring[i][0], ring[i][1]);
        if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      }
      ctx.closePath();
    }
    ctx.fillStyle = landFill;
    ctx.fill();
    ctx.strokeStyle = landStroke;
    ctx.lineWidth = Math.min(1.4, 0.6 + view.scale * 0.02);
    ctx.stroke();

    // 光点
    const radiusOf = (n) => Math.min(26, 4 + Math.log2(n + 1) * 3.4);
    ctx.lineWidth = 1.5;
    for (const p of points) {
      const [x, y] = transform(p.lng, p.lat);
      if (x < -40 || y < -40 || x > view.w + 40 || y > view.h + 40) continue;
      const r = radiusOf(p.count);
      const isHover = hover && hover.p === p;
      ctx.beginPath();
      ctx.arc(x, y, r, 0, Math.PI * 2);
      ctx.fillStyle = isHover ? 'rgba(255, 209, 102, 0.85)' : 'rgba(110, 168, 254, 0.55)';
      ctx.fill();
      ctx.strokeStyle = isHover ? '#ffd166' : 'rgba(110, 168, 254, 0.95)';
      ctx.stroke();
      if (p.count > 1 && r > 8) {
        ctx.fillStyle = isLight ? '#0f172a' : '#eaf1ff';
        ctx.font = `${Math.round(Math.min(14, r))}px -apple-system, "Segoe UI", sans-serif`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(String(p.count), x, y + 0.5);
      }
    }
    ctx.restore();
  }

  function hit(clientX, clientY) {
    const rect = canvas.getBoundingClientRect();
    const mx = clientX - rect.left;
    const my = clientY - rect.top;
    let best = null;
    let bestD = Infinity;
    for (const p of points) {
      const [x, y] = transform(p.lng, p.lat);
      const d = Math.hypot(x - mx, y - my);
      const r = Math.min(26, 4 + Math.log2(p.count + 1) * 3.4) + 4;
      if (d <= r && d < bestD) { bestD = d; best = { p, x, y }; }
    }
    return best;
  }

  /* ---------------- 事件 ---------------- */

  canvas.addEventListener('wheel', (e) => {
    e.preventDefault();
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    const factor = Math.exp(-e.deltaY * 0.0016);
    const next = Math.max(1, Math.min(80, view.scale * factor));
    const k = next / view.scale;
    view.x = mx - (mx - view.x) * k;
    view.y = my - (my - view.y) * k;
    view.scale = next;
    draw();
  }, { passive: false });

  canvas.addEventListener('pointerdown', (e) => {
    canvas.setPointerCapture(e.pointerId);
    dragging = { x: e.clientX, y: e.clientY, vx: view.x, vy: view.y, moved: false };
    canvas.classList.add('is-dragging');
  });

  canvas.addEventListener('pointermove', (e) => {
    if (dragging) {
      const dx = e.clientX - dragging.x;
      const dy = e.clientY - dragging.y;
      if (Math.abs(dx) + Math.abs(dy) > 3) dragging.moved = true;
      view.x = dragging.vx + dx;
      view.y = dragging.vy + dy;
      draw();
      return;
    }
    const h = hit(e.clientX, e.clientY);
    if ((h && h.p) !== (hover && hover.p)) {
      hover = h;
      draw();
    } else if (h) {
      hover = h;
    }
    if (h) showTip(h, e.clientX, e.clientY); else hideTip();
  });

  canvas.addEventListener('pointerup', (e) => {
    canvas.classList.remove('is-dragging');
    const wasDrag = dragging && dragging.moved;
    dragging = null;
    if (!wasDrag) {
      const h = hit(e.clientX, e.clientY);
      if (h && onPick) onPick(h.p);
    }
  });

  canvas.addEventListener('pointerleave', () => { hideTip(); hover = null; draw(); });

  function showTip(h, clientX, clientY) {
    const rect = canvas.parentElement.getBoundingClientRect();
    const p = h.p;
    tip.hidden = false;
    const cover = p.items[0]?.th;
    tip.innerHTML = `${cover ? `<img src="${encodePath(cover)}" alt="">` : ''}<div><strong>${escapeHtml(p.name)}</strong><br><span class="muted">${p.count} 张${
      p.first ? ` · ${p.first}${p.last && p.last !== p.first ? ' → ' + p.last : ''}` : ''}</span></div>`;
    const tipRect = tip.getBoundingClientRect();
    let left = h.x + 14;
    let top = h.y - tipRect.height - 10;
    if (left + tipRect.width > view.w) left = h.x - tipRect.width - 14;
    if (top < 0) top = h.y + 14;
    tip.style.left = `${Math.max(4, left)}px`;
    tip.style.top = `${Math.max(4, top)}px`;
  }

  function hideTip() { tip.hidden = true; }

  window.addEventListener('resize', () => { resize(); draw(); });

  return {
    setPhotos(list) {
      const map = new Map();
      for (const p of list) {
        if (!p.g) continue;
        const [lat, lng] = p.g;
        const key = `${lat.toFixed(2)},${lng.toFixed(2)}|${p.l || ''}`;
        if (!map.has(key)) {
          map.set(key, { lat, lng, name: p.l || '未命名位置', count: 0, items: [], first: p.d, last: p.d });
        }
        const e = map.get(key);
        e.count++;
        e.items.push(p);
        if (p.d && (!e.first || p.d < e.first)) e.first = p.d;
        if (p.d && (!e.last || p.d > e.last)) e.last = p.d;
      }
      points = [...map.values()].sort((a, b) => b.count - a.count);
      return points.length;
    },
    render() { resize(); fitToPoints(); draw(); },
    reset: () => { fitToPoints(); },
    /** 把视图移到某个坐标（从灯箱跳转过来时用） */
    focusOn(rec) {
      if (!rec || !rec.g) return;
      const [lat, lng] = rec.g;
      resize();
      view.scale = Math.max(view.scale, 6);
      const [x, y] = project(lng, lat);
      view.x = view.w / 2 - x * view.scale;
      view.y = view.h / 2 - y * view.scale;
      hover = null;
      draw();
    },
    get points() { return points; },
  };
}

function escapeHtml(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}
