# 城市路网 SVG 底图生成器

在线工具：选一座城市 / 搜一个地名 / 输入任意经纬度范围，得到一张**不含任何文字标注**的
矢量路网底图，支持浅色 / 深色 / 透明三种配色，SVG 与 PNG 一键下载。

- 在线版（GitHub Pages）：`/works/roadmap-svg/`
- 本地预览（矢量瓦片 / Overpass 需要 http 环境；预置城市在 `file://` 下也能用）：

```bash
# 在仓库根目录执行
python -m http.server 8000
# 然后打开 http://localhost:8000/works/roadmap-svg/
```

> 页面本身零依赖、零第三方 JS 库（MVT 解析器是自研的）。**预置城市读随站点分发的离线数据，
> 打开即秒开**；自定义区域才需要联网抓矢量瓦片；Overpass 只作兜底。

---

## 三档数据源

| 档位 | 触发条件 | 数据来源 | 典型耗时 |
| --- | --- | --- | --- |
| ① 内置离线数据 | 选择预置城市（29 城） | `cities/<slug>.js`，构建时从 VersaTiles 矢量瓦片抓取、量化压缩后随站点分发 | 100–450 ms（本地脚本） |
| ② 矢量瓦片 | 自定义 bbox / 名称搜索 / 暂无离线数据的城市 | VersaTiles（Shortbread schema）→ OpenFreeMap（OpenMapTiles schema） | 1.5–3 s（6–30 块瓦片，并发 6） |
| ③ Overpass 兜底 | 上面两档都不可用 | Overpass API 公共实例（分块、重试、换端点） | 数十秒起，取决于公共实例负载 |

页面左上角的「① 选择区域」标题处有数据源徽标（`内置数据` / `矢量瓦片` / `Overpass 兜底`）；
「统计与图例」里的「数据源」一行会显示具体来源（如 `矢量瓦片 · VersaTiles · z14`）。

### ① 预置城市（29 座，离线可用）

北京、上海、广州、深圳、成都、重庆、西安、武汉、杭州、南京、天津、苏州、长沙、郑州、青岛、
大连、厦门、济南、合肥、福州、昆明、沈阳、太原、石家庄、洛阳、长治、晋中、邯郸、宝鸡。

- 共 23.8 万条道路、约 10.1 MB（单城 61 KB–660 KB，gzip 后约 20–230 KB）。
- 坐标量化 `q=25000`（约 3.5 m 精度），`lon = w + x/q`，`lat = s + y/q`；几何已 Douglas-Peucker 简化（3.5 m 容差）。
- 数据文件：`cities/index.js` + `cities/<slug>.js`（动态 `<script>` 注入，`file://` 下同样可用）。
- 太原 7,928 条 / 338 KB；北京 16,811 条 / 626 KB；上海 16,299 条 / 652 KB。

### ② 矢量瓦片（自定义区域）

- 按 bbox 尺寸自动选 zoom：跨度 ≤3 km→z15、≤8 km→z14、≤20 km→z13、≤50 km→z12、≤100 km→z11（上限 z14；块数超过 36 时自动降 zoom）。
- 浏览器内**自研 MVT 解码器**（protobuf varint/zigzag + geometry 命令流），同时兼容：
  - **Shortbread**（VersaTiles）：`streets` 图层，属性 `kind`（含 `_link` 归一化，`track`/`path`/`footway` 等忽略）；
  - **OpenMapTiles**（OpenFreeMap）：`transportation` 图层，属性 `class` + `subclass`（`minor` 由 `subclass` 细分到街巷）。
- 单块先请求 VersaTiles，失败自动换 OpenFreeMap；两块都失败时记录失败块，继续抓其它块；整片都失败才回退 Overpass。
- 并发 6，进度 `[progress i / N]`，可取消并保留已取得的部分；跨瓦片重复几何按坐标量化哈希去重。

### ③ Overpass 兜底

对 bbox 分块（目标 0.09°，最多 24 块），逐块请求 `way["highway"~"..."]` + `out geom;`，
失败重试并轮换公共端点（overpass-api.de → kumi.systems → osm.ch → private.coffee）。

## 使用流程

1. 选择区域（预置城市 / 名称搜索 / 自定义 bbox）。预置城市会立刻加载内置离线数据；
   其它区域会显示预计使用哪个 zoom、多少块瓦片。
2. 点「获取道路数据」：预置城市重新载入内置数据（秒开）；其它区域走矢量瓦片（失败自动回退 Overpass）。
   抓取中显示 `[progress i / N]`，可随时取消。
3. 右侧预览，「实际大小 / 适应」切换缩放；选配色、画布宽度、PNG 倍率。
4. 下载 SVG / PNG 或复制 SVG 源码。导出文件请保留署名：
   **数据 © OpenStreetMap contributors，ODbL 1.0**。

## 渲染与导出

- Web Mercator 投影（`x = (rad(lon)-xmin)/spanX*width`，`y = (ymax-ln(tan(π/4+rad(lat)/2)))/spanY*height`），
  画布宽度 1600 / 2400 / 3200 可选（2400 与 Python 原版一致），高度按 bbox 比例自动计算。
- 道路分 6 组，线宽以 2400 px 画布为基准：

| 组 | highway / MVT 属性 | 线宽（px @2400） |
| --- | --- | --- |
| 快速路 / 高速 | motorway, trunk（含 `_link`） | 3.8 |
| 主干道 | primary | 2.4 |
| 次干道 | secondary | 1.7 |
| 支路 | tertiary | 1.15 |
| 街巷 | unclassified, residential, living_street, minor | 0.8 |
| 服务道路 | service | 0.5 |

- 粗线先画、细线后画；导出 SVG 每级一个 `<path>`（`shape-rendering="geometricPrecision"`、
  带 `viewBox`、深浅色带背景 / 透明配色不带背景、`<desc>` 内含 ODbL 署名），坐标保留 1 位小数。
- PNG 用 canvas 2×/3× 导出（最长边 8192 px、总像素约 3600 万，超限自动降倍率）。

## URL 参数（可分享）

```
/works/roadmap-svg/?city=beijing&palette=light
/works/roadmap-svg/?bbox=37.855,112.545,37.885,112.585&palette=dark
```

- `city=` 取城市 slug（`beijing`、`shanghai`、`taiyuan`…，见 `cities/index.js`）
- `bbox=` 四至坐标：`南纬,西经,北纬,东经`
- `palette=` 取 `light` / `dark` / `transparent`
- URL 参数优先于浏览器记住的上次选择；页面不会自动在线抓取（预置城市会自动加载离线数据）。

## 数据来源与许可

- 路网数据：© [OpenStreetMap](https://www.openstreetmap.org/) contributors，按
  [ODbL 1.0](https://opendatacommons.org/licenses/odbl/) 使用。二次分发请保留署名与许可链接。
- 矢量瓦片服务：[VersaTiles](https://versatiles.org/)（[Shortbread](https://shortbread-tiles.org/) schema）、
  [OpenFreeMap](https://openfreemap.org/)（[OpenMapTiles](https://openmaptiles.org/) schema）。
- 兜底查询：[Overpass API](https://overpass-api.de/)。地名搜索：[Nominatim](https://nominatim.openstreetmap.org/)
  （遵循其[使用政策](https://operations.osmfoundation.org/policies/nominatim/)，只在点击搜索时发一次请求）。
- 预置城市数据为构建时从公共矢量瓦片抓取，随站点分发。
- 页面加载本身只请求本站静态资源；只有用户点击后才会访问上述公共服务。

## 文件结构

```
works/roadmap-svg/
├─ index.html            工具页面（UI + 样式）
├─ app.js                全部逻辑：MVT 解码、瓦片/Overpass 抓取、离线城市加载、投影、渲染、导出
├─ cities/
│  ├─ index.js           29 城索引（slug/name/bbox/zoom/ways/bytes）
│  └─ <slug>.js × 29     离线路网（坐标量化 q=25000，roads 按 cls 升序）
├─ sample-data.js        内置示例数据（太原五一广场周边，477 条真实 OSM 道路）
├─ sample-dark.svg       内置示例的深色导出成品（2400×2027，约 44 KB）
├─ README.md             本说明
└─ python/               原版 Python 工具链（未改动，见 python/README.md）
```

> 原 `out/` 目录里的太原/南京成品 SVG 均为 2.5–3.6 MB（>2 MB），按约定未收录；
> 这里改用 477 条道路的小范围示例 `sample-dark.svg` 作为「示例成品」。

## 与原版 Python 工具的差异

| | Python 原版 | 网页版 |
| --- | --- | --- |
| 数据获取 | 城市写死，分块请求 Overpass，落盘缓存 | 预置城市读离线数据（秒开）；自定义区域用矢量瓦片（MVT 自研解码）；Overpass 仅兜底 |
| 区域 | 修改 `CITIES` 字典 | 29 座内置城市 + Nominatim 搜索 + 自定义 bbox / 中心点+宽高 |
| 渲染 | 离线 SVG 拼接，深色/浅色两种 | 浏览器内即时渲染，浅色/深色/透明三种 |
| 输出 | `out/<城市>-道路-深色.svg` | `<slug>-<palette>.svg` / `.png`、复制源码 |
| 交互 | 命令行脚本 | 进度、取消、重试、数据源徽标、统计与图例、URL 参数 |

保留不变的核心：Web Mercator 投影、按道路等级分组线宽、粗线先画细线后画、**无任何文字标注**。

## 自测记录（本机 2026-11，Edge headless + CDP）

- 预置城市离线：太原 7,928 条（338 KB）约 0.4 s 出图；北京 16,811 条（626 KB）约 0.14 s；上海 16,299 条约 0.17 s；
  `file://` 下同样可用（无 CORS 请求）。
- 矢量瓦片：自定义 2.6×3.3 km（z14、6 块、并发 6）→ 513 条 / **1.7 s**（VersaTiles）；
  强制 VersaTiles 失败 → OpenFreeMap 583 条 / 1.5 s；两者都失败 → Overpass 兜底成功。
- 导出：北京 2400 px SVG 729 KB；2× PNG 4800×4800 / 9.3 MB。全流程无 console 异常。
- 页面加载阶段仅请求本站静态资源（`cities/index.js` 4 KB + 单城数据），不发出任何外部请求。

## 已知限制

- 矢量瓦片 / Nominatim 是公共免费服务，可能限流或临时不可用，页面会自动切换 / 重试并提示原因。
- 自定义范围很大（>50 km）时瓦片自动降 zoom，路网会更概略；Overpass 兜底可能很慢。
- 只在用户点击后抓取，浏览器端不落盘缓存；重复加载同一自定义区域会重新请求瓦片。
- 只取道路中心线，不含建筑、水系、绿地等其它要素。
- PNG 导出受浏览器 canvas 尺寸限制，超长图会自动限制倍率。
- `works/index.html` 的作品列表需要在 `data/works.js` 里登记本页（站点构建流程的一部分）。
