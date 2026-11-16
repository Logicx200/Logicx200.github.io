import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  extractDate,
  extractLocation,
  extractTags,
  extractYears,
  parseArchivePath,
  parsePathString,
  cleanFallbackName,
} from '../src/parse.js';

/* ------------------------------------------------------------------ */
/* 日期：完整年月日                                                     */
/* ------------------------------------------------------------------ */

test('完整年月日：中文', () => {
  const r = extractDate('2024年10月3日 杭州西湖');
  assert.equal(r.date, '2024-10-03');
  assert.equal(r.yearInferred, false);
  assert.ok(r.confidence > 0.9);
});

test('完整年月日：无“日”字、带空格', () => {
  assert.equal(extractDate('2024 年 1 月 5 号 家里').date, '2024-01-05');
});

test('完整年月日：横杠 / 点 / 下划线 / 斜杠', () => {
  assert.equal(extractDate('2024-10-03-杭州-西湖').date, '2024-10-03');
  assert.equal(extractDate('2024.1.5').date, '2024-01-05');
  assert.equal(extractDate('2024_12_31 跨年').date, '2024-12-31');
  assert.equal(extractDate('2024/7/8').date, '2024-07-08');
});

test('完整年月日：8 位纯数字', () => {
  assert.equal(extractDate('20241003杭州').date, '2024-10-03');
  assert.equal(extractDate('IMG_20240105_123456').date, '2024-01-05');
});

/* ------------------------------------------------------------------ */
/* 日期：只有月日，靠父目录补年份                                        */
/* ------------------------------------------------------------------ */

test('只有月日 + 父目录年份', () => {
  const r = extractDate('10月3日 杭州西湖', { parentYear: 2024 });
  assert.equal(r.date, '2024-10-03');
  assert.equal(r.yearInferred, true);
});

test('只有月日且无父目录年份 → 部分日期', () => {
  const r = extractDate('10月3日');
  assert.equal(r.date, '10-03');
  assert.equal(r.year, null);
  assert.equal(r.partial, true);
});

test('紧凑月日 1003 + 父目录年份', () => {
  const r = extractDate('1003杭州', { parentYear: 2023 });
  assert.equal(r.date, '2023-10-03');
});

test('不把明显非日期的数字当月日', () => {
  // 13 月非法 → 不应命中
  const r = extractDate('1350 街头', { parentYear: 2024 });
  assert.equal(r, null);
});

test('非法日期被拒绝（2 月 30 日）', () => {
  assert.equal(extractDate('2024-02-30'), null);
});

/* ------------------------------------------------------------------ */
/* 年份 / 时间 / 标签                                                   */
/* ------------------------------------------------------------------ */

test('抽取年份', () => {
  assert.deepEqual(extractYears('2024年/2023回顾'), [2024, 2023]);
  assert.deepEqual(extractYears('照片'), []);
});

test('时间提示', () => {
  const r = extractDate('2024-10-03 14-30 西湖');
  assert.equal(r.date, '2024-10-03');
  assert.equal(r.hadTime, true);
});

test('标签抽取', () => {
  const tags = extractTags('10月3日 杭州西湖 夜景 长曝光');
  assert.ok(tags.includes('夜景'));
  assert.ok(tags.includes('长曝光'));
});

/* ------------------------------------------------------------------ */
/* 地点                                                               */
/* ------------------------------------------------------------------ */

test('地名归一化：西湖 → 带坐标', () => {
  const r = extractLocation('10月3日 杭州西湖');
  assert.ok(r.location.includes('西湖'));
  assert.ok(r.coords && r.coords.source === 'hint');
  assert.ok(Math.abs(r.coords.lat - 30.24) < 0.6);
});

test('地名：单独城市', () => {
  const r = extractLocation('2024-01-01 上海跨年');
  assert.ok(r.location.includes('上海'));
  assert.ok(r.coords);
});

test('地名：别名命中', () => {
  const r = extractLocation('羊城早茶');
  assert.equal(r.location, '广州');
});

test('地名：海外', () => {
  const r = extractLocation('2023-11-20 Tokyo 夜景');
  assert.ok(r.location.includes('东京'));
});

test('地名兜底：未知名也保留', () => {
  const r = extractLocation('2024-05-01 老家的河边');
  assert.ok(r.location && r.location.length > 0);
  assert.equal(r.coords, null);
  assert.ok(r.confidence < 0.5);
});

test('兜底名称会剥掉噪声词', () => {
  const name = cleanFallbackName('2024-05-01 精选 原片 东钱湖 备份');
  assert.ok(name.includes('东钱湖'));
  assert.ok(!name.includes('精选'));
  assert.ok(!name.includes('原片'));
});

/* ------------------------------------------------------------------ */
/* 整条路径                                                            */
/* ------------------------------------------------------------------ */

test('目录 + 父目录年份推断', () => {
  const r = parseArchivePath(['2024年', '10月3日 杭州西湖', '夜景']);
  assert.equal(r.date, '2024-10-03');
  assert.equal(r.year, 2024);
  assert.equal(r.dateSource, 'folder');
  assert.ok(r.location.includes('西湖'));
});

test('叶目录比祖先目录优先级更高', () => {
  const r = parseArchivePath(['2024年', '2023-05-01 婺源', '2024-10-03 杭州']);
  assert.equal(r.date, '2024-10-03');
});

test('父目录年份 + 地名分离', () => {
  const r = parseArchivePath(['2024', '10.3 西湖'], 'DSC01234.jpg');
  assert.equal(r.date, '2024-10-03');
  assert.ok(r.location.includes('西湖'));
});

test('文件名提供日期', () => {
  const r = parseArchivePath(['精选'], '2024-10-03-杭州-西湖-001.jpg');
  assert.equal(r.date, '2024-10-03');
  assert.equal(r.dateSource, 'filename');
  assert.ok(r.location.includes('杭州'));
});

test('手动覆盖优先级最高', () => {
  const r = parseArchivePath(['2024年', '10月3日'], 'a.jpg', {
    overrideDate: '2022-08-08',
    overrideLocation: '北京',
  });
  assert.equal(r.date, '2022-08-08');
  assert.equal(r.location, '北京');
  assert.ok(r.coords);
});

test('parsePathString：完整 Windows 路径', () => {
  const r = parsePathString('F:\\照片\\2024年\\10月3日 杭州西湖\\DSC01234.JPG');
  assert.equal(r.date, '2024-10-03');
  assert.ok(r.location.includes('西湖'));
});

test('parsePathString：不规则混排也能出结果', () => {
  const r = parsePathString('D:/photo/2024/国庆 西安 兵马俑/IMG_0001.jpeg');
  assert.equal(r.date, '2024-10-01');
  assert.ok(r.location.includes('西安') || r.location.includes('兵马俑'));
});

test('完全无信息时不抛错', () => {
  const r = parseArchivePath(['未分类'], 'abc.jpg');
  assert.equal(r.date, null);
  assert.equal(r.dateConfidence, 0);
});
