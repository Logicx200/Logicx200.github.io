// 生成一张测试用的 PNG（零依赖，只用 node 内置 zlib）。
// 用于无头浏览器验证：画一个在画面里横穿的高对比圆点，方便检验轨迹是否被正确累积。

const zlib = require('node:zlib');
const fs = require('node:fs');
const path = require('node:path');

// 输出到项目根目录下的 sample/，测试页按 ../sample/ 取用
const OUT_DIR = path.join(__dirname, '..', 'sample');

function crc32(buf) {
  let c;
  const table = crc32.table || (crc32.table = (() => {
    const t = new Int32Array(256);
    for (let n = 0; n < 256; n++) {
      c = n;
      for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
      t[n] = c;
    }
    return t;
  })());
  let crc = 0 ^ (-1);
  for (let i = 0; i < buf.length; i++) crc = (crc >>> 8) ^ table[(crc ^ buf[i]) & 0xff];
  return (crc ^ (-1)) >>> 0;
}

function chunk(type, data) {
  const len = Buffer.alloc(4);
  len.writeUInt32BE(data.length, 0);
  const body = Buffer.concat([Buffer.from(type, 'ascii'), data]);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(body), 0);
  return Buffer.concat([len, body, crc]);
}

function encodePNG(width, height, rgb) {
  const raw = Buffer.alloc((width * 3 + 1) * height);
  for (let y = 0; y < height; y++) {
    const rowStart = y * (width * 3 + 1);
    raw[rowStart] = 0; // filter: none
    rgb.copy(raw, rowStart + 1, y * width * 3, (y + 1) * width * 3);
  }
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(width, 0);
  ihdr.writeUInt32BE(height, 4);
  ihdr[8] = 8;   // bit depth
  ihdr[9] = 2;   // color type: truecolor
  ihdr[10] = 0; ihdr[11] = 0; ihdr[12] = 0;

  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk('IHDR', ihdr),
    chunk('IDAT', zlib.deflateSync(raw, { level: 6 })),
    chunk('IEND', Buffer.alloc(0))
  ]);
}

const W = 160, H = 120, N = 24;
function makeFrame(i) {
  const rgb = Buffer.alloc(W * H * 3);
  // 深色背景
  for (let p = 0; p < W * H; p++) {
    const v = p % 2 === 0 ? 12 : 18;
    rgb[p * 3] = v; rgb[p * 3 + 1] = v; rgb[p * 3 + 2] = v + 4;
  }
  const t = i / (N - 1);
  const cx = 18 + t * (W - 36);
  const cy = H / 2 + Math.sin(t * Math.PI * 2) * 26;
  // 亮橙色圆点：高对比，容易被阈值挑出来
  for (let y = 0; y < H; y++) {
    for (let x = 0; x < W; x++) {
      const d = Math.hypot(x - cx, y - cy);
      if (d < 7) {
        const k = 1 - d / 7;
        const p = (y * W + x) * 3;
        rgb[p] = Math.min(255, 40 + 215 * k);
        rgb[p + 1] = Math.min(255, 90 * k + 20);
        rgb[p + 2] = Math.min(255, 20 * k);
      }
    }
  }
  // 左上角一个固定的亮标记：用于验证「不动的物体在时间轴上糊成一条竖线」
  for (let y = 8; y < 16; y++) {
    for (let x = 8; x < 16; x++) {
      const p = (y * W + x) * 3;
      rgb[p] = 235; rgb[p + 1] = 235; rgb[p + 2] = 245;
    }
  }
  return rgb;
}

function main() {
  const out = OUT_DIR;
  fs.mkdirSync(out, { recursive: true });
  for (let i = 0; i < N; i++) {
    const name = `frame_${String(i).padStart(3, '0')}.png`;
    fs.writeFileSync(path.join(out, name), encodePNG(W, H, makeFrame(i)));
  }
  console.log(`已生成 ${N} 张测试图 -> ${out}`);
}

main();
