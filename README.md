# 学哲玩 · logic-x

> 但行好事，莫问前程。

一个物理学生的个人档案库：**学习**、**哲思**、**玩笑**。

在线地址：**https://logicx200.github.io/**

这里存放我读过的、算过的、写过的东西——量子力学与统计物理的课程笔记、几篇科普，
以及这几年用 AI 一起"vibecoding"出来的小工具与网页实验。
原先的 Hexo + NexT 主题已经退役，现在整站是一套**纯静态 HTML / CSS / 原生 JS**，
没有框架、没有 CDN、没有评论区、没有埋点，双击就能打开。

---

## 目录结构

```
index.html                首页：最近文章 / 精选作品 / 关于
notes/
  index.html              文章列表（按年份分组，可搜索、按科目筛选）
  <slug>/index.html       文章正文（7 篇）
works/
  index.html              作品索引（36 个作品，可搜索/筛选/排序）
  legacy/index.html       早期 Python 工具箱（保留 Hexo 时期的截图档案）
  <slug>/...              每个作品的源码、文档与可在线试玩页面
about/index.html          关于
404.html                  找不到页面时（「这一页大概是被波函数隧穿了」）
assets/
  css/site.css            全站样式（纸白 / 墨黑 / 单一墨绿强调色，明暗双主题）
  js/site.js              主题切换、搜索筛选排序、图片失效降级
  js/katex/               自托管的 KaTeX（公式渲染，不依赖任何 CDN）
  img/                    文章配图、作品封面、旧项目截图
data/                     站点数据（文章元信息与正文、作品清单、关于页文案）
docs/                     全量文件清单与上传说明（见下）
build.mjs                 零依赖构建脚本
```

## 本地预览

```bash
# 方式一：起个本地服务（推荐，路径行为与线上一致）
python -m http.server 8000
# 然后打开 http://127.0.0.1:8000/

# 方式二：直接双击 index.html
```

## 新增或修改内容

站点的页面由 `build.mjs` 从 `data/` 生成，改完数据重跑一条命令即可（Node ≥ 18，无需安装依赖）：

```bash
node build.mjs
```

- **加一篇文章**：在 `data/notes.json` 的 `posts` 里加一条（`body` 写 HTML，公式用 `$...$` / `$$...$$`），
  然后 `node build.mjs`。
- **改作品**：`data/works.json`（页面同时读取 `data/works.js`，两者保持同内容）。
- **改关于页**：`data/about.json`。

也可以完全不用构建脚本：直接编辑 `notes/<slug>/index.html`，效果一样。

## docs/ 里的两份清单

本站的"作品"是从本机工作区 `F:\DeepSeek工作区`（11081 个文件 / 14.4 GB）里**筛选**出来的：

| 文件 | 内容 |
| --- | --- |
| `docs/inventory.md` | 按目录分组的全量清单：每个条目有多少文件、多大、去了哪、为什么没上传 |
| `docs/inventory.csv` | 逐文件清单（11081 行）：相对路径、字节、修改时间、是否上传、发布路径、跳过原因 |
| `docs/upload-manifest.md` | 每个作品从源体积到发布体积的裁剪明细 |

未上传的主要是：仿真原始输出（`.plt` 单文件最大 2 GB）、HITRAN 谱线库、浏览器缓存与相册原图、
交付压缩包——它们超过 GitHub 单文件 100 MB 的限制，或属于可重新生成的中间数据。

## 技术说明

- **零框架**：没有 Hexo / Jekyll / React / Tailwind，GitHub Pages 直接托管静态文件（`.nojekyll` 关闭 Jekyll）。
- **零外部请求**：字体用系统字体栈，公式用自托管 KaTeX，页面加载完不再请求任何第三方域名。
- **渐进增强**：关掉 JavaScript，文章列表与正文依然完整可读；搜索、筛选、主题切换只是增强。
- **旧链接兼容**：原 Hexo 的 `/2025/...`、`/2026/...`、`/archives/`、`/categories/`、`/tags/`、`/projects/`
  都保留了 meta-refresh 跳转页，老文章的分享链接不会失效。

## 版权

文章与作品内容归作者所有；引用或转载请注明出处。代码部分随缘取用。
