'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const core = require('../js/ascii-core.js');

function makeImage(width, height, painter) {
  const data = new Uint8ClampedArray(width * height * 4);
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const index = (y * width + x) * 4;
      const color = painter(x, y);
      data[index] = color[0];
      data[index + 1] = color[1];
      data[index + 2] = color[2];
      data[index + 3] = color.length > 3 ? color[3] : 255;
    }
  }
  return { data, width, height };
}

function allChars(result) {
  return new Set(result.lines.join('').split(''));
}

function charIndex(result, char) {
  return result.charTable.indexOf(char);
}

test('charsets are ordered, non-empty and frozen', () => {
  const ids = Object.keys(core.CHARSETS);
  assert.ok(ids.length >= 5);
  for (const id of ids) {
    const preset = core.CHARSETS[id];
    assert.equal(preset.id, id);
    assert.ok(preset.chars.length >= 2);
    assert.ok(preset.label.length > 0);
    const normalized = core.normalizeCharset(preset.chars);
    assert.ok(normalized.length >= 2);
    assert.equal(new Set(normalized).size, normalized.length);
  }
  assert.ok(Object.isFrozen(core.CHARSETS.classic));
});

test('computeGrid preserves source aspect via cell aspect ratio', () => {
  const grid = core.computeGrid(1600, 1000, 100, 0.6);
  assert.deepEqual(grid, { cols: 100, rows: 38 });

  // (cols × cellAspect) / rows should approximate the source aspect ratio.
  const displayAspect = (grid.cols * 0.6) / grid.rows;
  const sourceAspect = 1600 / 1000;
  assert.ok(Math.abs(displayAspect - sourceAspect) < 0.08);

  const portrait = core.computeGrid(800, 1200, 80, 0.58);
  assert.equal(portrait.cols, 80);
  assert.ok(portrait.rows < portrait.cols);
  const portraitDisplayAspect = (portrait.cols * 0.58) / portrait.rows;
  assert.ok(Math.abs(portraitDisplayAspect - 800 / 1200) < 0.08);

  const clampedCols = core.computeGrid(100, 100, 9999, 0.58);
  assert.equal(clampedCols.cols, 500);
});

test('normalizeCharset removes controls, deduplicates and enforces two levels', () => {
  assert.deepEqual(core.normalizeCharset(' .:-=+*#%@'), Array.from(' .:-=+*#%@'));
  assert.deepEqual(core.normalizeCharset('ab\n\tc'), ['a', 'b', 'c']);
  assert.deepEqual(core.normalizeCharset('aabbcc'), ['a', 'b', 'c']);
  assert.ok(core.normalizeCharset('').length >= 2);
  assert.ok(core.normalizeCharset(' ').length >= 2);
  const long = core.normalizeCharset(
    Array.from({ length: 300 }, (_, i) => String.fromCharCode(0x4e00 + i)).join('')
  );
  assert.equal(long.length, 96);
});

test('resolveCharset handles presets and custom fallbacks', () => {
  assert.equal(core.resolveCharset('classic').length, 10);
  assert.deepEqual(core.resolveCharset('custom', 'ab'), ['a', 'b']);
  assert.equal(core.resolveCharset('custom', '').length, 10);
  assert.equal(core.resolveCharset('does-not-exist').length, 10);
});

test('black and white map to sparse and dense characters', () => {
  const image = makeImage(2, 1, (x) => (x === 0 ? [0, 0, 0] : [255, 255, 255]));
  const result = core.convert(image, { charset: ' .:-=+*#%@' });
  assert.equal(result.cols, 2);
  assert.equal(result.rows, 1);
  assert.equal(result.plain, ' @');
  assert.equal(result.lines[0], ' @');
  assert.equal(result.levels, 10);
  assert.equal(result.inked, 1);
  assert.equal(result.colorMode, 'mono');
  assert.equal(result.rgb, null);
});

test('invert swaps dark and light', () => {
  const image = makeImage(2, 1, (x) => (x === 0 ? [0, 0, 0] : [255, 255, 255]));
  const result = core.convert(image, { invert: true, charset: ' .:-=+*#%@' });
  assert.equal(result.plain, '@ ');
});

test('color mode preserves RGB data', () => {
  const image = makeImage(2, 1, (x) => (x === 0 ? [255, 0, 0] : [0, 0, 255]));
  const result = core.convert(image, { color: true, charset: ' .:-=+*#%@' });
  assert.equal(result.colorMode, 'color');
  assert.ok(result.rgb instanceof Uint8ClampedArray);
  assert.equal(result.rgb.length, 2 * 3);
  assert.equal(result.rgb[0], 255);
  assert.equal(result.rgb[1], 0);
  assert.equal(result.rgb[2], 0);
  assert.equal(result.rgb[3], 0);
  assert.equal(result.rgb[4], 0);
  assert.equal(result.rgb[5], 255);
});

test('brightness and contrast affect the selected level', () => {
  const image = makeImage(1, 1, () => [128, 128, 128]);
  const normal = core.convert(image, { charset: ' .:-=+*#%@' });
  const brighter = core.convert(image, { charset: ' .:-=+*#%@', brightness: 0.35 });
  const darker = core.convert(image, { charset: ' .:-=+*#%@', brightness: -0.35 });
  assert.ok(charIndex(brighter, brighter.plain) > charIndex(normal, normal.plain));
  assert.ok(charIndex(darker, darker.plain) < charIndex(normal, normal.plain));
  const harsh = core.convert(image, { charset: ' .:-=+*#%@', contrast: 3 });
  assert.equal(harsh.levels, 10);
});

test('auto levels expand a low-contrast dark image', () => {
  const dim = makeImage(32, 1, (x) => {
    const value = 10 + Math.round((x / 31) * 20);
    return [value, value, value];
  });
  const plain = core.convert(dim, { charset: ' .:-=+*#%@' });
  const enhanced = core.convert(dim, {
    charset: ' .:-=+*#%@',
    autoLevels: true,
    autoClip: 0.015
  });
  assert.ok(allChars(enhanced).size > allChars(plain).size);
  assert.equal(enhanced.lines[0][0], ' ');
  assert.equal(enhanced.lines[0][enhanced.lines[0].length - 1], '@');
});

test('auto levels can reuse a stable range for video frames', () => {
  const first = makeImage(16, 1, (x) => {
    const value = 20 + Math.round((x / 15) * 160);
    return [value, value, value];
  });
  const second = makeImage(16, 1, (x) => {
    const value = 10 + Math.round((x / 15) * 245);
    return [value, value, value];
  });
  const a = core.convert(first, { autoLevels: true, autoClip: 0.01, charset: ' .:-=+*#%@' });
  assert.ok(a.autoRange);
  assert.ok(a.autoRange.high > a.autoRange.low);
  const b = core.convert(second, {
    autoLevels: true,
    autoRange: a.autoRange,
    autoClip: 0.01,
    charset: ' .:-=+*#%@'
  });
  assert.deepEqual(b.autoRange, a.autoRange);
  assert.equal(b.lines[0][0], ' ');
  assert.equal(b.lines[0][b.lines[0].length - 1], '@');
});

test('ordered dithering breaks up flat midtones', () => {
  const uniform = makeImage(8, 8, () => [128, 128, 128]);
  const plain = core.convert(uniform, { charset: ' .:-=+*#%@' });
  const dithered = core.convert(uniform, { charset: ' .:-=+*#%@', dither: 'ordered' });
  assert.equal(plain.lines.join(''), '+'.repeat(64));
  assert.ok(allChars(dithered).size > 1, 'ordered dithering should produce multiple levels');
});

test('Floyd-Steinberg dithering stays within valid character bounds', () => {
  const gradient = makeImage(16, 9, (x) => {
    const value = Math.round((x / 15) * 255);
    return [value, value, value, 255];
  });
  const result = core.convert(gradient, { charset: ' .:-=+*#%@', dither: 'fs' });
  assert.equal(result.rows, 9);
  assert.equal(result.cols, 16);
  const allowed = new Set(Array.from(' .:-=+*#%@'));
  for (const ch of result.lines.join('')) {
    assert.ok(allowed.has(ch), 'unexpected glyph: ' + ch);
  }
  assert.ok(allChars(result).size > 4);
});

test('custom charset is used verbatim for levels', () => {
  const image = makeImage(3, 1, (x) => {
    if (x === 0) return [0, 0, 0];
    if (x === 1) return [128, 128, 128];
    return [255, 255, 255];
  });
  const result = core.convert(image, { charset: 'abc' });
  assert.equal(result.levels, 3);
  assert.equal(result.plain, 'abc');
  assert.deepEqual(result.charTable, ['a', 'b', 'c']);
});

test('convert rejects malformed image data', () => {
  assert.throws(() => core.convert(null), /imageData is required/);
  assert.throws(
    () => core.convert({ width: 4, height: 4, data: new Uint8ClampedArray(3) }),
    /width .* height .* 4/
  );
});

test('computeGrid handles absurd input safely', () => {
  const tiny = core.computeGrid(0, 0, 0, 0);
  assert.ok(tiny.cols >= 8);
  assert.ok(tiny.rows >= 1);
  const rowCapped = core.computeGrid(10, 4000, 220, 0.8, 500);
  assert.equal(rowCapped.rows, 500);
});
