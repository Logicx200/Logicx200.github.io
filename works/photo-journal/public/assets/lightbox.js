/**
 * 灯箱：查看大图 + 完整拍摄参数
 *
 * 参数面板的数据来自按月加载的完整记录（public/data/photos-YYYY-MM.json），
 * 因此打开时可能会先显示"加载中"。
 */

import {
  store, imageSrc, downloadSrc, formatDate, dateSourceLabel,
  humanBytes, coordsText, detailFromSummary, exposureSummary,
} from './data.js';
import { escapeHtml } from '../../src/util.js';

export function createLightbox({ root, onIndexChange }) {
  const canvas = root.querySelector('#lb-canvas');
  const spinner = root.querySelector('#lb-spinner');
  const caption = root.querySelector('#lb-caption');
  const info = root.querySelector('#lb-info');

  let seq = [];        // 当前列表（search.json 条目）
  let index = -1;
  let openToken = 0;

  function close() {
    root.hidden = true;
    document.body.style.overflow = '';
    canvas.replaceChildren();
    onIndexChange?.(null);
  }

  async function show(list, i) {
    seq = list || [];
    index = i;
    if (index < 0 || index >= seq.length) { close(); return; }
    root.hidden = false;
    document.body.style.overflow = 'hidden';
    onIndexChange?.(seq[index].i);

    const summary = seq[index];
    renderInfo(detailFromSummary(summary), true);

    const token = ++openToken;
    canvas.classList.add('is-loading');
    canvas.replaceChildren(spinner);
    spinner.hidden = false;

    // 先取完整记录（含 1600px 预览图路径），拿不到就退回缩略图
    const detail = await store.getDetail(summary.i);
    if (token !== openToken) return;
    const src = imageSrc(detail || summary, 'full');

    const img = new Image();
    img.alt = summary.x || summary.l || '照片';
    img.addEventListener('load', () => {
      if (token !== openToken) return;
      canvas.classList.remove('is-loading');
      canvas.replaceChildren(img);
      preloadNeighbours();
    });
    img.addEventListener('error', () => {
      if (token !== openToken) return;
      canvas.classList.remove('is-loading');
      canvas.innerHTML = '<p class="muted">无法加载这张照片（可能未生成缩略图，或原图不在仓库里）。</p>';
    });
    img.src = src;

    renderInfo(detail || detailFromSummary(summary), false);
  }

  function preloadNeighbours() {
    for (const d of [-1, 1]) {
      const n = seq[index + d];
      if (!n) continue;
      const im = new Image();
      // seq 里的条目是 search.json 的精简形状（字段名 th），这里只预载缩略图
      im.src = imageSrc(n, 'thumb');
    }
  }

  function renderInfo(rec, loading) {
    const camera = rec.camera ? [rec.camera.make, rec.camera.model].filter(Boolean).join(' ') : null;
    const ex = rec.exposure || {};
    const rows = [
      ['拍摄时间', formatDate(rec.date) + (rec.time ? ` ${rec.time}` : '')],
      ['日期来源', rec.dateSource ? dateSourceLabel(rec.dateSource) : (loading ? '加载中…' : '未知')],
      ['地点', rec.location || (rec.coords ? '（有坐标，未命名）' : '未识别')],
      rec.coords ? ['坐标', coordsText(rec.coords)] : null,
      ['相机', camera],
      ['镜头', rec.lens],
      ex.aperture ? ['光圈', ex.aperture] : null,
      ex.shutter ? ['快门', ex.shutter] : null,
      ex.iso ? ['ISO', String(ex.iso)] : null,
      ex.focal ? ['焦距', ex.focal] : null,
      ex.ev != null ? ['曝光补偿', `${ex.ev > 0 ? '+' : ''}${ex.ev} EV`] : null,
      ex.program ? ['曝光模式', ex.program] : null,
      ex.metering ? ['测光', ex.metering] : null,
      ex.whiteBalance ? ['白平衡', ex.whiteBalance] : null,
      rec.pixel ? ['像素', `${rec.pixel.width} × ${rec.pixel.height}`] : null,
      rec.bytes ? ['文件大小', humanBytes(rec.bytes)] : null,
      rec.software ? ['软件', rec.software] : null,
      rec.editedBy ? ['后期', rec.editedBy] : null,
      rec.rating ? ['星级', '★'.repeat(rec.rating)] : null,
      rec.label ? ['色标', rec.label] : null,
      rec.path ? ['归档路径', rec.path] : null,
    ].filter(Boolean);

    const tags = [...(rec.tags || []), ...(rec.keywords || []).filter((k) => !(rec.tags || []).includes(k))];

    info.innerHTML = `
      <h2>${escapeHtml(rec.caption || rec.location || '照片')}</h2>
      <div class="lb-sub">${escapeHtml([rec.date, rec.location].filter(Boolean).join(' · '))}
        ${loading ? '<span class="badge">读取参数…</span>' : ''}
        ${rec.dateSource && rec.dateSource !== 'exif' && rec.dateSource !== 'folder'
          ? `<span class="badge warn">日期来自${escapeHtml(dateSourceLabel(rec.dateSource))}</span>` : ''}
      </div>
      <div class="lb-actions">
        ${rec.src ? `<a class="btn" href="${downloadSrc(rec)}" download>下载原图</a>` : ''}
        ${rec.preview ? `<a class="btn" href="${imageSrc(rec, 'full')}" target="_blank" rel="noopener">新窗口打开</a>` : ''}
        ${rec.coords ? `<button class="btn" data-act="goto-map">在地图上查看</button>` : ''}
      </div>
      <div class="lb-section">
        <h4>拍摄参数</h4>
        <dl class="lb-kv">
          ${rows.map(([k, v]) => `<dt>${escapeHtml(k)}</dt><dd>${escapeHtml(v)}</dd>`).join('')}
        </dl>
        ${!camera && !ex.aperture ? `<p class="muted small" style="margin-top:8px">这张照片没有可读的 EXIF（可能是截图、被导出时去掉了元数据，或格式不被支持）。</p>` : ''}
      </div>
      ${tags.length ? `<div class="lb-section"><h4>标签 / 关键词</h4><div>${tags.map((t) => `<span class="badge">${escapeHtml(t)}</span>`).join(' ')}</div></div>` : ''}
      <div class="lb-section">
        <h4>快捷键</h4>
        <div class="muted small">← → 切换 · Esc 关闭 · I 显示/隐藏信息</div>
      </div>
    `;
  }

  function step(d) {
    const next = index + d;
    if (next < 0 || next >= seq.length) return;
    show(seq, next);
  }

  root.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-act]');
    if (btn) {
      const act = btn.dataset.act;
      if (act === 'close') close();
      if (act === 'prev') step(-1);
      if (act === 'next') step(1);
      if (act === 'goto-map') {
        const rec = seq[index];
        document.dispatchEvent(new CustomEvent('pj:goto-map', { detail: rec }));
      }
      return;
    }
    // 点击空白区域关闭
    if (e.target === root || e.target.classList.contains('lb-stage')) close();
  });

  window.addEventListener('keydown', (e) => {
    if (root.hidden) return;
    if (e.key === 'Escape') { close(); }
    else if (e.key === 'ArrowLeft') { step(-1); }
    else if (e.key === 'ArrowRight') { step(1); }
    else if (e.key === 'i' || e.key === 'I') {
      info.style.display = info.style.display === 'none' ? '' : 'none';
    }
  });

  return {
    show,
    close,
    isOpen: () => !root.hidden,
    syncHash() {
      if (root.hidden) {
        if (location.hash.startsWith('#p=')) history.replaceState(null, '', location.pathname + location.search);
      } else {
        const id = seq[index]?.i;
        if (id) history.replaceState(null, '', `#p=${id}`);
      }
    },
  };
}
