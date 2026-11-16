# 城市路网 SVG 底图生成器

在线工具：从 OpenStreetMap 抓取**任意城市 / 任意经纬度范围**的道路中心线，渲染成一张
**不含任何文字标注**的矢量路网底图，支持浅色 / 深色 / 透明三种配色，SVG 与 PNG 一键下载。

- 在线版（GitHub Pages）：`/works/roadmap-svg/`
- 本地预览（推荐，数据抓取需要 http 环境）：

```bash
# 在仓库根目录执行
python -m http.server 8000
# 然后打开 http://localhost:8000/works/roadmap-svg/
```

> 页面本身零依赖、可离线打开；但**抓取数据必须联网**。直接用 `file://` 双击打开时，
> 浏览器会把跨域请求判定为 CORS 失败（页面顶部会给出提示），此时仍可使用内置示例、
> 切换配色与导出。

---

## 功能

| 模块 | 说明 |
| --- | --- |
| 区域选择 | ① 预置 17 城（北京、上海、广州、深圳、成都、重庆、西安、武汉、杭州、南京、太原、石家庄、洛阳、长治、晋中、邯郸、宝鸡）；② Nominatim 地名搜索；③ 自定义 bbox（四至坐标，或「中心点 + 宽高 km」） |
| 数据抓取 | Overpass API 分块抓取，网格自动切分（单次最多 24 块）、显示 `[progress 3/16]`、失败自动重试并切换公共端点、可随时取消并保留已取得的部分 |
| 渲染 | Web Mercator 投影（按纬度做 cos 修正）；按 6 个道路等级分组、不同线宽与颜色；**不渲染任何路名/地名** |
| 配色 | 浅色、深色、透明背景（适合叠加到海报/图片上） |
| 导出 | 下载 SVG（含 `viewBox`、`shape-rendering="geometricPrecision"`、透明或指定背景）；下载 PNG（canvas 2×/3× 导出）；复制 SVG 源码 |
| 兜底 | 请求失败给出原因 + 重试 + 可继续使用/下载内置示例；内置示例打开页面即可见 |
| 细节 | 抓取中禁用按钮、进度条、范围过大提示、`localStorage` 记住上次城市与配色、明暗主题跟随站点 |

## 使用流程

1. 选择区域（预置城市 / 搜索 / 自定义 bbox），面板下方会显示 bbox、实际公里数与预计分块数。
2. 点「获取道路数据」。抓取按块进行，状态栏显示 `[progress i / N]`；可点「取消」保留已取得的数据。
3. 在右侧预览。点「实际大小 / 适应」可以在整图缩放与 1:1 像素之间切换。
4. 选配色、画布宽度、PNG 倍率，然后下载 SVG / PNG，或复制 SVG 源码。
5. 导出文件请保留署名：**数据 © OpenStreetMap contributors，ODbL 1.0**。

## URL 参数（可分享）

页面支持用 URL 参数直接打开某个区域/配色，例如：

```
/works/roadmap-svg/?city=beijing&palette=light
/works/roadmap-svg/?bbox=37.855,112.545,37.885,112.585&palette=dark
```

- `city=` 取预置城市的 key（`beijing`、`shanghai`、`taiyuan`……）
- `bbox=` 四至坐标：`南纬,西经,北纬,东经`
- `palette=` 取 `light` / `dark` / `transparent`
- URL 参数优先于浏览器里记住的上次选择；页面不会自动抓取，仍需点「获取道路数据」。

## 抓取与渲染原理

对每个 bbox 分块，向 Overpass API 发送如下查询（与 `python/roadmap_svg.py` 中的查询一致）：

```overpassql
[out:json][timeout:60];
way["highway"~"^(motorway|motorway_link|trunk|trunk_link|primary|primary_link|secondary|secondary_link|tertiary|tertiary_link|residential|unclassified|living_street|service)$"]
  (南纬,西经,北纬,东经);
out geom;
```

- 默认分块目标 0.09°（约 10 km），块数超过 24 时自动放大分块；范围超过约 120 km 会拒绝抓取。
- 公共端点按顺序轮换：`overpass-api.de` → `overpass.kumi.systems` → `overpass.osm.ch` → `overpass.private.coffee`，
  单块最多重试 3 次；HTTP 429/5xx 指数退避。
- 抓回来的每条 way 按 `id` 去重，只保留几何中心线；`_link` 归入所属等级。
- 投影为 Web Mercator：`x = (rad(lon)-xmin)/spanX*width`，`y = (ymax-ln(tan(π/4+rad(lat)/2)))/spanY*height`，
  画布宽度可选 1600 / 2400 / 3200 px（2400 与 Python 原版一致），高度按 bbox 比例自动计算。
- 道路等级分 6 组，线宽以 2400 px 画布为基准：

| 组 | highway 取值 | 线宽（px @2400） |
| --- | --- | --- |
| 快速路 / 高速 | motorway, trunk（含 `_link`） | 3.8 |
| 主干道 | primary（`_link`） | 2.4 |
| 次干道 | secondary（`_link`） | 1.7 |
| 支路 | tertiary（`_link`） | 1.15 |
| 街巷 | unclassified, residential, living_street, road | 0.8 |
| 服务道路 | service | 0.5 |

粗线先画、细线后画（与原版 `sorted(ROAD_WIDTH, key=-width)` 一致）；导出 SVG 每级一个
`<path>`，坐标保留 1 位小数。

## 数据来源与许可

- 路网数据：© [OpenStreetMap](https://www.openstreetmap.org/) contributors，通过
  [Overpass API](https://overpass-api.de/) 查询，按
  [ODbL 1.0](https://opendatacommons.org/licenses/odbl/) 使用。二次分发/再发布请保留署名与许可链接。
- 地名搜索：[Nominatim](https://nominatim.openstreetmap.org/)，遵循其
  [使用政策](https://operations.osmfoundation.org/policies/nominatim/)（本工具只在你点击搜索时发一次请求，不做自动补全）。
- 本工具只在**用户点击**后向上述公共服务发请求，页面加载本身不发任何外部请求。

## 文件结构

```
works/roadmap-svg/
├─ index.html            工具页面（UI + 样式）
├─ app.js                全部逻辑：投影、抓取、渲染、导出
├─ sample-data.js        内置示例数据（太原五一广场周边，477 条真实 OSM 道路，约 57 KB）
├─ sample-dark.svg       内置示例的深色导出成品（2400×2027，约 44 KB）
├─ README.md             本说明
└─ python/               原版 Python 工具链（未改动，见 python/README.md）
   ├─ roadmap_svg.py
   ├─ render_from_geojson.py
   ├─ preview.py
   ├─ download_bbbike.py
   ├─ trigger_bbbike.py
   ├─ preview_太原.png
   └─ preview_南京.png
```

> 原 `out/` 目录里的太原/南京成品 SVG 均为 2.5–3.6 MB（>2 MB），按约定未收录；
> 这里改用 477 条道路的小范围示例 `sample-dark.svg` 作为「示例成品」。

## 与原版 Python 工具的差异

| | Python 原版 | 网页版 |
| --- | --- | --- |
| 区域 | 城市字典写死在源码里（注释写「修改 CITIES 字典」） | 预置 17 城 + Nominatim 搜索 + 自定义 bbox |
| 数据 | 先分块下载到本地 `data/cache/`，再离线渲染 | 浏览器内即时抓取 → 渲染 → 导出，无落盘缓存 |
| 渲染 | matplotlib/纯 SVG 手写拼接，深色/浅色两种 | Canvas 预览 + SVG 同源几何，浅色/深色/透明三种 |
| 交互 | 命令行脚本 | 页面按钮：进度、取消、重试、配色、导出、统计 |
| 输出 | `out/<城市>-道路-深色.svg` | `<city>-<palette>.svg` / `.png`、复制源码 |
| 端点 | 4 个公共端点轮换 | 同样轮换 4 个端点 + 浏览器 CORS 约束下的重试逻辑 |

保留不变的核心：分块查询、Web Mercator 投影、按道路等级分组线宽、**无任何文字标注**。

## 已知限制

- Overpass / Nominatim 是公共免费服务，存在排队与限流；慢或临时 502 属正常现象，工具会自动重试并提示原因。
- 范围大于约 0.6°×0.6° 会明显变慢；单次抓取最多 24 块，超过 120 km 的范围会被拒绝。
- 只抓道路中心线，不包含建筑、水系、绿地等其它要素。
- PNG 导出受 canvas 尺寸限制（最长边 8192 px、总像素约 3600 万），过大时自动降低倍率。
- 浏览器端不做缓存，重复抓取同一区域会重新请求。
- 地名搜索依赖 Nominatim 的可达性；某些网络环境下无法访问时，请改用预置城市或自定义 bbox。
