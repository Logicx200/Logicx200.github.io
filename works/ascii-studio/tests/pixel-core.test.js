'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const pixelCore = require('../js/pixel-core.js');

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

function pixelColor(result, index) {
  const offset = index * 4;
  const r = result.pixels[offset];
  const g = result.pixels[offset + 1];
  const b = result.pixels[offset + 2];
  return '#' + [r, g, b].map((value) => value.toString(16).padStart(2, '0')).join('');
}

function uniqueColors(result) {
  const found = new Set();
  for (let i = 0; i < result.cols * result.rows; i++) found.add(pixelColor(result, i));
  return found;
}

test('retro palettes are valid and frozen', () => {
  assert.ok(pixelCore.PALETTE_LIST.length >= 5);
  for (const preset of pixelCore.PALETTE_LIST) {
    assert.ok(preset.id);
    assert.ok(preset.label);
    assert.ok(preset.colors.length >= 2);
    for (const color of preset.colors) {
      assert.match(color, /^#[0-9a-f]{6}$/i);
    }
  }
  assert.equal(pixelCore.resolvePalette('pico8').colors.length, 16);
  assert.equal(pixelCore.resolvePalette('gameboy').colors.length, 4);
  // Unknown ids fall back to a usable palette instead of crashing.
  assert.ok(pixelCore.resolvePalette('does-not-exist').colors.length >= 2);
});

test('exact colors quantize without changing hue', () => {
  const image = makeImage(2, 1, (x) => (x === 0 ? [255, 0, 0] : [0, 0, 255]));
  const palette = ['#000000', '#ff0000', '#0000ff'];
  const result = pixelCore.convertPixels(image, { palette });
  assert.equal(result.mode, 'pixel');
  assert.equal(result.cols, 2);
  assert.equal(result.rows, 1);
  assert.equal(pixelColor(result, 0), '#ff0000');
  assert.equal(pixelColor(result, 1), '#0000ff');
  assert.equal(result.pixels[3], 255);
  assert.equal(result.palette.id, 'custom');
});

test('every output pixel belongs to the chosen palette', () => {
  const image = makeImage(32, 18, (x, y) => {
    const r = Math.round((x / 31) * 255);
    const g = Math.round((y / 17) * 255);
    const b = Math.round(((x + y) / 49) * 255);
    return [r, g, b];
  });
  const result = pixelCore.convertPixels(image, {
    palette: 'gameboy',
    autoLevels: true,
    autoClip: 0.01,
    dither: 'fs',
    outline: false
  });
  const allowed = new Set(pixelCore.resolvePalette('gameboy').colors.map((color) => color.hex));
  for (const color of uniqueColors(result)) {
    assert.ok(allowed.has(color), 'unexpected palette color ' + color);
  }
});

test('ordered and FS dithering change the quantization pattern', () => {
  const image = makeImage(32, 8, (x) => {
    const value = Math.round((x / 31) * 255);
    return [value, value, value];
  });
  const palette = pixelCore.resolvePalette('duo');
  const plain = pixelCore.convertPixels(image, { palette: 'duo', outline: false });
  const ordered = pixelCore.convertPixels(image, { palette: 'duo', outline: false, dither: 'ordered' });
  const fs = pixelCore.convertPixels(image, { palette: 'duo', outline: false, dither: 'fs' });

  const allowed = new Set(palette.colors.map((color) => color.hex));
  for (const result of [plain, ordered, fs]) {
    for (const color of uniqueColors(result)) assert.ok(allowed.has(color));
  }
  assert.notDeepEqual(ordered.pixels, plain.pixels);
  assert.notDeepEqual(fs.pixels, plain.pixels);
});

test('auto levels expand a dark low-contrast image', () => {
  const dark = makeImage(48, 4, (x) => {
    const value = 20 + Math.round((x / 47) * 24);
    return [value, value, value];
  });
  const plain = pixelCore.convertPixels(dark, { palette: 'gray', outline: false });
  const enhanced = pixelCore.convertPixels(dark, {
    palette: 'gray',
    outline: false,
    autoLevels: true,
    autoClip: 0.01
  });
  assert.ok(uniqueColors(enhanced).size > uniqueColors(plain).size);
});

test('outline adds dark contour pixels on strong edges', () => {
  const image = makeImage(20, 12, (x) => (x < 10 ? [250, 250, 250] : [220, 20, 20]));
  const palette = ['#000000', '#ffffff', '#ff0000'];
  const plain = pixelCore.convertPixels(image, { palette, outline: false });
  const outlined = pixelCore.convertPixels(image, { palette, outline: true });
  let plainBlack = 0;
  let outlineBlack = 0;
  for (let i = 0; i < 20 * 12; i++) {
    if (pixelColor(plain, i) === '#000000') plainBlack++;
    if (pixelColor(outlined, i) === '#000000') outlineBlack++;
  }
  assert.equal(plainBlack, 0);
  assert.ok(outlineBlack > 0);
  assert.equal(outlined.outlined, true);
});

test('auto level range can be reused for stable video frames', () => {
  const first = makeImage(16, 3, (x) => {
    const value = 15 + Math.round((x / 15) * 120);
    return [value, value, value];
  });
  const second = makeImage(16, 3, (x) => {
    const value = 50 + Math.round((x / 15) * 120);
    return [value, value, value];
  });
  const a = pixelCore.convertPixels(first, { palette: 'pico8', autoLevels: true, autoClip: 0.01 });
  assert.ok(a.autoRange);
  const b = pixelCore.convertPixels(second, {
    palette: 'pico8',
    autoLevels: true,
    autoClip: 0.01,
    autoRange: a.autoRange
  });
  assert.deepEqual(b.autoRange, a.autoRange);
});

test('invalid pixel input is rejected', () => {
  assert.throws(() => pixelCore.convertPixels(null), /imageData is required/);
  assert.throws(
    () => pixelCore.convertPixels({ width: 4, height: 4, data: new Uint8ClampedArray(3) }),
    /width .* height .* 4/
  );
});
