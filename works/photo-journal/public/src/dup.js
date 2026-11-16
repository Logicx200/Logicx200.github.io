/**
 * 重复照片检测
 *
 * 两种重复：
 *   1. **完全重复**：文件内容一样（同一张照片导了两遍）→ 内容 id 相同
 *   2. **视觉重复**：同一张照片的不同版本 —— 导出多次、改过尺寸、Lightroom 修图前后、
 *      连拍里几乎一样的两张 → 用感知哈希（dHash）比较
 *
 * 感知哈希怎么算：把图缩到 9×8 的灰度图，逐行比较相邻像素的明暗，得到 64 位指纹。
 * 两张图指纹的"汉明距离"越小越像（0 = 一模一样，≤6 基本可认定是重复）。
 * 好处是缩放、轻微压缩、亮度微调都不会改变指纹。
 *
 * 本文件是纯函数 + 位运算，Node 与浏览器通用，有单元测试（tests/dup.test.mjs）。
 */

/** 汉明距离（两个 64 位指纹不同位的个数，0~64） */
export function hamming(hashA, hashB) {
  let x = BigInt('0x' + String(hashA || '0')) ^ BigInt('0x' + String(hashB || '0'));
  let n = 0;
  while (x) {
    x &= x - 1n;
    n++;
  }
  return n;
}

/* ------------------------------------------------------------------ */
/* 颜色分布指纹：消除"结构相似但内容不同"的误报                            */
/* ------------------------------------------------------------------ */

/**
 * 颜色特征：16 个十六进制字符
 *
 * 前 12 个：色度（去亮度）的 2×2×2 联合分布 —— 亮度变化不影响它，
 *           用来挡掉"结构相似但颜色完全不同"的误报；
 * 后 4 个：整体亮度档位 —— 只做参考，不参与判定。
 *
 * 为什么不用绝对 RGB：实测发现同一张照片只要调亮 6%，粗糙的 RGB 分箱就会跨档，
 * 导致颜色距离飙到阈值附近，真重复反而漏检。去掉亮度后这个问题消失。
 */
export function histogramFromPixels(data, channels = 3, sampleStep = 1, width = 0) {
  const joint = new Float64Array(8);      // 2×2×2
  let total = 0;
  let lumSum = 0;
  const step = channels * sampleStep;

  // 逐像素算色度需要知道每个像素的位置；调用方给了 width 时只取偶数行偶数列，
  // 这样色度是"隔点取样"，等价于在高斯模糊后再降采样，对压缩噪声更稳
  for (let i = 0; i + 2 < data.length; i += step) {
    if (width) {
      const pixelIndex = i / channels;
      const x = pixelIndex % width;
      const y = (pixelIndex / width) | 0;
      if ((x & 1) || (y & 1)) continue;
    }
    const r = data[i];
    const g = data[i + 1];
    const b = data[i + 2];
    const sum = r + g + b;
    if (sum < 12) continue;                // 近乎全黑的像素色度没有意义
    const lum = 0.299 * r + 0.587 * g + 0.114 * b;
    lumSum += lum;
    const nr = Math.min(1, Math.round(r / sum * 2));
    const ng = Math.min(1, Math.round(g / sum * 2));
    const nb = Math.min(1, Math.round(b / sum * 2));
    joint[(nr << 2) | (ng << 1) | nb]++;
    total++;
  }

  if (!total) return '0'.repeat(16);

  let out = '';
  for (let i = 0; i < 8; i++) {
    const ratio = joint[i] / total;
    const v = Math.min(15, Math.round(ratio * 15 * 2));
    out += v.toString(16);
  }
  const lumBin = Math.min(15, Math.round((lumSum / total) / 255 * 16));
  out += lumBin.toString(16);
  out += '000';                            // 预留
  return out.padEnd(16, '0').slice(0, 16);
}

/** 颜色距离（0~24）：比较前 12 个色度档位（后 4 个亮度档不参与） */
export function histogramDistance(histA, histB) {
  const a = String(histA || '');
  const b = String(histB || '');
  if (a.length < 8 || b.length < 8) return 24;
  let d = 0;
  for (let i = 0; i < 8; i++) {
    d += Math.abs((parseInt(a[i], 16) || 0) - (parseInt(b[i], 16) || 0));
  }
  // 8 个档位、每档最大 15 → 最大 120，映射到 0~24 保持原有阈值语义
  return Math.min(24, d / 5);
}

/* ------------------------------------------------------------------ */
/* 签名（结构 + 颜色）：存成一个字符串，省索引体积                         */
/* ------------------------------------------------------------------ */

/** 把 dHash 与颜色特征合成一个签名：前 16 位是 dHash，后面是颜色特征 */
export function makeSignature(dhashHex, histHex) {
  if (!dhashHex) return null;
  return `${String(dhashHex).padStart(16, '0')}${String(histHex || '').padEnd(16, '0').slice(0, 16)}`;
}

/** 拆开签名 */
export function parseSignature(sig) {
  const s = String(sig || '');
  if (s.length < 17) return { dhash: s || null, hist: null };
  return { dhash: s.slice(0, 16), hist: s.slice(16) };
}

/** 综合相似度（0~1，1 = 完全一致） */
export function signatureSimilarity(sigA, sigB) {
  const a = parseSignature(sigA);
  const b = parseSignature(sigB);
  const structural = 1 - hamming(a.dhash, b.dhash) / 64;
  const color = a.hist && b.hist ? 1 - histogramDistance(a.hist, b.hist) / 24 : structural;
  return Math.min(structural, color);
}

/** 64 位指纹之间的相似度（1 = 完全相同） */
export function similarity(hashA, hashB) {
  return 1 - hamming(hashA, hashB) / 64;
}

/** 分组用的并查集 */
function makeUnionFind(n) {
  const parent = Array.from({ length: n }, (_, i) => i);
  const find = (x) => {
    while (parent[x] !== x) {
      parent[x] = parent[parent[x]];
      x = parent[x];
    }
    return x;
  };
  const union = (a, b) => {
    const ra = find(a);
    const rb = find(b);
    if (ra !== rb) parent[rb] = ra;
  };
  return { find, union };
}

/** 挑出这一组里"最值得留"的那张 */
export function pickKeeper(items, { preferRating = true } = {}) {
  const score = (p) => {
    const px = p.pixel ? p.pixel.width * p.pixel.height : 0;
    const bytes = p.bytes || 0;
    // 像素数量级差异最大，其次星级，其次文件体积
    return px
      + (preferRating ? (p.rating || 0) * 120000 : 0)
      + Math.min(bytes, 40 * 1024 * 1024) / 1024;
  };
  return items.slice().sort((a, b) => score(b) - score(a))[0];
}

/**
 * 取出记录里的指纹。
 * 完整记录（photos-*.json）里字段名是 phash；
 * 精简索引（search.json）里是 ph。两种都要能认。
 */
export function signatureOf(p) {
  return p?.phash || p?.ph || null;
}

/**
 * 找出重复照片
 *
 * 判定条件（两个都满足才算重复）：
 *   1. 结构指纹（dHash）的汉明距离 ≤ threshold
 *   2. 颜色分布的 L1 距离 ≤ maxColorDistance —— 用来挡掉"结构撞车"的误报
 *
 * @param {Array} photos 记录数组（完整记录或 search.json 精简条目都行）
 * @param {object} [opts]
 * @param {number} [opts.threshold=5] 结构指纹距离阈值，越小越严格
 * @param {number} [opts.maxColorDistance=7] 颜色分布距离阈值（0~24）
 * @returns {{groups:Array, stats:object}}
 */
export function findDuplicates(photos, { threshold = 5, maxColorDistance = 7 } = {}) {
  const list = (photos || []).filter(Boolean);
  const n = list.length;
  const { find, union } = makeUnionFind(n);

  const sig = list.map((p) => parseSignature(signatureOf(p)));
  const colorOk = (a, b) => {
    if (!a.hist || !b.hist) return true;   // 老数据没有颜色信息时不因此拒绝
    return histogramDistance(a.hist, b.hist) <= maxColorDistance;
  };

  /* 视觉重复：两两比较指纹（先比结构，再验颜色） */
  const pairDistance = new Map();  // "i-j" → 结构距离
  let compared = 0;
  let colorRejected = 0;
  for (let i = 0; i < n; i++) {
    if (!sig[i].dhash) continue;
    for (let j = i + 1; j < n; j++) {
      if (!sig[j].dhash) continue;
      compared++;
      const d = hamming(sig[i].dhash, sig[j].dhash);
      if (d > threshold) continue;
      if (!colorOk(sig[i], sig[j])) {
        // 结构像但颜色分布差得多 → 判断为不同照片
        colorRejected++;
        continue;
      }
      pairDistance.set(`${i}-${j}`, d);
      union(i, j);
    }
  }

  /* 3) 收集分组 */
  const buckets = new Map();
  for (let i = 0; i < n; i++) {
    const root = find(i);
    if (!buckets.has(root)) buckets.set(root, []);
    buckets.get(root).push(i);
  }

  const groups = [];
  for (const indices of buckets.values()) {
    if (indices.length < 2) continue;

    // 组内最大距离：用来判断这组是"完全一样"还是"只是相似"
    let maxD = 0;
    let minD = 64;
    for (let x = 0; x < indices.length; x++) {
      for (let y = x + 1; y < indices.length; y++) {
        const a = indices[x];
        const b = indices[y];
        const d = pairDistance.get(`${Math.min(a, b)}-${Math.max(a, b)}`);
        const dist = d === undefined ? hamming(sig[a].dhash, sig[b].dhash) : d;
        if (dist > maxD) maxD = dist;
        if (dist < minD) minD = dist;
      }
    }

    const items = indices.map((i) => list[i]);
    const keeper = pickKeeper(items);
    const totalBytes = items.reduce((s, p) => s + (p.bytes || 0), 0);
    const wastedBytes = items.reduce((s, p) => s + (p.bytes || 0), 0) - (keeper.bytes || 0);

    groups.push({
      id: `dup-${keeper.id}`,
      kind: minD === 0 && maxD === 0 ? 'exact' : 'visual',
      // 置信度分级：完全一样 > 高度相似（重导出/缩放/调亮/连拍）> 可能重复（需要人工判断）
      confidence: (minD === 0 && maxD === 0) ? 'exact' : maxD <= 3 ? 'high' : 'low',
      distance: maxD,
      colorDistance: Math.max(
        ...indices.flatMap((a) => indices.map((b) => histogramDistance(sig[a].hist, sig[b].hist))),
      ),
      count: items.length,
      keeper,
      photos: items.slice().sort((a, b) => (a.date || '').localeCompare(b.date || '')),
      totalBytes,
      wastedBytes,
    });
  }

  // 重复最多的、浪费空间最大的排在前面
  groups.sort((a, b) => b.wastedBytes - a.wastedBytes || b.count - a.count);

  const stats = {
    photos: n,
    compared,
    colorRejected,
    groups: groups.length,
    photosInGroups: groups.reduce((s, g) => s + g.count, 0),
    redundant: groups.reduce((s, g) => s + g.count - 1, 0),
    wastedBytes: groups.reduce((s, g) => s + g.wastedBytes, 0),
    threshold,
    maxColorDistance,
  };

  return { groups, stats };
}

/** 把一组按"建议保留"排序（保留项在最前） */
export function sortGroupByKeeper(group) {
  const keeper = group.keeper || pickKeeper(group.photos);
  const rest = (group.photos || []).filter((p) => p.id !== keeper.id);
  return [keeper, ...rest];
}

/** 精简索引条目（search.json）里的字段名与完整记录不同，这里统一一下常用字段 */
export function asFullRecord(p) {
  if (!p) return null;
  if (p.id) return p;
  return {
    id: p.i,
    path: p.path || p.th || '',
    date: p.d || null,
    bytes: p.bytes || 0,
    pixel: p.pixel || null,
    rating: p.r ?? 0,
    camera: p.c ? { make: null, model: p.c } : null,
    lens: p.e || null,
    location: p.l || null,
    phash: p.ph || null,
    thumb: p.th || null,
    dateSource: p.ds || null,
  };
}
