'use strict';
/* ============================================================================
   城市路网 SVG 底图生成器 —— 移植自 F:\Project 系列 Python 脚本（roadmap_svg.py 等）
   纯前端、零依赖。只有用户点击「获取道路数据 / 搜索」后才向 Overpass / Nominatim
   发请求；页面本身与静态资源全部本地。
   ============================================================================ */
(function () {
  var $ = function (id) { return document.getElementById(id); };
  var RAD = Math.PI / 180;
  var MAX_TILES = 24;          // 单次抓取最大分块数（控制请求量）
  var CONCURRENCY = 2;         // 同时进行的 Overpass 请求数（对公共实例礼貌一点）
  var REQUEST_TIMEOUT = 120000;
  var NOMINATIM = 'https://nominatim.openstreetmap.org/search';
  var ENDPOINTS = [
    'https://overpass-api.de/api/interpreter',
    'https://overpass.kumi.systems/api/interpreter',
    'https://overpass.osm.ch/api/interpreter',
    'https://overpass.private.coffee/api/interpreter'
  ];
  var HIGHWAY_LIST = [
    'motorway', 'motorway_link', 'trunk', 'trunk_link',
    'primary', 'primary_link', 'secondary', 'secondary_link',
    'tertiary', 'tertiary_link', 'residential', 'unclassified',
    'living_street', 'service'
  ];

  /* ---------- 数据源与矢量瓦片 ---------- */
  var CITY_INDEX_URL = 'cities/index.js';
  var CITY_DATA_DIR = 'cities/';
  var TILE_CONCURRENCY = 6;      // 矢量瓦片并发数
  var MAX_VTILES = 36;           // 单次矢量瓦片抓取最大块数
  var TILE_TIMEOUT = 30000;
  var VERSATILES_URL = 'https://tiles.versatiles.org/tiles/osm/{z}/{x}/{y}';
  var OPENFREEMAP_TILEJSON = 'https://tiles.openfreemap.org/planet';
  var VECTOR_SOURCE_NAMES = { versatiles: 'VersaTiles', openfreemap: 'OpenFreeMap' };
  var GROUP_SERVICE = 5;

  /* ---------- 视图 / 标记 / 名称 ---------- */
  var ZOOM_MIN = 1, ZOOM_MAX = 16;
  var LABEL_REF = 900;                 // 文字/标记尺寸的屏幕参考宽度（900px 时按 1:1 像素设计）
  var MAX_LABELS = 260;                // 单次渲染标签上限（避免全画糊成一团）
  var DRAG_THRESHOLD = 3;              // 拖拽阈值（px）
  var LABEL_FONT = '"Microsoft YaHei", "PingFang SC", "Hiragino Sans GB", "Noto Sans CJK SC", system-ui, sans-serif';
  var ROAD_LABEL_FONT = [13, 12.5, 12, 11.5, 11, 11];   // 6 级道路名称字号（屏幕 px）
  var STORE_MARKERS = 'xz-roadmap-markers:';
  var PLACE_KINDS = { city: 1, town: 1, village: 1, suburb: 1, quarter: 1, neighbourhood: 1, hamlet: 1 };
  var POI_KINDS = { station: 1, bus_station: 1, halt: 1, helipad: 1, airport: 1, attraction: 1, museum: 1, monument: 1, park: 1, zoo: 1, university: 1, hospital: 1 };

  /* ---------- 道路分组（6 组，线宽为 2400px 画布下的像素） ---------- */
  var GROUPS = [
    { key: 'arterial', name: '快速路 / 高速', width: 3.8, match: ['motorway', 'motorway_link', 'trunk', 'trunk_link'] },
    { key: 'primary', name: '主干道', width: 2.4, match: ['primary', 'primary_link'] },
    { key: 'secondary', name: '次干道', width: 1.7, match: ['secondary', 'secondary_link'] },
    { key: 'tertiary', name: '支路', width: 1.15, match: ['tertiary', 'tertiary_link'] },
    { key: 'street', name: '街巷', width: 0.8, match: ['unclassified', 'residential', 'living_street', 'road', 'track'] },
    { key: 'service', name: '服务道路', width: 0.5, match: ['service'] }
  ];
  var GROUP_INDEX = {};
  GROUPS.forEach(function (g, gi) { g.match.forEach(function (k) { GROUP_INDEX[k] = gi; }); });

  var PALETTES = {
    light: {
      name: '浅色', bg: '#f7f4ec',
      colors: ['#23221e', '#3c3b35', '#5c5a51', '#7d7a6e', '#8f8b7f', '#a5a195']
    },
    dark: {
      name: '深色', bg: '#12141a',
      colors: ['#f4f1e8', '#dcd8cb', '#b8b3a4', '#969183', '#7a766a', '#5c5950']
    },
    transparent: {
      name: '透明', bg: null,
      colors: ['#ffffff', '#e8e8e8', '#cccccc', '#ababab', '#8d8d8d', '#6f6f6f']
    }
  };

  /* ---------- 预置城市（主城区 bbox：南纬, 西经, 北纬, 东经） ---------- */
  var CITIES = [
    { key: 'beijing', name: '北京', bbox: [39.80, 116.30, 40.00, 116.52] },
    { key: 'shanghai', name: '上海', bbox: [31.14, 121.37, 31.32, 121.58] },
    { key: 'guangzhou', name: '广州', bbox: [23.04, 113.17, 23.22, 113.36] },
    { key: 'shenzhen', name: '深圳', bbox: [22.46, 113.96, 22.63, 114.16] },
    { key: 'chengdu', name: '成都', bbox: [30.48, 103.97, 30.67, 104.17] },
    { key: 'chongqing', name: '重庆', bbox: [29.47, 106.45, 29.66, 106.65] },
    { key: 'xian', name: '西安', bbox: [34.25, 108.84, 34.43, 109.04] },
    { key: 'wuhan', name: '武汉', bbox: [30.50, 114.21, 30.69, 114.41] },
    { key: 'hangzhou', name: '杭州', bbox: [30.18, 120.05, 30.37, 120.26] },
    { key: 'nanjing', name: '南京', bbox: [31.97, 118.70, 32.15, 118.90] },
    { key: 'taiyuan', name: '太原', bbox: [37.78, 112.45, 37.96, 112.65] },
    { key: 'shijiazhuang', name: '石家庄', bbox: [37.96, 114.42, 38.13, 114.61] },
    { key: 'luoyang', name: '洛阳', bbox: [34.53, 112.36, 34.71, 112.55] },
    { key: 'changzhi', name: '长治', bbox: [36.11, 113.03, 36.28, 113.21] },
    { key: 'jinzhong', name: '晋中', bbox: [37.60, 112.66, 37.77, 112.85] },
    { key: 'handan', name: '邯郸', bbox: [36.54, 114.45, 36.71, 114.63] },
    { key: 'baoji', name: '宝鸡', bbox: [34.28, 107.14, 34.45, 107.34] }
  ];
  var CITY_MAP = {};
  CITIES.forEach(function (c) { CITY_MAP[c.key] = c; });
  /* 城市列表允许在 cities/index.js 加载后被重建（CITIES / CITY_MAP 均为 var） */

  /* ---------- 全局状态 ---------- */
  var state = {
    // 当前选择的区域（获取数据时用）
    region: null,          // [s, w, n, e]
    regionLabel: '',
    mode: 'preset',        // preset | search | bbox
    cityKey: 'taiyuan',
    searchLabel: '',

    // 当前渲染的数据
    ready: {
      ways: [],            // [{g: groupIndex, c: [lon, lat, lon, lat, ...]}]
      bbox: null,
      label: '',
      source: 'sample',    // sample | offline | vector | osm
      sourceDetail: '',
      slug: 'taiyuan-sample',
      fetchMs: 0,
      tiles: 0,
      zoom: 0,
      version: 0
    },
    palette: 'dark',
    width: 2400,
    pngScale: 2,

    sample: null,
    /* 预览视图：z 为相对“适应全图”的倍数，cx/cy 为地图坐标中心 */
    view: { z: 1, cx: 0, cy: 0 },
    viewKey: '',
    domSig: '',
    projCache: null,
    labelGeomCache: null,
    labelId: 0,
    markers: [],
    markerMode: false,
    labelsRoad: false,
    labelsPlace: false,
    exportScope: 'view',
    cityIndex: null,          // cities/index.js 的内容（含离线数据的城市列表）
    offlineLoading: {},       // slug -> Promise（避免重复注入脚本）
    geom: { key: '', data: null },
    busy: false,
    searchBusy: false,
    abort: null,
    logCount: 0
  };

  /* ---------- 小工具 ---------- */
  function clamp(v, a, b) { return Math.min(b, Math.max(a, v)); }
  function fmtInt(n) { return (Math.round(n) || 0).toLocaleString('zh-CN'); }
  function fmtBytes(n) {
    if (!isFinite(n)) return '—';
    if (n < 1024) return Math.round(n) + ' B';
    if (n < 1024 * 1024) return (n / 1024).toFixed(1) + ' KB';
    return (n / (1024 * 1024)).toFixed(2) + ' MB';
  }
  function sleep(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }
  function escapeHtml(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function round5(v) { return Math.round(v * 1e5) / 1e5; }
  function mercY(lat) { return Math.log(Math.tan(Math.PI / 4 + lat * RAD / 2)); }

  function bboxKm(bbox) {
    var midLat = (bbox[0] + bbox[2]) / 2;
    return {
      w: (bbox[3] - bbox[1]) * 111.32 * Math.cos(midLat * RAD),
      h: (bbox[2] - bbox[0]) * 111.32
    };
  }
  function fmtBboxShort(bbox) {
    return bbox[0].toFixed(4) + '°N–' + bbox[2].toFixed(4) + '°N, ' +
      bbox[1].toFixed(4) + '°E–' + bbox[3].toFixed(4) + '°E';
  }
  function epHost(url) {
    try { return new URL(url).host; } catch (e) { return url; }
  }
  function describeError(err) {
    var msg = err && err.message ? String(err.message) : String(err);
    if (/Failed to fetch|NetworkError|Load failed/i.test(msg)) return '网络请求失败（离线、被墙或 file:// 跨域拦截）';
    if (/HTTP 429/.test(msg)) return '请求过于频繁，公共实例限流（稍后重试）';
    if (/HTTP 5\d\d/.test(msg)) return 'Overpass 公共实例繁忙或维护中';
    if (/HTTP 403/.test(msg)) return '该端点拒绝了跨域请求（换其它端点重试）';
    if (/abort|AbortError/i.test(msg)) return '请求已取消或超时';
    return msg;
  }

  /* ============================================================
     MVT（Mapbox Vector Tile）解码器 —— 零依赖自研实现
     支持两种 schema：
       Shortbread（VersaTiles）：layer "streets"，属性 kind（link 为布尔）
       OpenMapTiles（OpenFreeMap）：layer "transportation"，属性 class/subclass
     ============================================================ */
  var _utf8 = (typeof TextDecoder !== 'undefined') ? new TextDecoder('utf-8') : null;
  function utf8Decode(buf, start, end) {
    if (_utf8) return _utf8.decode(buf.subarray(start, end));
    var out = '';
    for (var i = start; i < end; i++) out += String.fromCharCode(buf[i]);
    return out;
  }
  /* protobuf varint（LEB128，用乘法避免 32 位按位溢出） */
  function readVarint(buf, pos) {
    var result = 0, shift = 0, b;
    do {
      b = buf[pos++];
      result += (b & 0x7f) * Math.pow(2, shift);
      shift += 7;
    } while ((b & 0x80) && pos < buf.length);
    return [result, pos];
  }
  function skipField(buf, pos, wire) {
    if (wire === 0) return readVarint(buf, pos)[1];
    if (wire === 1) return pos + 8;
    if (wire === 2) { var r = readVarint(buf, pos); return r[1] + r[0]; }
    if (wire === 5) return pos + 4;
    return buf.length;
  }
  function zigzag(n) { return (n >>> 1) ^ (-(n & 1)); }
  function readPackedUint32(buf, pos, end) {
    var out = [];
    while (pos < end) { var r = readVarint(buf, pos); out.push(r[0]); pos = r[1]; }
    return out;
  }
  function decodeMvtValue(buf, start, end) {
    var pos = start;
    while (pos < end) {
      var tr = readVarint(buf, pos); pos = tr[1];
      var field = tr[0] >>> 3, wire = tr[0] & 7;
      if (wire === 2) {
        var r = readVarint(buf, pos); pos = r[1];
        if (field === 1) return utf8Decode(buf, pos, pos + r[0]);
        pos += r[0];
      } else if (wire === 5) {
        return new DataView(buf.buffer, buf.byteOffset + pos, 4).getFloat32(0, true);
      } else if (wire === 1) {
        return new DataView(buf.buffer, buf.byteOffset + pos, 8).getFloat64(0, true);
      } else if (wire === 0) {
        var vr = readVarint(buf, pos); pos = vr[1];
        var v = vr[0];
        if (field === 6) v = zigzag(v);
        else if (field === 7) v = !!v;
        return v;
      } else {
        pos = skipField(buf, pos, wire);
      }
    }
    return null;
  }
  function decodeMvtFeature(buf, start, end) {
    var f = { id: 0, tagsRaw: null, type: 0, geomRaw: null };
    var pos = start;
    while (pos < end) {
      var tr = readVarint(buf, pos); pos = tr[1];
      var field = tr[0] >>> 3, wire = tr[0] & 7;
      if (wire === 2) {
        var r = readVarint(buf, pos); pos = r[1];
        var send = pos + r[0];
        if (field === 2) f.tagsRaw = readPackedUint32(buf, pos, send);
        else if (field === 4) f.geomRaw = readPackedUint32(buf, pos, send);
        pos = send;
      } else if (wire === 0) {
        var vr = readVarint(buf, pos); pos = vr[1];
        if (field === 1) f.id = vr[0];
        else if (field === 3) f.type = vr[0];
      } else {
        pos = skipField(buf, pos, wire);
      }
    }
    return f;
  }
  function decodeMvtLayer(buf, start, end) {
    var layer = { name: '', extent: 4096, keys: [], values: [], features: [] };
    var pos = start;
    while (pos < end) {
      var tr = readVarint(buf, pos); pos = tr[1];
      var field = tr[0] >>> 3, wire = tr[0] & 7;
      if (field === 1 && wire === 2) {
        var r = readVarint(buf, pos); pos = r[1];
        layer.name = utf8Decode(buf, pos, pos + r[0]); pos += r[0];
      } else if (field === 2 && wire === 2) {
        var r2 = readVarint(buf, pos); pos = r2[1];
        layer.features.push(decodeMvtFeature(buf, pos, pos + r2[0])); pos += r2[0];
      } else if (field === 3 && wire === 2) {
        var r3 = readVarint(buf, pos); pos = r3[1];
        layer.keys.push(utf8Decode(buf, pos, pos + r3[0])); pos += r3[0];
      } else if (field === 4 && wire === 2) {
        var r4 = readVarint(buf, pos); pos = r4[1];
        layer.values.push(decodeMvtValue(buf, pos, pos + r4[0])); pos += r4[0];
      } else if (field === 5 && wire === 0) {
        var r5 = readVarint(buf, pos); pos = r5[1];
        layer.extent = r5[0] || 4096;
      } else {
        pos = skipField(buf, pos, wire);
      }
    }
    return layer;
  }
  function decodeMvt(buf) {
    var layers = [];
    var pos = 0, len = buf.length;
    while (pos < len) {
      var tr = readVarint(buf, pos); pos = tr[1];
      var field = tr[0] >>> 3, wire = tr[0] & 7;
      if (field === 3 && wire === 2) {
        var r = readVarint(buf, pos); pos = r[1];
        layers.push(decodeMvtLayer(buf, pos, pos + r[0])); pos += r[0];
      } else {
        pos = skipField(buf, pos, wire);
      }
    }
    return layers;
  }
  /* geometry 命令流 -> 若干折线（每条为 [x0,y0,x1,y1,...]，瓦片局部坐标，绝对增量已还原） */
  function decodeMvtGeometry(geomRaw) {
    var parts = [], cur = null, x = 0, y = 0, i = 0, n = geomRaw.length;
    while (i < n) {
      var cmdInt = geomRaw[i++];
      var cmd = cmdInt & 7, count = cmdInt >>> 3;
      if (cmd === 1) {                         // MoveTo
        for (var k = 0; k < count; k++) {
          x += zigzag(geomRaw[i++]); y += zigzag(geomRaw[i++]);
          cur = [x, y]; parts.push(cur);
        }
      } else if (cmd === 2) {                  // LineTo
        if (!cur) { cur = []; parts.push(cur); }
        for (var k2 = 0; k2 < count; k2++) {
          x += zigzag(geomRaw[i++]); y += zigzag(geomRaw[i++]);
          cur.push(x, y);
        }
      } else if (cmd === 7) {                  // ClosePath（道路中心线不需要）
      } else { break; }
    }
    return parts;
  }
  /* 瓦片局部坐标 -> 经纬度 */
  function tilePointToLonLat(z, tx, ty, px, py, extent) {
    var scale = Math.pow(2, z);
    var worldX = (tx + px / extent) / scale;
    var worldY = (ty + py / extent) / scale;
    var lon = worldX * 360 - 180;
    var lat = Math.atan(Math.sinh(Math.PI * (1 - 2 * worldY))) * 180 / Math.PI;
    return [lon, lat];
  }
  var IGNORED_KINDS = {
    track: 1, path: 1, footway: 1, cycleway: 1, steps: 1, pedestrian: 1,
    bridleway: 1, rail: 1, transit: 1, ferry: 1, aerialway: 1, raceway: 1
  };
  /* 两种 schema 的属性映射到现有 6 级；返回 -1 表示忽略 */
  function mapMvtProps(layerName, tags) {
    if (layerName === 'streets') {
      var kind = tags.kind;
      if (kind == null) return -1;
      var k = String(kind);
      if (k.indexOf('_link') >= 0) k = k.replace('_link', '');
      if (IGNORED_KINDS[k]) return -1;
      if (k === 'minor') return 4;
      var gi = GROUP_INDEX[k];
      return gi === undefined ? -1 : gi;
    }
    if (layerName === 'transportation') {
      var cls = tags.class;
      if (cls == null) return -1;
      var c = String(cls);
      if (IGNORED_KINDS[c]) return -1;
      if (c === 'minor') {
        var sub = tags.subclass == null ? '' : String(tags.subclass).replace('_link', '');
        if (IGNORED_KINDS[sub]) return -1;
        if (GROUP_INDEX[sub] !== undefined) return GROUP_INDEX[sub];
        return 4;
      }
      if (c === 'service') return GROUP_SERVICE;
      var gc = GROUP_INDEX[c];
      if (gc !== undefined) return gc;
      var sub2 = tags.subclass == null ? '' : String(tags.subclass).replace('_link', '');
      if (GROUP_INDEX[sub2] !== undefined && !IGNORED_KINDS[sub2]) return GROUP_INDEX[sub2];
      return -1;
    }
    return -1;
  }
  function resolveMvtTags(layer, feature) {
    var tags = {};
    if (!feature.tagsRaw) return tags;
    for (var i = 0; i + 1 < feature.tagsRaw.length; i += 2) {
      var key = layer.keys[feature.tagsRaw[i]];
      var val = layer.values[feature.tagsRaw[i + 1]];
      if (key !== undefined && val !== undefined) tags[key] = val;
    }
    return tags;
  }
  /* 解码一个瓦片里的道路折线；bbox 外的整段丢弃，跨瓦片重复几何去重 */
  var LABEL_LAYERS = {
    street_labels: { role: 'road', kindTag: 'kind' },
    place_labels: { role: 'place', kindTag: 'kind' },
    public_transport: { role: 'poi', kindTag: 'kind' },
    water_lines_labels: { role: 'waterline' },
    water_polygons_labels: { role: 'water' },
    transportation_name: { role: 'road', kindTag: 'class' },
    place: { role: 'place', kindTag: 'class' },
    poi: { role: 'poi', kindTag: 'class' },
    waterway: { role: 'waterline' }
  };
  var POI_TILE_CLASSES = {
    station: 1, bus_station: 1, halt: 1, helipad: 1, airport: 1,
    attraction: 1, museum: 1, monument: 1, park: 1, zoo: 1, university: 1, hospital: 1
  };
  /* 在同一个瓦片里同时解出道路（ways）与名称（labels） */
  function extractTileData(bytes, tile, bbox, seen, includeService, labelAcc, labelSeen) {
    var buf = new Uint8Array(bytes);
    var layers = decodeMvt(buf);
    var out = [];
    for (var li = 0; li < layers.length; li++) {
      var layer = layers[li];
      var spec = LABEL_LAYERS[layer.name];
      if (spec) {
        extractLayerLabels(layer, spec, tile, bbox, labelAcc, labelSeen);
        continue;
      }
      if (layer.name !== 'streets' && layer.name !== 'transportation') continue;
      var extent = layer.extent || 4096;
      for (var fi = 0; fi < layer.features.length; fi++) {
        var f = layer.features[fi];
        if (f.type !== 2 || !f.geomRaw || !f.geomRaw.length) continue;
        var tags = resolveMvtTags(layer, f);
        var gi = mapMvtProps(layer.name, tags);
        if (gi < 0) continue;
        if (!includeService && gi === GROUP_SERVICE) continue;
        var parts = decodeMvtGeometry(f.geomRaw);
        for (var pi = 0; pi < parts.length; pi++) {
          var ring = parts[pi];
          if (ring.length < 4) continue;
          var coords = [];
          var inBox = false;
          for (var k = 0; k + 1 < ring.length; k += 2) {
            var ll = tilePointToLonLat(tile.z, tile.x, tile.y, ring[k], ring[k + 1], extent);
            coords.push(ll[0], ll[1]);
            if (!inBox && ll[0] >= bbox[1] && ll[0] <= bbox[3] && ll[1] >= bbox[0] && ll[1] <= bbox[2]) inBox = true;
          }
          if (!inBox) continue;
          var keyParts = [];
          for (var c2 = 0; c2 < coords.length; c2++) keyParts.push(Math.round(coords[c2] * 1e6));
          var hash = gi + ':' + keyParts.join(',');
          if (seen.has(hash)) continue;
          seen.add(hash);
          out.push({ g: gi, c: coords });
        }
      }
    }
    return out;
  }
  function extractLayerLabels(layer, spec, tile, bbox, labelAcc, labelSeen) {
    if (!labelAcc) return;
    var extent = layer.extent || 4096;
    var pad = 0.002;
    for (var fi = 0; fi < layer.features.length; fi++) {
      var f = layer.features[fi];
      if (!f.geomRaw || !f.geomRaw.length) continue;
      var tags = resolveMvtTags(layer, f);
      var name = tags.name;
      if (typeof name !== 'string') continue;
      name = name.trim();
      if (!name) continue;
      var kind = spec.kindTag ? tags[spec.kindTag] : (tags.kind || tags.class);
      var role = spec.role;
      var rank = -1, tier = 1;
      if (role === 'road') {
        rank = roadKindRank(kind);
        if (rank < 0) continue;
      } else if (role === 'place') {
        if (!PLACE_KINDS[String(kind || '')]) continue;
        tier = placeTier(kind);
      } else if (role === 'poi') {
        var kstr = String(kind || '');
        if (layer.name === 'poi') {
          if (!POI_TILE_CLASSES[kstr]) continue;
        } else if (layer.name === 'public_transport') {
          if (!/station|halt|stop|platform|airport/i.test(kstr)) continue;
        }
        tier = poiTier(kstr);
      } else if (role === 'water') {
        tier = 0;
      }
      var parts = decodeMvtGeometry(f.geomRaw);
      if (!parts.length) continue;
      if (role === 'road' || role === 'waterline') {
        for (var pi = 0; pi < parts.length; pi++) {
          var ring = parts[pi];
          if (ring.length < 4) continue;
          var pts = [];
          var inBox = false;
          for (var k = 0; k + 1 < ring.length; k += 2) {
            var ll = tilePointToLonLat(tile.z, tile.x, tile.y, ring[k], ring[k + 1], extent);
            pts.push([ll[0], ll[1]]);
            if (!inBox && ll[0] >= bbox[1] - pad && ll[0] <= bbox[3] + pad && ll[1] >= bbox[0] - pad && ll[1] <= bbox[2] + pad) inBox = true;
          }
          if (!inBox || pts.length < 2) continue;
          var key = role + '|' + name + '|' + pts[0][0].toFixed(5) + ',' + pts[0][1].toFixed(5);
          if (labelSeen.has(key)) continue;
          labelSeen.add(key);
          var bucket = role === 'road' ? labelAcc.roads : labelAcc.waters;
          if (bucket.length > 6000) continue;
          bucket.push(role === 'road'
            ? { name: name, rank: rank, pts: pts }
            : { name: name, tier: 0, pts: pts });
        }
      } else {
        var ring0 = parts[0];
        if (!ring0 || ring0.length < 2) continue;
        var ll0 = tilePointToLonLat(tile.z, tile.x, tile.y, ring0[0], ring0[1], extent);
        if (ll0[0] < bbox[1] - pad || ll0[0] > bbox[3] + pad || ll0[1] < bbox[0] - pad || ll0[1] > bbox[2] + pad) continue;
        var key2 = role + '|' + name + '|' + ll0[0].toFixed(5) + ',' + ll0[1].toFixed(5);
        if (labelSeen.has(key2)) continue;
        labelSeen.add(key2);
        var bucket2 = role === 'place' ? labelAcc.places : (role === 'poi' ? labelAcc.pois : labelAcc.waters);
        if (bucket2.length > 3000) continue;
        bucket2.push({ name: name, tier: tier, lon: ll0[0], lat: ll0[1] });
      }
    }
  }

  /* ---------- 矢量瓦片：zoom / 瓦片范围 / 抓取 ---------- */
  function lon2tileX(lon, z) { return Math.floor((lon + 180) / 360 * Math.pow(2, z)); }
  function lat2tileY(lat, z) {
    var r = lat * RAD;
    return Math.floor((1 - Math.log(Math.tan(r) + 1 / Math.cos(r)) / Math.PI) / 2 * Math.pow(2, z));
  }
  function tileRangeForBbox(bbox, z) {
    var max = Math.pow(2, z) - 1;
    var x0 = clamp(lon2tileX(bbox[1], z), 0, max);
    var x1 = clamp(lon2tileX(bbox[3], z), 0, max);
    var y0 = clamp(lat2tileY(bbox[2], z), 0, max);
    var y1 = clamp(lat2tileY(bbox[0], z), 0, max);
    if (x1 < x0) { var t = x0; x0 = x1; x1 = t; }
    if (y1 < y0) { var t2 = y0; y0 = y1; y1 = t2; }
    var tiles = [];
    for (var y = y0; y <= y1; y++) {
      for (var x = x0; x <= x1; x++) tiles.push({ z: z, x: x, y: y });
    }
    return { tiles: tiles, nx: x1 - x0 + 1, ny: y1 - y0 + 1, count: tiles.length, x0: x0, x1: x1, y0: y0, y1: y1 };
  }
  /* 按 bbox 尺寸选 zoom（跨度 ≤3km→z15、≤8→z14、≤20→z13、≤50→z12…，上限 z14，块数受 MAX_VTILES 约束） */
  function chooseVectorZoom(bbox) {
    var km = bboxKm(bbox);
    var span = Math.max(km.w, km.h);
    var z = span <= 3 ? 15 : span <= 8 ? 14 : span <= 20 ? 13 : span <= 50 ? 12 : span <= 100 ? 11 : 10;
    z = Math.min(z, 14);
    var range = tileRangeForBbox(bbox, z);
    while (range.count > MAX_VTILES && z > 7) {
      z--;
      range = tileRangeForBbox(bbox, z);
    }
    return { z: z, range: range, capped: range.count > MAX_VTILES };
  }
  var _ofmTemplatePromise = null;
  function getOpenFreeMapTemplate() {
    if (_ofmTemplatePromise) return _ofmTemplatePromise;
    _ofmTemplatePromise = fetch(OPENFREEMAP_TILEJSON, { mode: 'cors', credentials: 'omit' })
      .then(function (r) {
        if (!r.ok) throw new Error('TileJSON HTTP ' + r.status);
        return r.json();
      })
      .then(function (j) {
        var tiles = (j && j.tiles) || [];
        for (var i = 0; i < tiles.length; i++) {
          if (/\{z\}/.test(tiles[i]) && /\{x\}/.test(tiles[i]) && /\{y\}/.test(tiles[i])) return tiles[i];
        }
        throw new Error('TileJSON 中没有 tiles 模板');
      })
      .catch(function (e) { _ofmTemplatePromise = null; throw e; });
    return _ofmTemplatePromise;
  }
  async function fetchTileBytes(url, timeoutMs) {
    var ctrl = new AbortController();
    if (state.abort) state.abort.controllers.push(ctrl);
    var timer = setTimeout(function () { try { ctrl.abort(); } catch (e) { } }, timeoutMs || TILE_TIMEOUT);
    try {
      var res = await fetch(url, { mode: 'cors', credentials: 'omit', signal: ctrl.signal });
      if (res.status === 404 || res.status === 204) return null;
      if (!res.ok) throw new Error('HTTP ' + res.status);
      return await res.arrayBuffer();
    } finally {
      clearTimeout(timer);
      if (state.abort) {
        var ix = state.abort.controllers.indexOf(ctrl);
        if (ix >= 0) state.abort.controllers.splice(ix, 1);
      }
    }
  }
  /* 单块瓦片：先 VersaTiles（Shortbread），失败再 OpenFreeMap（OpenMapTiles） */
  async function fetchVectorTile(tile) {
    var errors = [];
    try {
      var url = VERSATILES_URL.replace('{z}', tile.z).replace('{x}', tile.x).replace('{y}', tile.y);
      var bytes = await fetchTileBytes(url);
      if (!bytes || !bytes.byteLength) return { bytes: null, source: 'versatiles' };
      return { bytes: bytes, source: 'versatiles' };
    } catch (e) {
      if (state.abort && state.abort.aborted) throw makeAbortError();
      errors.push('VersaTiles ' + describeError(e));
    }
    try {
      var tpl = await getOpenFreeMapTemplate();
      var url2 = tpl.replace('{z}', tile.z).replace('{x}', tile.x).replace('{y}', tile.y);
      var bytes2 = await fetchTileBytes(url2);
      if (!bytes2 || !bytes2.byteLength) return { bytes: null, source: 'openfreemap' };
      return { bytes: bytes2, source: 'openfreemap' };
    } catch (e2) {
      if (state.abort && state.abort.aborted) throw makeAbortError();
      errors.push('OpenFreeMap ' + describeError(e2));
    }
    throw new Error(errors.join('；') || '瓦片获取失败');
  }
  function describeVectorSources(sources) {
    var names = [];
    if (sources.versatiles) names.push('VersaTiles');
    if (sources.openfreemap) names.push('OpenFreeMap');
    return names.length ? names.join(' + ') : '矢量瓦片';
  }
  function updateVectorProgress(done, total, wayCount, zoom) {
    setProgress(total ? done / total : 0);
    var txt = '矢量瓦片抓取中… <b>[progress ' + done + ' / ' + total + ']</b> · z' + zoom + ' · 已取得 ' + fmtInt(wayCount) + ' 条道路';
    setStatusHtml(txt);
    var lt = $('loadingText');
    if (lt) lt.textContent = '正在抓取矢量瓦片… [progress ' + done + '/' + total + ']';
  }
  function fetchAllVectorTiles(plan, bbox, includeService) {
    return new Promise(function (resolve) {
      var tiles = plan.range.tiles;
      var ways = [];
      var seen = new Set();
      var failed = [];
      var labels = { roads: [], places: [], pois: [], waters: [] };
      var labelSeen = new Set();
      var sources = { versatiles: 0, openfreemap: 0 };
      var next = 0, active = 0, done = 0, stopped = false;
      function finish() {
        if (stopped) return;
        stopped = true;
        resolve({
          ways: ways, failed: failed, sources: sources, labels: labels,
          aborted: !!(state.abort && state.abort.aborted),
          total: tiles.length
        });
      }
      function launch() {
        if (stopped) return;
        while (active < TILE_CONCURRENCY && next < tiles.length) runTile(tiles[next++]);
        if (active === 0 && next >= tiles.length) finish();
      }
      function runTile(tile) {
        active++;
        (async function () {
          var got = await fetchVectorTile(tile);
          var added = 0;
          if (got && got.bytes) {
            sources[got.source]++;
            var newWays = extractTileData(got.bytes, tile, bbox, seen, includeService, labels, labelSeen);
            for (var i = 0; i < newWays.length; i++) ways.push(newWays[i]);
            added = newWays.length;
          }
          done++;
          updateVectorProgress(done, tiles.length, ways.length, plan.z);
          logLine('[progress ' + done + '/' + tiles.length + '] tile ' + plan.z + '/' + tile.x + '/' + tile.y +
            ' · ' + (got && got.source ? VECTOR_SOURCE_NAMES[got.source] : '空瓦片') + ' · ' + added + ' 条', 'ok');
        })().then(function () {
          active--; launch();
        }, function (err) {
          active--;
          if (err && err.userAbort) { finish(); return; }
          failed.push({ tile: tile, message: describeError(err) });
          done++;
          updateVectorProgress(done, tiles.length, ways.length, plan.z);
          logLine('[progress ' + done + '/' + tiles.length + '] tile ' + plan.z + '/' + tile.x + '/' + tile.y + ' ✗ ' + describeError(err), 'warn');
          launch();
        });
      }
      launch();
    });
  }

  /* ---------- 预置城市离线数据（cities/index.js + cities/<slug>.js） ---------- */
  function loadScriptAsync(src, timeoutMs) {
    return new Promise(function (resolve, reject) {
      var s = document.createElement('script');
      s.src = src;
      s.async = true;
      var done = false;
      var timer = setTimeout(function () {
        if (done) return;
        done = true;
        if (s.parentNode) s.parentNode.removeChild(s);
        reject(new Error('加载超时'));
      }, timeoutMs || 8000);
      s.onload = function () {
        if (done) return;
        done = true; clearTimeout(timer); resolve();
      };
      s.onerror = function () {
        if (done) return;
        done = true; clearTimeout(timer);
        if (s.parentNode) s.parentNode.removeChild(s);
        reject(new Error('脚本加载失败'));
      };
      document.head.appendChild(s);
    });
  }
  var _cityIndexPromise = null;
  function ensureCityIndex() {
    if (state.cityIndex) return Promise.resolve(state.cityIndex);
    if (_cityIndexPromise) return _cityIndexPromise;
    _cityIndexPromise = loadScriptAsync(CITY_INDEX_URL, 6000).then(function () {
      var idx = window.XZ_CITY_INDEX;
      if (!Array.isArray(idx) || !idx.length) throw new Error('cities/index.js 格式不正确');
      state.cityIndex = idx;
      return idx;
    }).catch(function (e) {
      _cityIndexPromise = null;
      throw e;
    });
    return _cityIndexPromise;
  }
  function cityIndexEntry(slug) {
    if (!state.cityIndex) return null;
    for (var i = 0; i < state.cityIndex.length; i++) {
      if (state.cityIndex[i] && state.cityIndex[i].slug === slug) return state.cityIndex[i];
    }
    return null;
  }
  function cityIndexHas(slug) { return !!cityIndexEntry(slug); }
  function loadCityOffline(slug) {
    var cached = window.XZ_CITIES && window.XZ_CITIES[slug];
    if (cached) return Promise.resolve(cached);
    if (state.offlineLoading[slug]) return state.offlineLoading[slug];
    var p = loadScriptAsync(CITY_DATA_DIR + slug + '.js', 12000).then(function () {
      var data = window.XZ_CITIES && window.XZ_CITIES[slug];
      if (!data || !data.roads || !data.roads.length) throw new Error('城市数据为空');
      delete state.offlineLoading[slug];
      return data;
    }).catch(function (e) {
      delete state.offlineLoading[slug];
      throw e;
    });
    state.offlineLoading[slug] = p;
    return p;
  }
  /* 离线数据反量化：lon = w + x/q, lat = s + y/q（q=100000） */
  function offlineCityWays(data) {
    var q = data.q || 100000;
    var w = data.bbox[1], s = data.bbox[0];
    var ways = [];
    var roads = data.roads || [];
    for (var i = 0; i < roads.length; i++) {
      var road = roads[i];
      if (!road || road.length < 2) continue;
      var g = road[0], arr = road[1];
      if (g == null || !arr || arr.length < 4) continue;
      var coords = new Array(arr.length);
      for (var j = 0; j + 1 < arr.length; j += 2) {
        coords[j] = w + arr[j] / q;
        coords[j + 1] = s + arr[j + 1] / q;
      }
      ways.push({ g: g, c: coords });
    }
    return ways;
  }
  async function tryLoadOfflineCity(key) {
    var city = CITY_MAP[key] || { name: key, bbox: null };
    var entry = cityIndexEntry(key);
    if (!entry) return false;
    clearLog();
    setStatusHtml('正在加载「' + escapeHtml(city.name) + '」内置离线数据…');
    var t0 = performance.now();
    try {
      var data = await loadCityOffline(key);
      var ways = offlineCityWays(data);
      if (!ways.length) throw new Error('离线数据中没有道路');
      var bbox = (data.bbox && data.bbox.length === 4) ? data.bbox.slice() : (entry.bbox ? entry.bbox.slice() : city.bbox.slice());
      state.region = bbox.slice();
      state.regionLabel = data.name || city.name;
      syncBboxInputs();
      updateRegionInfo();
      state.ready = {
        ways: ways,
        bbox: bbox,
        label: data.name || city.name,
        source: 'offline',
        sourceDetail: '内置数据 · 离线可用',
        slug: key,
        fetchMs: performance.now() - t0,
        tiles: 0,
        zoom: entry.zoom || 0,
        labels: parseOfflineLabels(data),
        version: state.ready.version + 1
      };
      state.geom = { key: '', data: null };
      state.projCache = null;
      state.labelGeomCache = null;
      renderPreview();
      setProgress(1);
      setStatusHtml('已加载内置城市数据：<b>' + fmtInt(ways.length) + '</b> 条道路 · ' +
        escapeHtml(state.ready.label) + ' · 离线可用（' + (entry.bytes ? fmtBytes(entry.bytes) : '随站点分发') + '）');
      logLine('内置城市数据：' + state.ready.label + ' · ' + fmtInt(ways.length) + ' 条道路（离线，秒开）', 'ok');
      return true;
    } catch (e) {
      logLine('内置城市数据加载失败：' + describeError(e) + '（可改用在线抓取）', 'warn');
      return false;
    }
  }
  /* 数据源徽标（①卡片标题处） */
  function drawSourceBadge(kind) {
    var el = $('regionSourceBadge');
    if (!el) return;
    var map = {
      offline: { text: '内置数据', cls: 'src-offline' },
      vector: { text: '矢量瓦片', cls: 'src-vector' },
      osm: { text: 'Overpass 兜底', cls: 'src-osm' },
      sample: { text: '内置示例', cls: 'src-offline' },
      none: { text: '—', cls: '' }
    };
    var m = map[kind] || map.none;
    el.textContent = m.text;
    el.className = 'rm-src-badge ' + m.cls;
  }

  /* ---------- 主题 ---------- */

  /* ---------- 主题 ---------- */
  (function themeInit() {
    var btn = $('themeToggle');
    if (!btn) return;
    btn.addEventListener('click', function () {
      var cur = document.documentElement.getAttribute('data-theme');
      var next = cur === 'dark' ? 'light' : 'dark';
      document.documentElement.setAttribute('data-theme', next);
      try { localStorage.setItem('xz-theme', next); } catch (e) { }
    });
  })();

  /* ---------- 提示条 ---------- */
  var toastTimer = 0;
  function toast(msg, ms) {
    var el = $('toast');
    if (!el) return;
    el.textContent = msg;
    el.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { el.classList.remove('show'); }, ms || 3200);
  }

  /* ---------- 日志 ---------- */
  function logLine(text, cls) {
    var el = $('log');
    if (!el) return;
    var line = document.createElement('div');
    if (cls) line.className = cls;
    line.textContent = text;
    el.appendChild(line);
    state.logCount++;
    while (el.childNodes.length > 80) el.removeChild(el.firstChild);
    el.scrollTop = el.scrollHeight;
  }
  function clearLog() {
    var el = $('log');
    if (el) el.innerHTML = '';
    state.logCount = 0;
  }
  function setStatusHtml(html) {
    var el = $('status');
    if (el) el.innerHTML = html;
  }
  function setProgress(frac) {
    var bar = $('progBar');
    if (bar) bar.style.width = clamp(frac * 100, 0, 100).toFixed(1) + '%';
  }

  /* ---------- 投影与 SVG 构建 ---------- */
  function makeProjection(bbox, width) {
    var s = bbox[0], w = bbox[1], n = bbox[2], e = bbox[3];
    var xmin = w * RAD, xmax = e * RAD;
    var ymin = mercY(s), ymax = mercY(n);
    var spanX = Math.max(1e-12, xmax - xmin);
    var spanY = Math.max(1e-12, ymax - ymin);
    var height = clamp(Math.round(width * spanY / spanX), 80, 32000);
    return {
      width: width,
      height: height,
      project: function (lon, lat) {
        return [
          (lon * RAD - xmin) / spanX * width,
          (ymax - mercY(lat)) / spanY * height
        ];
      }
    };
  }

  /* 把 ways 投影成每组的 path d 字符串（与 Python 原版一样，坐标保留 1 位小数） */
  function computeGeom(ways, bbox, width) {
    var proj = makeProjection(bbox, width);
    var buckets = [[], [], [], [], [], []];
    for (var i = 0; i < ways.length; i++) {
      var w = ways[i];
      if (!w || w.g == null || !w.c || w.c.length < 4) continue;
      buckets[w.g].push(w.c);
    }
    var groups = [];
    var counts = [0, 0, 0, 0, 0, 0];
    var totalPts = 0;
    for (var gi = 0; gi < buckets.length; gi++) {
      var lines = buckets[gi];
      if (!lines.length) continue;
      var dParts = [];
      for (var li = 0; li < lines.length; li++) {
        var c = lines[li];
        var x = proj.project(c[0], c[1]);
        var d = 'M' + x[0].toFixed(1) + ' ' + x[1].toFixed(1);
        for (var pi = 2; pi < c.length; pi += 2) {
          var p = proj.project(c[pi], c[pi + 1]);
          d += 'L' + p[0].toFixed(1) + ' ' + p[1].toFixed(1);
        }
        dParts.push(d);
        counts[gi]++;
        totalPts += (c.length >> 1);
      }
      groups.push({ gi: gi, d: dParts.join(''), count: counts[gi] });
    }
    // 粗线先画、细线后画（与 Python 原版 sorted by -ROAD_WIDTH 一致）
    groups.sort(function (a, b) { return GROUPS[b.gi].width - GROUPS[a.gi].width; });
    return {
      width: proj.width,
      height: proj.height,
      groups: groups,
      counts: counts,
      totalWays: ways.length,
      totalPts: totalPts
    };
  }

  function svgFromGeom(geom, paletteKey, labelOverride) {
    var pal = PALETTES[paletteKey] || PALETTES.dark;
    var scale = geom.width / 2400;
    var body = [];
    for (var i = 0; i < geom.groups.length; i++) {
      var gr = geom.groups[i];
      var g = GROUPS[gr.gi];
      body.push('<path d="' + gr.d + '" fill="none" stroke="' + pal.colors[gr.gi] +
        '" stroke-width="' + (g.width * scale).toFixed(2) +
        '" stroke-linecap="round" stroke-linejoin="round"/>');
    }
    var bg = pal.bg ? '<rect width="' + geom.width + '" height="' + geom.height + '" fill="' + pal.bg + '"/>' : '';
    var label = labelOverride || state.ready.label || '自定义范围';
    var svg = '<?xml version="1.0" encoding="UTF-8"?>\n' +
      '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ' + geom.width + ' ' + geom.height +
      '" width="' + geom.width + '" height="' + geom.height + '" shape-rendering="geometricPrecision">\n' +
      '<title>' + escapeHtml(label) + ' · 道路底图（无文字标注，' + pal.name + '）</title>\n' +
      '<desc>Data (c) OpenStreetMap contributors, ODbL 1.0. https://www.openstreetmap.org/copyright</desc>\n' +
      (bg ? bg + '\n' : '') +
      body.join('\n') + '\n' +
      '</svg>\n';
    return svg;
  }

  function ensureGeom() {
    var key = state.ready.version + '|' + state.width;
    if (state.geom.key === key && state.geom.data) return state.geom.data;
    var data = computeGeom(state.ready.ways, state.ready.bbox, state.width);
    state.geom = { key: key, data: data };
    return data;
  }

  /* ============================================================
     视图（缩放 / 平移）
     ============================================================ */
  function paletteInk() {
    if (state.palette === 'light') return { ink: '#23221e', halo: '#f7f4ec' };
    if (state.palette === 'dark') { return { ink: '#f4f1e8', halo: '#12141a' }; }
    return { ink: '#1c1c1a', halo: '#ffffff' };
  }
  function stageSize() {
    var v = $('mapView');
    return { w: v ? Math.max(1, v.clientWidth) : 1, h: v ? Math.max(1, v.clientHeight) : 1 };
  }
  function fitMetrics(geom) {
    var st = stageSize();
    var aspect = st.w / st.h;
    var mapW = geom.width, mapH = geom.height;
    var fitW, fitH;
    if (mapW / mapH >= aspect) { fitW = mapW; fitH = mapW / aspect; }
    else { fitH = mapH; fitW = mapH * aspect; }
    return { fitW: fitW, fitH: fitH, aspect: aspect, mapW: mapW, mapH: mapH };
  }
  function viewRect() {
    if (!state.ready.ways.length || !state.ready.bbox) return null;
    var geom = ensureGeom();
    var f = fitMetrics(geom);
    var z = clamp(state.view.z || 1, ZOOM_MIN, ZOOM_MAX);
    var vw = f.fitW / z, vh = f.fitH / z;
    var cx = state.view.cx, cy = state.view.cy;
    if (!isFinite(cx)) cx = geom.width / 2;
    if (!isFinite(cy)) cy = geom.height / 2;
    if (vw >= geom.width) cx = geom.width / 2;
    else cx = clamp(cx, vw / 2, geom.width - vw / 2);
    if (vh >= geom.height) cy = geom.height / 2;
    else cy = clamp(cy, vh / 2, geom.height - vh / 2);
    state.view.cx = cx;
    state.view.cy = cy;
    var st = stageSize();
    return { x: cx - vw / 2, y: cy - vh / 2, w: vw, h: vh, z: z, dispW: st.w, dispH: st.h, mapW: geom.width, mapH: geom.height };
  }
  function resetView() {
    var geom = ensureGeom();
    state.view = { z: 1, cx: geom.width / 2, cy: geom.height / 2 };
  }
  function zoomAt(factor, sx, sy) {
    var r = viewRect();
    if (!r) return;
    var geom = ensureGeom();
    var f = fitMetrics(geom);
    var mapX = r.x + sx / r.dispW * r.w;
    var mapY = r.y + sy / r.dispH * r.h;
    var nz = clamp(state.view.z * factor, ZOOM_MIN, ZOOM_MAX);
    if (Math.abs(nz - state.view.z) < 1e-6) return;
    var nvw = f.fitW / nz, nvh = f.fitH / nz;
    state.view.z = nz;
    state.view.cx = mapX - (sx / r.dispW - 0.5) * nvw;
    state.view.cy = mapY - (sy / r.dispH - 0.5) * nvh;
    applyView(false);
  }
  function zoomCenter(factor) {
    var st = stageSize();
    zoomAt(factor, st.w / 2, st.h / 2);
  }
  function panByPx(dx, dy) {
    var r = viewRect();
    if (!r) return;
    state.view.cx -= dx / r.dispW * r.w;
    state.view.cy -= dy / r.dispH * r.h;
    applyView(false);
  }
  function applyView(labelsNow) {
    var svg = $('mapSvg');
    if (!svg) return;
    var r = viewRect();
    if (!r) return;
    svg.setAttribute('viewBox', r.x.toFixed(2) + ' ' + r.y.toFixed(2) + ' ' + r.w.toFixed(2) + ' ' + r.h.toFixed(2));
    var bg = $('bgRect');
    if (bg) {
      bg.setAttribute('x', r.x.toFixed(2));
      bg.setAttribute('y', r.y.toFixed(2));
      bg.setAttribute('width', r.w.toFixed(2));
      bg.setAttribute('height', r.h.toFixed(2));
    }
    var ml = $('markersLayer');
    if (ml) ml.innerHTML = markersSvg(r);
    var zv = $('zoomLevel');
    if (zv) zv.textContent = r.z.toFixed(1) + '×';
    var zin = $('btnZoomIn'), zout = $('btnZoomOut');
    if (zin) zin.disabled = r.z >= ZOOM_MAX - 1e-6;
    if (zout) zout.disabled = r.z <= ZOOM_MIN + 1e-6;
    if (labelsNow) updateLabelsNow(r); else scheduleLabels();
  }
  var _labelTimer = 0;
  function scheduleLabels() {
    clearTimeout(_labelTimer);
    _labelTimer = setTimeout(function () { updateLabelsNow(viewRect()); }, 130);
  }
  function updateLabelsNow(r) {
    var el = $('labelsLayer');
    if (!el) return;
    el.innerHTML = buildLabelsSvg(r);
    if (state.ready.ways.length && r) {
      try { updatePreviewMeta(ensureGeom(), bboxKm(state.ready.bbox)); } catch (e) { }
    }
  }

  /* ============================================================
     投影 / 当前数据坐标
     ============================================================ */
  function mapProjectorCached() {
    var geom = ensureGeom();
    var key = state.ready.version + '|' + state.width;
    if (state.projCache && state.projCache.key === key) return state.projCache;
    var bbox = state.ready.bbox;
    var xmin = bbox[1] * RAD, xmax = bbox[3] * RAD;
    var ymin = mercY(bbox[0]), ymax = mercY(bbox[2]);
    var spanX = Math.max(1e-12, xmax - xmin);
    var spanY = Math.max(1e-12, ymax - ymin);
    var W = geom.width, H = geom.height;
    var project = function (lon, lat) {
      return [(lon * RAD - xmin) / spanX * W, (ymax - mercY(lat)) / spanY * H];
    };
    var unproject = function (x, y) {
      var lon = (x / W * spanX + xmin) / RAD;
      var my = ymax - (y / H) * spanY;
      var lat = Math.atan(Math.sinh(my)) / RAD;
      return [lon, lat];
    };
    state.projCache = { key: key, project: project, unproject: unproject };
    return state.projCache;
  }

  /* ============================================================
     标记点
     ============================================================ */
  function markerAreaKey() {
    var r = state.ready;
    if (!r || !r.bbox) return '';
    if (r.source === 'offline') return 'city:' + (r.slug || 'unknown');
    return 'bbox:' + r.bbox.map(function (v) { return v.toFixed(4); }).join(',');
  }
  function loadMarkersForArea() {
    var key = markerAreaKey();
    state.markers = [];
    if (key) {
      try {
        var raw = localStorage.getItem(STORE_MARKERS + key);
        if (raw) {
          var arr = JSON.parse(raw);
          if (Array.isArray(arr)) {
            state.markers = arr.filter(function (m) {
              return m && isFinite(m.lon) && isFinite(m.lat);
            }).map(function (m) { return { lon: +m.lon, lat: +m.lat }; });
          }
        }
      } catch (e) { state.markers = []; }
    }
    updateMarkerPanel();
  }
  function saveMarkers() {
    var key = markerAreaKey();
    if (!key) return;
    try { localStorage.setItem(STORE_MARKERS + key, JSON.stringify(state.markers)); } catch (e) { }
  }
  function markerScreenPos(m, r) {
    var p = mapProjectorCached().project(m.lon, m.lat);
    return { x: (p[0] - r.x) / r.w * r.dispW, y: (p[1] - r.y) / r.h * r.dispH, map: p };
  }
  function markersSvg(r) {
    if (!state.markers.length) return '';
    var ink = paletteInk().ink;
    var unit = r.w / (r.dispW || LABEL_REF);
    var rr = 6 * unit, tick0 = 7.6 * unit, tick1 = 9.6 * unit, sw = 1.15 * unit, dot = 1.35 * unit;
    var parts = ['<g class="markers">'];
    for (var i = 0; i < state.markers.length; i++) {
      var p = mapProjectorCached().project(state.markers[i].lon, state.markers[i].lat);
      var x = p[0], y = p[1];
      parts.push('<g class="marker" data-idx="' + i + '"><title>标记 ' + (i + 1) + '（点击删除）</title>' +
        '<circle cx="' + x.toFixed(2) + '" cy="' + y.toFixed(2) + '" r="' + rr.toFixed(2) + '" fill="none" stroke="' + ink + '" stroke-width="' + sw.toFixed(2) + '"/>' +
        '<circle cx="' + x.toFixed(2) + '" cy="' + y.toFixed(2) + '" r="' + dot.toFixed(2) + '" fill="' + ink + '"/>' +
        '<path d="M' + (x - tick1).toFixed(2) + ' ' + y.toFixed(2) + 'H' + (x - tick0).toFixed(2) +
        'M' + (x + tick0).toFixed(2) + ' ' + y.toFixed(2) + 'H' + (x + tick1).toFixed(2) +
        'M' + x.toFixed(2) + ' ' + (y - tick1).toFixed(2) + 'V' + (y - tick0).toFixed(2) +
        'M' + x.toFixed(2) + ' ' + (y + tick0).toFixed(2) + 'V' + (y + tick1).toFixed(2) +
        '" fill="none" stroke="' + ink + '" stroke-width="' + (1.05 * unit).toFixed(2) + '" stroke-linecap="square"/>' +
        '</g>');
    }
    parts.push('</g>');
    return parts.join('');
  }
  function markersHit(sx, sy, r) {
    var best = -1, bestD = 12 * 12;
    for (var i = 0; i < state.markers.length; i++) {
      var pos = markerScreenPos(state.markers[i], r);
      var dx = pos.x - sx, dy = pos.y - sy, d = dx * dx + dy * dy;
      if (d <= bestD) { bestD = d; best = i; }
    }
    return best;
  }
  function addMarkerAtMap(x, y) {
    var geom = ensureGeom();
    if (x < 0 || y < 0 || x > geom.width || y > geom.height) {
      toast('点在地图范围外，未添加标记');
      return false;
    }
    var ll = mapProjectorCached().unproject(x, y);
    state.markers.push({ lon: ll[0], lat: ll[1] });
    saveMarkers();
    updateMarkerPanel();
    applyView(false);
    return true;
  }
  function deleteMarker(idx) {
    if (idx < 0 || idx >= state.markers.length) return;
    state.markers.splice(idx, 1);
    saveMarkers();
    updateMarkerPanel();
    applyView(false);
  }
  function clearMarkers() {
    if (!state.markers.length) return;
    state.markers = [];
    saveMarkers();
    updateMarkerPanel();
    applyView(false);
    toast('已清空全部标记点');
  }
  function updateMarkerPanel() {
    var list = $('markerList');
    var cnt = $('markerCount');
    if (cnt) cnt.textContent = state.markers.length + ' 个';
    var clearBtn = $('btnClearMarkers');
    if (clearBtn) clearBtn.disabled = !state.markers.length;
    if (!list) return;
    if (!state.markers.length) {
      list.innerHTML = '<div class="rm-marker-empty">暂无标记点。切到「标记」模式后点击地图添加。</div>';
      return;
    }
    var html = [];
    for (var i = 0; i < state.markers.length; i++) {
      var m = state.markers[i];
      var ll = m.lat.toFixed(6) + ', ' + m.lon.toFixed(6);
      html.push('<div class="rm-marker-row" data-idx="' + i + '">' +
        '<span class="idx">' + (i + 1) + '</span>' +
        '<span class="ll" title="' + ll + '">' + ll + '</span>' +
        '<button type="button" data-act="copy" data-idx="' + i + '">复制</button>' +
        '<button type="button" data-act="del" data-idx="' + i + '">删除</button>' +
        '</div>');
    }
    list.innerHTML = html.join('');
    if (state.ready.ways.length) {
      try { updatePreviewMeta(ensureGeom(), bboxKm(state.ready.bbox)); } catch (e) { }
    }
  }
  function copyText(text, okMsg) {
    function fallback() {
      var ta = document.createElement('textarea');
      ta.value = text;
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      var ok = false;
      try { ok = document.execCommand('copy'); } catch (e) { ok = false; }
      document.body.removeChild(ta);
      toast(ok ? (okMsg || '已复制') : '复制失败（浏览器限制了剪贴板）');
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function () { toast(okMsg || '已复制'); }, fallback);
    } else fallback();
  }
  function setMarkerMode(on) {
    state.markerMode = !!on;
    var p = $('modePointer'), m = $('modeMarker'), v = $('mapView');
    if (p) p.classList.toggle('active', !state.markerMode);
    if (m) m.classList.toggle('active', state.markerMode);
    if (v) {
      v.classList.toggle('mode-marker', state.markerMode);
      v.classList.toggle('mode-pointer', !state.markerMode);
      if (!state.markerMode) v.classList.remove('hover-marker');
    }
    savePrefs();
  }

  /* ============================================================
     名称（道路名称 / 地标名称）
     ============================================================ */
  function labelsAvailable() {
    var L = state.ready.labels;
    return {
      roads: !!(L && L.roads && L.roads.length),
      places: !!(L && ((L.places && L.places.length) || (L.pois && L.pois.length) || (L.waters && L.waters.length)))
    };
  }
  function normRoadKind(k) {
    if (k == null) return '';
    var s = String(k);
    var i = s.indexOf('_link');
    if (i >= 0) s = s.slice(0, i);
    return s;
  }
  function roadKindRank(k) {
    var s = normRoadKind(k);
    if (!s || IGNORED_KINDS[s]) return -1;
    if (s === 'minor') return 4;
    return GROUP_INDEX[s] === undefined ? -1 : GROUP_INDEX[s];
  }
  function placeTier(k) {
    var s = String(k || '');
    if (s === 'city' || s === 'town') return 0;
    return 1;
  }
  function poiTier(k) {
    var s = String(k || '');
    return /^(station|bus_station|halt|helipad|airport)$/.test(s) ? 0 : 1;
  }
  function waterTier(k) { return 0; }
  function parseOfflineLabels(data) {
    if (!data || !data.labels) return null;
    var q = data.q || 25000, w = data.bbox[1], s = data.bbox[0];
    var L = data.labels;
    var out = { roads: [], places: [], pois: [], waters: [] };
    var i;
    var roads = L.roads || [];
    for (i = 0; i < roads.length; i++) {
      var r = roads[i];
      if (!r || !r.n || !r.l || r.l.length < 4) continue;
      var rank = roadKindRank(r.k);
      if (rank < 0) continue;
      var pts = [];
      for (var k = 0; k + 1 < r.l.length; k += 2) pts.push([w + r.l[k] / q, s + r.l[k + 1] / q]);
      if (pts.length >= 2) out.roads.push({ name: String(r.n), rank: rank, pts: pts });
    }
    function points(arr, tierFn, isLine) {
      var res = [];
      arr = arr || [];
      for (var j = 0; j < arr.length; j++) {
        var p = arr[j];
        if (!p || !p.n) continue;
        if (isLine && p.l && p.l.length >= 4) {
          var pp = [];
          for (var t = 0; t + 1 < p.l.length; t += 2) pp.push([w + p.l[t] / q, s + p.l[t + 1] / q]);
          if (pp.length >= 2) res.push({ name: String(p.n), tier: tierFn(p.k), pts: pp });
        } else if (p.p && p.p.length >= 2) {
          res.push({ name: String(p.n), tier: tierFn(p.k), lon: w + p.p[0] / q, lat: s + p.p[1] / q });
        }
      }
      return res;
    }
    out.places = points(L.places, placeTier, false);
    out.pois = points(L.pois, poiTier, false);
    out.waters = points(L.waters, waterTier, true);
    if (!out.roads.length && !out.places.length && !out.pois.length && !out.waters.length) return null;
    return out;
  }
  function updateLabelToggles() {
    var av = labelsAvailable();
    var road = $('optRoadNames'), place = $('optPlaceNames');
    if (road) {
      road.disabled = !av.roads;
      road.checked = !!(av.roads && state.labelsRoad);
      road.title = av.roads ? '沿道路排版显示道路名称' : '该区域暂无道路名称数据';
    }
    if (place) {
      place.disabled = !av.places;
      place.checked = !!(av.places && state.labelsPlace);
      place.title = av.places ? '显示区域/站点/水系等名称' : '该区域暂无地标名称数据';
    }
  }
  function labelGeom() {
    var L = state.ready.labels;
    if (!L) return null;
    var key = state.ready.version + '|' + state.width;
    if (state.labelGeomCache && state.labelGeomCache.key === key) return state.labelGeomCache.data;
    var proj = mapProjectorCached().project;
    var out = { roads: [], places: [], pois: [], waters: [] };
    var i;
    for (i = 0; i < (L.roads || []).length; i++) {
      var r = L.roads[i];
      if (!r.pts || r.pts.length < 2) continue;
      var pts = [];
      var bx0 = Infinity, by0 = Infinity, bx1 = -Infinity, by1 = -Infinity;
      for (var j = 0; j < r.pts.length; j++) {
        var p = proj(r.pts[j][0], r.pts[j][1]);
        pts.push(p);
        if (p[0] < bx0) bx0 = p[0];
        if (p[0] > bx1) bx1 = p[0];
        if (p[1] < by0) by0 = p[1];
        if (p[1] > by1) by1 = p[1];
      }
      out.roads.push({ name: r.name, rank: r.rank, pts: pts, bx: [bx0, by0, bx1, by1] });
    }
    function pointList(arr) {
      var res = [];
      for (var q = 0; q < (arr || []).length; q++) {
        var it = arr[q];
        if (!isFinite(it.lon) || !isFinite(it.lat)) continue;
        var pp = proj(it.lon, it.lat);
        res.push({ name: it.name, tier: it.tier, x: pp[0], y: pp[1] });
      }
      return res;
    }
    out.places = pointList(L.places);
    out.pois = pointList(L.pois);
    for (i = 0; i < (L.waters || []).length; i++) {
      var w = L.waters[i];
      if (w.pts && w.pts.length >= 2) {
        var wp = [];
        for (var t = 0; t < w.pts.length; t++) wp.push(proj(w.pts[t][0], w.pts[t][1]));
        out.waters.push({ name: w.name, tier: 0, pts: wp });
      } else if (isFinite(w.lon) && isFinite(w.lat)) {
        var wpp = proj(w.lon, w.lat);
        out.waters.push({ name: w.name, tier: 0, x: wpp[0], y: wpp[1] });
      }
    }
    state.labelGeomCache = { key: key, data: out };
    return out;
  }
  function textWidthMap(name, fontPx) {
    var w = 0;
    for (var i = 0; i < name.length; i++) {
      var code = name.charCodeAt(i);
      w += (code < 128) ? 0.55 : 1.0;
    }
    return w * fontPx * 1.02;
  }
  function clipSegmentRect(x0, y0, x1, y1, rx0, ry0, rx1, ry1) {
    var dx = x1 - x0, dy = y1 - y0;
    var t0 = 0, t1 = 1;
    var p = [-dx, dx, -dy, dy];
    var q = [x0 - rx0, rx1 - x0, y0 - ry0, ry1 - y0];
    for (var i = 0; i < 4; i++) {
      if (Math.abs(p[i]) < 1e-12) { if (q[i] < 0) return null; }
      else {
        var t = q[i] / p[i];
        if (p[i] < 0) { if (t > t1) return null; if (t > t0) t0 = t; }
        else { if (t < t0) return null; if (t < t1) t1 = t; }
      }
    }
    return [[x0 + t0 * dx, y0 + t0 * dy], [x0 + t1 * dx, y0 + t1 * dy]];
  }
  function clipPolylineRect(pts, rx0, ry0, rx1, ry1) {
    var pieces = [];
    var cur = null;
    for (var i = 0; i + 1 < pts.length; i++) {
      var seg = clipSegmentRect(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1], rx0, ry0, rx1, ry1);
      if (!seg) { cur = null; continue; }
      var a = seg[0], b = seg[1];
      if (cur && Math.abs(cur[cur.length - 1][0] - a[0]) < 1e-6 && Math.abs(cur[cur.length - 1][1] - a[1]) < 1e-6) {
        cur.push(b);
      } else {
        cur = [a, b];
        pieces.push(cur);
      }
    }
    return pieces;
  }
  function polylineLen(pts) {
    var len = 0;
    for (var i = 1; i < pts.length; i++) {
      var dx = pts[i][0] - pts[i - 1][0], dy = pts[i][1] - pts[i - 1][1];
      len += Math.sqrt(dx * dx + dy * dy);
    }
    return len;
  }
  function polylineAt(pts, target) {
    var acc = 0;
    for (var i = 1; i < pts.length; i++) {
      var dx = pts[i][0] - pts[i - 1][0], dy = pts[i][1] - pts[i - 1][1];
      var seg = Math.sqrt(dx * dx + dy * dy);
      if (acc + seg >= target || i === pts.length - 1) {
        var f = seg > 1e-9 ? (target - acc) / seg : 0;
        f = clamp(f, 0, 1);
        return { x: pts[i - 1][0] + dx * f, y: pts[i - 1][1] + dy * f, dx: dx, dy: dy };
      }
      acc += seg;
    }
    return { x: pts[0][0], y: pts[0][1], dx: 0, dy: 0 };
  }
  function polylineIntersects(pts, rx0, ry0, rx1, ry1) {
    for (var i = 0; i < pts.length; i++) {
      if (pts[i][0] >= rx0 && pts[i][0] <= rx1 && pts[i][1] >= ry0 && pts[i][1] <= ry1) return true;
    }
    return false;
  }
  function polylineD(pts) {
    var parts = [];
    for (var i = 0; i < pts.length; i++) {
      parts.push((i === 0 ? 'M' : 'L') + pts[i][0].toFixed(1) + ' ' + pts[i][1].toFixed(1));
    }
    return parts.join('');
  }
  function buildLabelsSvg(r) {
    var LG = labelGeom();
    if (!LG) return '';
    var showRoads = !!state.labelsRoad;
    var showPlaces = !!state.labelsPlace;
    if (!showRoads && !showPlaces) return '';
    var inkC = paletteInk();
    var unit = r.w / (r.dispW || LABEL_REF);
    var rx0 = r.x - 8 * unit, ry0 = r.y - 8 * unit, rx1 = r.x + r.w + 8 * unit, ry1 = r.y + r.h + 8 * unit;
    var placed = [];
    var placedNames = [];
    var out = [];
    var count = 0;
    function sameNameNear(name, x, y, minD) {
      for (var i = 0; i < placedNames.length; i++) {
        var q = placedNames[i];
        if (q.name !== name) continue;
        var dx = q.x - x, dy = q.y - y;
        if (dx * dx + dy * dy < minD * minD) return true;
      }
      return false;
    }
    function overlapBox(b) {
      for (var i = 0; i < placed.length; i++) {
        var p = placed[i];
        if (b.x0 < p.x1 && b.x1 > p.x0 && b.y0 < p.y1 && b.y1 > p.y0) return true;
      }
      return false;
    }
    function inside(b) {
      return b.x1 > rx0 && b.x0 < rx1 && b.y1 > ry0 && b.y0 < ry1;
    }
    function textSvg(x, y, name, fontPx, extra) {
      return '<text x="' + x.toFixed(1) + '" y="' + y.toFixed(1) + '" text-anchor="middle" dominant-baseline="central" ' +
        'font-family=\'' + LABEL_FONT + '\' font-size="' + fontPx.toFixed(2) + '" fill="' + inkC.ink + '" ' +
        'stroke="' + inkC.halo + '" stroke-width="' + (2.6 * unit).toFixed(2) + '" paint-order="stroke" stroke-linejoin="round"' +
        (extra || '') + '>' + escapeHtml(name) + '</text>';
    }
    function layoutLine(c) {
      var pieces = clipPolylineRect(c.pts, rx0, ry0, rx1, ry1);
      if (!pieces.length) return;
      var best = null, bestLen = 0;
      for (var i = 0; i < pieces.length; i++) {
        var len = polylineLen(pieces[i]);
        if (len > bestLen) { bestLen = len; best = pieces[i]; }
      }
      if (!best || bestLen < 30 * unit) return;
      // 让文字方向保持“可读”：路径整体若朝左下/向下则反转
      var endX = best[best.length - 1][0] - best[0][0];
      var endY = best[best.length - 1][1] - best[0][1];
      if (endX < 0 || (Math.abs(endX) <= Math.abs(endY) && endY > 0)) {
        best = best.slice().reverse();
      }
      var fontBase = (c.kind === 'road') ? ROAD_LABEL_FONT[c.rank] : 11;
      var fontPx = fontBase * unit;
      var tw = textWidthMap(c.name, fontPx);
      if (bestLen < tw * 1.18) return;
      var mid = polylineAt(best, bestLen / 2);
      var ang = Math.atan2(mid.dy, mid.dx);
      if (Math.abs(ang) > Math.PI / 2) { ang += (ang > 0 ? -Math.PI : Math.PI); }
      var aabbW = Math.abs(Math.cos(ang)) * tw + Math.abs(Math.sin(ang)) * fontPx * 1.25;
      var aabbH = Math.abs(Math.sin(ang)) * tw + Math.abs(Math.cos(ang)) * fontPx * 1.25;
      var b = { x0: mid.x - aabbW / 2, x1: mid.x + aabbW / 2, y0: mid.y - aabbH / 2, y1: mid.y + aabbH / 2 };
      if (!inside(b) || overlapBox(b)) return;
      if (sameNameNear(c.name, mid.x, mid.y, tw * 1.8)) return;
      placed.push(b);
      placedNames.push({ name: c.name, x: mid.x, y: mid.y });
      var id = 'rl' + (++state.labelId);
      out.push('<path id="' + id + '" d="' + polylineD(best) + '" fill="none" stroke="none"/>');
      out.push('<text font-family=\'' + LABEL_FONT + '\' font-size="' + fontPx.toFixed(2) + '" fill="' + inkC.ink + '" ' +
        'stroke="' + inkC.halo + '" stroke-width="' + (2.6 * unit).toFixed(2) + '" paint-order="stroke" stroke-linejoin="round"' +
        (c.kind === 'waterline' ? ' font-style="italic"' : '') + '>' +
        '<textPath href="#' + id + '" startOffset="50%" text-anchor="middle">' + escapeHtml(c.name) + '</textPath></text>');
      count++;
    }
    function layoutPoint(c) {
      var fontBase = 10;
      if (c.kind === 'place') fontBase = c.tier === 0 ? 13 : 11.5;
      else if (c.kind === 'water') fontBase = 11;
      else if (c.kind === 'poi') fontBase = c.tier === 0 ? 11 : 10;
      var fontPx = fontBase * unit;
      var tw = textWidthMap(c.name, fontPx);
      var dotR = c.dot ? 2.2 * unit : 0;
      var gap = c.dot ? 3.4 * unit : 0;
      var totalW = tw + (c.dot ? dotR * 2 + gap : 0);
      var left = c.dot ? c.x : c.x - tw / 2;          // 盒子左边
      var b = { x0: left, x1: left + totalW, y0: c.y - fontPx * 0.78, y1: c.y + fontPx * 0.78 };
      if (!inside(b) || overlapBox(b)) return;
      if (sameNameNear(c.name, c.x, c.y, tw * 1.6)) return;
      placed.push(b);
      placedNames.push({ name: c.name, x: c.x, y: c.y });
      var tx = c.dot ? (c.x + dotR * 2 + gap + tw / 2) : c.x;
      if (c.dot) {
        out.push('<circle cx="' + c.x.toFixed(1) + '" cy="' + c.y.toFixed(1) + '" r="' + dotR.toFixed(2) +
          '" fill="none" stroke="' + inkC.ink + '" stroke-width="' + (0.95 * unit).toFixed(2) + '"/>');
      }
      out.push(textSvg(tx, c.y, c.name, fontPx, c.kind === 'water' ? ' font-style="italic"' : ''));
      count++;
    }
    var cands = [];
    var i;
    var cxv = r.x + r.w / 2, cyv = r.y + r.h / 2;
    function distC(x, y) { var dx = x - cxv, dy = y - cyv; return Math.sqrt(dx * dx + dy * dy); }
    function inView(x, y) { return x > rx0 && x < rx1 && y > ry0 && y < ry1; }
    if (showPlaces) {
      for (i = 0; i < LG.places.length; i++) {
        var pl = LG.places[i];
        if (!inView(pl.x, pl.y)) continue;
        cands.push({ prio: 0 + pl.tier, dist: distC(pl.x, pl.y), kind: 'place', name: pl.name, tier: pl.tier, x: pl.x, y: pl.y, dot: false });
      }
      for (i = 0; i < LG.waters.length; i++) {
        var wa = LG.waters[i];
        if (wa.pts) {
          if (!polylineIntersects(wa.pts, rx0, ry0, rx1, ry1)) continue;
          var wp0 = wa.pts[Math.floor(wa.pts.length / 2)];
          cands.push({ prio: 30, dist: distC(wp0[0], wp0[1]), kind: 'waterline', name: wa.name, pts: wa.pts });
        } else if (inView(wa.x, wa.y)) cands.push({ prio: 31, dist: distC(wa.x, wa.y), kind: 'water', name: wa.name, x: wa.x, y: wa.y, dot: true });
      }
      for (i = 0; i < LG.pois.length; i++) {
        var po = LG.pois[i];
        if (!inView(po.x, po.y)) continue;
        cands.push({ prio: 40 + po.tier, dist: distC(po.x, po.y), kind: 'poi', name: po.name, tier: po.tier, x: po.x, y: po.y, dot: true });
      }
    }
    if (showRoads) {
      for (i = 0; i < LG.roads.length; i++) {
        var rd = LG.roads[i];
        var bx = rd.bx;
        if (!(bx[0] < rx1 && bx[2] > rx0 && bx[1] < ry1 && bx[3] > ry0)) continue;
        var midx = (bx[0] + bx[2]) / 2, midy = (bx[1] + bx[3]) / 2;
        cands.push({ prio: 10 + rd.rank, dist: distC(midx, midy), kind: 'road', name: rd.name, rank: rd.rank, pts: rd.pts });
      }
    }
    cands.sort(function (a, b2) {
      return (a.prio - b2.prio) || ((a.dist || 0) - (b2.dist || 0)) || (a.name.length - b2.name.length);
    });
    for (i = 0; i < cands.length && count < MAX_LABELS; i++) {
      var c = cands[i];
      if (c.kind === 'road' || c.kind === 'waterline') layoutLine(c);
      else layoutPoint(c);
    }
    return out.join('');
  }
  function currentLabelCount() {
    var el = $('labelsLayer');
    return el ? el.querySelectorAll('text').length : 0;
  }

  /* ============================================================
     导出（当前视图 / 全图）
     ============================================================ */
  function exportRect(scope) {
    var geom = ensureGeom();
    if (scope === 'full') {
      var st = stageSize();
      return { x: 0, y: 0, w: geom.width, h: geom.height, z: 1, dispW: st.w, dispH: st.h, mapW: geom.width, mapH: geom.height };
    }
    return viewRect();
  }
  function composeSvg(scope, exportWidth) {
    var geom = ensureGeom();
    var pal = PALETTES[state.palette];
    var r = exportRect(scope);
    var outW = exportWidth || state.width;
    var outH = Math.max(1, Math.round(outW * r.h / r.w));
    var scale = geom.width / 2400;
    var body = [];
    for (var i = 0; i < geom.groups.length; i++) {
      var gr = geom.groups[i];
      var g = GROUPS[gr.gi];
      body.push('<path d="' + gr.d + '" fill="none" stroke="' + pal.colors[gr.gi] +
        '" stroke-width="' + (g.width * scale).toFixed(2) +
        '" stroke-linecap="round" stroke-linejoin="round"/>');
    }
    var bg = pal.bg ? '<rect x="' + r.x.toFixed(2) + '" y="' + r.y.toFixed(2) + '" width="' + r.w.toFixed(2) +
      '" height="' + r.h.toFixed(2) + '" fill="' + pal.bg + '"/>' : '';
    var labels = buildLabelsSvg(r);
    var markers = markersSvg(r);
    var label = state.ready.label || '自定义范围';
    var title = label + ' · 道路底图（' + pal.name + (state.markers.length ? '，' + state.markers.length + ' 个标记' : '') + '）';
    var desc = 'Data (c) OpenStreetMap contributors, ODbL 1.0. https://www.openstreetmap.org/copyright' +
      (state.markers.length ? ' | markers: ' + state.markers.length : '') +
      (labels ? ' | labels: ' + (labels.match(/<text /g) || []).length : '');
    var svg = '<?xml version="1.0" encoding="UTF-8"?>\n' +
      '<svg xmlns="http://www.w3.org/2000/svg" viewBox="' + r.x.toFixed(2) + ' ' + r.y.toFixed(2) + ' ' + r.w.toFixed(2) + ' ' + r.h.toFixed(2) +
      '" width="' + outW + '" height="' + outH + '" shape-rendering="geometricPrecision">\n' +
      '<title>' + escapeHtml(title) + '</title>\n' +
      '<desc>' + escapeHtml(desc) + '</desc>\n' +
      (bg ? bg + '\n' : '') +
      body.join('\n') + '\n' + labels + markers + '\n' +
      '</svg>\n';
    return { svg: svg, width: outW, height: outH, labels: labels, markers: markers };
  }
  function exportNameSuffix(scope) {
    if (scope === 'full') return 'full';
    return (Math.round(viewRect().z * 10) / 10).toFixed(1) + 'x';
  }

  /* ============================================================
     缩放 / 平移 / 标记交互
     ============================================================ */
  function bindMapInteractions() {
    var view = $('mapView');
    if (!view || view.__bound) return;
    view.__bound = true;
    var down = null, last = null, dragging = false;
    var lastClickTs = 0, lastClickX = 0, lastClickY = 0;
    function local(e) {
      var rect = view.getBoundingClientRect();
      return { x: e.clientX - rect.left, y: e.clientY - rect.top };
    }
    view.addEventListener('wheel', function (e) {
      e.preventDefault();
      var p = local(e);
      var factor = Math.exp(-e.deltaY * 0.0015);
      factor = clamp(factor, 0.5, 2);
      zoomAt(factor, p.x, p.y);
    }, { passive: false });
    view.addEventListener('pointerdown', function (e) {
      if (state.busy) return;
      if (e.button !== undefined && e.button !== 0) return;
      down = local(e);
      last = down;
      dragging = false;
      try { view.setPointerCapture(e.pointerId); } catch (err) { }
    });
    view.addEventListener('pointermove', function (e) {
      var p = local(e);
      if (down) {
        var dx = p.x - last.x, dy = p.y - last.y;
        if (!dragging && Math.abs(p.x - down.x) + Math.abs(p.y - down.y) > DRAG_THRESHOLD) {
          dragging = true;
          view.classList.add('dragging');
        }
        if (dragging) {
          panByPx(dx, dy);
          last = p;
        }
      } else if (state.markerMode && state.markers.length && $('mapSvg')) {
        var r = viewRect();
        var hit = markersHit(p.x, p.y, r);
        view.classList.toggle('hover-marker', hit >= 0);
      }
    });
    view.addEventListener('pointerup', function (e) {
      var p = local(e);
      var wasDrag = dragging;
      down = null; last = null; dragging = false;
      view.classList.remove('dragging');
      if (wasDrag || !state.markerMode) return;
      var nowTs = Date.now();
      var nearLast = Math.abs(p.x - lastClickX) < 8 && Math.abs(p.y - lastClickY) < 8;
      if (nowTs - lastClickTs < 320 && nearLast) { lastClickTs = nowTs; lastClickX = p.x; lastClickY = p.y; return; }
      lastClickTs = nowTs; lastClickX = p.x; lastClickY = p.y;
      // 标记模式下的点击：先测已有标记，否则新增
      var rr = viewRect();
      if (!rr) return;
      var hitIdx = markersHit(p.x, p.y, rr);
      if (hitIdx >= 0) { deleteMarker(hitIdx); toast('已删除标记 ' + (hitIdx + 1)); }
      else {
        var mapX = rr.x + p.x / rr.dispW * rr.w;
        var mapY = rr.y + p.y / rr.dispH * rr.h;
        addMarkerAtMap(mapX, mapY);
        toast('已添加标记 ' + state.markers.length);
      }
    });
    view.addEventListener('pointercancel', function () {
      down = null; last = null; dragging = false; view.classList.remove('dragging');
    });
    view.addEventListener('dblclick', function (e) {
      if (state.markerMode) return;
      e.preventDefault();
      var p = local(e);
      zoomAt(2, p.x, p.y);
    });
    var wheelGuard = function (e) { e.preventDefault(); };
    view.addEventListener('contextmenu', function (e) { e.preventDefault(); });
  }

  /* ---------- 预览渲染 ---------- */
  function paletteStageClass() {
    if (state.palette === 'light') return 'rm-stage stage-light';
    if (state.palette === 'dark') return 'rm-stage stage-dark';
    return 'rm-stage stage-transparent';
  }

  function sourceBadgeText() {
    if (state.ready.source === 'sample') return '内置示例数据';
    if (state.ready.source === 'offline') return '内置数据 · 离线可用';
    if (state.ready.source === 'vector') return '矢量瓦片 · ' + (state.ready.sourceDetail || 'VersaTiles');
    if (state.ready.source === 'osm') return 'Overpass 实时数据';
    return '—';
  }

  function resetReadyData() {
    state.ready = {
      ways: [],
      bbox: null,
      label: '',
      source: 'sample',
      sourceDetail: '',
      slug: 'roadmap',
      fetchMs: 0,
      tiles: 0,
      zoom: 0,
      labels: null,
      version: state.ready.version + 1
    };
    state.geom = { key: '', data: null };
    state.projCache = null;
    state.labelGeomCache = null;
    state.markers = [];
    updateMarkerPanel();
    renderPreview();
  }

  function buildBaseSvg(geom) {
    var pal = PALETTES[state.palette];
    var scale = geom.width / 2400;
    var body = [];
    for (var i = 0; i < geom.groups.length; i++) {
      var gr = geom.groups[i];
      var g = GROUPS[gr.gi];
      body.push('<path d="' + gr.d + '" fill="none" stroke="' + pal.colors[gr.gi] +
        '" stroke-width="' + (g.width * scale).toFixed(2) +
        '" stroke-linecap="round" stroke-linejoin="round"/>');
    }
    return '<svg id="mapSvg" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="xMidYMid meet" shape-rendering="geometricPrecision">' +
      (pal.bg ? '<rect id="bgRect" x="0" y="0" width="1" height="1" fill="' + pal.bg + '"/>' : '') +
      '<g id="roadsLayer" fill="none" stroke-linecap="round" stroke-linejoin="round">' + body.join('') + '</g>' +
      '<g id="labelsLayer"></g><g id="markersLayer"></g>' +
      '</svg>';
  }

  var _renderRetry = 0;
  function renderPreview() {
    var host = $('mapView');
    if (!host) return;
    if (!state.ready.ways.length || !state.ready.bbox) {
      host.innerHTML = '<div class="rm-empty">还没有路网数据。<br>预置城市会自动加载内置离线数据；其它区域点「获取道路数据」用矢量瓦片抓取。</div>';
      state.domSig = '';
      var tEl0 = $('previewTitle');
      if (tEl0) tEl0.textContent = '未加载数据';
      var mEl0 = $('previewMeta');
      if (mEl0) mEl0.textContent = '选择区域后加载';
      var bEl0 = $('previewBadge');
      if (bEl0) bEl0.textContent = '—';
      $('paletteChip').textContent = PALETTES[state.palette].name;
      drawSourceBadge('none');
      updateEmptyStats();
      updateLegend(null);
      updateLabelToggles();
      return;
    }
    var geom = ensureGeom();
    if (stageSize().w < 10) {
      if (_renderRetry < 60) {
        _renderRetry++;
        setTimeout(renderPreview, 60);
      }
      return;
    }
    _renderRetry = 0;
    var sig = state.ready.version + '|' + state.palette + '|' + state.width;
    var viewKey = state.ready.version + '|' + state.width;
    if (state.domSig !== sig || !$('mapSvg')) {
      host.innerHTML = buildBaseSvg(geom);
      state.domSig = sig;
      if (state.viewKey !== viewKey) {
        state.viewKey = viewKey;
        resetView();
        loadMarkersForArea();
      }
    }
    var stage = $('previewStage');
    stage.className = paletteStageClass();
    var km = bboxKm(state.ready.bbox);
    var prefix = state.ready.source === 'sample' ? '内置示例 · ' : (state.ready.source === 'offline' ? '内置数据 · ' : '');
    $('previewTitle').textContent = prefix + state.ready.label;
    var badge = $('previewBadge');
    if (badge) badge.textContent = sourceBadgeText();
    $('paletteChip').textContent = PALETTES[state.palette].name;
    drawSourceBadge(state.ready.source);
    updateLabelToggles();
    applyView(true);
    updatePreviewMeta(geom, km);
    updateStats(geom, svgFromGeom(geom, state.palette));
    updateLegend(geom);
  }

  function updatePreviewMeta(geom, km) {
    var el = $('previewMeta');
    if (!el) return;
    var txt = fmtInt(state.ready.ways.length) + ' 条道路 · ' + geom.width + '×' + geom.height + ' px · ' +
      km.w.toFixed(1) + '×' + km.h.toFixed(1) + ' km';
    var parts = [];
    if (state.labelsRoad || state.labelsPlace) {
      var n = currentLabelCount();
      if (n > 0) parts.push('名称 ' + n + ' 条');
    }
    if (state.markers.length) parts.push('标记 ' + state.markers.length);
    if (parts.length) txt += ' · ' + parts.join(' · ');
    el.textContent = txt;
  }

  function updateEmptyStats() {
    ['stWays', 'stBbox', 'stSize', 'stCanvas', 'stBytes', 'stTime', 'stSource'].forEach(function (id) {
      var el = $(id);
      if (el) { el.textContent = '—'; if (el.title) el.title = ''; }
    });
    var step = $('sourceStep');
    if (step) step.textContent = '未加载';
  }

  function updateStats(geom, svg) {
    var km = bboxKm(state.ready.bbox);
    var src = state.ready.source;
    $('stWays').textContent = fmtInt(state.ready.ways.length);
    $('stBbox').textContent = state.ready.bbox[0].toFixed(3) + '–' + state.ready.bbox[2].toFixed(3) + ' N / ' +
      state.ready.bbox[1].toFixed(3) + '–' + state.ready.bbox[3].toFixed(3) + ' E';
    $('stBbox').title = fmtBboxShort(state.ready.bbox);
    $('stSize').textContent = km.w.toFixed(1) + ' × ' + km.h.toFixed(1) + ' km';
    $('stCanvas').textContent = geom.width + ' × ' + geom.height + ' px';
    $('stBytes').textContent = fmtBytes(new Blob([svg]).size);
    var srcText = '—', stepText = '—', timeText = '—';
    if (src === 'sample') {
      srcText = '内置示例（太原五一广场周边）';
      stepText = '内置示例';
      timeText = '—（示例）';
    } else if (src === 'offline') {
      srcText = '内置城市数据 · 离线可用';
      stepText = '内置数据';
      timeText = '≈ 0 s（离线）';
    } else if (src === 'vector') {
      srcText = '矢量瓦片 · ' + (state.ready.sourceDetail || 'VersaTiles') + (state.ready.zoom ? ' · z' + state.ready.zoom : '');
      stepText = '矢量瓦片';
      timeText = (state.ready.fetchMs / 1000).toFixed(1) + ' s · ' + state.ready.tiles + ' 块';
    } else {
      srcText = 'Overpass API' + (state.ready.tiles ? ' · ' + state.ready.tiles + ' 块' : '');
      stepText = 'Overpass 抓取';
      timeText = (state.ready.fetchMs / 1000).toFixed(1) + ' s' + (state.ready.tiles ? ' · ' + state.ready.tiles + ' 块' : '');
    }
    var srcEl = $('stSource');
    if (srcEl) { srcEl.textContent = srcText; srcEl.title = srcText; }
    $('stTime').textContent = timeText;
    $('sourceStep').textContent = stepText;
  }

  function updateLegend(geom) {
    var pal = PALETTES[state.palette];
    var el = $('legend');
    if (!el) return;
    var html = '';
    for (var gi = 0; gi < GROUPS.length; gi++) {
      var g = GROUPS[gi];
      var count = (geom && geom.counts[gi]) || 0;
      var w = Math.max(1, Math.round(g.width * 0.9));
      var swatchBg = state.palette === 'transparent' ? 'background:#2a2c33;' : '';
      html += '<div class="rm-legend-row">' +
        '<i style="height:' + (w + 2) + 'px;border-top:' + w + 'px solid ' + pal.colors[gi] + ';' + swatchBg + '"></i>' +
        '<span>' + g.name + '</span>' +
        '<span class="count">' + fmtInt(count) + '</span></div>';
    }
    el.innerHTML = html;
    el.classList.toggle('transparent', state.palette === 'transparent');
  }

  /* ---------- 导出 ---------- */
  function currentSlug() {
    return state.ready.slug || 'roadmap';
  }
  function downloadBlob(blob, filename) {
    var a = document.createElement('a');
    var url = URL.createObjectURL(blob);
    a.href = url;
    a.download = filename;
    a.rel = 'noopener';
    document.body.appendChild(a);
    a.click();
    setTimeout(function () {
      try { URL.revokeObjectURL(url); } catch (e) { }
      if (a.parentNode) a.parentNode.removeChild(a);
    }, 1500);
  }
  function requireData() {
    if (!state.ready.ways.length || !state.ready.bbox) {
      toast('还没有可导出的数据：先加载城市或抓取区域');
      return false;
    }
    return true;
  }
  function downloadSvg() {
    if (!requireData()) return;
    var scope = state.exportScope;
    var out = composeSvg(scope, state.width);
    var name = currentSlug() + '-' + state.palette + '-' + exportNameSuffix(scope) + '.svg';
    downloadBlob(new Blob([out.svg], { type: 'image/svg+xml;charset=utf-8' }), name);
    toast('已导出 ' + name + '（' + fmtBytes(new Blob([out.svg]).size) +
      (state.markers.length ? '，含 ' + state.markers.length + ' 个标记' : '') + '）· 数据 © OpenStreetMap contributors, ODbL', 4200);
  }
  function downloadPng() {
    if (!requireData()) return;
    var scope = state.exportScope;
    var out = composeSvg(scope, state.width);
    var scale = state.pngScale;
    var MAX_SIDE = 8192, MAX_PIXELS = 36e6;
    if (out.width * scale > MAX_SIDE) scale = MAX_SIDE / out.width;
    if (out.height * scale > MAX_SIDE) scale = Math.min(scale, MAX_SIDE / out.height);
    if (out.width * out.height * scale * scale > MAX_PIXELS) scale = Math.sqrt(MAX_PIXELS / (out.width * out.height));
    scale = Math.max(0.3, Math.floor(scale * 100) / 100);
    var canvas = document.createElement('canvas');
    canvas.width = Math.max(1, Math.round(out.width * scale));
    canvas.height = Math.max(1, Math.round(out.height * scale));
    var blob = new Blob([out.svg], { type: 'image/svg+xml;charset=utf-8' });
    var url = URL.createObjectURL(blob);
    var img = new Image();
    img.onload = function () {
      try {
        var ctx = canvas.getContext('2d');
        ctx.imageSmoothingEnabled = true;
        ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
        canvas.toBlob(function (png) {
          URL.revokeObjectURL(url);
          if (!png) { toast('PNG 生成失败（画布过大时浏览器可能拒绝）'); return; }
          var name = currentSlug() + '-' + state.palette + '-' + exportNameSuffix(scope) + '@' + scale.toFixed(1) + 'x.png';
          downloadBlob(png, name);
          toast('已导出 ' + name + '（' + canvas.width + '×' + canvas.height + '）· 数据 © OpenStreetMap contributors, ODbL', 4500);
        }, 'image/png');
      } catch (e) {
        URL.revokeObjectURL(url);
        toast('PNG 导出失败：' + (e && e.message ? e.message : e));
      }
    };
    img.onerror = function () {
      URL.revokeObjectURL(url);
      toast('PNG 导出失败：SVG 光栅化出错，请改用「下载 SVG」');
    };
    img.src = url;
  }
  function copySvg() {
    if (!requireData()) return;
    var out = composeSvg(state.exportScope, state.width);
    copyText(out.svg, '已复制 SVG 源码（' + fmtBytes(new Blob([out.svg]).size) + '）');
  }
  function downloadSample() {
    if (!state.sample) { toast('内置示例数据未加载'); return; }
    var ways = state.sample.ways.map(function (w) { return { g: w[0], c: w[1] }; });
    var geom = computeGeom(ways, state.sample.bbox, state.width);
    var svg = svgFromGeom(geom, state.palette, (state.sample.label || '内置示例') + '（内置示例）');
    var name = 'sample-taiyuan-' + state.palette + '.svg';
    downloadBlob(new Blob([svg], { type: 'image/svg+xml;charset=utf-8' }), name);
    toast('已导出内置示例 ' + name + ' · 数据 © OpenStreetMap contributors, ODbL');
  }

  /* ---------- 区域信息 ---------- */
  function computeTiles(bbox, maxTiles) {
    var latSpan = bbox[2] - bbox[0];
    var lonSpan = bbox[3] - bbox[1];
    var target = 0.09;
    var nx = 1, ny = 1, span = target, capped = false;
    for (var iter = 0; iter < 20; iter++) {
      nx = Math.max(1, Math.ceil(lonSpan / span - 1e-9));
      ny = Math.max(1, Math.ceil(latSpan / span - 1e-9));
      if (nx * ny <= maxTiles) break;
      span *= 1.18;
      capped = true;
    }
    var tiles = [];
    for (var iy = 0; iy < ny; iy++) {
      var s = bbox[0] + iy * span;
      var n = Math.min(bbox[2], s + span);
      if (s >= bbox[2] - 1e-12) break;
      for (var ix = 0; ix < nx; ix++) {
        var w = bbox[1] + ix * span;
        var e = Math.min(bbox[3], w + span);
        if (w >= bbox[3] - 1e-12) break;
        tiles.push([round5(s), round5(w), round5(n), round5(e)]);
      }
    }
    return { tiles: tiles, nx: nx, ny: ny, span: span, capped: capped };
  }

  function updateRegionInfo() {
    var el = $('regionInfo');
    if (!el) return;
    if (!state.region) { el.textContent = '—'; return; }
    var km = bboxKm(state.region);
    var offlineCity = state.mode === 'preset' && cityIndexHas(state.cityKey);
    var plan = chooseVectorZoom(state.region);
    var warn = '';
    if (km.w > 45 || km.h > 45) warn = ' · <b>范围较大，建议缩小</b>';
    if (km.w > 120 || km.h > 120) warn = ' · <b>范围过大，无法抓取</b>';
    var line3;
    if (offlineCity) {
      line3 = '内置离线数据 · 秒开';
    } else if (plan.range.count <= MAX_VTILES) {
      line3 = '矢量瓦片 z' + plan.z + ' · ' + plan.range.nx + '×' + plan.range.ny + ' = ' + plan.range.count + ' 块';
    } else {
      line3 = '<b>范围过大</b>，请缩小';
    }
    el.innerHTML = '<b>' + escapeHtml(state.regionLabel || '自定义范围') + '</b><br>' +
      'S ' + state.region[0].toFixed(4) + ' · W ' + state.region[1].toFixed(4) +
      ' · N ' + state.region[2].toFixed(4) + ' · E ' + state.region[3].toFixed(4) + '<br>' +
      '约 ' + km.w.toFixed(1) + ' × ' + km.h.toFixed(1) + ' km · ' + line3 + warn;
    savePrefs();
  }

  function syncBboxInputs() {
    if (!state.region) return;
    var b = state.region;
    if ($('bS')) $('bS').value = b[0].toFixed(4);
    if ($('bW')) $('bW').value = b[1].toFixed(4);
    if ($('bN')) $('bN').value = b[2].toFixed(4);
    if ($('bE')) $('bE').value = b[3].toFixed(4);
    var km = bboxKm(b);
    if ($('cLat')) $('cLat').value = ((b[0] + b[2]) / 2).toFixed(4);
    if ($('cLon')) $('cLon').value = ((b[1] + b[3]) / 2).toFixed(4);
    if ($('cWkm')) $('cWkm').value = km.w.toFixed(1);
    if ($('cHkm')) $('cHkm').value = km.h.toFixed(1);
  }

  function setRegion(bbox, label, mode, extra) {
    state.region = bbox.slice();
    state.regionLabel = label;
    state.mode = mode;
    if (extra && extra.cityKey !== undefined) state.cityKey = extra.cityKey;
    if (extra && extra.searchLabel !== undefined) state.searchLabel = extra.searchLabel;
    if (!extra || extra.syncInputs !== false) syncBboxInputs();
    updateRegionInfo();
  }

  function applyPresetCity(key) {
    var city = CITY_MAP[key];
    if (!city) return;
    state.cityKey = key;
    if ($('citySelect')) $('citySelect').value = key;
    setRegion(city.bbox, city.name, 'preset', { cityKey: key });
    resetReadyData();
    if (cityIndexHas(key)) {
      drawSourceBadge('offline');
      tryLoadOfflineCity(key).then(function (ok) {
        if (!ok) {
          drawSourceBadge('vector');
          setStatusHtml('「' + escapeHtml(city.name) + '」内置数据加载失败，点「获取道路数据」用矢量瓦片抓取（失败自动回退 Overpass）。');
        }
      });
    } else {
      drawSourceBadge('vector');
      setStatusHtml('已选择「' + escapeHtml(city.name) + '」。点「获取道路数据」用矢量瓦片抓取（失败自动回退 Overpass）。');
    }
  }

  function validateBBox(bbox) {
    if (!bbox || bbox.length !== 4) return 'bbox 无效';
    var s = bbox[0], w = bbox[1], n = bbox[2], e = bbox[3];
    if (![s, w, n, e].every(function (v) { return isFinite(v); })) return '请输入数字';
    if (s < -85 || n > 85) return '纬度需在 ±85° 之间（Web Mercator 限制）';
    if (w < -180 || e > 180) return '经度需在 ±180° 之间';
    if (!(s < n)) return '南纬必须小于北纬';
    if (!(w < e)) return '西经必须小于东经';
    if (n - s < 0.0008) return '南北范围太小（< 90 m）';
    if (e - w < 0.0008) return '东西范围太小（< 90 m）';
    if ((n - s) / (e - w) > 8 || (e - w) / (n - s) > 8) return '长宽比过大（> 8:1），请调整范围';
    return null;
  }

  function applyCustomBbox() {
    var bbox;
    var mode = document.querySelector('input[name="bboxmode"]:checked');
    var useCenter = mode && mode.value === 'center';
    if (useCenter) {
      var lat = parseFloat($('cLat').value);
      var lon = parseFloat($('cLon').value);
      var wkm = parseFloat($('cWkm').value);
      var hkm = parseFloat($('cHkm').value);
      if (![lat, lon, wkm, hkm].every(function (v) { return isFinite(v); })) {
        toast('请填写完整的中心点与宽高'); return;
      }
      if (wkm <= 0 || hkm <= 0) { toast('宽、高必须大于 0'); return; }
      var dLat = hkm / 111.32;
      var dLon = wkm / (111.32 * Math.cos(lat * RAD));
      bbox = [lat - dLat / 2, lon - dLon / 2, lat + dLat / 2, lon + dLon / 2];
    } else {
      bbox = [
        parseFloat($('bS').value), parseFloat($('bW').value),
        parseFloat($('bN').value), parseFloat($('bE').value)
      ];
    }
    var err = validateBBox(bbox);
    if (err) { toast(err); return; }
    bbox = bbox.map(function (v) { return round5(v); });
    setRegion(bbox, '自定义范围', 'bbox', { searchLabel: '' });
    resetReadyData();
    drawSourceBadge('vector');
    $('status').textContent = '已应用自定义范围。点「获取道路数据」用矢量瓦片抓取（失败自动回退 Overpass）。';
  }

  /* ---------- Overpass 抓取 ---------- */
  function buildOverpassQuery(tb, includeService) {
    var list = HIGHWAY_LIST.slice();
    if (!includeService) {
      list = list.filter(function (x) { return x !== 'service'; });
    }
    var re = '^(' + list.join('|') + ')$';
    return '[out:json][timeout:60];\nway["highway"~"' + re + '"](' +
      tb[0] + ',' + tb[1] + ',' + tb[2] + ',' + tb[3] + ');\nout geom;';
  }

  function makeAbortError() {
    var e = new Error('已取消');
    e.name = 'AbortError';
    e.userAbort = true;
    return e;
  }

  async function fetchOverpass(query, tileIdx) {
    var lastErr = null;
    var attempts = 3;
    for (var a = 0; a < attempts; a++) {
      if (state.abort && state.abort.aborted) throw makeAbortError();
      var ep = ENDPOINTS[(tileIdx + a) % ENDPOINTS.length];
      var ctrl = new AbortController();
      state.abort.controllers.push(ctrl);
      var timer = setTimeout(function () { try { ctrl.abort(); } catch (e) { } }, REQUEST_TIMEOUT);
      try {
        var res = await fetch(ep, {
          method: 'POST',
          mode: 'cors',
          credentials: 'omit',
          headers: { 'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8' },
          body: 'data=' + encodeURIComponent(query),
          signal: ctrl.signal
        });
        clearTimeout(timer);
        if (!res.ok) {
          var wait = 1000 * Math.pow(2, a);
          var ra = parseInt(res.headers.get('Retry-After') || '0', 10);
          if (ra > 0 && ra < 20) wait = ra * 1000;
          logLine('  ! ' + epHost(ep) + ' → HTTP ' + res.status + (res.status >= 500 ? '（实例繁忙）' : ''), 'warn');
          if (a < attempts - 1) await sleep(wait);
          lastErr = new Error(epHost(ep) + ' HTTP ' + res.status);
          continue;
        }
        var text = await res.text();
        var json;
        try { json = JSON.parse(text); }
        catch (e) { throw new Error(epHost(ep) + ' 返回了非 JSON 内容（可能被限流或拦截）'); }
        return json;
      } catch (err) {
        clearTimeout(timer);
        if (state.abort && state.abort.aborted) throw makeAbortError();
        lastErr = err;
        logLine('  ! ' + epHost(ep) + ' 请求失败：' + describeError(err), 'warn');
        if (a < attempts - 1) await sleep(1000 * Math.pow(2, a));
      } finally {
        clearTimeout(timer);
        var ix = state.abort.controllers.indexOf(ctrl);
        if (ix >= 0) state.abort.controllers.splice(ix, 1);
      }
    }
    throw lastErr || new Error('请求失败');
  }

  function updateFetchProgress(done, total, waysCount) {
    setProgress(total ? done / total : 0);
    var txt = '抓取中… <b>[progress ' + done + ' / ' + total + ']</b> · 已取得 ' + fmtInt(waysCount) + ' 条道路';
    setStatusHtml(txt);
    var lt = $('loadingText');
    if (lt) lt.textContent = '正在抓取道路数据… [progress ' + done + '/' + total + ']';
  }

  function fetchAllTiles(tiles, includeService) {
    return new Promise(function (resolve) {
      var waysMap = new Map();
      var failed = [];
      var labels = { roads: [] };
      var labelSeen = new Set();
      var next = 0, active = 0, done = 0, stopped = false;
      function finish() {
        if (stopped) return;
        stopped = true;
        resolve({
          ways: waysMap,
          labels: labels,
          failed: failed,
          aborted: !!(state.abort && state.abort.aborted)
        });
      }
      function launch() {
        if (stopped) return;
        while (active < CONCURRENCY && next < tiles.length) {
          runTile(next++);
        }
        if (active === 0 && next >= tiles.length) finish();
      }
      function runTile(myIdx) {
        var tb = tiles[myIdx];
        active++;
        (async function () {
          if (state.abort && state.abort.aborted) throw makeAbortError();
          var q = buildOverpassQuery(tb, includeService);
          var json = await fetchOverpass(q, myIdx);
          var els = (json && json.elements) || [];
          var added = 0;
          for (var k = 0; k < els.length; k++) {
            var el = els[k];
            if (!el || el.type !== 'way' || !el.geometry) continue;
            if (waysMap.has(el.id)) continue;
            var highway = (el.tags && el.tags.highway) || '';
            var gi = GROUP_INDEX[highway];
            if (gi === undefined) continue;
            var coords = [];
            for (var p = 0; p < el.geometry.length; p++) {
              var pt = el.geometry[p];
              if (pt && typeof pt.lon === 'number' && typeof pt.lat === 'number') {
                coords.push(pt.lon, pt.lat);
              }
            }
            if (coords.length >= 4) {
              waysMap.set(el.id, { g: gi, c: coords });
              added++;
              var nm = el.tags && el.tags.name;
              if (typeof nm === 'string' && nm.trim()) {
                var lk = nm.trim() + '|' + coords[0].toFixed(5) + ',' + coords[1].toFixed(5);
                if (!labelSeen.has(lk) && labels.roads.length < 6000) {
                  labelSeen.add(lk);
                  var pts = [];
                  for (var q = 0; q + 1 < coords.length; q += 2) pts.push([coords[q], coords[q + 1]]);
                  labels.roads.push({ name: nm.trim(), rank: gi, pts: pts });
                }
              }
            }
          }
          done++;
          updateFetchProgress(done, tiles.length, waysMap.size);
          logLine('[progress ' + done + '/' + tiles.length + '] 块 ' + (myIdx + 1) +
            ' · ' + tb[0].toFixed(3) + ',' + tb[1].toFixed(3) + ' ✓ ' + added + ' 条', 'ok');
        })().then(function () {
          active--;
          launch();
        }, function (err) {
          active--;
          if (err && err.userAbort) { finish(); return; }
          failed.push({ tile: tb, message: describeError(err) });
          done++;
          updateFetchProgress(done, tiles.length, waysMap.size);
          logLine('[progress ' + done + '/' + tiles.length + '] 块 ' + (myIdx + 1) + ' ✗ ' + describeError(err), 'warn');
          launch();
        });
      }
      launch();
    });
  }

  function showRetry(on) {
    var btn = $('btnRetry');
    if (btn) btn.hidden = !on;
  }

  function setBusy(busy) {
    state.busy = busy;
    ['btnFetch', 'btnSearch', 'btnApplyBbox'].forEach(function (id) {
      var el = $(id);
      if (el) el.disabled = busy;
    });
    var tabs = document.querySelectorAll('.rm-tab');
    for (var i = 0; i < tabs.length; i++) tabs[i].disabled = busy;
    var cancel = $('btnCancel');
    if (cancel) cancel.disabled = !busy;
    var loading = $('loading');
    if (loading) loading.hidden = !busy;
  }

  async function doFetchOverpass(isFallback) {
    if (state.busy) return;
    if (!state.region) { toast('请先选择区域'); return; }
    var bbox = state.region;
    var km = bboxKm(bbox);
    if (km.w > 120 || km.h > 120) {
      toast('范围过大（约 ' + km.w.toFixed(0) + ' × ' + km.h.toFixed(0) + ' km），请缩小到 120 km 以内');
      return;
    }
    var includeService = $('optService').checked;
    var t = computeTiles(bbox, MAX_TILES);
    var tileKm = t.span * 111.32;
    state.abort = { aborted: false, controllers: [] };
    if (!isFallback) clearLog();
    else logLine('—— 回退 Overpass 兜底 ——', 'warn');
    setProgress(0);
    showRetry(false);
    setBusy(true);
    setStatusHtml('Overpass 兜底抓取中… <b>[progress 0 / ' + t.tiles.length + ']</b>');
    logLine('范围 ' + fmtBboxShort(bbox) + '（约 ' + km.w.toFixed(1) + ' × ' + km.h.toFixed(1) + ' km）');
    logLine('Overpass 分块 ' + t.nx + ' × ' + t.ny + ' = ' + t.tiles.length + ' 块，每块约 ' +
      tileKm.toFixed(1) + ' km' + (t.capped ? '（已自动放大分块以控制请求数）' : ''));
    var t0 = performance.now();
    try {
      var res = await fetchAllTiles(t.tiles, includeService);
      var elapsed = performance.now() - t0;
      var waysArr = Array.from(res.ways.values());
      if (res.failed.length) {
        logLine('! ' + res.failed.length + ' 个分块失败（部分路网可能缺失）', 'warn');
      }
      if (!waysArr.length) {
        if (res.aborted) {
          setStatusHtml('已取消：没有取得有效数据。');
          showRetry(false);
          logLine('已取消', 'warn');
        } else {
          var reason = res.failed.length ? describeError({ message: res.failed[0].message }) : '该区域没有匹配的道路数据';
          setStatusHtml('<span class="err">抓取失败：' + escapeHtml(reason) + '</span><br>可以重试，或用「下载内置示例」继续。');
          showRetry(true);
          logLine('✗ 没有取得道路数据：' + reason, 'err');
          toast('没有取得道路数据：' + reason);
        }
        return;
      }
      state.ready = {
        ways: waysArr,
        bbox: bbox.slice(),
        label: labelForRegion(),
        source: 'osm',
        sourceDetail: 'Overpass API',
        slug: slugForRegion(),
        fetchMs: elapsed,
        tiles: t.tiles.length,
        zoom: 0,
        labels: (res.labels && res.labels.roads && res.labels.roads.length)
          ? { roads: res.labels.roads, places: [], pois: [], waters: [] } : null,
        version: state.ready.version + 1
      };
      state.geom = { key: '', data: null };
      state.projCache = null;
      state.labelGeomCache = null;
      renderPreview();
      if (res.aborted) {
        setProgress(1);
        setStatusHtml('已取消：保留已取得的 <b>' + fmtInt(waysArr.length) + '</b> 条道路（' +
          (res.failed.length ? res.failed.length + ' 块失败 · ' : '') + (elapsed / 1000).toFixed(1) + ' s）。');
        logLine('已取消，保留已取得的 ' + waysArr.length + ' 条道路', 'warn');
        toast('已取消：保留已取得的 ' + fmtInt(waysArr.length) + ' 条道路');
      } else {
        setProgress(1);
        setStatusHtml('Overpass 抓取完成：<b>' + fmtInt(waysArr.length) + '</b> 条道路 · ' +
          t.tiles.length + ' 块 · 用时 ' + (elapsed / 1000).toFixed(1) + ' s。');
        toast('Overpass 抓取完成：' + fmtInt(waysArr.length) + ' 条道路（' + (elapsed / 1000).toFixed(1) + ' s）');
      }
    } catch (err) {
      var msg = describeError(err);
      setStatusHtml('<span class="err">抓取失败：' + escapeHtml(msg) + '</span><br>' +
        '可以重试，或用「下载内置示例」继续使用示例数据。' +
        (location.protocol === 'file:' ? '<br>当前为 file:// 打开，跨域请求会被拦截，建议用本地 http 服务。' : ''));
      logLine('✗ ' + msg, 'err');
      showRetry(true);
      toast('抓取失败：' + msg);
    } finally {
      setBusy(false);
      state.abort = null;
    }
  }


  /* ---------- 矢量瓦片抓取（自定义 bbox / 无离线数据的预置城市） ---------- */
  async function doFetchVector(bbox, includeService) {
    if (state.busy) return { ok: false, aborted: false, reason: 'busy' };
    var plan = chooseVectorZoom(bbox);
    if (plan.range.count > MAX_VTILES) {
      return { ok: false, aborted: false, reason: '范围过大（需要 ' + plan.range.count + ' 块瓦片），请缩小区域' };
    }
    var km = bboxKm(bbox);
    state.abort = { aborted: false, controllers: [] };
    clearLog();
    setProgress(0);
    showRetry(false);
    setBusy(true);
    setStatusHtml('矢量瓦片抓取中… <b>[progress 0 / ' + plan.range.count + ']</b>');
    logLine('矢量瓦片：' + fmtBboxShort(bbox) + '（约 ' + km.w.toFixed(1) + ' × ' + km.h.toFixed(1) + ' km）');
    logLine('zoom z' + plan.z + ' · 瓦片 ' + plan.range.nx + ' × ' + plan.range.ny + ' = ' +
      plan.range.count + ' 块 · 并发 ' + TILE_CONCURRENCY + ' · 先 VersaTiles，失败换 OpenFreeMap');
    var t0 = performance.now();
    try {
      var res = await fetchAllVectorTiles(plan, bbox, includeService);
      var elapsed = performance.now() - t0;
      if (res.failed.length) {
        logLine('! ' + res.failed.length + ' 块瓦片失败（部分路网可能缺失）', 'warn');
      }
      var srcDetail = describeVectorSources(res.sources);
      if (!res.ways.length) {
        var reason = res.aborted ? '已取消，没有取得瓦片数据'
          : (res.failed.length ? '瓦片请求失败：' + res.failed[0].message : '当前区域没有匹配的道路数据');
        setStatusHtml('<span class="err">' + escapeHtml(reason) + '</span>');
        logLine('✗ ' + reason, res.aborted ? 'warn' : 'err');
        return { ok: false, aborted: !!res.aborted, reason: reason };
      }
      var vLabels = null;
      if (res.labels && (res.labels.roads.length || res.labels.places.length || res.labels.pois.length || res.labels.waters.length)) {
        vLabels = res.labels;
      }
      state.ready = {
        ways: res.ways,
        bbox: bbox.slice(),
        label: labelForRegion(),
        source: 'vector',
        sourceDetail: srcDetail,
        slug: slugForRegion(),
        fetchMs: elapsed,
        tiles: plan.range.count,
        zoom: plan.z,
        labels: vLabels,
        version: state.ready.version + 1
      };
      state.geom = { key: '', data: null };
      state.projCache = null;
      state.labelGeomCache = null;
      renderPreview();
      setProgress(1);
      if (res.aborted) {
        setStatusHtml('已取消：保留已取得的 <b>' + fmtInt(res.ways.length) + '</b> 条道路（' +
          srcDetail + ' · ' + (elapsed / 1000).toFixed(1) + ' s）。');
        logLine('已取消，保留 ' + res.ways.length + ' 条道路', 'warn');
        toast('已取消：保留已取得的 ' + fmtInt(res.ways.length) + ' 条道路');
      } else {
        setStatusHtml('矢量瓦片抓取完成：<b>' + fmtInt(res.ways.length) + '</b> 条道路 · ' + srcDetail +
          ' · z' + plan.z + ' · ' + plan.range.count + ' 块 · 用时 ' + (elapsed / 1000).toFixed(1) + ' s。');
        logLine('完成：' + res.ways.length + ' 条道路 · ' + srcDetail + ' · ' + (elapsed / 1000).toFixed(1) + ' s', 'ok');
        toast('矢量瓦片抓取完成：' + fmtInt(res.ways.length) + ' 条道路（' + (elapsed / 1000).toFixed(1) + ' s）');
      }
      return { ok: true, aborted: !!res.aborted };
    } catch (err) {
      var msg = describeError(err);
      logLine('✗ 矢量瓦片：' + msg, 'err');
      return { ok: false, aborted: false, reason: msg };
    } finally {
      setBusy(false);
      state.abort = null;
    }
  }

  /* 「获取道路数据」总入口：预置城市离线数据 → 矢量瓦片 → Overpass 兜底 */
  async function doFetch() {
    if (state.busy) return;
    if (!state.region) { toast('请先选择区域'); return; }
    var bbox = state.region;
    var km = bboxKm(bbox);
    if (km.w > 120 || km.h > 120) {
      toast('范围过大（约 ' + km.w.toFixed(0) + ' × ' + km.h.toFixed(0) + ' km），请缩小到 120 km 以内');
      return;
    }
    var includeService = $('optService').checked;
    // 1) 预置城市：有内置离线数据就直接秒开（点按钮 = 重新加载内置数据）
    if (state.mode === 'preset' && state.cityKey && cityIndexHas(state.cityKey)) {
      var loaded = await tryLoadOfflineCity(state.cityKey);
      if (loaded) {
        toast('已使用内置离线数据（秒开）；在线抓取请改用「自定义 bbox」或「名称搜索」。', 3600);
        return;
      }
    }
    // 2) 矢量瓦片
    var vr = await doFetchVector(bbox, includeService);
    if (vr && (vr.ok || vr.aborted)) return;
    // 3) Overpass 兜底
    logLine('矢量瓦片不可用（' + ((vr && vr.reason) || '未知原因') + '），回退 Overpass 兜底…', 'warn');
    setStatusHtml('矢量瓦片不可用，正在回退 Overpass 兜底…');
    await doFetchOverpass(true);
  }

  function cancelFetch() {
    if (!state.busy || !state.abort) return;
    state.abort.aborted = true;
    setStatusHtml('正在取消…（保留已取得的数据）');
    state.abort.controllers.forEach(function (c) { try { c.abort(); } catch (e) { } });
  }

  function labelForRegion() {
    if (state.mode === 'preset' && CITY_MAP[state.cityKey]) return CITY_MAP[state.cityKey].name;
    if (state.mode === 'search') return state.searchLabel || '搜索结果';
    return '自定义范围';
  }
  function slugForRegion() {
    if (state.mode === 'preset' && CITY_MAP[state.cityKey]) return CITY_MAP[state.cityKey].key;
    if (state.mode === 'search') return 'search';
    return 'custom-bbox';
  }

  /* ---------- Nominatim 名称搜索 ---------- */
  async function doSearch() {
    if (state.searchBusy) return;
    var q = ($('searchInput').value || '').trim();
    if (!q) { toast('请输入地名或城市名'); $('searchInput').focus(); return; }
    state.searchBusy = true;
    $('btnSearch').disabled = true;
    setStatusHtml('正在用 Nominatim 搜索「' + escapeHtml(q) + '」…');
    try {
      var url = NOMINATIM + '?' + new URLSearchParams({
        format: 'json', q: q, limit: '6',
        'accept-language': 'zh-CN,zh,en', addressdetails: '0'
      }).toString();
      var res = await fetch(url, { mode: 'cors', credentials: 'omit', headers: { 'Accept': 'application/json' } });
      if (!res.ok) throw new Error('Nominatim HTTP ' + res.status);
      var arr = await res.json();
      showSearchResults(arr);
      if (arr && arr.length) {
        var firstSel = document.querySelector('#searchResults li button');
        if (firstSel) firstSel.click();
        $('searchResults').hidden = false;   // 自动选中后仍保留列表，方便改选
        setStatusHtml('搜索完成：' + arr.length + ' 个结果，已采用第一个结果的 bbox；如果不对，请从下方列表改选，再点「获取道路数据」。');
      } else {
        setStatusHtml('搜索完成：没有找到匹配结果，换个写法试试（例如加上省份或国家）。');
      }
    } catch (err) {
      var msg = describeError(err);
      setStatusHtml('<span class="err">地名搜索失败：' + escapeHtml(msg) + '</span><br>' +
        '可以直接使用预置城市，或在「自定义 bbox」里输入范围。');
      logLine('✗ Nominatim：' + msg, 'err');
      toast('地名搜索失败：' + msg);
    } finally {
      state.searchBusy = false;
      $('btnSearch').disabled = false;
    }
  }

  function showSearchResults(arr) {
    var ul = $('searchResults');
    if (!ul) return;
    ul.innerHTML = '';
    if (!arr || !arr.length) {
      ul.innerHTML = '<li class="rm-hint" style="margin:0">没有找到匹配结果，换个写法试试（例如加上省份或国家）。</li>';
      ul.hidden = false;
      return;
    }
    for (var i = 0; i < arr.length; i++) {
      (function (r) {
        var bb = (r.boundingbox || []).map(Number);
        if (bb.length !== 4 || !bb.every(function (v) { return isFinite(v); })) return;
        // Nominatim boundingbox 顺序：南纬, 北纬, 西经, 东经
        var bbox = [bb[0], bb[2], bb[1], bb[3]];
        var li = document.createElement('li');
        var btn = document.createElement('button');
        btn.type = 'button';
        var nameEl = document.createElement('span');
        nameEl.className = 'res-name';
        nameEl.textContent = (r.display_name || '').split(',')[0] || '未命名';
        var subEl = document.createElement('span');
        subEl.className = 'res-bbox';
        var dn = r.display_name || '';
        subEl.textContent = dn.length > 72 ? dn.slice(0, 72) + '…' : dn;
        btn.appendChild(nameEl);
        btn.appendChild(subEl);
        btn.addEventListener('click', function () {
          setRegion(bbox, (r.display_name || '').split(',')[0] || '搜索结果', 'search',
            { searchLabel: (r.display_name || '').split(',')[0] || '搜索结果' });
          resetReadyData();
          drawSourceBadge('vector');
          ul.hidden = true;
          setStatusHtml('已选中「' + escapeHtml(nameEl.textContent) + '」。点「获取道路数据」用矢量瓦片抓取（失败自动回退 Overpass）。');
        });
        li.appendChild(btn);
        ul.appendChild(li);
      })(arr[i]);
    }
    ul.hidden = false;
  }

  /* ---------- 偏好存取 ---------- */
  function savePrefs() {
    try {
      localStorage.setItem('xz-roadmap-prefs', JSON.stringify({
        cityKey: state.cityKey,
        mode: state.mode,
        palette: state.palette,
        width: state.width,
        pngScale: state.pngScale,
        includeService: $('optService') ? $('optService').checked : true,
        labelsRoad: !!state.labelsRoad,
        labelsPlace: !!state.labelsPlace,
        exportScope: state.exportScope,
        markerMode: !!state.markerMode,
        region: state.region,
        regionLabel: state.regionLabel,
        searchLabel: state.searchLabel
      }));
    } catch (e) { }
  }
  function loadPrefs() {
    var prefs = null;
    try { prefs = JSON.parse(localStorage.getItem('xz-roadmap-prefs') || 'null'); } catch (e) { }
    if (!prefs) return null;
    if (prefs.palette && PALETTES[prefs.palette]) state.palette = prefs.palette;
    if ([1600, 2400, 3200].indexOf(Number(prefs.width)) >= 0) state.width = Number(prefs.width);
    if ([2, 3].indexOf(Number(prefs.pngScale)) >= 0) state.pngScale = Number(prefs.pngScale);
    if ($('optService') && typeof prefs.includeService === 'boolean') $('optService').checked = prefs.includeService;
    if (typeof prefs.labelsRoad === 'boolean') state.labelsRoad = prefs.labelsRoad;
    if (typeof prefs.labelsPlace === 'boolean') state.labelsPlace = prefs.labelsPlace;
    if (prefs.exportScope === 'view' || prefs.exportScope === 'full') state.exportScope = prefs.exportScope;
    if (typeof prefs.markerMode === 'boolean') state.markerMode = prefs.markerMode;
    return prefs;
  }

  /* ---------- 界面绑定 ---------- */
  function buildCitySelect() {
    var sel = $('citySelect');
    if (!sel) return;
    var prev = sel.value;
    sel.innerHTML = '';
    for (var i = 0; i < CITIES.length; i++) {
      var opt = document.createElement('option');
      opt.value = CITIES[i].key;
      opt.textContent = CITIES[i].name + (cityIndexHas(CITIES[i].key) ? '（内置）' : '（在线）');
      sel.appendChild(opt);
    }
    if (prev && CITY_MAP[prev]) sel.value = prev;
  }

  /* 用 cities/index.js 的信息重建城市列表（没有索引时保留硬编码 17 城） */
  function rebuildCityMapFromIndex(idx) {
    var list = [];
    var map = {};
    for (var i = 0; i < idx.length; i++) {
      var it = idx[i];
      if (!it || !it.slug || !it.name || !it.bbox || it.bbox.length !== 4) continue;
      var city = {
        key: it.slug,
        name: it.name,
        bbox: it.bbox.slice(),
        zoom: it.zoom || 0,
        bytes: it.bytes || 0,
        ways: it.ways || 0,
        offline: true
      };
      list.push(city);
      map[city.key] = city;
    }
    if (!list.length) return;
    CITIES = list;
    CITY_MAP = map;
  }

  function switchTab(tab) {
    state.mode = tab;
    var tabs = document.querySelectorAll('.rm-tab');
    for (var i = 0; i < tabs.length; i++) {
      var active = tabs[i].getAttribute('data-tab') === tab;
      tabs[i].classList.toggle('active', active);
      tabs[i].setAttribute('aria-selected', active ? 'true' : 'false');
    }
    var panels = document.querySelectorAll('.rm-tab-panel');
    for (var j = 0; j < panels.length; j++) {
      panels[j].hidden = panels[j].getAttribute('data-panel') !== tab;
    }
    var names = { preset: '预置城市', search: '名称搜索', bbox: '自定义 bbox' };
    if ($('modeStep')) $('modeStep').textContent = names[tab] || '';
  }

  function bindUI() {
    // 主题按钮已绑定
    // tabs
    var tabs = document.querySelectorAll('.rm-tab');
    for (var i = 0; i < tabs.length; i++) {
      tabs[i].addEventListener('click', function (ev) {
        if (state.busy) return;
        var t = ev.currentTarget.getAttribute('data-tab');
        if (t === 'preset' && !state.region) applyPresetCity($('citySelect').value);
        switchTab(t);
      });
    }
    // 预置城市
    $('citySelect').addEventListener('change', function () {
      if (state.busy) return;
      applyPresetCity($('citySelect').value);
    });
    // 名称搜索
    $('btnSearch').addEventListener('click', doSearch);
    $('searchInput').addEventListener('keydown', function (ev) {
      if (ev.key === 'Enter') { ev.preventDefault(); doSearch(); }
    });
    // 自定义 bbox
    var modes = document.querySelectorAll('input[name="bboxmode"]');
    for (var m = 0; m < modes.length; m++) {
      modes[m].addEventListener('change', function () {
        var center = document.querySelector('input[name="bboxmode"]:checked').value === 'center';
        $('bboxEdges').hidden = center;
        $('bboxCenter').hidden = !center;
      });
    }
    $('btnApplyBbox').addEventListener('click', applyCustomBbox);
    // 抓取
    $('btnFetch').addEventListener('click', doFetch);
    var retryBtn = $('btnRetry');
    if (retryBtn) retryBtn.addEventListener('click', doFetch);
    $('btnCancel').addEventListener('click', cancelFetch);
    // 配色
    var pals = document.querySelectorAll('.rm-palette');
    for (var p = 0; p < pals.length; p++) {
      pals[p].addEventListener('click', function (ev) {
        var key = ev.currentTarget.getAttribute('data-palette');
        if (!PALETTES[key]) return;
        state.palette = key;
        syncPaletteButtons();
        renderPreview();
        savePrefs();
      });
    }
    // 宽度 / PNG 倍率
    $('optWidth').addEventListener('change', function () {
      state.width = parseInt($('optWidth').value, 10) || 2400;
      renderPreview();
      savePrefs();
    });
    $('optPngScale').addEventListener('change', function () {
      state.pngScale = parseInt($('optPngScale').value, 10) || 2;
      savePrefs();
    });
    $('optService').addEventListener('change', savePrefs);
    // 导出
    $('btnSvg').addEventListener('click', downloadSvg);
    $('btnPng').addEventListener('click', downloadPng);
    $('btnCopy').addEventListener('click', copySvg);
    $('btnSample').addEventListener('click', downloadSample);
    // 地图交互：缩放 / 平移 / 标记
    bindMapInteractions();
    var mp = $('modePointer'), mm = $('modeMarker');
    if (mp) mp.addEventListener('click', function () { setMarkerMode(false); });
    if (mm) mm.addEventListener('click', function () { setMarkerMode(true); });
    var zin = $('btnZoomIn'), zout = $('btnZoomOut'), zfit = $('btnZoomFit');
    if (zin) zin.addEventListener('click', function () { zoomCenter(1.5); });
    if (zout) zout.addEventListener('click', function () { zoomCenter(1 / 1.5); });
    if (zfit) zfit.addEventListener('click', function () { resetView(); applyView(true); toast('已适应全图'); });
    // 名称开关
    var orn = $('optRoadNames'), opn = $('optPlaceNames');
    function labelsChanged() {
      if (!state.ready.ways.length) return;
      savePrefs();
      updateLabelsNow(viewRect());
      updatePreviewMeta(ensureGeom(), bboxKm(state.ready.bbox));
    }
    if (orn) orn.addEventListener('change', function () { state.labelsRoad = orn.checked; labelsChanged(); });
    if (opn) opn.addEventListener('change', function () { state.labelsPlace = opn.checked; labelsChanged(); });
    // 导出范围
    var scope = $('optExportScope');
    if (scope) scope.addEventListener('change', function () {
      state.exportScope = scope.value === 'full' ? 'full' : 'view';
      savePrefs();
    });
    // 标记点面板
    var list = $('markerList');
    if (list) list.addEventListener('click', function (ev) {
      var b = ev.target.closest('button');
      if (!b) return;
      var idx = parseInt(b.getAttribute('data-idx'), 10);
      var act = b.getAttribute('data-act');
      if (act === 'del') deleteMarker(idx);
      else if (act === 'copy') {
        var m = state.markers[idx];
        if (m) copyText(m.lat.toFixed(6) + ', ' + m.lon.toFixed(6), '已复制经纬度（纬度, 经度）');
      }
    });
    var clr = $('btnClearMarkers');
    if (clr) clr.addEventListener('click', clearMarkers);
    // 窗口尺寸变化后重新布局视图
    var _rs = 0;
    window.addEventListener('resize', function () {
      clearTimeout(_rs);
      _rs = setTimeout(function () { if ($('mapSvg')) applyView(true); }, 140);
    });
    // file:// 提示
    if (location.protocol === 'file:') {
      var n = $('envNotice');
      if (n) {
        n.hidden = false;
        n.innerHTML = '<b>当前是 file:// 直接打开的页面：</b>在线数据抓取（矢量瓦片 / Overpass）会被浏览器的跨域（CORS）策略拦截；' +
          '<b>预置城市的内置离线数据仍可正常使用</b>。要在线抓取任意地区，请在站点根目录运行 ' +
          '<code>python -m http.server 8000</code>，然后访问 ' +
          '<code>http://localhost:8000/works/roadmap-svg/</code>。';
      }
    }
  }

  function syncPaletteButtons() {
    var pals = document.querySelectorAll('.rm-palette');
    for (var i = 0; i < pals.length; i++) {
      var on = pals[i].getAttribute('data-palette') === state.palette;
      pals[i].classList.toggle('active', on);
      pals[i].setAttribute('aria-checked', on ? 'true' : 'false');
    }
  }

  /* ---------- 内置示例 ---------- */
  function loadSample() {
    var S = window.ROADMAP_SAMPLE;
    if (!S || !S.ways || !S.ways.length) {
      var host = $('mapView');
      if (host) host.innerHTML = '<div class="rm-empty">内置示例数据缺失（sample-data.js 未加载）。<br>仍可选择区域并联网抓取。</div>';
      return;
    }
    state.sample = S;
    state.ready = {
      ways: S.ways.map(function (w) { return { g: w[0], c: w[1] }; }),
      bbox: S.bbox.slice(),
      label: S.label,
      source: 'sample',
      slug: 'sample-taiyuan',
      fetchMs: 0,
      tiles: 0,
      labels: null,
      version: state.ready.version + 1
    };
    state.geom = { key: '', data: null };
    state.projCache = null;
    state.labelGeomCache = null;
    renderPreview();
    logLine('已加载内置示例：' + S.label + '（' + fmtInt(S.ways.length) + ' 条道路，真实 OSM 数据快照）', 'ok');
    logLine('提示：选择区域后点「获取道路数据」，即可抓取任意地区的路网。');
  }

  /* ---------- 初始化 ---------- */
  function init() {
    readThemePaletteDefault();
    buildCitySelect();
    var prefs = loadPrefs();
    syncPaletteButtons();
    if ($('optWidth')) $('optWidth').value = String(state.width);
    if ($('optPngScale')) $('optPngScale').value = String(state.pngScale);
    if ($('optExportScope')) $('optExportScope').value = state.exportScope;
    bindUI();
    setMarkerMode(state.markerMode);
    syncPaletteButtons();
    // URL 参数优先：?city=beijing / ?bbox=s,w,n,e / ?palette=light
    var urlApplied = false;
    try {
      var params = new URLSearchParams(location.search);
      var urlCity = params.get('city');
      var urlBbox = params.get('bbox');
      var urlPalette = params.get('palette');
      if (urlPalette && PALETTES[urlPalette]) state.palette = urlPalette;
      if (urlCity && CITY_MAP[urlCity]) {
        applyPresetCity(urlCity);
        switchTab('preset');
        urlApplied = true;
      } else if (urlBbox) {
        var bb = urlBbox.split(',').map(Number);
        if (!validateBBox(bb)) {
          setRegion(bb.map(round5), 'URL 指定范围', 'bbox', { syncInputs: true });
          switchTab('bbox');
          urlApplied = true;
        }
      }
    } catch (e) { }
    // 默认区域：URL 参数 > 上次选择 > 太原
    var restored = urlApplied;
    if (!urlApplied && prefs && prefs.region && !validateBBox(prefs.region) && prefs.mode) {
      setRegion(prefs.region, prefs.regionLabel || '上次选择', prefs.mode, {
        cityKey: prefs.cityKey || state.cityKey,
        searchLabel: prefs.searchLabel || '',
        syncInputs: true
      });
      if (prefs.mode === 'preset' && CITY_MAP[prefs.cityKey]) {
        state.cityKey = prefs.cityKey;
        $('citySelect').value = prefs.cityKey;
      }
      switchTab(prefs.mode);
      restored = true;
    }
    if (!restored) {
      applyPresetCity('taiyuan');
      switchTab('preset');
    }
    loadSample();
    setStatusHtml('就绪。当前显示内置示例数据（' + fmtInt(state.ready.ways.length) +
      ' 条道路）。预置城市会自动加载内置离线数据；其它区域点「获取道路数据」用矢量瓦片抓取。');
    renderPreview();
    savePrefs();
    // 异步加载预置城市离线索引；成功则重建城市列表并按需秒开默认城市
    ensureCityIndex().then(function (idx) {
      rebuildCityMapFromIndex(idx);
      buildCitySelect();
      if (state.mode === 'preset' && state.cityKey) {
        if ($('citySelect')) $('citySelect').value = state.cityKey;
        tryLoadOfflineCity(state.cityKey).then(function (ok) {
          if (!ok) renderPreview();
        });
      } else {
        renderPreview();
      }
      updateRegionInfo();
    }).catch(function () {
      /* 没有 cities/index.js：保持硬编码 17 城 + 在线抓取 */
      logLine('未找到 cities/index.js（预置城市离线数据未生成），已回退为在线抓取模式。', 'warn');
      buildCitySelect();
      updateRegionInfo();
    });
  }

  function readThemePaletteDefault() {
    // 用户显式保存过配色就用保存的；否则跟随站点明暗主题
    state.palette = document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light';
    try {
      var raw = localStorage.getItem('xz-roadmap-prefs');
      if (raw) {
        var prefs = JSON.parse(raw);
        if (prefs && prefs.palette && PALETTES[prefs.palette]) state.palette = prefs.palette;
      }
    } catch (e) { }
  }

  // 供调试/自动化测试使用（只读辅助）
  window.ROADMAP = {
    state: state,
    ensureGeom: ensureGeom,
    svgFromGeom: svgFromGeom,
    doFetch: doFetch,
    doFetchVector: doFetchVector,
    doFetchOverpass: doFetchOverpass,
    setRegion: setRegion,
    applyPresetCity: applyPresetCity,
    loadSample: loadSample,
    ensureCityIndex: ensureCityIndex,
    tryLoadOfflineCity: tryLoadOfflineCity,
    loadCityOffline: loadCityOffline,
    decodeMvt: decodeMvt,
    mapMvtProps: mapMvtProps,
    chooseVectorZoom: chooseVectorZoom,
    tileRangeForBbox: tileRangeForBbox,
    viewRect: viewRect,
    resetView: resetView,
    zoomAt: zoomAt,
    zoomCenter: zoomCenter,
    applyView: applyView,
    setMarkerMode: setMarkerMode,
    updateMarkerPanel: updateMarkerPanel,
    composeSvg: composeSvg,
    labelsAvailable: labelsAvailable,
    buildLabelsSvg: buildLabelsSvg,
    _internals: { extractTileData: extractTileData, offlineCityWays: offlineCityWays, parseOfflineLabels: parseOfflineLabels },
    getSvg: function (scope) { return composeSvg(scope || state.exportScope, state.width).svg; },
    getFullSvg: function () { return composeSvg('full', state.width).svg; },
    getCsvStats: function () {
      var g = ensureGeom();
      return { totalWays: state.ready.ways.length, width: g.width, height: g.height, counts: g.counts.slice() };
    }
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
