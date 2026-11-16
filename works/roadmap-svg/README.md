# 城市路网 SVG 底图生成器

在线工具：选一座城市 / 搜一个地名 / 输入任意经纬度范围，得到一张**不含文字标注**的矢量路网底图；
预览支持**缩放平移、标记点、道路/地标名称开关**；支持浅色 / 深色 / 透明三种配色，
SVG 与 PNG 一键导出**当前视图**（或全图）。适合做海报底纹、示意图背景或数据可视化底图。

- 在线版（GitHub Pages）：`/works/roadmap-svg/`
- 本地预览（矢量瓦片 / Overpass / Nominatim 需要 http 环境；预置城市在 `file://` 下也能用）：

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

「① 选择区域」标题处有数据源徽标（`内置数据` / `矢量瓦片` / `Overpass 兜底`）；
「统计与图例」里的「数据源」一行显示具体来源（如 `矢量瓦片 · VersaTiles · z14`）。

### 预置城市（29 座，离线可用）

北京、上海、广州、深圳、成都、重庆、西安、武汉、杭州、南京、天津、苏州、长沙、郑州、青岛、
大连、厦门、济南、合肥、福州、昆明、沈阳、太原、石家庄、洛阳、长治、晋中、邯郸、宝鸡。

- 路网约 23.8 万条、名称约 2 万条；总大小约 12.5 MB（单城 77 KB–782 KB）。
- 坐标量化 `q=25000`（约 3.5 m 精度），`lon = w + x/q`，`lat = s + y/q`；几何已 Douglas-Peucker 简化。
- 名称字段：`labels.roads`（沿线摆放线 + kind）、`labels.places`（区/街道/村庄）、
  `labels.pois`（地铁/公交站/POI）、`labels.waters`（湖/河/水系）。
- 太原：7,928 条道路 / 1,162 条名称；北京：16,811 条道路 / 2,046 条名称。

### 矢量瓦片（自定义区域）

- 按 bbox 尺寸自动选 zoom：跨度 ≤3 km→z15、≤8 km→z14、≤20 km→z13、≤50 km→z12、≤100 km→z11
  （上限 z14；块数超过 36 时自动降 zoom）。
- 浏览器内**自研 MVT 解码器**（protobuf varint/zigzag + geometry 命令流），同时兼容：
  - **Shortbread**（VersaTiles）：道路 `streets`（`kind`）；名称 `street_labels`、`place_labels`、
    `public_transport`、`water_lines_labels`、`water_polygons_labels`；
  - **OpenMapTiles**（OpenFreeMap）：道路 `transportation`（`class`+`subclass`）；名称
    `transportation_name`、`place`、`poi`、`waterway`。
- 单块先请求 VersaTiles，失败自动换 OpenFreeMap；整片都失败才回退 Overpass。
- 并发 6、进度 `[progress i / N]`、可取消并保留已取得的部分；跨瓦片重复几何/名称按坐标与名称去重。

### Overpass 兜底

对 bbox 分块（目标 0.09°，最多 24 块），逐块请求 `way["highway"~"..."]` + `out geom;`，
失败重试并轮换公共端点；名字来自 `name` 标签（仅道路名，无地标名）。

## 预览交互

### 缩放 / 平移

- **滚轮**以光标为中心缩放（1×–16×，已阻止页面滚动）；**拖拽**平移（阈值 3px，避免误触）；
  **双击**放大一级；工具条上有 `− / +`、`适应` 与当前倍数（如 `2.3×`）。
- 道路线宽保持地图单位（放大后变粗属正常）；**文字与标记点的尺寸按屏幕像素自适应**
  （道路名 11–13 px、地标 10–13 px、标记环半径约 6 px），放大后依然可读。
- 缩放/平移结束后自动**重新排版名称**：可见范围变小，能容纳更多名称（贪心避让重算）。

### 标记点

- 工具条切到 `标记` 模式（光标变十字）：点击地图添加标记；点击已有标记删除（hover 显示 `标记 N（点击删除）`）。
- 样式与地图风格一致、**不含文字/阴影/emoji**：细描边空心圆环 + 中心实心小点 + 4 向小刻度，
  颜色取当前配色主墨色（浅色底=深墨、深色底=浅墨、透明底=深墨）。
- 侧栏「③ 标记点」列出编号、经纬度（6 位小数，可复制）、单独删除、清空全部；顺序按添加时间。
- 标记随缩放/平移正确变换，导出 SVG / PNG 会包含（`<g class="markers">`，`<desc>` 注明数量）。
- 标记按城市或 bbox 分别保存在 `localStorage`，刷新/重开页面自动恢复。

### 名称开关（默认都关）

- `道路名称`：沿道路方向用 `<text><textPath>` 排版，带描边光晕（`paint-order="stroke"`，光环取底色）；
  字号按道路等级 11–13 px；**贪心避让**（已放置文字框与新的重叠就跳过），优先级：等级高 → 名称短。
- `地标名称`：区域/街道/村庄、地铁/公交/POI、湖/河/水系三类；点位上居中排版，站点/水系带小空心点；
  字号分级（区 > 站点 > 水系）；同样避让。
- 两个开关互不影响（只控制各自类别）；一次最多显示约 260 条，按优先级取舍；只绘制落在当前
  视野（viewBox）内的名称，放大后自动重新排版显示更多。
- 导出时按开关决定是否包含文字；SVG 文字使用系统字体栈并写全 `font-family`，可复制/再编辑。

## 抓取与渲染原理

对每个 bbox 分块，向 Overpass API 发送如下查询（与 `python/roadmap_svg.py` 中的查询一致）：

```overpassql
[out:json][timeout:60];
way["highway"~"^(motorway|motorway_link|trunk|trunk_link|primary|primary_link|secondary|secondary_link|tertiary|tertiary_link|residential|unclassified|living_street|service)$"]
  (南纬,西经,北纬,东经);
out geom;
```

- 公共端点轮换：`overpass-api.de` → `overpass.kumi.systems` → `overpass.osm.ch` → `overpass.private.coffee`。
- 投影为 Web Mercator：`x = (rad(lon)-xmin)/spanX*width`，`y = (ymax-ln(tan(π/4+rad(lat)/2)))/spanY*height`，
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
  带 `viewBox`、深浅色带背景 / 透明配色不带背景、`<desc>` 含 ODbL 署名与标记/名称数量）。
- 导出范围：默认**当前视图**（缩放/平移后的 viewBox），可切换「全图」；文件名带视图后缀
  （如 `taiyuan-dark-2.3x.svg` / `taiyuan-dark-full.svg`）。
- PNG 导出用 canvas 光栅化同一份 SVG（2×/3×，最长边 8192 px、总像素约 3600 万，超限自动降倍率）。

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

- 路网与名称数据：© [OpenStreetMap](https://www.openstreetmap.org/) contributors，按
  [ODbL 1.0](https://opendatacommons.org/licenses/odbl/) 使用。二次分发请保留署名与许可链接。
- 矢量瓦片服务：[VersaTiles](https://versatiles.org/)（[Shortbread](https://shortbread-tiles.org/) schema）、
  [OpenFreeMap](https://openfreemap.org/)（[OpenMapTiles](https://openmaptiles.org/) schema）。
- 兜底查询：[Overpass API](https://overpass-api.de/)。地名搜索：[Nominatim](https://nominatim.openstreetmap.org/)
  （遵循其[使用政策](https://operations.osmfoundation.org/policies/nominatim/)，只在点击搜索时发一次请求）。
- 预置城市数据（路网 + 名称）为构建时从公共矢量瓦片抓取，随站点分发。
- 页面加载本身只请求本站静态资源；只有用户点击后才会访问上述公共服务。

## 文件结构

```
works/roadmap-svg/
├─ index.html            工具页面（UI + 样式）
├─ app.js                全部逻辑：MVT 解码、瓦片/Overpass 抓取、离线城市加载、投影、视图、标记、名称、导出
├─ cities/
│  ├─ index.js           29 城索引（slug/name/bbox/zoom/ways/labels/bytes）
│  └─ <slug>.js × 29     离线路网 + labels（坐标量化 q=25000）
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
| 预览 | 无（直接看导出的静态 SVG） | 缩放/平移/双击/适应、标记点、道路/地标名称开关 |
| 渲染 | 离线 SVG 拼接，深色/浅色两种 | 浏览器内即时渲染，浅色/深色/透明三种；名称带光晕与贪心避让 |
| 输出 | `out/<城市>-道路-深色.svg`（全图） | 当前视图或全图；SVG / PNG / 复制源码；含标记与名称 |

保留不变的核心：Web Mercator 投影、按道路等级分组线宽、粗线先画细线后画、**默认无任何文字标注**。

## 自测记录（本机 2026-11，Edge headless + CDP）

- 预置城市离线：太原 7,928 条（416 KB，含 1,162 条名称）约 0.4 s 出图；北京 16,811 条（含 2,046 条名称）
  约 0.14 s；`file://` 下同样可用（无 CORS 请求），名称/标记/缩放均正常，刷新后标记恢复。
- 名称开关：太原全图视野约 95 条（道路 32 条沿路 + 地标 63 条），道路名字号 11–13 屏幕像素；
  放大 2.3× 后自动重排为 119 条；北京全图 2,046 条名称按优先级取 156 条（上限 260）。
- 标记点：标记模式加 3 个、点标记删 1 个、列表删 1 个、刷新恢复、清空；标记环屏幕半径 6 px；
  导出 SVG 含 `<g class="markers">` 与 `<desc> markers: 3`。
- 导出：当前视图 2.3× 的 SVG 约 456 KB（含 119 条文字 / 3 个标记）、2× PNG 4800×3216 约 5.2 MB
  （PNG 中名称与标记均正确光栅化，无 `<image>`/外链）；全图导出 viewBox `0 0 2400 2400`。
- 性能：太原全图名称排版 + 渲染在 1 帧内完成；北京开启名称后仍可交互（缩放/平移只更新 viewBox，
  名称在 130 ms 防抖后重排）。

## 已知限制

- 矢量瓦片 / Nominatim 是公共免费服务，可能限流或临时不可用，页面会自动切换 / 重试并提示原因。
- 自定义范围很大（>50 km）时瓦片自动降 zoom，路网会更概略；Overpass 兜底可能很慢。
- 名称一次最多约 260 条（贪心避让），极密集区域会主动舍弃部分低优先级名称。
- 标记点保存在浏览器 `localStorage`，按城市 / bbox 区分；清理浏览器数据会丢失。
- 只在用户点击后抓取，浏览器端不落盘缓存；重复加载同一自定义区域会重新请求瓦片。
- 只取道路中心线与名称，不含建筑、水系、绿地等其它要素的几何。
- PNG 导出受浏览器 canvas 尺寸限制，超长图会自动限制倍率。
- `works/index.html` 的作品列表需要在 `data/works.js` 里登记本页（站点构建流程的一部分）。
