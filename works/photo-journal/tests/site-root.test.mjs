/**
 * 站点目录校验的单元测试
 *
 * 这组测试针对一个真实踩过的坑：
 * 用户在网页导入时选了自己的照片文件夹，代码却在里面新建了 public 子目录，
 * 把索引和缩略图写了进去 —— 站点自然读不到，"导入后什么都没有"。
 * 现在的规则是：认不出是本站目录就直接报错，绝不擅自新建/改写去向。
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { inspectSiteRoot, findSiteRoots, describeSitePick } from '../src/site-root.js';

/* ---- 用真实目录做一个 FileSystemDirectoryHandle 的桩 ---- */

function fakeDir(absPath) {
  const name = path.basename(absPath);
  return {
    kind: 'directory',
    name,
    async getFileHandle(fileName, opts = {}) {
      const p = path.join(absPath, fileName);
      if (!fs.existsSync(p)) {
        if (!opts.create) {
          const err = new Error('not found');
          err.name = 'NotFoundError';
          throw err;
        }
        fs.writeFileSync(p, '');
      }
      return { kind: 'file', name: fileName, text: fs.readFileSync(p, 'utf8') };
    },
    async getDirectoryHandle(dirName, opts = {}) {
      const p = path.join(absPath, dirName);
      if (!fs.existsSync(p)) {
        if (!opts.create) {
          const err = new Error('not found');
          err.name = 'NotFoundError';
          throw err;
        }
        fs.mkdirSync(p, { recursive: true });
      }
      return fakeDir(p);
    },
    async *entries() {
      for (const e of fs.readdirSync(absPath, { withFileTypes: true })) {
        const p = path.join(absPath, e.name);
        yield [e.name, e.isDirectory() ? fakeDir(p) : { kind: 'file', name: e.name }];
      }
    },
  };
}

function tmpDir(label) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), `pj-site-${label}-`));
  return dir;
}

const SITE_HTML = `<!DOCTYPE html><html lang="zh-CN" data-pj-site="photo-journal"><body>
<section id="view-import" hidden></section><section id="view-grid"></section></body></html>`;

test('能识别带标记文件的站点目录', async () => {
  const root = tmpDir('marker');
  fs.writeFileSync(path.join(root, 'site-id.txt'), 'photo-journal site root\n');
  const r = await inspectSiteRoot(fakeDir(root));
  assert.equal(r.ok, true);
  assert.equal(r.via, 'marker');
});

test('没有标记文件时用 index.html 判断', async () => {
  const root = tmpDir('html');
  fs.writeFileSync(path.join(root, 'index.html'), SITE_HTML);
  const r = await inspectSiteRoot(fakeDir(root));
  assert.equal(r.ok, true);
  assert.equal(r.via, 'index.html');
});

test('照片文件夹（没有 index.html）必须被拒绝', async () => {
  const root = tmpDir('photos');
  fs.writeFileSync(path.join(root, 'DSC01234.JPG'), 'x');
  fs.mkdirSync(path.join(root, '2024年'));
  const r = await inspectSiteRoot(fakeDir(root));
  assert.equal(r.ok, false);
  assert.match(r.reason, /没有 index\.html/);
});

test('别的网站的 index.html 也要被拒绝', async () => {
  const root = tmpDir('other');
  fs.writeFileSync(path.join(root, 'index.html'), '<html><body>hello</body></html>');
  const r = await inspectSiteRoot(fakeDir(root));
  assert.equal(r.ok, false);
  assert.match(r.reason, /不是本站页面/);
});

test('选到项目根目录时能在里面找到 public', async () => {
  const root = tmpDir('proj');
  const pub = path.join(root, 'public');
  fs.mkdirSync(pub, { recursive: true });
  fs.writeFileSync(path.join(pub, 'index.html'), SITE_HTML);
  fs.writeFileSync(path.join(pub, 'site-id.txt'), 'photo-journal site root');

  const found = await findSiteRoots(fakeDir(root));
  assert.equal(found.length, 1);
  assert.equal(found[0].label, 'public');
  assert.equal(found[0].handle.name, 'public');
});

test('照片文件夹里找不到任何站点目录（不会误判）', async () => {
  const root = tmpDir('nodata');
  fs.mkdirSync(path.join(root, '2024年', '十月'), { recursive: true });
  fs.writeFileSync(path.join(root, 'a.jpg'), 'x');
  const found = await findSiteRoots(fakeDir(root));
  assert.equal(found.length, 0);
});

test('报错信息包含"选的是哪个目录"和"该选哪个"', () => {
  const msg = describeSitePick('照片归档', '目录里没有 index.html，看起来不是站点根目录');
  assert.match(msg, /照片归档/);
  assert.match(msg, /public/);
  assert.match(msg, /不会擅自新建目录/);
});
