/** 开发辅助：验证布局计算数值（不依赖 sharp） */
import { writeExifApp1 } from '../src/exif-write.js';

const base = new Uint8Array(Buffer.from(
  '/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/wAALCAABAAEBAREA/8QAFAABAAAAAAAAAAAAAAAAAAAACf/EABQQAQAAAAAAAAAAAAAAAAAAAAD/2gAIAQEAAD8AKp//2Q==',
  'base64',
));

const out = writeExifApp1(base, {
  make: 'SONY',
  model: 'ILCE-7M4',
  dateTimeOriginal: new Date('2024-10-03T17:42:10'),
  lensModel: 'FE 24-70mm F2.8 GM II',
  fNumber: 5.6,
  exposureTime: 1 / 250,
  iso: 100,
  focalLength: 35,
  pixelXDimension: 300,
  pixelYDimension: 200,
  gps: { lat: 30.2442, lng: 120.139, alt: 12 },
});

const dv = (b, off = 0, le = true) => {
  const v = new DataView(b.buffer, b.byteOffset);
  return {
    u16: (o) => v.getUint16(o, le),
    u32: (o) => v.getUint32(o, le),
    i32: (o) => v.getInt32(o, le),
  };
};

let i = 2;
let app1 = null;
while (i + 4 <= out.length) {
  if (out[i] !== 0xff) break;
  const marker = out[i + 1];
  if (marker === 0xda) break;
  const len = new DataView(out.buffer, out.byteOffset).getUint16(i + 2, false);
  if (marker === 0xe1) { app1 = out.subarray(i + 4, i + 2 + len); break; }
  i += 2 + len;
}
if (!app1) { console.log('没有 APP1'); process.exit(1); }

const t = app1.subarray(6);
const r16 = (o) => new DataView(t.buffer, t.byteOffset).getUint16(o, true);
const r32 = (o) => new DataView(t.buffer, t.byteOffset).getUint32(o, true);

console.log('APP1 负载', app1.length, 'TIFF', t.length, 'IFD0@', r32(4));
const n = r16(8);
console.log('IFD0 条目', n);
const pointers = {};
for (let k = 0; k < n; k++) {
  const b = 8 + 2 + k * 12;
  const tag = r16(b);
  const cnt = r32(b + 4);
  const val = r32(b + 8);
  let show = '';
  if (cnt > 4 && tag !== 0x8769 && tag !== 0x8825) {
    show = ` => "${new TextDecoder('latin1').decode(t.subarray(val, val + Math.min(cnt, 30))).replace(/\0.*$/, '')}"`;
  }
  if (tag === 0x8769 || tag === 0x8825) pointers[tag] = val;
  console.log(`  0x${tag.toString(16).padStart(4, '0')} type=${r16(b + 2)} cnt=${cnt} val=${val}${show}`);
}
for (const [tag, off] of Object.entries(pointers)) {
  const label = tag === '34537' ? 'ExifIFD' : 'GPSIFD';
  const cnt = r16(off);
  console.log(`${label} @${off} 条目数=${cnt}${cnt > 0 && cnt < 40 ? '' : '  <-- 异常'}`);
  if (cnt > 0 && cnt < 40) {
    for (let k = 0; k < cnt; k++) {
      const b = off + 2 + k * 12;
      const tg = r16(b);
      const c = r32(b + 4);
      const v = r32(b + 8);
      let s = '';
      if (r16(b + 2) === 2) {
        const start = c <= 4 ? b + 8 : v;
        s = ` => "${new TextDecoder('latin1').decode(t.subarray(start, start + Math.min(c, 40))).replace(/\0.*$/, '')}"`;
      } else if (r16(b + 2) === 5) {
        s = ` => ${r32(v)}/${r32(v + 4)}`;
      } else if (c === 1) {
        s = ` => ${v}`;
      }
      console.log(`    0x${tg.toString(16).padStart(4, '0')} type=${r16(b + 2)} cnt=${c}${s}`);
    }
  }
}

// 用 exifr 复核
const { readExif } = await import('../src/exif.js');
const fs = await import('node:fs/promises');
await fs.writeFile('.cache/exif-selftest.jpg', out);
const parsed = await readExif('.cache/exif-selftest.jpg');
console.log('\nexifr 复核:', JSON.stringify({
  capturedAt: parsed.capturedAt,
  camera: parsed.camera,
  lens: parsed.lens,
  f: parsed.exposure?.aperture,
  t: parsed.exposure?.shutter,
  iso: parsed.exposure?.iso,
  focal: parsed.exposure?.focal,
  gps: parsed.gps,
  pixels: parsed.pixels,
}, null, 1));
