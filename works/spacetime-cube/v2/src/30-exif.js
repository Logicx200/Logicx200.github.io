/* 时空立方体 · EXIF 最小读取
 *
 * 只做一件事：从 JPEG 里读出「拍摄时间」和「方向」，用来决定照片在时间轴上的先后。
 *
 * 为什么必须读 EXIF 而不是用文件修改时间：
 *   拷来拷去、批量导出、网盘同步都会改掉 mtime，但 EXIF 里的 DateTimeOriginal
 *   是相机按下快门那一刻写下的，那才是真正的拍摄时刻。
 *
 * 只读头部若干字节（APP1 一定在最前面几段里），不解码整张图。
 */
(function (STC) {
  'use strict';

  var HEAD_BYTES = 256 * 1024;

  /** 解析 JPEG 的 EXIF；返回 {date:Date|null, orientation:int, hasExif:bool} */
  function parseJpeg(view, bytes) {
    var out = { date: null, orientation: 1, hasExif: false };
    if (bytes < 4 || view.getUint8(0) !== 0xFF || view.getUint8(1) !== 0xD8) return out;

    var off = 2;
    while (off + 4 <= bytes) {
      if (view.getUint8(off) !== 0xFF) break;
      var marker = view.getUint8(off + 1);
      off += 2;
      if (marker === 0xD8 || marker === 0x01 || (marker >= 0xD0 && marker <= 0xD7)) continue;
      if (marker === 0xDA) break;                       // 进入压缩数据，后面不再有元数据
      if (off + 2 > bytes) break;
      var size = view.getUint16(off, false);
      if (size < 2) break;
      var segStart = off + 2;
      var segEnd = off + size;
      if (segEnd > bytes) segEnd = bytes;

      if (marker === 0xE1 && segStart + 6 <= segEnd &&
          view.getUint32(segStart, false) === 0x45786966 &&   // "Exif"
          view.getUint16(segStart + 4, false) === 0x0000) {
        out.hasExif = true;
        readTiff(view, segStart + 6, segEnd, out);
        return out;
      }
      off = segEnd;
    }
    return out;
  }

  function readTiff(view, tiff, end, out) {
    if (tiff + 8 > end) return;
    var order = view.getUint16(tiff, false);
    var le;
    if (order === 0x4949) le = true;        // "II"
    else if (order === 0x4D4D) le = false;  // "MM"
    else return;
    if (view.getUint16(tiff + 2, le) !== 0x002A) return;

    var ifd0 = view.getUint32(tiff + 4, le);
    var exifIfd = 0;

    // ---- IFD0：拿 Orientation，同时找 Exif 子目录的指针 ----
    var n = readIfd(view, tiff, tiff + ifd0, end, le, function (tag, type, count, valOff) {
      if (tag === 0x0112) out.orientation = readShort(view, type, count, valOff, le) || 1;
      else if (tag === 0x8769) exifIfd = readLong(view, type, count, valOff, le);
    });

    // ---- Exif 子目录：拿 DateTimeOriginal(0x9003)，退而求其次 DateTimeDigitized(0x9004) ----
    var best = null, digitized = null;
    if (exifIfd && n >= 0) {
      readIfd(view, tiff, tiff + exifIfd, end, le, function (tag, type, count, valOff) {
        if (tag === 0x9003) best = readAscii(view, count, valOff, end);
        else if (tag === 0x9004) digitized = readAscii(view, count, valOff, end);
      });
    }
    if (!best) best = digitized;
    if (best) out.date = parseStamp(best);
  }

  /** 遍历一个 IFD，对每个条目调用 cb(tag, type, count, valueOffsetOrInline) */
  function readIfd(view, tiff, ifd, end, le, cb) {
    if (ifd + 2 > end) return -1;
    var count = view.getUint16(ifd, le);
    if (count > 512) return -1;                 // 明显不合理，防止越界乱跑
    for (var i = 0; i < count; i++) {
      var e = ifd + 2 + i * 12;
      if (e + 12 > end) break;
      var tag = view.getUint16(e, le);
      var type = view.getUint16(e + 2, le);
      var num = view.getUint32(e + 4, le);
      var size = typeSize(type) * num;
      // 值 ≤ 4 字节时直接内联在条目里，否则是个偏移
      var valOff = size <= 4 ? e + 8 : tiff + view.getUint32(e + 8, le);
      cb(tag, type, num, valOff);
    }
    return count;
  }

  function typeSize(t) {
    switch (t) {
      case 1: case 2: case 6: case 7: return 1;
      case 3: case 8: return 2;
      case 4: case 9: case 11: return 4;
      case 5: case 10: case 12: return 8;
      default: return 1;
    }
  }

  function readShort(view, type, count, off, le) {
    if (type !== 3 || count < 1) return 0;
    return view.getUint16(off, le);
  }

  function readLong(view, type, count, off, le) {
    if (type !== 4 || count < 1) return 0;
    return view.getUint32(off, le);
  }

  function readAscii(view, count, off, end) {
    var s = '';
    for (var i = 0; i < count && off + i < end; i++) {
      var c = view.getUint8(off + i);
      if (c === 0) break;
      s += String.fromCharCode(c);
    }
    return s.trim();
  }

  /** EXIF 格式是 "YYYY:MM:DD HH:MM:SS"，注意是冒号分隔日期 */
  function parseStamp(s) {
    var m = /^(\d{4}):(\d{2}):(\d{2})[ T](\d{2}):(\d{2}):(\d{2})/.exec(s);
    if (!m) return null;
    var y = +m[1], mo = +m[2], d = +m[3], h = +m[4], mi = +m[5], se = +m[6];
    if (y < 1900 || mo < 1 || mo > 12 || d < 1 || d > 31) return null;
    // 相机时间没有时区信息，按本地时间解释 —— 单调排序不受影响
    var t = new Date(y, mo - 1, d, h, mi, se);
    return isNaN(t.getTime()) ? null : t;
  }

  /** 读一个 File 的拍摄信息；任何失败都安静地退回默认值 */
  async function read(file) {
    var out = { date: null, orientation: 1, hasExif: false, error: null };
    try {
      if (!/jpe?g$/i.test(file.name) && file.type !== 'image/jpeg') return out;
      var buf = await file.slice(0, Math.min(HEAD_BYTES, file.size)).arrayBuffer();
      return parseJpeg(new DataView(buf), buf.byteLength);
    } catch (e) {
      out.error = String(e && e.message || e);
      return out;
    }
  }

  STC.exif = { read: read, parseJpeg: parseJpeg };
})(window.STC = window.STC || {});
