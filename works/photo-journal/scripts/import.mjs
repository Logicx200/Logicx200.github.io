#!/usr/bin/env node
/**
 * 摄影归档导入器
 *
 *   node scripts/import.mjs --src "D:\\照片归档" [选项]
 *
 * 它会：
 *   1. 递归扫描照片（默认不含视频）
 *   2. 读取 EXIF / XMP：拍摄日期、相机、镜头、光圈、快门、ISO、焦距、GPS、评级、关键词
 *   3. 解析"几月几日何处拍摄"式的不规则文件夹名 → 日期 / 地点 / 标签
 *   4. （可选）生成 WebP 缩略图与预览图、抽取主色调
 *   5. 输出静态站点需要的 JSON 索引：public/data/index.json 等
 *
 * 常用选项：
 *   --src <目录>        照片根目录（必填，或写在 photojournal.config.json）
 *   --out <目录>        站点根目录，默认仓库根
 *   --title <标题>      站点标题
 *   --copy              把原图复制进 public/media/originals（GitHub Pages 可直接显示原图）
 *   --no-previews       不生成 WebP 缩略图/预览图（只写索引）
 *   --force             重新生成已存在的缩略图
 *   --dry-run           只打印识别结果，不写任何文件
 *   --concurrency <n>   并发数，默认 4
 *   --limit <n>         只处理前 n 张（调试用）
 *   --include-video     也索引 mp4/mov（只取文件时间与文件夹解析）
 */

import fs from 'node:fs/promises';
import path from 'node:path';
import crypto from 'node:crypto';
import { parseArgs } from 'node:util';
import { fileURLToPath } from 'node:url';

import { isSupportedPhoto, extOf } from '../src/exif.js';
import { readExif } from '../src/exif-parse.js';
import { buildRecord, explainArchive, shortHash } from '../src/record.js';
import { makeMedia, loadSharp, sharpError, humanSize, dirSize, perceptualHash } from '../src/media-node.js';
import { findDuplicates } from '../src/dup.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, '..');

const VIDEO_EXT = new Set(['.mp4', '.mov', '.m4v', '.avi', '.mkv']);

/* ------------------------------------------------------------------ */
/* 参数                                                                */
/* ------------------------------------------------------------------ */

function parseCli() {
  const raw = process.argv.slice(2);
  const values = {
    src: undefined, out: undefined, title: undefined, subtitle: undefined,
    copy: false, previews: true, force: false, 'dry-run': false,
    'origin-base': undefined, concurrency: undefined, limit: undefined,
    'include-video': false, config: undefined, help: false, clean: false, duplicates: false,
  };
  const BOOL = new Set(['copy', 'previews', 'force', 'dry-run', 'include-video', 'help', 'clean', 'duplicates']);
  for (let i = 0; i < raw.length; i++) {
    let a = raw[i];
    if (a === '-h') { values.help = true; continue; }
    if (!a.startsWith('--')) continue;          // 位置参数暂不支持
    a = a.slice(2);
    // 支持 --no-xxx 取反
    const negated = a.startsWith('no-');
    if (negated) a = a.slice(3);
    const eq = a.indexOf('=');
    let key = eq >= 0 ? a.slice(0, eq) : a;
    let val = eq >= 0 ? a.slice(eq + 1) : undefined;

    if (key === 'include-video') { /* 保持原名 */ }
    if (!(key in values)) {
      console.error(`未知参数：--${negated ? 'no-' : ''}${key}（用 --help 查看用法）`);
      process.exitCode = 1;
      return { help: false, __bad: true };
    }
    if (BOOL.has(key)) {
      if (val !== undefined) values[key] = !/^(0|false|no)$/i.test(val);
      else values[key] = !negated;
    } else {
      if (val === undefined) val = raw[++i];
      values[key] = val;
    }
  }
  return values;
}

async function loadConfig(file) {
  const p = path.resolve(REPO_ROOT, file || 'photojournal.config.json');
  try {
    return JSON.parse(await fs.readFile(p, 'utf8'));
  } catch {
    return {};
  }
}

const HELP = `
摄影归档导入器

  node scripts/import.mjs --src "D:\\照片归档" [选项]

选项：
  --src <目录>        照片根目录
  --out <目录>        站点根目录（默认仓库根）
  --title <标题>      站点标题
  --subtitle <副标题> 站点副标题
  --copy              把原图复制到 public/media/originals/（适合 ≤ 2GB 的仓库）
  --origin-base <URL> 原图托管在别处时的前缀，例如 https://cdn.example.com/photos
                      索引里的 src 会拼成 <URL>/<相对路径>，灯箱即可"下载原图"
  --no-previews       跳过 WebP 缩略图生成
  --force             强制重建缩略图
  --dry-run           只预览识别结果
  --concurrency <n>   并发数（默认 4）
  --limit <n>         只处理前 n 张
  --include-video     同时索引视频
  --clean             先清空站点已导入的数据（public/data 与 public/media）再导入
  --duplicates        额外打印检测到的重复照片分组
  --config <文件>     配置文件，默认 photojournal.config.json
`;

/* ------------------------------------------------------------------ */
/* 扫描                                                                */
/* ------------------------------------------------------------------ */

const SKIP_DIRS = new Set([
  'node_modules', '.git', '.cache', '.npm-cache', 'dist', '$RECYCLE.BIN',
  'System Volume Information', 'Lightroom Catalog Previews.lrdata',
  '.LightroomCatalog', 'Previews.lrdata', '.thumbnails',
]);

const SKIP_FILE_RE = /(^\.|^Thumbs\.db$|^desktop\.ini$|\.xmp$|\.lrcat|\.lrdata|\.tmp$|\.bak$|\.dop$|\.pp3$)/i;

async function scan(dir, { includeVideo }) {
  const out = [];
  const stack = [dir];
  while (stack.length) {
    const cur = stack.pop();
    let entries;
    try {
      entries = await fs.readdir(cur, { withFileTypes: true });
    } catch (err) {
      console.warn(`  ! 无法读取目录：${cur}（${err.code || err.message}）`);
      continue;
    }
    for (const e of entries) {
      const full = path.join(cur, e.name);
      if (e.isDirectory()) {
        if (SKIP_DIRS.has(e.name) || e.name.startsWith('.')) continue;
        stack.push(full);
      } else if (e.isFile()) {
        if (SKIP_FILE_RE.test(e.name)) continue;
        const ext = extOf(e.name);
        if (isSupportedPhoto(e.name) || (includeVideo && VIDEO_EXT.has(ext))) out.push(full);
      }
    }
  }
  return out.sort((a, b) => a.localeCompare(b, 'zh-Hans-CN'));
}

/* ------------------------------------------------------------------ */
/* 并发控制                                                            */
/* ------------------------------------------------------------------ */

async function mapLimit(items, limit, fn) {
  const results = new Array(items.length);
  let cursor = 0;
  let done = 0;
  const total = items.length;
  const workers = Array.from({ length: Math.max(1, Math.min(limit, total)) }, async () => {
    while (true) {
      const i = cursor++;
      if (i >= total) return;
      try {
        results[i] = await fn(items[i], i);
      } catch (err) {
        results[i] = { __error: String(err && err.stack ? err.stack : err) };
      }
      done++;
      if (done % 25 === 0 || done === total) {
        process.stdout.write(`\r  处理中 ${done}/${total} …`);
      }
    }
  });
  await Promise.all(workers);
  process.stdout.write('\r' + ' '.repeat(40) + '\r');
  return results;
}

async function hashFile(file) {
  const h = crypto.createHash('sha1');
  const fh = await fs.open(file, 'r');
  try {
    const buf = Buffer.alloc(256 * 1024);
    let read;
    // 前 256KB + 文件大小即可保证日常去重足够
    read = (await fh.read(buf, 0, buf.length, 0)).bytesRead;
    h.update(buf.subarray(0, read));
    const st = await fh.stat();
    h.update(String(st.size));
  } finally {
    await fh.close();
  }
  return h.digest('hex').slice(0, 20);
}

/* ------------------------------------------------------------------ */
/* 主流程                                                              */
/* ------------------------------------------------------------------ */

async function main() {
  const cli = parseCli();
  if (cli.help) { console.log(HELP); return; }
  const config = await loadConfig(cli.config);

  const srcRoot = path.resolve(cli.src || config.source || '');
  if (!cli.src && !config.source) {
    console.error('缺少 --src（照片根目录）。用 --help 查看用法。');
    process.exitCode = 1;
    return;
  }
  let srcStat;
  try {
    srcStat = await fs.stat(srcRoot);
  } catch {
    console.error(`照片目录不存在：${srcRoot}`);
    process.exitCode = 1;
    return;
  }
  if (!srcStat.isDirectory()) {
    console.error(`--src 必须是目录：${srcRoot}`);
    process.exitCode = 1;
    return;
  }

  const outRoot = path.resolve(REPO_ROOT, cli.out || config.out || '.');
  const publicRoot = path.join(outRoot, 'public');
  const mediaRoot = path.join(publicRoot, 'media');
  const dataRoot = path.join(publicRoot, 'data');

  const prefs = {
    overrideDate: config.overrideDate || null,
    overrideLocation: config.overrideLocation || null,
    ignoreFolders: config.ignoreFolders || [],
  };

  // 手动纠正表：{"2023/精选 原片 归档": {"date": "2023-08-12", "location": "杭州"}}
  const overrides = config.overrides || {};
  const overrideMatchers = Object.entries(overrides).map(([pattern, patch]) => {
    const isRe = pattern.startsWith('/') && pattern.lastIndexOf('/') > 0;
    if (isRe) {
      const end = pattern.lastIndexOf('/');
      return { test: (p) => new RegExp(pattern.slice(1, end), pattern.slice(end + 1)).test(p), patch };
    }
    const norm = pattern.replace(/\\/g, '/');
    return { test: (p) => p.includes(norm), patch };
  });

  function patchFor(relPath) {
    for (const m of overrideMatchers) {
      if (m.test(relPath)) return m.patch;
    }
    return null;
  }

  const wantPreviews = cli.previews !== false && config.previews !== false;
  const wantCopy = Boolean(cli.copy || config.copy);
  const originBase = cli['origin-base'] || config.originBase || null;
  const concurrency = Number(cli.concurrency || config.concurrency || 4);
  const limit = cli.limit ? Number(cli.limit) : 0;
  const includeVideo = Boolean(cli['include-video'] || config.includeVideo);
  const dryRun = Boolean(cli['dry-run']);

  console.log('摄影归档导入');
  console.log(`  来源目录 : ${srcRoot}`);
  console.log(`  输出站点 : ${outRoot}`);
  console.log(`  缩略图   : ${wantPreviews ? '生成' : '跳过'}`);
  console.log(`  复制原图 : ${wantCopy ? '是' : '否'}`);
  console.log('');

  if (cli.clean) {
    // 不直接删除：先改名留一份，避免误删已经导入好的数据
    const stamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
    for (const dir of [dataRoot, mediaRoot]) {
      if (!(await fs.stat(dir).then(() => true, () => false))) continue;
      const bak = `${dir}-bak-${stamp}`;
      await fs.rename(dir, bak);
      console.log(`  已备份 ${path.relative(outRoot, dir)} → ${path.basename(bak)}`);
    }
    console.log('  （确认不需要后可以手动删掉这些 -bak- 目录）');
    console.log('');
  }

  let files = await scan(srcRoot, { includeVideo });
  // 忽略配置里指定的目录片段
  if (prefs.ignoreFolders.length) {
    files = files.filter((f) => !prefs.ignoreFolders.some((ig) => f.includes(ig)));
  }
  console.log(`  扫描到 ${files.length} 个文件`);
  if (limit) files = files.slice(0, limit);
  if (!files.length) {
    console.log('  没有可处理的照片，退出。');
    return;
  }

  if (dryRun) {
    console.log('\n解析预览（前 60 条）：');
    const rows = files.slice(0, 60).map((f) => explainArchive(path.relative(srcRoot, f), prefs));
    console.table(rows);
    return;
  }

  if (wantPreviews) {
    const sharp = await loadSharp();
    if (!sharp) {
      console.log(`  ! sharp 未安装或加载失败（${sharpError()?.message || 'unknown'}），本次跳过缩略图生成`);
      console.log('    站点仍可正常使用（直接加载原图），安装后可重新运行以生成缩略图。');
    }
  }

  await fs.mkdir(mediaRoot, { recursive: true });
  await fs.mkdir(dataRoot, { recursive: true });

  const sharpOk = wantPreviews && Boolean(await loadSharp());
  let copiedBytes = 0;
  let previewBytes = 0;
  let generatedThumbs = 0;
  const errors = [];

  const records = await mapLimit(files, concurrency, async (abs) => {
    const rel = path.relative(srcRoot, abs).replace(/\\/g, '/');
    const fileName = path.basename(abs);
    const st = await fs.stat(abs);
    const ext = extOf(fileName);
    const isVideo = VIDEO_EXT.has(ext);

    const exif = isVideo ? { empty: true } : await readExif(abs);

    let media = null;
    let dominantColor = null;
    let displaySize = null;
    let phash = null;

    if (wantCopy) {
      const hash = await hashFile(abs);
      const dir = path.join(mediaRoot, 'originals', hash.slice(0, 2));
      await fs.mkdir(dir, { recursive: true });
      const target = path.join(dir, hash + ext);
      try {
        const exists = await fs.access(target).then(() => true, () => false);
        if (!exists) {
          await fs.copyFile(abs, target);
          copiedBytes += st.size;
        }
      } catch (err) {
        errors.push(`${rel}: 复制失败 ${err.message}`);
      }
      media = { original: `media/originals/${hash.slice(0, 2)}/${hash}${ext}` };
    }

    if (sharpOk && !isVideo) {
      const hash = await hashFile(abs);
      const m = await makeMedia({
        srcPath: abs,
        mediaRoot,
        hash,
        thumbWidth: 400,
        previewWidth: 1600,
        force: Boolean(cli.force),
      });
      if (m.error) errors.push(`${rel}: 缩略图 ${m.error}`);
      dominantColor = m.color;
      displaySize = m.size;
      phash = await perceptualHash(abs);
      if (!wantCopy) {
        // 未复制原图时，src 指向原图在源目录的位置（站点本地预览可用）
        media = media || {};
      }
      media = { ...(media || {}), thumb: m.thumb, preview: m.preview };
      if (m.thumb || m.preview) generatedThumbs++;
    }

    const patch = patchFor(rel);
    const rec = buildRecord({
      relPath: rel,
      fileName,
      bytes: st.size,
      exif,
      prefs: {
        overrideDate: patch?.date || prefs.overrideDate,
        overrideLocation: patch?.location || prefs.overrideLocation,
      },
      media,
      dominantColor,
      displaySize,
      originBase,
      phash,
    });
    if (patch?.note) rec.note = patch.note;
    if (patch?.location) rec.locationConfidence = 1;
    if (patch?.tags?.length) rec.tags = [...new Set([...(rec.tags || []), ...patch.tags])];
    if (!wantCopy && !originBase) rec.src = null;   // 既没复制原图也没配外部前缀时不提供原图直链
    rec.video = isVideo || undefined;
    // 文件系统时间作为最后兜底
    if (!rec.date) {
      const d = new Date(st.mtime);
      rec.date = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
      rec.dateSource = 'mtime';
      rec.dateConfidence = 0.2;
    }
    return rec;
  });

  for (const r of records) {
    if (r && r.__error) errors.push(r.__error);
  }
  const photos = records.filter((r) => r && !r.__error);

  /* ---------------- 排序与索引 ---------------- */
  photos.sort((a, b) => {
    const da = a.date || '0000-00-00';
    const db = b.date || '0000-00-00';
    if (da !== db) return db.localeCompare(da);           // 新→旧
    return (b.time || '').localeCompare(a.time || '');
  });

  const byMonth = new Map();
  for (const p of photos) {
    const key = /^\d{4}-\d{2}/.test(p.date || '') ? p.date.slice(0, 7) : 'unknown';
    if (!byMonth.has(key)) byMonth.set(key, []);
    byMonth.get(key).push(p);
  }

  const years = {};
  for (const [key, list] of byMonth) {
    if (key === 'unknown') continue;
    const y = key.slice(0, 4);
    years[y] = (years[y] || 0) + list.length;
  }

  // 地点聚合
  const locMap = new Map();
  for (const p of photos) {
    const name = p.location || '未识别地点';
    const lat = p.coords?.lat;
    const lng = p.coords?.lng;
    const key = lat != null && lng != null ? `${name}|${lat.toFixed(3)},${lng.toFixed(3)}` : name;
    if (!locMap.has(key)) {
      locMap.set(key, { name, lat: lat ?? null, lng: lng ?? null, count: 0, first: p.date, last: p.date, cover: p.thumb || p.preview || p.src });
    }
    const e = locMap.get(key);
    e.count++;
    if (p.date && (!e.first || p.date < e.first)) e.first = p.date;
    if (p.date && (!e.last || p.date > e.last)) e.last = p.date;
  }
  const locations = [...locMap.values()].sort((a, b) => b.count - a.count);

  // 相机 / 镜头 / 后期软件 / 标签聚合
  const tally = (fn) => {
    const m = new Map();
    for (const p of photos) {
      const v = fn(p);
      if (!v) continue;
      m.set(v, (m.get(v) || 0) + 1);
    }
    return [...m.entries()].sort((a, b) => b[1] - a[1]).map(([name, count]) => ({ name, count }));
  };

  const cameras = tally((p) => (p.camera ? [p.camera.make, p.camera.model].filter(Boolean).join(' ') : null));
  const lenses = tally((p) => p.lens);
  const editors = tally((p) => p.editedBy);
  const tagList = (() => {
    const m = new Map();
    for (const p of photos) for (const t of p.tags || []) m.set(t, (m.get(t) || 0) + 1);
    return [...m.entries()].sort((a, b) => b[1] - a[1]).map(([name, count]) => ({ name, count }));
  })();

  const dates = photos.map((p) => p.date).filter((d) => /^\d{4}/.test(d || '')).sort();
  const stats = {
    photos: photos.length,
    withGps: photos.filter((p) => p.coords).length,
    withExifDate: photos.filter((p) => p.dateSource === 'exif').length,
    fromFolderName: photos.filter((p) => p.dateSource === 'folder' || p.dateSource === 'folder-partial').length,
    fromMtime: photos.filter((p) => p.dateSource === 'mtime').length,
    withLocation: photos.filter((p) => p.location).length,
    lowConfidence: photos.filter((p) => (p.dateConfidence ?? 0) < 0.6 || !p.location).length,
    firstDate: dates[0] || null,
    lastDate: dates[dates.length - 1] || null,
    bytes: photos.reduce((s, p) => s + (p.bytes || 0), 0),
  };

  const index = {
    generatedAt: new Date().toISOString(),
    title: cli.title || config.title || '我的摄影记录',
    subtitle: cli.subtitle || config.subtitle || '',
    author: config.author || '',
    source: config.sourceLabel || path.basename(srcRoot),
    stats,
    years,
    months: [...byMonth.entries()]
      .map(([key, list]) => ({ key, count: list.length, cover: list[0].thumb || list[0].preview || list[0].src }))
      .sort((a, b) => b.key.localeCompare(a.key)),
    locations,
    cameras,
    lenses,
    editors,
    tags: tagList,
  };

  /* ---------------- 写文件 ---------------- */
  const pretty = (o) => JSON.stringify(o, null, 1);
  await fs.writeFile(path.join(dataRoot, 'index.json'), pretty(index), 'utf8');

  for (const [key, list] of byMonth) {
    await fs.writeFile(
      path.join(dataRoot, key === 'unknown' ? 'photos-unknown.json' : `photos-${key}.json`),
      pretty({ month: key, count: list.length, photos: list }),
      'utf8',
    );
  }

  // 搜索 / 地图用的精简索引（全量，体积小）
  const search = photos.map((p) => ({
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
    // 注意：这里存的是「日期来源」，字段名用 ds 而不是 src —— src 在图片地址解析里
    // 表示"原图路径"，两者同名会导致把 dateSource 当成图片路径去请求（会 404）
    ds: p.dateSource || undefined,
    ph: p.phash || undefined,          // 感知指纹：站点的「重复照片」页用它分组
    b: p.bytes || undefined,           // 文件体积：重复页用它算"能省多少空间"
    px: p.pixel ? [p.pixel.width, p.pixel.height] : undefined,
  }));

  // 重复检测：命令行也给出一份统计（网页端有专门的「重复照片」页）
  const dup = findDuplicates(photos, { threshold: 5 });
  index.duplicates = dup.stats;
  await fs.writeFile(path.join(dataRoot, 'search.json'), JSON.stringify(search), 'utf8');

  // 顺手把重复组单独存一份，方便外部脚本使用
  if (dup.groups.length) {
    await fs.writeFile(
      path.join(dataRoot, 'duplicates.json'),
      pretty({
        threshold: 5,
        stats: dup.stats,
        groups: dup.groups.map((g) => ({
          id: g.id, kind: g.kind, distance: g.distance, count: g.count,
          keeper: { id: g.keeper.id, path: g.keeper.path, bytes: g.keeper.bytes },
          photos: g.photos.map((p) => ({ id: p.id, path: p.path, date: p.date, bytes: p.bytes, phash: p.phash })),
          wastedBytes: g.wastedBytes,
        })),
      }),
      'utf8',
    );
  }

  /* ---------------- 汇报 ---------------- */
  const mediaStat = await dirSize(mediaRoot);
  console.log('导入完成');
  console.log(`  照片数量      : ${stats.photos}`);
  console.log(`  日期来自 EXIF : ${stats.withExifDate}｜来自文件夹名：${stats.fromFolderName}｜来自文件时间：${stats.fromMtime}`);
  console.log(`  GPS 坐标      : ${stats.withGps}`);
  console.log(`  识别到地点    : ${stats.withLocation}`);
  console.log(`  识别区间      : ${stats.firstDate || '-'} → ${stats.lastDate || '-'}`);
  console.log(`  低置信度待确认: ${stats.lowConfidence}`);
  console.log(`  生成缩略图    : ${generatedThumbs}`);
  console.log(`  重复照片      : ${dup.stats.groups} 组，涉及 ${dup.stats.photosInGroups} 张，冗余 ${dup.stats.redundant} 张（约 ${humanSize(dup.stats.wastedBytes)}）`);  console.log(`  media 目录体积: ${humanSize(mediaStat.bytes)}（${mediaStat.count} 个文件）`);
  if (wantCopy) console.log(`  本次复制原图  : ${humanSize(copiedBytes)}`);
  if (errors.length) {
    console.log(`  警告 ${errors.length} 条：`);
    for (const e of errors.slice(0, 10)) console.log(`    - ${e}`);
    if (errors.length > 10) console.log(`    …还有 ${errors.length - 10} 条`);
  }
  if (cli.duplicates && dup.groups.length) {
    console.log('');
    console.log('重复照片分组（最多列出 20 组）：');
    for (const g of dup.groups.slice(0, 20)) {
      console.log(`  [${g.kind === 'exact' ? '完全相同' : `相似度距离 ${g.distance}`}] ${g.count} 张，建议保留：${g.keeper.path}`);
      for (const p of g.photos) {
        console.log(`      ${p.id === g.keeper.id ? '★' : ' '} ${p.path}  ${humanSize(p.bytes || 0)}`);
      }
    }
    if (dup.groups.length > 20) console.log(`  …还有 ${dup.groups.length - 20} 组，见 public/data/duplicates.json`);
  }
  console.log('');
  console.log('下一步：npm run serve  然后在浏览器打开提示的地址');
}

main().catch((err) => {
  console.error('导入失败：', err);
  process.exitCode = 1;
});
