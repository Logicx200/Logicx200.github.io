/**
 * 索引合并的纯函数（Node 与浏览器通用，可单元测试）
 *
 * 网页导入和命令行导入共用同一套合并规则：
 *   - 站点上已有的照片必须保留（否则"导入一次就只剩这一批"）
 *   - 同一张照片（id 相同）重新导入时是"更新"，不是重复
 */

/**
 * 把新导入的记录合并进已有记录（按 id 去重，新数据优先）
 * @param {Array} newRecords 本次导入的完整记录
 * @param {Array} existingRecords 站点上已有的完整记录
 * @returns {{photos:Array, added:number, replaced:number, kept:number, total:number}}
 */
export function mergeRecords(newRecords, existingRecords) {
  const byId = new Map();
  for (const p of existingRecords || []) byId.set(p.id, p);

  let added = 0;
  let replaced = 0;
  for (const p of newRecords) {
    if (byId.has(p.id)) replaced++;
    else added++;
    byId.set(p.id, p);
  }

  const photos = [...byId.values()];
  return {
    photos,
    added,
    replaced,
    kept: photos.length - (newRecords ? newRecords.length : 0),
    total: photos.length,
  };
}

/** 完整记录 → 精简索引条目（字段与 scripts/import.mjs 保持一致） */
export function compactRecord(p) {
  return {
    i: p.id,
    d: p.date,
    t: p.time || undefined,
    l: p.location || undefined,
    g: p.coords ? [Number(p.coords.lat.toFixed(5)), Number(p.coords.lng.toFixed(5))] : undefined,
    c: p.camera ? [p.camera.make, p.camera.model].filter(Boolean).join(' ') : undefined,
    e: p.lens || undefined,
    s: p.exposure?.shutter || undefined,
    a: p.exposure?.aperture || undefined,
    o: p.exposure?.iso || undefined,
    f: p.exposure?.focal || undefined,
    k: p.tags?.length ? p.tags : undefined,
    x: p.caption || undefined,
    th: p.thumb || p.preview || undefined,
    r: p.rating ?? undefined,
    cl: p.color || undefined,
    aspect: p.pixel ? Number((p.pixel.width / p.pixel.height).toFixed(3)) : undefined,
    ds: p.dateSource || undefined,   // 日期来源；不要叫 src，避免和"原图路径"混淆
    ph: p.phash || undefined,
    b: p.bytes || undefined,
    px: p.pixel ? [p.pixel.width, p.pixel.height] : undefined,
  };
}
