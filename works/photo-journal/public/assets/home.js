/**
 * 首页：随机一张照片 → 点云 → 鼠标交互 + 拍摄参数
 *
 * 设计语言参考 DeepSeek Harness：中性偏蓝的深色底、克制的品牌蓝点缀、
 * 等宽字体做参数、细边框卡片、无多余装饰。
 */

import { imageSrc, formatDate, dateSourceLabel, humanBytes, coordsText, exposureSummary, store } from './data.js';
import { createPointCloud } from './pointcloud.js';
import { escapeHtml } from '../../src/util.js';

const $ = (s) => document.querySelector(s);

export function createHomeView({ onOpenPhoto, onEnterGallery } = {}) {
  if (!$('#pointcloud')) return { activate() {}, deactivate() {}, hasPhoto: () => false };

  const canvas = $('#pointcloud');
  const metaHost = $('#home-meta');
  const loading = $('#home-loading');

  const reducedMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches === true;

  const cloud = createPointCloud(canvas, {
    reducedMotion,
    onPick: () => next(),        // 点击画面 = 换一张
  });

  let photos = [];
  let current = null;
  let token = 0;
  let active = false;

  /* ---------------- 选片 ---------------- */

  /** 只挑"有预览图"的照片，否则点云拿不到可读的像素 */
  function pickable() {
    return photos.filter((p) => p.th || p.preview);
  }

  function randomIndex(list, avoid) {
    if (list.length <= 1) return 0;
    let i = 0;
    for (let tries = 0; tries < 8; tries++) {
      i = Math.floor(Math.random() * list.length);
      if (list[i].i !== avoid) return i;
    }
    return i;
  }

  async function show(index) {
    const list = pickable();
    if (!list.length) {
      renderEmpty();
      return false;
    }
    const item = list[((index % list.length) + list.length) % list.length];
    current = item;

    const my = ++token;
    loading.hidden = false;
    loading.textContent = '正在把照片变成点云…';

    // 详情（完整参数）与点云并行准备
    const detailPromise = store.getDetail(item.i).catch(() => null);
    const url = imageSrc(item, 'full');
    const result = await cloud.load(url);

    if (my !== token) return false;      // 期间又换了别的照片

    loading.hidden = true;
    if (!result.ok) {
      // 预览图读不了（跨域/缺失）时退到缩略图再试一次
      const fallback = item.th ? await cloud.load(item.th) : { ok: false };
      if (my !== token) return false;
      if (!fallback.ok) {
        loading.hidden = false;
        loading.textContent = '这张照片读不出像素，换一张试试';
        return false;
      }
    }

    const detail = await detailPromise;
    if (my !== token) return false;
    renderMeta(detail || itemToRecord(item));
    return true;
  }

  /** 详情还没读回来时的兜底展示 */
  function itemToRecord(p) {
    return {
      id: p.i,
      date: p.d,
      time: p.t,
      location: p.l,
      coords: p.g ? { lat: p.g[0], lng: p.g[1] } : null,
      camera: p.c ? { model: p.c } : null,
      lens: p.e,
      exposure: { aperture: p.a, shutter: p.s, iso: p.o, focal: p.f },
      tags: p.k || [],
      rating: p.r,
      color: p.cl,
      dateSource: p.ds,
      thumb: p.th,
    };
  }

  function next() {
    const list = pickable();
    if (list.length < 2) { show(0); return; }
    const avoid = current?.i;
    show(randomIndex(list, avoid));
  }

  /* ---------------- 参数面板 ---------------- */

  function renderMeta(rec) {
    if (!metaHost) return;
    const ex = rec.exposure || {};
    const camera = rec.camera ? [rec.camera.make, rec.camera.model].filter(Boolean).join(' ') : null;

    const rows = [
      ex.shutter ? ['快门', ex.shutter] : null,
      ex.aperture ? ['光圈', ex.aperture] : null,
      ex.iso ? ['ISO', String(ex.iso)] : null,
      ex.focal ? ['焦距', ex.focal] : null,
      ex.ev != null ? ['曝光补偿', `${ex.ev > 0 ? '+' : ''}${ex.ev} EV`] : null,
      camera ? ['机身', camera] : null,
      rec.lens ? ['镜头', rec.lens] : null,
      rec.pixel ? ['尺寸', `${rec.pixel.width}×${rec.pixel.height}`] : null,
      rec.color ? ['主色', rec.color] : null,
      rec.bytes ? ['体积', humanBytes(rec.bytes)] : null,
      rec.coords ? ['坐标', coordsText(rec.coords)] : null,
      rec.location ? ['地点', rec.location] : null,
      rec.dateSource ? ['日期来源', dateSourceLabel(rec.dateSource)] : null,
    ].filter(Boolean);

    const tags = [...(rec.tags || []), ...(rec.keywords || [])].slice(0, 8);

    metaHost.innerHTML = `
      <h3>${escapeHtml(rec.caption || rec.location || '未命名照片')}</h3>
      <div class="meta-date">${escapeHtml([formatDate(rec.date), rec.time].filter(Boolean).join('　'))}</div>
      <dl>
        ${rows.map(([k, v]) => `<dt>${escapeHtml(k)}</dt><dd>${escapeHtml(v)}</dd>`).join('')}
      </dl>
      ${tags.length ? `<div class="meta-tags">${tags.map((t) => `<span class="meta-tag">${escapeHtml(t)}</span>`).join('')}</div>` : ''}
      <div class="meta-stats">
        ${cloud.pointCount ? `点云 ${cloud.pointCount.toLocaleString('en-US')} 个点` : ''}
        ${photos.length ? `<br>随机取自站点 ${photos.length.toLocaleString('en-US')} 张照片` : ''}
      </div>`;
  }

  function renderEmpty() {
    if (metaHost) metaHost.innerHTML = '';
    if (loading) loading.hidden = true;
    const hero = $('.hero');
    if (!hero || $('.hero-empty')) return;
    const box = document.createElement('div');
    box.className = 'hero-empty';
    box.innerHTML = `
      <h3>还没有照片可以显示</h3>
      <p>切到「导入」页把照片文件夹拖进来，这里就会随机挑一张变成点云。</p>`;
    hero.append(box);
  }

  /* ---------------- 事件 ---------------- */

  const onResize = () => { if (active) cloud.resize(); };
  window.addEventListener('resize', onResize);

  $('#home-shuffle')?.addEventListener('click', () => next());
  $('#home-enter')?.addEventListener('click', () => onEnterGallery?.());
  $('#home-open')?.addEventListener('click', () => {
    if (current) onOpenPhoto?.(current.i, photos);
  });

  return {
    /** 数据就绪后调用，传入 search.json 的条目 */
    setPhotos(list) {
      photos = list || [];
      if (!photos.length) renderEmpty();
      return pickable().length;
    },
    activate() {
      active = true;
      cloud.setVisible(true);
      cloud.resize();
      if (!photos.length) { renderEmpty(); return; }
      if (!current) next();
      else show(photos.findIndex((p) => p.i === current.i));
    },
    deactivate() {
      active = false;
      cloud.setVisible(false);
    },
    /** 进入首页时若无当前照片就随机一张 */
    async randomNew() {
      return show(randomIndex(pickable(), current?.i));
    },
    /** 供自检脚本使用 */
    total: () => pickable().length,
    /** 指定某张（自检/分享链接用） */
    showById(id) {
      const list = pickable();
      const i = list.findIndex((p) => p.i === id);
      return i < 0 ? false : show(i);
    },
    get current() { return current; },
    get pointCount() { return cloud.pointCount; },
  };
}
