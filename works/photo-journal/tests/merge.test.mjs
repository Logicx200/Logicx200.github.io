/**
 * 导入合并逻辑单元测试
 *
 * 覆盖"导入后站点标签没更新"的两个根因：
 *   1. 再次导入时不能把站点上已有的照片冲掉（必须按 id 合并）
 *   2. 同一张照片重复导入时应该被"更新"而不是重复出现
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mergeRecords, compactRecord } from '../src/merge.js';

const make = (id, extra = {}) => ({
  id,
  path: `${id}.JPG`,
  date: '2024-01-01',
  dateSource: 'folder',
  location: '杭州',
  thumb: `media/thumbs/${id}.webp`,
  pixel: { width: 3000, height: 2000 },
  exposure: { aperture: 'f/2.8', shutter: '1/250', iso: 100, focal: '35mm' },
  camera: { make: 'SONY', model: 'A7M4' },
  tags: ['夜景'],
  ...extra,
});

test('合并：新照片追加，已有照片保留', () => {
  const existing = [make('a'), make('b')];
  const incoming = [make('c')];
  const r = mergeRecords(incoming, existing);
  assert.equal(r.total, 3);
  assert.equal(r.added, 1);
  assert.equal(r.replaced, 0);
  assert.equal(r.kept, 2);
});

test('合并：同 id 视为更新而不是重复', () => {
  const existing = [make('a'), make('b')];
  const incoming = [make('a', { location: '西湖' })];
  const r = mergeRecords(incoming, existing);
  assert.equal(r.total, 2);
  assert.equal(r.added, 0);
  assert.equal(r.replaced, 1);
  const a = r.photos.find((p) => p.id === 'a');
  assert.equal(a.location, '西湖');
});

test('合并：站点为空时等价于首次导入', () => {
  const r = mergeRecords([make('a'), make('b')], []);
  assert.equal(r.total, 2);
  assert.equal(r.added, 2);
  assert.equal(r.kept, 0);
});

test('合并：已有记录为空数组/undefined 都不崩', () => {
  assert.equal(mergeRecords([make('a')], undefined).total, 1);
  assert.equal(mergeRecords([], [make('a')]).total, 1);
  assert.equal(mergeRecords([], []).total, 0);
});

test('合并：两次导入不同文件夹不会互相冲掉', () => {
  const first = [make('a'), make('b')];
  const second = [make('c'), make('d')];
  const round1 = mergeRecords(first, []);
  const round2 = mergeRecords(second, round1.photos);
  assert.equal(round2.total, 4);
  assert.deepEqual(round2.photos.map((p) => p.id).sort(), ['a', 'b', 'c', 'd']);
});

test('精简索引：字段与命令行脚本一致', () => {
  const c = compactRecord(make('a'));
  for (const k of ['i', 'd', 'l', 'a', 's', 'o', 'f', 'th', 'aspect', 'ds']) {
    assert.ok(k in c, `缺少字段 ${k}`);
  }
  assert.equal(c.i, 'a');
  assert.equal(c.d, '2024-01-01');
  assert.equal(c.aspect, 1.5);
  assert.equal(c.th, 'media/thumbs/a.webp');
});

test('精简索引：不把"日期来源"塞进 src（那会被误当图片路径）', () => {
  const c = compactRecord(make('a', { dateSource: 'folder' }));
  assert.equal(c.ds, 'folder', '日期来源应放在 ds');
  assert.ok(!('src' in c), 'src 不能出现，否则图片地址解析会去请求 /folder');
});
