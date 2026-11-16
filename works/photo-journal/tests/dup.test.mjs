/**
 * 重复照片检测的单元测试
 *
 * 覆盖：
 *   - 汉明距离 / 相似度
 *   - 完全一致、轻微差异、明显不同的分组行为
 *   - 分组是"传递"的（A≈B、B≈C → 三张一组）
 *   - 建议保留项的选择规则（像素 > 星级 > 体积）
 *   - 冗余张数与可省空间的统计
 */

import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  hamming, similarity, findDuplicates, pickKeeper, sortGroupByKeeper,
  makeSignature, parseSignature, histogramFromPixels, histogramDistance,
} from '../src/dup.js';

const H = (hex) => BigInt('0x' + hex).toString(16).padStart(16, '0');

/** 造一张假照片；颜色特征用 hist 区分（默认都一样） */
const photo = (id, hashHex, extra = {}) => {
  const { hist = 'f000080000000000', ...rest } = extra;
  return {
    id,
    path: `${id}.JPG`,
    date: '2024-01-01',
    bytes: 5 * 1024 * 1024,
    pixel: { width: 6000, height: 4000 },
    rating: 0,
    phash: makeSignature(H(hashHex), hist),
    ...rest,
  };
};

test('汉明距离：相同为 0，差一位为 1', () => {
  assert.equal(hamming(H('0000000000000000'), H('0000000000000000')), 0);
  assert.equal(hamming(H('0000000000000000'), H('0000000000000001')), 1);
  assert.equal(hamming(H('ffffffffffffffff'), H('0000000000000000')), 64);
});

test('相似度：0 距离 = 1', () => {
  assert.equal(similarity(H('abcdef0123456789'), H('abcdef0123456789')), 1);
  assert.ok(Math.abs(similarity(H('0000000000000000'), H('000000000000000f')) - (1 - 4 / 64)) < 1e-9);
});

test('完全相同的照片被分到一组', () => {
  const { groups, stats } = findDuplicates([
    photo('a', '1111111111111111'),
    photo('b', '1111111111111111'),
    photo('c', '9999999999999999'),
  ]);
  assert.equal(groups.length, 1);
  assert.equal(groups[0].kind, 'exact');
  assert.equal(groups[0].count, 2);
  assert.equal(groups[0].distance, 0);
  assert.equal(stats.redundant, 1);
});

test('轻微差异（缩过尺寸/重压缩）也算重复', () => {
  const { groups } = findDuplicates([
    photo('a', '1111111111111111'),
    photo('b', '1111111111111113'),   // 距离 1
  ]);
  assert.equal(groups.length, 1);
  assert.equal(groups[0].kind, 'visual');
  assert.equal(groups[0].distance, 1);
});

test('差异过大不算重复', () => {
  const { groups } = findDuplicates([
    photo('a', '0000000000000000'),
    photo('b', 'ffffffffffffffff'),   // 距离 64
  ]);
  assert.equal(groups.length, 0);
});

/* ---------- 颜色特征校验（消除"结构撞车"的误报） ---------- */

test('签名：结构 + 颜色，前 16 位是结构', () => {
  const sig = makeSignature('abcd1234abcd1234', 'f0f0f0f000000000');
  assert.equal(sig.length, 32);
  const parsed = parseSignature(sig);
  assert.equal(parsed.dhash, 'abcd1234abcd1234');
  assert.equal(parsed.hist, 'f0f0f0f000000000');
});

test('颜色特征：同一张图重复计算完全一致', () => {
  const pixels = new Uint8Array(64 * 64 * 4);
  for (let i = 0; i < pixels.length; i += 4) {
    pixels[i] = 200; pixels[i + 1] = 60; pixels[i + 2] = 30; pixels[i + 3] = 255;
  }
  const h1 = histogramFromPixels(pixels, 4, 1, 64);
  const h2 = histogramFromPixels(pixels, 4, 1, 64);
  assert.equal(h1, h2);
  assert.equal(histogramDistance(h1, h2), 0);
});

test('颜色特征不受亮度影响（关键：调亮后仍算同一张）', () => {
  const make = (scale) => {
    const pixels = new Uint8Array(64 * 64 * 4);
    for (let i = 0; i < pixels.length; i += 4) {
      pixels[i] = Math.min(255, 120 * scale);
      pixels[i + 1] = Math.min(255, 90 * scale);
      pixels[i + 2] = Math.min(255, 60 * scale);
      pixels[i + 3] = 255;
    }
    return histogramFromPixels(pixels, 4, 1, 64);
  };
  const base = make(1);
  for (const scale of [1.06, 1.12, 1.3]) {
    const d = histogramDistance(base, make(scale));
    assert.ok(d <= 2, `亮度 ×${scale} 的颜色距离 ${d} 应当很小`);
  }
});

test('结构像但颜色分布差很多 → 判定为不同照片', () => {
  // 结构距离 1（很像），但色度分布完全不同
  const { groups, stats } = findDuplicates([
    photo('night', '1111111111111111', { hist: 'ffffffff00000000' }),
    photo('snow', '1111111111111113', { hist: '00000000ffffffff' }),
  ]);
  assert.equal(groups.length, 0, '不该判为重复');
  assert.equal(stats.colorRejected, 1, '应当被颜色校验挡下');
});

test('结构像且颜色也接近 → 仍判定为重复', () => {
  const { groups } = findDuplicates([
    photo('a', '1111111111111111', { hist: 'f0f0f0f000000000' }),
    photo('b', '1111111111111113', { hist: 'f0f0f0f000000001' }),
  ]);
  assert.equal(groups.length, 1);
});

test('放大阈值后，之前被颜色挡下的也能合并进来', () => {
  // 色度距离 raw=45 → 归一化 9：默认阈值 7 挡下，放到 12 就合并
  const photos = [
    photo('a', '1111111111111111', { hist: 'f0f0f00000000000' }),
    photo('b', '1111111111111113', { hist: '00000000f0f0f000' }),
  ];
  assert.equal(findDuplicates(photos).groups.length, 0);
  assert.equal(findDuplicates(photos, { maxColorDistance: 12 }).groups.length, 1);
});

test('置信度分级：完全相同 / 高度相似 / 可能重复', () => {
  const exact = findDuplicates([
    photo('a', '1111111111111111'),
    photo('b', '1111111111111111'),
  ]).groups[0];
  assert.equal(exact.confidence, 'exact');

  const high = findDuplicates([
    photo('a', '1111111111111111'),
    photo('b', '1111111111111113'),   // 距离 1
  ]).groups[0];
  assert.equal(high.confidence, 'high');

  // 距离 4：仍然会被列出来，但要标记为"需要人工确认"
  const low = findDuplicates([
    photo('a', '0000000000000000'),
    photo('b', '000000000000000f'),   // 距离 4
  ]).groups[0];
  assert.equal(low.confidence, 'low');
});

test('阈值可调：放宽后能合并进来', () => {
  const photos = [
    photo('a', '0000000000000000'),
    photo('b', '0000000000000fff'),   // 距离 12
  ];
  assert.equal(findDuplicates(photos, { threshold: 6 }).groups.length, 0);
  assert.equal(findDuplicates(photos, { threshold: 12 }).groups.length, 1);
});

test('分组是传递的：A≈B、B≈C 会合成一组', () => {
  const { groups } = findDuplicates([
    photo('a', '0000000000000000'),
    photo('b', '0000000000000003'),
    photo('c', '000000000000000f'),
  ], { threshold: 6 });
  assert.equal(groups.length, 1);
  assert.equal(groups[0].count, 3);
  // 最大距离记录为 a-c 的距离
  assert.equal(groups[0].distance, 4);
});

test('建议保留：优先像素最多，其次星级，其次体积', () => {
  const big = photo('big', '1111111111111111', { pixel: { width: 8000, height: 6000 } });
  const starred = photo('starred', '1111111111111111', { pixel: { width: 4000, height: 3000 }, rating: 5 });
  const small = photo('small', '1111111111111111', { pixel: { width: 2000, height: 1500 }, bytes: 1024 });
  assert.equal(pickKeeper([starred, big, small]).id, 'big', '像素多的优先');

  // 像素相同的情况下看星级
  const a = photo('a', '1111111111111111', { pixel: { width: 4000, height: 3000 }, rating: 0 });
  const b = photo('b', '1111111111111111', { pixel: { width: 4000, height: 3000 }, rating: 4 });
  assert.equal(pickKeeper([a, b]).id, 'b');
});

test('统计：冗余张数与可省空间', () => {
  const { stats, groups } = findDuplicates([
    photo('a', '1111111111111111', { bytes: 8 * 1024 * 1024 }),
    photo('b', '1111111111111111', { bytes: 3 * 1024 * 1024, pixel: { width: 3000, height: 2000 } }),
    photo('c', '2222222222222222'),
  ]);
  assert.equal(stats.photos, 3);
  assert.equal(stats.groups, 1);
  assert.equal(stats.redundant, 1);
  assert.equal(groups[0].keeper.id, 'a', '像素/体积都更大，应保留 a');
  assert.equal(groups[0].wastedBytes, 3 * 1024 * 1024);
});

test('没有指纹的照片被忽略，不影响其它分组', () => {
  const { groups, stats } = findDuplicates([
    photo('a', '1111111111111111'),
    { id: 'nohash', path: 'x.JPG', bytes: 100, pixel: { width: 100, height: 100 } },
    photo('b', '1111111111111111'),
  ]);
  assert.equal(stats.photos, 3);
  assert.equal(groups.length, 1);
  assert.equal(groups[0].count, 2);
});

test('排序：保留项排在最前', () => {
  const group = findDuplicates([
    photo('small', '1111111111111111', { pixel: { width: 2000, height: 1500 } }),
    photo('big', '1111111111111111', { pixel: { width: 6000, height: 4000 } }),
  ]).groups[0];
  const sorted = sortGroupByKeeper(group);
  assert.equal(sorted[0].id, 'big');
});

test('空输入不报错', () => {
  const { groups, stats } = findDuplicates([]);
  assert.equal(groups.length, 0);
  assert.equal(stats.redundant, 0);
  assert.equal(findDuplicates(undefined).groups.length, 0);
});

test('照片多时不会算到爆炸（性能兜底）', () => {
  // 400 张互不相同的图：两两比较 79800 次，应在毫秒级完成
  const photos = [];
  for (let i = 0; i < 400; i++) {
    // 每个哈希都不同（把 i 的低 4 位散开），随机分布
    const v = (BigInt(i) * 0x9e3779b97f4a7c15n) & 0xffffffffffffffffn;
    photos.push(photo(`p${i}`, v.toString(16).padStart(16, '0')));
  }
  const t0 = Date.now();
  const { stats } = findDuplicates(photos);
  const ms = Date.now() - t0;
  assert.equal(stats.photos, 400);
  assert.ok(ms < 3000, `400 张比较耗时 ${ms}ms，太慢了`);
});
