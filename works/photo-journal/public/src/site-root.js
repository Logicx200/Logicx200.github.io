/**
 * 站点目录校验（Node 与浏览器通用）
 *
 * 背景：网页导入需要用户授权一个目录，把 data/ 与 media/ 写进去。
 * 如果用户选错了目录（比如选了自己的照片文件夹），
 * **绝不能在别人目录里乱建文件夹**，必须明确报错并告诉他该选哪个。
 *
 * 这里只依赖最小接口（getFileHandle / getDirectoryHandle / entries 可省略），
 * 因此 Node 里可以用桩对象跑单元测试，见 tests/site-root.test.mjs。
 */

export const SITE_MARKER_FILE = 'site-id.txt';
export const SITE_MARKER_TEXT = 'photo-journal site root';

/**
 * 判断一个目录句柄是不是本站的站点根目录（本项目的 public/）
 * @param {object} dir FileSystemDirectoryHandle 或同形桩对象
 * @returns {Promise<{ok:boolean, reason?:string, via?:string}>}
 */
export async function inspectSiteRoot(dir) {
  if (!dir || typeof dir.getFileHandle !== 'function') {
    return { ok: false, reason: '无法读取该目录' };
  }

  // 1) 标记文件最可靠
  try {
    const fh = await dir.getFileHandle(SITE_MARKER_FILE);
    const text = typeof fh.text === 'string' ? fh.text : await (await fh.getFile()).text();
    if (String(text).includes(SITE_MARKER_TEXT)) return { ok: true, via: 'marker' };
  } catch { /* 没有标记文件，继续 */ }

  // 2) index.html 里有没有本站独有的标记
  try {
    const fh = await dir.getFileHandle('index.html');
    const text = typeof fh.text === 'string' ? fh.text : await (await fh.getFile()).text();
    const s = String(text);
    if (s.includes('data-pj-site') && s.includes('id="view-import"')) {
      return { ok: true, via: 'index.html' };
    }
    return { ok: false, reason: '目录里的 index.html 不是本站页面' };
  } catch {
    return { ok: false, reason: '目录里没有 index.html，看起来不是站点根目录' };
  }
}

/** 给出人类可读的目录说明 */
export function describeSitePick(name, reason) {
  return `你选择的是「${name}」，${reason}。\n`
    + '请选择本项目里的 public 目录（里面有 index.html 的那个）。\n'
    + '为避免写错位置，导入器不会擅自新建目录或改写去向。';
}

/**
 * 在选错的目录里找一找有没有真正的站点目录（例如用户选了项目根目录）
 * @returns {Promise<Array<{handle:object, label:string}>>}
 */
export async function findSiteRoots(dir, maxDepth = 2) {
  const out = [];
  if (!dir || typeof dir.entries !== 'function' || maxDepth < 0) return out;
  try {
    for await (const [name, handle] of dir.entries()) {
      if (!handle || handle.kind !== 'directory') continue;
      if (name === 'public') {
        const check = await inspectSiteRoot(handle);
        if (check.ok) out.push({ handle, label: 'public' });
      }
      if (maxDepth > 0) {
        const deeper = await findSiteRoots(handle, maxDepth - 1);
        for (const d of deeper) out.push({ handle: d.handle, label: `${name}/${d.label}` });
      }
    }
  } catch { /* 权限不足等，忽略 */ }
  return out;
}
