# 原版 Python 工具链（未改动）

这里的脚本是「城市路网 SVG 底图生成器」的原始桌面版实现，从早期项目目录原样复制，
仅用于存档与对照。网页版（上级目录 `index.html` + `app.js`）保留了它们的核心思路：
分块向 Overpass API 请求道路、Web Mercator 投影、按道路等级分组线宽、输出**无文字标注**的 SVG。

## 文件

| 文件 | 作用 |
| --- | --- |
| `roadmap_svg.py` | 主脚本：按城市 bbox 分块抓取 Overpass（`way["highway"~...]` + `out geom;`），按 way id 去重，逐块缓存到 `data/cache/`，失败重试；用 Web Mercator 投影后把道路按等级分组拼成 SVG，输出深色/浅色两种配色。城市与 bbox 写死在 `CITIES` 字典里。 |
| `render_from_geojson.py` | 从 BBBike 导出的 `.geojson.xz` 离线渲染 SVG，逻辑与主脚本一致，额外支持 `service`/步行道等等级；`NOISE` 集合用于「纯道路」模式。 |
| `preview.py` | 用 Pillow 从同一份数据画 PNG 预览，便于快速看路网形态（依赖 Pillow）。 |
| `download_bbbike.py` | 轮询并下载 BBBike 已触发好的 extract（含 20 分钟超时）。 |
| `trigger_bbbike.py` | 向 BBBike 提交自定义 bbox 的提取请求（网页表单自动化）。 |
| `preview_太原.png` / `preview_南京.png` | 原版把太原、南京数据画出来的预览图（Pillow 生成）。 |

## 原版用法

```bash
# 需要 Python 3 与标准库；preview.py 需要 Pillow
python roadmap_svg.py
python render_from_geojson.py --inspect --roads-only
python preview.py
```

输出落在脚本同目录的 `out/`：`<城市>-道路-深色.svg`、`<城市>-道路-浅色.svg`。

## 与网页版的关系

- 相同的：分块抓取与重试、Overpass 查询语句、Web Mercator 投影、按等级分线宽、无标注、
  2400 px 基准画布、粗线先画细线后画。
- 网页版新增：任意地区（预置 17 城 / Nominatim 搜索 / 自定义 bbox）、浅色/深色/透明三配色、
  SVG/PNG/复制源码导出、进度与取消、失败兜底、内置示例。
- 数据许可：OpenStreetMap contributors，ODbL 1.0。
