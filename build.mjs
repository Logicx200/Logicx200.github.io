#!/usr/bin/env node
/* ==========================================================================
   学哲玩 · 纯静态站点生成器
   --------------------------------------------------------------------------
   用法：在站点根目录执行 `node build.mjs`
   读取同目录 data/ 下的只读数据：
     data/notes.json           文章（site / posts / subjects / categories）
     data/notes-summaries.json 可选：文章摘要 / 阅读时间补充
     data/works.js 或 .json    作品数据（window.INDEX_DATA）
     data/legacy.json          旧项目页数据
     data/about.json           关于页数据
   生成同目录下的页面：
     index.html、notes/index.html、notes/<slug>/index.html、works/index.html、
     works/legacy/index.html、about/index.html、404.html
   不清理、不改动 works/、docs/、assets/（内容与静态资源由人工维护）。
   数据缺失时脚本会直接报错并提示缺哪个文件，不做静默兜底。
   零依赖：只用 Node 内置模块。
   ========================================================================== */

import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';

const SITE = path.dirname(fileURLToPath(import.meta.url));
const DATA_DIR = path.join(SITE, 'data');

const warnings = [];
function warn(message) {
  warnings.push(message);
  console.log('  ! ' + message);
}

/* ---------- 基础工具 ---------- */

function esc(value) {
  return String(value === null || value === undefined ? '' : value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function pad2(value) {
  return String(value).padStart(2, '0');
}

function trim(value) {
  return typeof value === 'string' ? value.trim() : '';
}

function formatNumber(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return '—';
  return new Intl.NumberFormat('zh-CN').format(number);
}

function formatBytes(value) {
  const number = Number(value);
  if (!Number.isFinite(number) || number < 0) return '—';
  if (number < 1024) return Math.round(number) + ' B';
  const units = ['KB', 'MB', 'GB', 'TB'];
  let size = number / 1024;
  let index = 0;
  while (size >= 1024 && index < units.length - 1) {
    size /= 1024;
    index += 1;
  }
  const rounded = Math.round(size * 10) / 10;
  return (rounded % 1 === 0 ? String(rounded) : rounded.toFixed(1)) + ' ' + units[index];
}

function parseDateParts(raw) {
  const match = trim(raw).match(/^(\d{4})-(\d{1,2})-(\d{1,2})/);
  if (!match) return null;
  return { year: Number(match[1]), month: Number(match[2]), day: Number(match[3]) };
}

function longDate(raw) {
  const parts = parseDateParts(raw);
  if (!parts) return trim(raw) || '—';
  return parts.year + ' 年 ' + parts.month + ' 月 ' + parts.day + ' 日';
}

function compactDate(raw) {
  const parts = parseDateParts(raw);
  if (!parts) return trim(raw) || '—';
  return parts.year + '.' + pad2(parts.month) + '.' + pad2(parts.day);
}

function plainText(html) {
  return String(html || '')
    .replace(/<script[\s\S]*?<\/script>/gi, ' ')
    .replace(/<style[\s\S]*?<\/style>/gi, ' ')
    .replace(/<[^>]+>/g, ' ')
    .replace(/&nbsp;/g, ' ')
    .replace(/&emsp;/g, ' ')
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/\s+/g, ' ')
    .trim();
}

function truncate(text, max) {
  const value = String(text || '').trim();
  if (value.length <= max) return value;
  return value.slice(0, max).replace(/[，。、；：,.;:\s]+$/, '') + '…';
}

function readingMinutes(text) {
  const chars = String(text || '').replace(/\s+/g, '').length;
  return Math.max(1, Math.ceil(chars / 350));
}

function firstChar(text) {
  const value = trim(text);
  if (!value) return '·';
  return Array.from(value)[0] || '·';
}

function relPrefix(depth) {
  return '../'.repeat(depth);
}

function fileExistsInSite(relativePath) {
  const clean = trim(relativePath).replace(/^\/+/, '');
  if (!clean) return false;
  return fs.existsSync(path.join(SITE, clean));
}

function readJsonIfExists(filePath) {
  if (!fs.existsSync(filePath)) return null;
  try {
    return JSON.parse(fs.readFileSync(filePath, 'utf8'));
  } catch (error) {
    warn('无法解析 ' + path.relative(SITE, filePath) + '：' + error.message);
    return null;
  }
}

function normalizeText(value) {
  try {
    return String(value || '').normalize('NFKC').toLocaleLowerCase('zh-CN');
  } catch (error) {
    return String(value || '').toLowerCase();
  }
}

function decodeEntities(text) {
  return String(text || '')
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'");
}

/* 正文清洗：先保公式，再剥离旧 Hexo 主题残留（侧栏/页脚/脚本/图标等安全兜底） */
function cleanPostBody(body) {
  let html = String(body || '');

  /* 1) 旧 MathJax 的 <script type="math/tex"> 转成 KaTeX 定界符（新数据已经转换过，这里兜底） */
  html = html.replace(
    /<script\b[^>]*type=["']math\/tex;\s*mode=display["'][^>]*>([\s\S]*?)<\/script>/gi,
    (match, expression) => '\\[' + decodeEntities(expression) + '\\]'
  );
  html = html.replace(
    /<script\b[^>]*type=["']math\/tex["'][^>]*>([\s\S]*?)<\/script>/gi,
    (match, expression) => '\\(' + decodeEntities(expression) + '\\)'
  );

  /* 2) 去掉其余脚本 / 样式 / 外链 / 注释等不应出现在正文里的元素 */
  html = html.replace(/<!--[\s\S]*?-->/g, '');
  html = html.replace(/<script\b[\s\S]*?<\/script>/gi, '');
  html = html.replace(/<script\b[^>]*\/?\s*>/gi, '');
  html = html.replace(/<style\b[\s\S]*?<\/style>/gi, '');
  html = html.replace(/<link\b[^>]*>/gi, '');
  html = html.replace(/<meta\b[^>]*>/gi, '');

  /* 3) 旧主题残留：侧栏 / 页脚 / 遮罩 / 图标 / meta 小件 */
  html = html.replace(/<aside\b[\s\S]*?<\/aside>/gi, '');
  html = html.replace(/<footer\b[\s\S]*?<\/footer>/gi, '');
  html = html.replace(/<div[^>]*id="sidebar-dimmer"[^>]*>\s*<\/div>/gi, '');
  html = html.replace(/<i\b[^>]*class="[^"]*\bfa[ab]?\b[^"]*"[^>]*>\s*<\/i>/gi, '');
  html = html.replace(/<span[^>]*class="[^"]*(?:with-love|post-meta-item-icon)[^"]*"[^>]*>[\s\S]*?<\/span>/gi, '');
  html = html.replace(
    /<div[^>]*class="[^"]*(?:post-copyright|post-toc-wrap|post-footer|post-nav|comments)[^"]*"[^>]*>[\s\S]*?<\/div>\s*/gi,
    ''
  );

  /* 4) 去 headerlink 空锚点 */
  html = html.replace(/<a\b[^>]*class="[^"]*headerlink[^"]*"[^>]*>\s*<\/a>/gi, '');

  return html.replace(/[ \t]+\n/g, '\n').replace(/\n{3,}/g, '\n\n').trim();
}

/* 只有「正文第一个 h1 的纯文本 == 文章标题」时才删掉这个重复标题 */
function stripDuplicateTitle(html, title) {
  const match = html.match(/^\s*<h1\b[^>]*>([\s\S]*?)<\/h1>\s*/i);
  if (!match) return html;
  const headingText = normalizeText(plainText(match[1]));
  if (headingText && headingText === normalizeText(title)) {
    return html.slice(match[0].length);
  }
  return html;
}

function fixRootRelative(html, prefix) {
  return String(html || '')
    .replace(/\b(src|href)="\/(?!\/)([^"]*)"/g, (match, attribute, url) => {
      return attribute + '="' + prefix + url.replace(/^\/+/, '') + '"';
    })
    .replace(/\b(src|href)="((?:assets|images)\/[^"]*)"/g, (match, attribute, url) => {
      return attribute + '="' + prefix + url + '"';
    });
}

/* ---------- 文章数据 ---------- */

function loadNotesData() {
  const raw = readJsonIfExists(path.join(DATA_DIR, 'notes.json'));
  if (!raw) {
    throw new Error('缺少文章数据：请把 notes.json 放到 data/ 目录后重跑 node build.mjs');
  }
  const source = 'data/notes.json';

  const site = Object.assign({
    title: '学哲玩',
    tagline: '但行好事，莫问前程',
    owner: 'Logicx200',
    email: '1831665169@qq.com',
    github: 'https://github.com/logicx200',
    description: '学习 · 哲思 · 玩笑。一个物理学生的个人档案库。'
  }, raw.site || {});

  const summaries = readJsonIfExists(path.join(DATA_DIR, 'notes-summaries.json')) || {};
  const subjects = (Array.isArray(raw.subjects) ? raw.subjects : [])
    .map(trim).filter((subject) => subject && subject !== '全部');

  const posts = (Array.isArray(raw.posts) ? raw.posts : []).map((post) => {
    const slug = trim(post.slug) || slugify(post.title) || 'post';
    const body = String(post.body || '');
    const text = plainText(body);
    const extra = summaries[slug] || {};
    const summary = trim(post.summary) || trim(extra.summary) || truncate(text, 90);
    const minutes = Number(post.minutes) > 0
      ? Number(post.minutes)
      : (Number(extra.minutes) > 0 ? Number(extra.minutes) : readingMinutes(text));
    const date = trim(post.date) || trim(post.iso).slice(0, 10);
    return {
      slug,
      title: trim(post.title) || '未命名文章',
      date,
      iso: trim(post.iso) || date,
      subject: trim(post.subject) || '随笔',
      kind: trim(post.kind) || '文章',
      categories: (Array.isArray(post.categories) ? post.categories : []).map(trim).filter(Boolean),
      tags: (Array.isArray(post.tags) ? post.tags : []).map(trim).filter(Boolean),
      minutes,
      summary,
      body: stripDuplicateTitle(cleanPostBody(body), trim(post.title) || '')
    };
  }).filter((post) => post.slug);

  posts.sort((a, b) => String(b.iso).localeCompare(String(a.iso)));
  if (!posts.length) throw new Error('文章数据为空，无法生成站点');

  return { site, posts, subjects, source };
}

/* ---------- 作品数据 ---------- */

function normalizeRepo(rawRepo) {
  if (!rawRepo) return null;
  let owner = '';
  let name = '';
  let branch = '';
  if (typeof rawRepo === 'string') {
    const parts = rawRepo.replace(/^https?:\/\/github\.com\//i, '').replace(/\.git$/i, '').split('/');
    owner = parts[0] || '';
    name = parts[1] || '';
  } else {
    owner = trim(rawRepo.owner);
    name = trim(rawRepo.name);
    branch = trim(rawRepo.branch);
  }
  if (!owner || !name) return null;
  return { owner, name, branch: branch || 'main', base: 'https://github.com/' + owner + '/' + name };
}

function stripWorksPrefix(value) {
  let clean = trim(value).replace(/^\.?\//, '').replace(/^\/+/, '');
  clean = clean.replace(/^(?:works|projects)\//i, '');
  return clean;
}

function readWorksRaw() {
  const jsonPath = path.join(DATA_DIR, 'works.json');
  const jsPath = path.join(DATA_DIR, 'works.js');
  if (fs.existsSync(jsonPath)) {
    return { data: JSON.parse(fs.readFileSync(jsonPath, 'utf8')), source: 'data/works.json' };
  }
  if (fs.existsSync(jsPath)) {
    const text = fs.readFileSync(jsPath, 'utf8');
    const match = text.match(/window\.INDEX_DATA\s*=\s*([\s\S]*?);?\s*$/);
    if (!match) throw new Error('data/works.js 不是 window.INDEX_DATA = {...}; 形式');
    return { data: JSON.parse(match[1].replace(/;\s*$/, '')), source: 'data/works.js' };
  }
  throw new Error('缺少作品数据：请把 works.js 或 works.json 放到 data/ 目录后重跑 node build.mjs');
}

function loadWorksData() {
  const { data, source } = readWorksRaw();
  const categories = (Array.isArray(data.categories) ? data.categories : []).map((category, index) => ({
    id: trim(category.id) || 'category-' + index,
    name: trim(category.name) || trim(category.id) || '未分类'
  }));
  const categoryMap = {};
  categories.forEach((category) => { categoryMap[category.id] = category; });

  const repo = normalizeRepo(data.repo);
  if (!repo) warn('作品数据里没有可用的 repo 字段，将不生成 GitHub 源码链接。');

  const projects = (Array.isArray(data.projects) ? data.projects : [])
    .filter((item) => item && typeof item === 'object');

  function normalizeProject(project, index) {
    const dir = trim(project.dir);
    const slug = trim(project.id) || dir.split('/').filter(Boolean).pop() || 'work-' + index;
    const category = categoryMap[trim(project.category)]
      ? trim(project.category)
      : (categories[0] ? categories[0].id : 'misc');
    return {
      slug,
      dir: dir || ('works/' + slug),
      title: trim(project.title) || slug,
      subtitle: trim(project.subtitle),
      summary: trim(project.summary),
      category,
      categoryName: categoryMap[category] ? categoryMap[category].name : category,
      tags: (Array.isArray(project.tags) ? project.tags : []).map(trim).filter(Boolean),
      highlights: (Array.isArray(project.highlights) ? project.highlights : []).map(trim).filter(Boolean),
      tech: (Array.isArray(project.tech) ? project.tech : []).map(trim).filter(Boolean),
      cover: stripWorksPrefix(project.cover),
      demo: stripWorksPrefix(project.demo),
      entry: stripWorksPrefix(project.entry),
      featured: project.featured === true,
      published: project.published !== false,
      publishedFiles: Number(project.publishedFiles),
      publishedBytes: Number(project.publishedBytes),
      sourceFiles: Number(project.sourceFiles),
      sourceBytes: Number(project.sourceBytes),
      excludeReason: trim(project.excludeReason),
      excludeNote: trim(project.excludeNote),
      order: index
    };
  }

  const all = projects.map(normalizeProject);
  const published = all.filter((project) => project.published);
  const unpublished = all.filter((project) => !project.published);
  published.forEach((project, index) => { project.order = index; });

  const demoWorks = published.filter((project) => project.demo && fileExistsInSite('works/' + project.demo));
  const featured = published.filter((project) => project.featured);
  const featuredFallback = !featured.length;

  return { repo, categories, published, unpublished, demoWorks, featured, featuredFallback, source };
}

/* ---------- 关于 / 旧项目数据 ---------- */

function loadAboutData(site) {
  const about = readJsonIfExists(path.join(DATA_DIR, 'about.json')) || {};
  return {
    title: trim(about.title) || '关于',
    heading: trim(about.heading),
    paragraphs: (Array.isArray(about.paragraphs) ? about.paragraphs : []).map(trim).filter(Boolean),
    nameParts: (about.name && Array.isArray(about.name.parts) ? about.name.parts : []).map(trim).filter(Boolean),
    image: trim(about.image).replace(/^\/+/, ''),
    imageCaption: trim(about.imageCaption),
    note: trim(about.note),
    contact: Object.assign({
      email: site.email,
      qq: '',
      github: site.github
    }, about.contact || {})
  };
}

function loadLegacyData() {
  const raw = readJsonIfExists(path.join(DATA_DIR, 'legacy.json'));
  if (raw) {
    return {
      intro: trim(raw.intro),
      repo: trim(raw.repo),
      repoName: trim(raw.repoName),
      tools: (Array.isArray(raw.tools) ? raw.tools : []).map((tool, index) => ({
        name: trim(tool.name) || '未命名项目',
        slug: trim(tool.slug) || 'legacy-' + (index + 1),
        desc: trim(tool.desc),
        tech: trim(tool.tech),
        source: trim(tool.source),
        demo: trim(tool.demo),
        images: (Array.isArray(tool.images) ? tool.images : []).map((image) => trim(image).replace(/^\/+/, '')).filter(Boolean)
      })),
      stats: raw.stats || {},
      contact: raw.contact || {}
    };
  }
  warn('data/legacy.json 不存在，早期项目页将显示空列表。');
  return { intro: '', repo: '', repoName: '', tools: [], stats: {}, contact: {} };
}

/* ---------- 作品卡片 ---------- */

function repoTreeUrl(repo, repoPath) {
  if (!repo) return '';
  const clean = trim(repoPath).replace(/^\/+|\/+$/g, '');
  if (!clean) return repo.base;
  const encoded = clean.split('/').map(encodeURIComponent).join('/');
  return repo.base + '/tree/' + encodeURIComponent(repo.branch) + '/' + encoded;
}

function coverHtml(project, prefix) {
  const glyph = esc(firstChar(project.title));
  const exists = project.cover && fileExistsInSite('works/' + project.cover);
  if (exists) {
    return '<div class="work-cover">' +
      '<img src="' + esc((prefix || '') + project.cover) + '" alt="" loading="lazy" decoding="async" data-cover>' +
      '<span class="cover-glyph" aria-hidden="true">' + glyph + '</span>' +
      '</div>';
  }
  return '<div class="work-cover is-fallback">' +
    '<span class="cover-glyph" aria-hidden="true">' + glyph + '</span>' +
    '</div>';
}

function workCardHtml(project, repo, options) {
  const opts = options || {};
  const prefix = opts.prefix || '';
  const id = opts.anchorId ? ' id="' + esc(project.slug) + '"' : '';
  const demo = project.demo && fileExistsInSite('works/' + project.demo) ? project.demo : '';
  const docPath = project.slug + '/README.html';
  const primary = demo || docPath;
  const searchText = normalizeText([project.title, project.subtitle, project.summary, project.tags.join(' ')].join(' '));

  const cover = coverHtml(project, prefix);
  const coverMarkup = primary
    ? '<a class="work-cover-link" href="' + esc(prefix + primary) + '" tabindex="-1" aria-hidden="true">' + cover + '</a>'
    : cover;

  const title = primary
    ? '<a href="' + esc(prefix + primary) + '">' + esc(project.title) + '</a>'
    : esc(project.title);

  const meta = ['<span>' + esc(project.categoryName) + '</span>'];
  if (Number.isFinite(project.publishedFiles)) meta.push('<span>' + formatNumber(project.publishedFiles) + ' 个文件</span>');
  if (Number.isFinite(project.publishedBytes)) meta.push('<span>' + formatBytes(project.publishedBytes) + '</span>');

  const sub = truncate(project.subtitle || project.summary, 70);

  const links = [];
  if (demo) links.push('<a class="is-demo" href="' + esc(prefix + demo) + '">在线试玩 ▶</a>');
  const sourceUrl = repoTreeUrl(repo, 'works/' + project.slug);
  if (sourceUrl) links.push('<a href="' + esc(sourceUrl) + '" target="_blank" rel="noopener noreferrer">源码 ↗</a>');
  links.push('<a href="' + esc(prefix + docPath) + '">说明文档</a>');

  return '<article class="work-card"' + id +
    ' data-search="' + esc(searchText) + '"' +
    ' data-category="' + esc(project.category) + '"' +
    ' data-size="' + (Number.isFinite(project.publishedBytes) ? project.publishedBytes : 0) + '"' +
    ' data-order="' + project.order + '"' +
    ' data-title="' + esc(project.title) + '">' +
    coverMarkup +
    '<h3 class="work-title">' + title + '</h3>' +
    (sub ? '<p class="work-sub">' + esc(sub) + '</p>' : '') +
    '<div class="work-meta">' + meta.join('') + '</div>' +
    (links.length ? '<div class="work-links">' + links.join('') + '</div>' : '') +
    '</article>';
}

/* ==========================================================================
   零依赖 Markdown 渲染器（README → HTML）
   - 支持：ATX/Setext 标题、段落、粗体/斜体/删除线、行内代码、围栏代码块、
     有序/无序列表（含嵌套）、表格（含对齐）、引用、分隔线、链接、图片、
     自动链接 <https://…>、行内 HTML 白名单透传
   - 安全：转义原始文本；行内 HTML 走白名单 + 属性过滤；URL 过滤 javascript: 等
   ========================================================================== */

const INLINE_HTML_TAGS = new Set([
  'a', 'abbr', 'b', 'br', 'code', 'del', 'em', 'i', 'img', 'ins', 'kbd',
  'mark', 's', 'small', 'span', 'strong', 'sub', 'sup', 'u', 'details', 'summary'
]);
const INLINE_HTML_ATTRS = new Set([
  'href', 'src', 'alt', 'title', 'class', 'width', 'height', 'align',
  'colspan', 'rowspan', 'id', 'name'
]);

function sanitizeMarkdownUrl(raw) {
  const url = trim(raw);
  if (!url) return '';
  if (/^(?:javascript|vbscript|data:text\/html)/i.test(url)) return '';
  return url;
}

function sanitizeRawHtmlTag(tag) {
  const match = String(tag).match(/^<\s*(\/?)\s*([a-zA-Z][a-zA-Z0-9]*)((?:\s[^<>]*)?)\s*\/?>$/);
  if (!match) return null;
  const closing = match[1] === '/';
  const name = match[2].toLowerCase();
  if (!INLINE_HTML_TAGS.has(name)) return null;
  if (closing) return '</' + name + '>';
  if (name === 'br') return '<br>';

  const attributes = [];
  const attrRe = /([a-zA-Z_:][-a-zA-Z0-9_:.]*)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'=<>`]+)))?/g;
  let attrMatch;
  while ((attrMatch = attrRe.exec(match[3] || ''))) {
    const attribute = attrMatch[1].toLowerCase();
    const value = attrMatch[2] !== undefined ? attrMatch[2]
      : (attrMatch[3] !== undefined ? attrMatch[3]
        : (attrMatch[4] !== undefined ? attrMatch[4] : ''));
    if (/^on/.test(attribute) || attribute === 'style') continue;
    if (!INLINE_HTML_ATTRS.has(attribute)) continue;
    if (attribute === 'href' || attribute === 'src') {
      const safe = sanitizeMarkdownUrl(decodeEntities(value));
      if (!safe) continue;
      attributes.push(attribute + '="' + esc(safe) + '"');
    } else {
      attributes.push(attribute + '="' + esc(decodeEntities(value)) + '"');
    }
  }
  const suffix = attributes.length ? ' ' + attributes.join(' ') : '';
  if (name === 'img') return '<img' + suffix + ' loading="lazy" decoding="async">';
  return '<' + name + suffix + '>';
}

function applyEmphasis(text) {
  let value = text;
  value = value.replace(/\*\*\*([^*\n]+)\*\*\*/g, '<strong><em>$1</em></strong>');
  value = value.replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>');
  value = value.replace(/__([^_\n]+)__/g, '<strong>$1</strong>');
  value = value.replace(/~~([^~\n]+)~~/g, '<del>$1</del>');
  value = value.replace(/(^|[^\w*])\*([^*\n]+)\*(?!\*)/g, '$1<em>$2</em>');
  value = value.replace(/(^|[^\w_])_([^_\n]+)_(?![\w_])/g, '$1<em>$2</em>');
  return value;
}

function renderInline(raw) {
  const tokens = [];
  function token(html) {
    tokens.push(html);
    return '\u0000T' + (tokens.length - 1) + '\u0000';
  }

  let text = String(raw === null || raw === undefined ? '' : raw);

  /* 硬换行：行尾两个空格或反斜杠 */
  text = text.replace(/[ \t]{2,}\n/g, function () { return token('<br>') + '\n'; });
  text = text.replace(/\\\n/g, function () { return token('<br>') + '\n'; });

  /* 行内代码 */
  text = text.replace(/`([^`\n]+)`/g, function (match, code) {
    return token('<code>' + esc(code) + '</code>');
  });

  /* 行内 HTML（白名单） */
  text = text.replace(/<\/?[a-zA-Z][^<>]*>/g, function (tag) {
    const sanitized = sanitizeRawHtmlTag(tag);
    return sanitized === null ? tag : token(sanitized);
  });

  /* 自动链接 <https://…> */
  text = text.replace(/<((?:https?:\/\/|mailto:)[^<>\s]+)>/g, function (match, url) {
    const safe = sanitizeMarkdownUrl(url);
    if (!safe) return match;
    return token('<a href="' + esc(safe) + '" target="_blank" rel="noopener noreferrer">' + esc(url) + '</a>');
  });

  /* 转义剩余文本 */
  text = esc(text);

  /* 反斜杠转义 */
  text = text.replace(/\\([\\`*_{}\[\]()#+\-.!~>|])/g, function (match, character) {
    return token(esc(character));
  });

  /* 图片 */
  text = text.replace(
    /!\[([^\]]*)\]\(\s*([^)\s]+)(?:\s+&quot;([^&]*)&quot;)?\s*\)/g,
    function (match, alt, source, title) {
      const safe = sanitizeMarkdownUrl(decodeEntities(source));
      if (!safe) return match;
      const image = '<img src="' + esc(safe) + '" alt="' + esc(decodeEntities(alt)) + '"' +
        (title ? ' title="' + esc(decodeEntities(title)) + '"' : '') +
        ' loading="lazy" decoding="async">';
      return token(image);
    }
  );

  /* 链接 */
  text = text.replace(
    /\[([^\]]+)\]\(\s*([^)\s]+)(?:\s+&quot;([^&]*)&quot;)?\s*\)/g,
    function (match, label, href, title) {
      const safe = sanitizeMarkdownUrl(decodeEntities(href));
      if (!safe) return match;
      const external = /^(?:https?:\/\/|mailto:)/i.test(safe);
      const attributes = ' href="' + esc(safe) + '"' +
        (title ? ' title="' + esc(decodeEntities(title)) + '"' : '') +
        (external ? ' target="_blank" rel="noopener noreferrer"' : '');
      return token('<a' + attributes + '>' + applyEmphasis(label) + '</a>');
    }
  );

  /* 其余强调 */
  text = applyEmphasis(text);

  /* 段内换行 → 空格 */
  text = text.replace(/\n+/g, ' ');

  /* 还原 token（允许嵌套） */
  let guard = 0;
  while (/\u0000T\d+\u0000/.test(text) && guard < 20) {
    text = text.replace(/\u0000T(\d+)\u0000/g, function (match, index) {
      return tokens[Number(index)] || '';
    });
    guard += 1;
  }
  return text;
}

function isAtxHeading(line) {
  return /^\s{0,3}#{1,6}\s+\S/.test(line);
}

function isFenceStart(line) {
  return /^\s{0,3}```+|^\s{0,3}~~~+/.test(line);
}

function isHorizontalRule(line) {
  return /^\s{0,3}(?:(?:\*\s*){3,}|(?:-\s*){3,}|(?:_\s*){3,})$/.test(line);
}

function isBlockquoteLine(line) {
  return /^\s{0,3}>/.test(line);
}

function isListLine(line) {
  return /^\s{0,3}(?:[-*+]|\d+[.)])\s+\S/.test(line);
}

function isSetextUnderline(line) {
  return /^\s{0,3}(?:=+|-+)\s*$/.test(line) && line.trim().length >= 2;
}

function splitTableRow(row) {
  let value = String(row).trim();
  if (value.startsWith('|')) value = value.slice(1);
  if (value.endsWith('|')) value = value.slice(0, -1);
  return value.split('|').map(function (cell) { return cell.trim(); });
}

function isTableStart(lines, index) {
  if (index + 1 >= lines.length) return false;
  if (lines[index].indexOf('|') === -1) return false;
  return /^\s{0,3}\|?\s*:?-{2,}:?\s*(?:\|\s*:?-{2,}:?\s*)+\|?\s*$/.test(lines[index + 1]);
}

function renderTable(lines, start) {
  const header = splitTableRow(lines[start]);
  const alignments = splitTableRow(lines[start + 1]).map(function (cell) {
    const left = cell.startsWith(':');
    const right = cell.endsWith(':');
    if (left && right) return 'center';
    if (right) return 'right';
    if (left) return 'left';
    return '';
  });
  let index = start + 2;
  const rows = [];
  while (index < lines.length && lines[index].trim() !== '' && lines[index].indexOf('|') !== -1) {
    rows.push(splitTableRow(lines[index]));
    index += 1;
  }
  function renderRow(cells, tag) {
    return '<tr>' + cells.map(function (cell, cellIndex) {
      const align = alignments[cellIndex];
      return '<' + tag + (align ? ' style="text-align:' + align + '"' : '') + '>' +
        renderInline(cell) + '</' + tag + '>';
    }).join('') + '</tr>';
  }
  const head = renderRow(header, 'th');
  const body = rows.map(function (row) { return renderRow(row, 'td'); }).join('');
  return {
    html: '<div class="table-container"><table><thead>' + head + '</thead>' +
      (body ? '<tbody>' + body + '</tbody>' : '') + '</table></div>',
    consumed: index - start
  };
}

function parseList(lines, start) {
  const first = String(lines[start]).match(/^(\s*)([-*+]|\d+[.)])\s+([\s\S]*)$/);
  const baseIndent = first[1].length;
  const ordered = /^\d/.test(first[2]);
  const items = [];
  let index = start;

  while (index < lines.length) {
    const heading = String(lines[index]).match(/^(\s*)([-*+]|\d+[.)])\s+([\s\S]*)$/);
    if (!heading) break;
    if (heading[1].length !== baseIndent) break;
    if (/^\d/.test(heading[2]) !== ordered) break;

    const itemLines = [heading[3]];
    index += 1;

    while (index < lines.length) {
      const line = lines[index];
      if (line.trim() === '') {
        let lookahead = index + 1;
        while (lookahead < lines.length && lines[lookahead].trim() === '') lookahead += 1;
        if (lookahead >= lines.length) break;
        const nextMatch = String(lines[lookahead]).match(/^(\s*)([-*+]|\d+[.)])\s+/);
        if (nextMatch && nextMatch[1].length >= baseIndent) {
          itemLines.push('');
          index += 1;
          continue;
        }
        break;
      }
      const nested = String(line).match(/^(\s*)([-*+]|\d+[.)])\s+/);
      if (nested) {
        if (nested[1].length > baseIndent) {
          itemLines.push(line);
          index += 1;
          continue;
        }
        break;
      }
      if (/^\s{2,}\S/.test(line)) {
        itemLines.push(line.trim());
        index += 1;
        continue;
      }
      itemLines.push(line.trim());
      index += 1;
    }
    items.push(itemLines);
  }

  const rendered = items.map(function (itemLines) {
    let splitIndex = -1;
    for (let lineIndex = 0; lineIndex < itemLines.length; lineIndex += 1) {
      const nested = String(itemLines[lineIndex]).match(/^(\s*)([-*+]|\d+[.)])\s+/);
      if (nested && nested[1].length > baseIndent) { splitIndex = lineIndex; break; }
    }
    const textLines = splitIndex === -1 ? itemLines : itemLines.slice(0, splitIndex);
    const nestedLines = splitIndex === -1 ? [] : itemLines.slice(splitIndex);
    const paragraphs = textLines.join('\n').split(/\n{2,}/).map(function (part) {
      return part.trim();
    }).filter(Boolean);
    let inner = '';
    if (nestedLines.length) {
      inner = parseList(nestedLines, 0).html;
    }
    let body;
    if (paragraphs.length > 1) {
      body = paragraphs.map(function (part) { return '<p>' + renderInline(part) + '</p>'; }).join('');
    } else {
      body = renderInline(paragraphs[0] || '');
    }
    return '<li>' + body + inner + '</li>';
  });

  return {
    html: (ordered ? '<ol>' : '<ul>') + rendered.join('') + (ordered ? '</ol>' : '</ul>'),
    consumed: index - start
  };
}

function renderMarkdown(source) {
  const lines = String(source === null || source === undefined ? '' : source)
    .replace(/\r\n?/g, '\n')
    .split('\n');
  const output = [];
  const usedHeadingIds = Object.create(null);
  let index = 0;

  /* GitHub 风格 heading id：保留字母/数字/下划线/连字符，空格转连字符 */
  function headingId(text) {
    let base = plainText(renderInline(text)).toLowerCase()
      .replace(/[^\p{L}\p{N}\s_-]/gu, '')
      .replace(/\s/g, '-');
    if (!base) base = 'section';
    let id = base;
    let counter = 1;
    while (usedHeadingIds[id]) {
      id = base + '-' + counter;
      counter += 1;
    }
    usedHeadingIds[id] = true;
    return id;
  }

  while (index < lines.length) {
    const line = lines[index];
    if (line.trim() === '') { index += 1; continue; }

    /* 围栏代码块 */
    const fence = line.match(/^\s{0,3}(```+|~~~+)\s*([^\s`]*)\s*$/);
    if (fence) {
      const marker = fence[1][0];
      const markerLength = fence[1].length;
      const lang = fence[2] || '';
      const codeLines = [];
      index += 1;
      while (index < lines.length) {
        const closed = String(lines[index]).match(/^\s{0,3}(```+|~~~+)\s*$/);
        if (closed && closed[1][0] === marker && closed[1].length >= markerLength) { index += 1; break; }
        codeLines.push(lines[index]);
        index += 1;
      }
      const langClass = lang ? ' class="language-' + esc(lang.replace(/[^\w#+.-]/g, '')) + '"' : '';
      output.push('<pre><code' + langClass + '>' + esc(codeLines.join('\n')) + '</code></pre>');
      continue;
    }

    /* ATX 标题 */
    const atx = line.match(/^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$/);
    if (atx) {
      const level = atx[1].length;
      output.push('<h' + level + ' id="' + esc(headingId(atx[2])) + '">' + renderInline(atx[2]) + '</h' + level + '>');
      index += 1;
      continue;
    }

    /* Setext 标题 */
    if (index + 1 < lines.length && isSetextUnderline(lines[index + 1]) && !isListLine(line) &&
      !isBlockquoteLine(line) && !isHorizontalRule(line)) {
      const level = lines[index + 1].trim().charAt(0) === '=' ? 1 : 2;
      output.push('<h' + level + ' id="' + esc(headingId(line.trim())) + '">' + renderInline(line.trim()) + '</h' + level + '>');
      index += 2;
      continue;
    }

    /* 分隔线 */
    if (isHorizontalRule(line)) { output.push('<hr>'); index += 1; continue; }

    /* 表格 */
    if (isTableStart(lines, index)) {
      const table = renderTable(lines, index);
      output.push(table.html);
      index += table.consumed;
      continue;
    }

    /* 引用 */
    if (isBlockquoteLine(line)) {
      const inner = [];
      while (index < lines.length) {
        const quoted = String(lines[index]).match(/^\s{0,3}>\s?([\s\S]*)$/);
        if (quoted) { inner.push(quoted[1]); index += 1; continue; }
        if (lines[index].trim() === '' && index + 1 < lines.length && isBlockquoteLine(lines[index + 1])) {
          inner.push('');
          index += 1;
          continue;
        }
        break;
      }
      output.push('<blockquote>' + renderMarkdown(inner.join('\n')) + '</blockquote>');
      continue;
    }

    /* 列表 */
    if (isListLine(line)) {
      const list = parseList(lines, index);
      output.push(list.html);
      index += list.consumed;
      continue;
    }

    /* 段落 */
    const paragraph = [line];
    index += 1;
    while (index < lines.length) {
      const next = lines[index];
      if (next.trim() === '') break;
      if (isAtxHeading(next) || isFenceStart(next) || isHorizontalRule(next) ||
        isTableStart(lines, index) || isBlockquoteLine(next) || isListLine(next)) break;
      paragraph.push(next);
      index += 1;
    }
    output.push('<p>' + renderInline(paragraph.join('\n')) + '</p>');
  }

  return output.join('\n');
}

/* README 标题处理：页头已有 h1。第一个 h1 与作品标题相同则去掉；
   其余情况把正文第一个 h1 降为 h2，保证页面只有一个 h1。 */
function normalizeReadmeTitle(markdown, title) {
  const lines = String(markdown).replace(/\r\n?/g, '\n').split('\n');
  let first = -1;
  for (let index = 0; index < lines.length; index += 1) {
    if (lines[index].trim() !== '') { first = index; break; }
  }
  if (first === -1) return markdown;
  const heading = lines[first].match(/^\s{0,3}#\s+(.*?)\s*#*\s*$/);
  if (!heading) return markdown;
  const headingText = normalizeText(plainText(renderInline(heading[1])).replace(/[*_`~]/g, ''));
  if (headingText && headingText === normalizeText(title)) {
    lines.splice(first, 1);
    return lines.join('\n');
  }
  lines[first] = lines[first].replace(/^(\s{0,3})#\s+/, '$1## ');
  return lines.join('\n');
}

/* ---------- 图片尺寸解析（PNG / JPEG / GIF / WebP / SVG） ---------- */

function parseImageSize(buffer, ext) {
  try {
    if (ext === '.png' && buffer.length > 24 &&
      buffer.readUInt32BE(0) === 0x89504e47 && buffer.readUInt32BE(4) === 0x0d0a1a0a) {
      return { width: buffer.readUInt32BE(16), height: buffer.readUInt32BE(20) };
    }
    if (ext === '.gif' && buffer.length > 10) {
      return { width: buffer.readUInt16LE(6), height: buffer.readUInt16LE(8) };
    }
    if (ext === '.jpg' || ext === '.jpeg') {
      let offset = 2;
      while (offset + 9 < buffer.length) {
        if (buffer[offset] !== 0xff) { offset += 1; continue; }
        const marker = buffer[offset + 1];
        if (marker >= 0xc0 && marker <= 0xcf &&
          marker !== 0xc4 && marker !== 0xc8 && marker !== 0xcc) {
          return {
            height: buffer.readUInt16BE(offset + 5),
            width: buffer.readUInt16BE(offset + 7)
          };
        }
        const length = buffer.readUInt16BE(offset + 2);
        if (!length) break;
        offset += 2 + length;
      }
    }
    if (ext === '.webp' && buffer.length > 30) {
      const chunk = buffer.toString('ascii', 12, 16);
      if (chunk === 'VP8X') {
        return {
          width: 1 + (buffer[24] | (buffer[25] << 8) | (buffer[26] << 16)),
          height: 1 + (buffer[27] | (buffer[28] << 8) | (buffer[29] << 16))
        };
      }
    }
    if (ext === '.svg') {
      const head = buffer.toString('utf8', 0, Math.min(buffer.length, 4096));
      const width = head.match(/\bwidth\s*=\s*["']?\s*([\d.]+)/i);
      const height = head.match(/\bheight\s*=\s*["']?\s*([\d.]+)/i);
      if (width && height) return { width: parseFloat(width[1]), height: parseFloat(height[1]) };
      const viewBox = head.match(/viewBox\s*=\s*["']\s*([-\d.]+)[\s,]+([-\d.]+)[\s,]+([-\d.]+)[\s,]+([-\d.]+)/i);
      if (viewBox) return { width: parseFloat(viewBox[3]), height: parseFloat(viewBox[4]) };
    }
  } catch (error) { /* 解析失败按未知处理 */ }
  return null;
}

/* ---------- 作品说明页 / 图集 ---------- */

const README_NAMES = ['README.md', 'readme.md', 'Readme.md', 'README.MD', 'README_交付说明.md', 'README.txt', 'readme.txt'];
const GALLERY_EXTS = new Set(['.png', '.jpg', '.jpeg', '.webp', '.gif', '.svg']);
const GALLERY_SKIP_DIRS = new Set([
  'node_modules', '__pycache__', '.git', '.cache', '.npm-cache', '.venv', 'venv',
  '.pytest_cache', '.mypy_cache', 'dist', 'build', 'site-packages', '.idea', '.vscode'
]);
const GALLERY_ICON_RE = /icon|logo|favicon|sprite|badge|avatar|emoji|thumb/i;
const GALLERY_GOOD_RE = /fig|figure|图|result|preview|效果|曲线|对比|output|plot|chart|demo|screen|screenshot|cover/i;

function findReadmeFile(projectDir, entry) {
  const entryPath = trim(entry);
  if (entryPath && /\.(?:md|txt)$/i.test(entryPath)) {
    const relative = entryPath.replace(/^(?:works|projects)\//i, '');
    const absolute = path.join(SITE, 'works', relative.replace(/^\/+/, ''));
    if (fs.existsSync(absolute) && fs.statSync(absolute).isFile()) {
      return { absolute, name: path.basename(absolute) };
    }
  }
  for (const name of README_NAMES) {
    const absolute = path.join(projectDir, name);
    if (fs.existsSync(absolute) && fs.statSync(absolute).isFile()) {
      return { absolute, name };
    }
  }
  return null;
}

/* 正文配图少于 3 张时，从作品目录挑最多 8 张「有意义」的图 */
function collectGalleryImages(projectDir, referencePaths) {
  const referenced = new Set((referencePaths || []).map(function (item) {
    return String(item).replace(/^\.\//, '').split('#')[0].replace(/\\/g, '/');
  }));
  const seen = new Set();
  const candidates = [];

  function walk(directory, depth) {
    let entries;
    try {
      entries = fs.readdirSync(directory, { withFileTypes: true });
    } catch (error) {
      return;
    }
    entries.sort(function (a, b) { return a.name.localeCompare(b.name, 'zh-CN'); });
    for (const entry of entries) {
      const full = path.join(directory, entry.name);
      if (entry.isDirectory()) {
        if (!GALLERY_SKIP_DIRS.has(entry.name)) walk(full, depth + 1);
        continue;
      }
      const ext = path.extname(entry.name).toLowerCase();
      if (!GALLERY_EXTS.has(ext)) continue;
      if (GALLERY_ICON_RE.test(entry.name)) continue;
      let stat;
      try { stat = fs.statSync(full); } catch (error) { continue; }
      if (!stat.isFile() || stat.size < 20 * 1024 || stat.size > 3 * 1024 * 1024) continue;
      const relative = path.relative(projectDir, full).split(path.sep).join('/');
      if (referenced.has(relative)) continue;

      let buffer;
      try { buffer = fs.readFileSync(full); } catch (error) { continue; }
      const size = parseImageSize(buffer, ext);
      if (size && (size.width < 300 || size.height < 160)) continue;
      if (size && (size.width / size.height < 0.35 || size.width / size.height > 3.6)) continue;
      const digest = crypto.createHash('sha1').update(buffer).digest('hex');
      if (seen.has(digest)) continue;
      seen.add(digest);

      const named = GALLERY_GOOD_RE.test(relative);
      const sizePreference = stat.size >= 60 * 1024 && stat.size <= 1.6 * 1024 * 1024 ? 1 : 0;
      const depthPreference = depth === 0 ? 3 : (depth === 1 ? 2 : (depth === 2 ? 1 : 0));
      candidates.push({
        relative,
        name: entry.name,
        size: stat.size,
        score: (named ? 4 : 0) + sizePreference * 2 + depthPreference
      });
    }
  }

  walk(projectDir, 0);
  candidates.sort(function (a, b) {
    return b.score - a.score || b.size - a.size || a.relative.localeCompare(b.relative, 'zh-CN');
  });
  return candidates.slice(0, 8);
}

function buildFallbackDocBody(project) {
  const parts = [];
  if (project.summary) parts.push('<p>' + esc(project.summary) + '</p>');
  if (project.highlights.length) {
    parts.push('<h2>要点</h2><ul>' + project.highlights.map(function (item) {
      return '<li>' + renderInline(item) + '</li>';
    }).join('') + '</ul>');
  }
  if (project.tech.length) {
    parts.push('<h2>技术栈</h2><p>' + project.tech.map(function (item) {
      return '<span class="tag">' + esc(item) + '</span>';
    }).join(' ') + '</p>');
  }
  if (!parts.length) parts.push('<p>这个作品暂时没有更详细的文字说明。</p>');
  return parts.join('\n');
}

function workDocDemoHref(project) {
  if (!project.demo || !fileExistsInSite('works/' + project.demo)) return '';
  const relative = path.posix.relative(project.slug, project.demo);
  if (!relative || relative.startsWith('..')) return project.demo;
  return relative;
}

function renderGallery(images) {
  if (!images.length) return '';
  const items = images.map(function (image) {
    return '<figure class="work-gallery-item">' +
      '<a href="' + esc(image.relative) + '"><img src="' + esc(image.relative) + '" alt="' +
      esc(image.name) + '" loading="lazy" decoding="async"></a>' +
      '<figcaption>' + esc(image.name) + '</figcaption>' +
      '</figure>';
  }).join('\n');
  return '<section class="work-gallery" aria-labelledby="work-gallery-title">' +
    '<h2 class="work-gallery-title" id="work-gallery-title">图集</h2>' +
    '<p class="work-gallery-note">正文配图较少，以下从项目目录挑选了 ' + images.length + ' 张图片。</p>' +
    '<div class="work-gallery-grid">' + items + '</div>' +
    '</section>';
}

/* README 里指向发布副本中不存在的本地文件时，降级为不可点击的说明文字，避免死链 */
function sanitizeDocTargets(html, projectDir) {
  let missing = 0;

  function localTargetExists(url) {
    const raw = decodeEntities(url).split('#')[0].split('?')[0];
    if (!raw || /^(?:https?:\/\/|mailto:|data:|javascript:)/i.test(raw) || raw.startsWith('#')) return true;
    const candidates = [raw];
    try { candidates.push(decodeURIComponent(raw)); } catch (error) { /* 非法编码忽略 */ }
    return candidates.some(function (candidate) {
      if (!candidate || candidate.startsWith('/')) return false;
      const absolute = path.join(projectDir, candidate.replace(/^\.\//, ''));
      return fs.existsSync(absolute);
    });
  }

  let result = html.replace(/<a\s+([^>]*?)href="([^"]+)"([^>]*)>([\s\S]*?)<\/a>/g,
    function (match, before, href, after, label) {
      if (localTargetExists(href)) return match;
      missing += 1;
      return '<span class="doc-link-missing" title="该文件未随发布副本保留">' + label + '</span>';
    });

  result = result.replace(/<img\b([^>]*?)src="([^"]+)"([^>]*?)>/g,
    function (match, before, source) {
      if (localTargetExists(source)) return match;
      missing += 1;
      const name = decodeEntities(source).split('/').pop() || source;
      return '<span class="doc-media-missing">[图片未随发布副本保留：' + esc(name) + ']</span>';
    });

  return { html: result, missing };
}

function buildWorkDocPage(site, project, works, stats) {
  const projectDir = path.join(SITE, 'works', project.slug);
  const readme = findReadmeFile(projectDir, project.entry);
  let hasReadme = false;
  let bodyHtml = '';
  let missingTargets = 0;
  const referenceImages = [];

  if (readme) {
    hasReadme = true;
    const markdown = fs.readFileSync(readme.absolute, 'utf8');
    for (const match of markdown.matchAll(/!\[[^\]]*\]\(\s*([^)\s]+)/g)) {
      referenceImages.push(match[1]);
    }
    for (const match of markdown.matchAll(/<img[^>]+src=["']([^"']+)["']/gi)) {
      referenceImages.push(match[1]);
    }
    bodyHtml = renderMarkdown(normalizeReadmeTitle(markdown, project.title));
    const sanitized = sanitizeDocTargets(bodyHtml, projectDir);
    bodyHtml = sanitized.html;
    missingTargets = sanitized.missing;
  } else {
    bodyHtml = buildFallbackDocBody(project);
  }

  const bodyImageCount = (bodyHtml.match(/<img\b/g) || []).length;
  const gallery = bodyImageCount < 3 ? collectGalleryImages(projectDir, referenceImages) : [];

  const demoHref = workDocDemoHref(project);
  const sourceUrl = repoTreeUrl(works.repo, 'works/' + project.slug);
  const metaParts = ['<span>' + esc(project.categoryName) + '</span>'];
  if (Number.isFinite(project.publishedFiles)) {
    metaParts.push('<span>' + formatNumber(project.publishedFiles) + ' 个文件</span>');
  }
  if (Number.isFinite(project.publishedBytes)) {
    metaParts.push('<span>' + formatBytes(project.publishedBytes) + '</span>');
  }
  project.tags.slice(0, 6).forEach(function (tag) {
    metaParts.push('<span class="tag">' + esc(tag) + '</span>');
  });

  const actions = ['<a href="../../works/">← 返回作品列表</a>'];
  if (demoHref) actions.push('<a class="is-demo" href="' + esc(demoHref) + '">在线试玩 ▶</a>');
  if (sourceUrl) {
    actions.push('<a href="' + esc(sourceUrl) + '" target="_blank" rel="noopener noreferrer">GitHub 源码 ↗</a>');
  }
  if (readme) {
    actions.push('<a href="' + esc(readme.name) + '">原始 Markdown</a>');
  }

  const content =
    '<div class="wrap-narrow work-doc">' +
    '<header class="work-doc-head">' +
    '<p class="work-doc-kicker">说明 · ' + esc(project.categoryName) + '</p>' +
    '<h1 class="work-doc-title">' + esc(project.title) + '</h1>' +
    (project.subtitle ? '<p class="work-doc-sub">' + esc(project.subtitle) + '</p>' : '') +
    '<div class="work-doc-meta">' + metaParts.join('') + '</div>' +
    '<div class="work-doc-actions">' + actions.join('') + '</div>' +
    '</header>' +
    '<article class="prose work-doc-body">' + bodyHtml + '</article>' +
    renderGallery(gallery) +
    '<p class="work-doc-foot"><a class="back-link" href="../../works/">← 返回作品列表</a></p>' +
    '</div>';

  return {
    html: renderPage({
      site, stats, depth: 2, current: 'works', page: 'work-doc', bodyClass: 'page-work-doc',
      title: project.title + ' · 说明 · ' + site.title,
      description: project.subtitle || project.summary || project.title,
      content
    }),
    hasReadme,
    galleryCount: gallery.length,
    bodyImageCount,
    missingTargets,
    readmeName: readme ? readme.name : ''
  };
}

/* ---------- 维护：作品筛选页 /curate/ ---------- */

function buildCuratePage(site, works, stats) {
  const published = works.published;
  const totalBytes = published.reduce(function (sum, project) {
    return sum + (Number.isFinite(project.publishedBytes) ? project.publishedBytes : 0);
  }, 0);

  const rows = published.map(function (project, index) {
    const searchText = normalizeText([
      project.title, project.subtitle, project.categoryName, project.tags.join(' ')
    ].join(' '));
    return '<li class="curate-row" data-slug="' + esc(project.slug) + '"' +
      ' data-dir="' + esc(project.dir) + '"' +
      ' data-category="' + esc(project.category) + '"' +
      ' data-bytes="' + (Number.isFinite(project.publishedBytes) ? project.publishedBytes : 0) + '"' +
      ' data-files="' + (Number.isFinite(project.publishedFiles) ? project.publishedFiles : 0) + '"' +
      ' data-search="' + esc(searchText) + '">' +
      '<input type="checkbox" class="curate-check" value="' + esc(project.slug) + '" checked' +
      ' aria-label="保留 ' + esc(project.title) + '">' +
      '<span class="curate-title">' + esc(project.title) + '</span>' +
      '<span class="curate-cat">' + esc(project.categoryName) + '</span>' +
      '<span class="curate-files">' + formatNumber(project.publishedFiles) + ' 个文件</span>' +
      '<span class="curate-size">' + formatBytes(project.publishedBytes) + '</span>' +
      '</li>';
  }).join('\n');

  const counts = {};
  works.categories.forEach(function (category) { counts[category.id] = 0; });
  published.forEach(function (project) {
    if (!(project.category in counts)) counts[project.category] = 0;
    counts[project.category] += 1;
  });
  const options = works.categories.filter(function (category) {
    return counts[category.id] > 0;
  }).map(function (category) {
    return '<option value="' + esc(category.id) + '">' + esc(category.name) +
      '（' + counts[category.id] + '）</option>';
  }).join('');

  const content =
    '<div class="wrap curate" data-site-url="' + esc(site.baseUrl || 'https://logicx200.github.io/') + '">' +
    '<header class="page-head">' +
    '<p class="page-eyebrow">MAINTENANCE · 维护</p>' +
    '<h1 class="page-title">筛选保留哪些作品</h1>' +
    '<p class="page-desc">默认全部保留。取消勾选的作品会进入排除清单；清单可复制或下载为 JSON，交给 AI 即可从站点和仓库里删掉它们。选择会保存在本机浏览器。</p>' +
    '</header>' +
    '<div class="curate-stats" aria-live="polite">' +
    '<span>保留 <span class="stat-value" id="curate-keep-count">' + formatNumber(published.length) + '</span> 个</span>' +
    '<span>排除 <span class="stat-value" id="curate-exclude-count">0</span> 个</span>' +
    '<span>排除体积 <span class="stat-value" id="curate-exclude-bytes">0 B</span></span>' +
    '<span>全部体积 <span class="stat-value">' + formatBytes(totalBytes) + '</span></span>' +
    '</div>' +
    '<div class="curate-controls">' +
    '<div class="search-field">' +
    '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" aria-hidden="true"><circle cx="7" cy="7" r="4.3"></circle><path d="M10.3 10.3 14 14"></path></svg>' +
    '<label class="sr-only" for="curate-search">搜索作品</label>' +
    '<input class="search-input" id="curate-search" type="search" placeholder="搜索标题、分类或标签…" autocomplete="off" spellcheck="false">' +
    '</div>' +
    '<div class="curate-buttons">' +
    '<button class="curate-button" type="button" id="curate-select-all">全选</button>' +
    '<button class="curate-button" type="button" id="curate-select-none">全不选</button>' +
    '<button class="curate-button" type="button" id="curate-reset">重置</button>' +
    '</div>' +
    '<select class="curate-select" id="curate-category" aria-label="按分类批量操作">' + options + '</select>' +
    '<button class="curate-button" type="button" id="curate-category-select">全选该分类</button>' +
    '<button class="curate-button" type="button" id="curate-category-unselect">全不选该分类</button>' +
    '</div>' +
    '<ul class="curate-list" id="curate-list">' + rows + '</ul>' +
    '<div class="curate-empty" id="curate-empty" hidden>没有匹配的作品</div>' +
    '<div class="curate-actions">' +
    '<button class="curate-button curate-button-primary" type="button" id="curate-copy">复制排除清单</button>' +
    '<button class="curate-button curate-button-primary" type="button" id="curate-download">下载 curate-exclude.json</button>' +
    '<span class="curate-status" id="curate-status" role="status"></span>' +
    '</div>' +
    '<p class="curate-note">把这份 JSON 交给 AI，即可从站点和仓库中删除这些作品。选择保存在本机浏览器（localStorage），清除浏览器数据或点「重置」即可恢复。</p>' +
    '<details class="curate-preview">' +
    '<summary>查看排除清单 JSON</summary>' +
    '<textarea class="curate-output" id="curate-output" readonly rows="14" aria-label="排除清单 JSON"></textarea>' +
    '</details>' +
    '</div>';

  return renderPage({
    site, stats, depth: 1, current: '', page: 'curate', bodyClass: 'page-curate',
    title: '作品筛选 · ' + site.title,
    description: '学哲玩作品集维护页：勾选要保留的作品，导出排除清单 JSON。',
    content
  });
}

/* ---------- 页面骨架 ---------- */

function iconSun() {
  return '<svg class="icon-sun" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" aria-hidden="true">' +
    '<circle cx="8" cy="8" r="3"></circle>' +
    '<path d="M8 1.3v1.6M8 13.1v1.6M1.3 8h1.6M13.1 8h1.6M3.3 3.3l1.1 1.1M11.6 11.6l1.1 1.1M12.7 3.3l-1.1 1.1M4.4 11.6l-1.1 1.1"></path></svg>';
}

function iconMoon() {
  return '<svg class="icon-moon" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
    '<path d="M13.3 9.6A5.8 5.8 0 0 1 6.4 2.7a5.9 5.9 0 1 0 6.9 6.9Z"></path></svg>';
}

function navHtml(site, current, depth) {
  const prefix = relPrefix(depth);
  const items = [
    { key: 'notes', label: '文章', href: prefix + 'notes/' },
    { key: 'works', label: '作品', href: prefix + 'works/' },
    { key: 'about', label: '关于', href: prefix + 'about/' }
  ];
  return '<header class="site-header"><div class="wrap nav">' +
    '<a class="brand" href="' + prefix + 'index.html"><span class="brand-mark" aria-hidden="true"></span>' + esc(site.title) + '</a>' +
    '<div class="nav-right"><nav aria-label="主导航"><ul class="nav-links">' +
    items.map((item) => '<li><a class="nav-link" href="' + item.href + '"' +
      (current === item.key ? ' aria-current="page"' : '') + '>' + item.label + '</a></li>').join('') +
    '</ul></nav>' +
    '<button class="theme-toggle" type="button" data-theme-toggle aria-label="切换到暗色模式" title="暗色">' +
    iconSun() + iconMoon() + '</button></div></div></header>';
}

function footerHtml(site, stats, depth) {
  const year = new Date().getFullYear();
  return '<footer class="site-footer"><div class="wrap"><div class="footer-row">' +
    '<p>© ' + year + ' ' + esc(site.title) +
    '<span class="footer-sep">·</span>' + stats.posts + ' 篇文章' +
    '<span class="footer-sep">·</span>' + stats.works + ' 个作品</p>' +
    '<p>本站由纯静态 HTML / CSS / JS 构建' +
    '<span class="footer-sep">·</span>' +
    '<span class="footer-links"><a href="' + esc(site.github) + '" target="_blank" rel="noopener noreferrer">GitHub</a>' +
    '<a href="mailto:' + esc(site.email) + '">邮箱</a></span></p>' +
    '</div></div></footer>';
}

const THEME_BOOT = '<script>(function(){var d=document.documentElement;d.className=d.className.replace(/\\bno-js\\b/,"js");try{var t=localStorage.getItem("xz-theme");if(t!=="light"&&t!=="dark"){t=window.matchMedia&&window.matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light";}d.setAttribute("data-theme",t);}catch(e){}})();</script>';

/* 极简内联 SVG favicon：墨绿底 + 纸白「学」字（无外部文件、无 emoji） */
const FAVICON = 'data:image/svg+xml,%3Csvg xmlns=%27http://www.w3.org/2000/svg%27 viewBox=%270 0 32 32%27%3E%3Crect width=%2732%27 height=%2732%27 rx=%273%27 fill=%27%232f6f5e%27/%3E%3Ctext x=%2716%27 y=%2722.5%27 font-family=%27Georgia,serif%27 font-size=%2719%27 text-anchor=%27middle%27 fill=%27%23fbfaf7%27%3E%E5%AD%A6%3C/text%3E%3C/svg%3E';

function renderPage(options) {
  const {
    site, stats, depth, current, page, bodyClass,
    title, description, content, headExtra = '', bodyScripts = ''
  } = options;
  const prefix = relPrefix(depth);
  return '<!doctype html>\n<html lang="zh-CN" class="no-js">\n<head>\n' +
    '<meta charset="utf-8">\n' +
    '<meta name="viewport" content="width=device-width, initial-scale=1">\n' +
    '<meta name="color-scheme" content="light dark">\n' +
    '<meta name="theme-color" content="#fbfaf7" media="(prefers-color-scheme: light)">\n' +
    '<meta name="theme-color" content="#161816" media="(prefers-color-scheme: dark)">\n' +
    '<title>' + esc(title) + '</title>\n' +
    '<meta name="description" content="' + esc(description) + '">\n' +
    '<link rel="icon" href="' + FAVICON + '">\n' +
    THEME_BOOT + '\n' +
    '<link rel="stylesheet" href="' + prefix + 'assets/css/site.css">\n' +
    headExtra +
    '</head>\n<body class="' + esc(bodyClass || '') + '" data-page="' + esc(page || 'page') + '">\n' +
    '<a class="skip-link" href="#main">跳到正文</a>\n' +
    navHtml(site, current, depth) + '\n' +
    '<main id="main">\n' + content + '\n</main>\n' +
    footerHtml(site, stats, depth) + '\n' +
    '<script src="' + prefix + 'assets/js/site.js" defer></script>\n' +
    bodyScripts +
    '</body>\n</html>\n';
}

/* ---------- 首页 ---------- */

function buildHome(site, posts, works, stats, about) {
  const recent = posts.slice(0, 5);
  const recentRows = recent.map((post) =>
    '<li><a class="post-row" href="notes/' + esc(post.slug) + '/">' +
    '<time class="post-date" datetime="' + esc(post.date) + '">' + compactDate(post.date) + '</time>' +
    '<span class="post-body"><span class="post-row-title">' + esc(post.title) + '</span></span>' +
    '<span class="post-cat">' + esc(post.subject) + '</span>' +
    '</a></li>'
  ).join('\n');

  let featured = works.featured.slice(0, 6);
  if (!featured.length) featured = works.demoWorks.slice(0, 6);
  if (!featured.length) featured = works.published.slice(0, 6);

  const featuredCards = featured.map((project) =>
    workCardHtml(project, works.repo, { prefix: 'works/', anchorId: false })
  ).join('\n');

  const aboutBrief = about.paragraphs[0]
    ? (about.paragraphs[0].split('。')[0] + '。')
    : '这里是一个学习过程的档案库。';

  const content =
    '<section class="hero"><div class="wrap">' +
    '<p class="hero-eyebrow">学习 · 哲思 · 玩笑</p>' +
    '<h1 class="hero-title">' + esc(site.title) + '</h1>' +
    '<p class="hero-tagline">' + esc(site.tagline) + '</p>' +
    '<div class="hero-intro">' +
    '<p>这里与其说是一个博客，更像是一个学习过程的档案库：把读过的、算过的、写过的整理在这里，作为回忆的归属地。</p>' +
    '<p>如果这些内容恰好对你有用，是我的荣幸；如果没有，就当是个玩笑，愿你今天心情愉快。</p>' +
    '</div><div class="hero-rule" aria-hidden="true"></div>' +
    '</div></section>' +

    '<section class="section"><div class="wrap">' +
    '<div class="section-head"><h2 class="section-title"><span class="section-num">01</span>最近文章</h2>' +
    '<a class="section-link" href="notes/index.html">全部文章 →</a></div>' +
    '<ol class="post-list">' + recentRows + '</ol>' +
    '</div></section>' +

    '<section class="section"><div class="wrap">' +
    '<div class="section-head"><h2 class="section-title"><span class="section-num">02</span>作品</h2>' +
    '<a class="section-link" href="works/index.html">全部作品 →</a></div>' +
    '<div class="works-grid">' + featuredCards + '</div>' +
    '</div></section>' +

    '<section class="section"><div class="wrap">' +
    '<div class="section-head"><h2 class="section-title"><span class="section-num">03</span>关于</h2>' +
    '<a class="section-link" href="about/index.html">了解更多 →</a></div>' +
    '<div class="about-brief">' +
    '<p>' + esc(aboutBrief) + '</p>' +
    '<p>学、哲、玩：认真一点，也轻松一点。</p>' +
    '<div class="contact-line">' +
    '<a href="mailto:' + esc(about.contact.email) + '">' + esc(about.contact.email) + '</a>' +
    '<a href="' + esc(about.contact.github) + '" target="_blank" rel="noopener noreferrer">' +
    esc(about.contact.github.replace(/^https?:\/\//, '')) + '</a>' +
    '</div></div>' +
    '</div></section>';

  return renderPage({
    site, stats, depth: 0, current: 'home', page: 'home', bodyClass: 'page-home',
    title: site.title + ' · ' + site.tagline,
    description: site.description,
    content
  });
}

/* ---------- 文章列表 ---------- */

function buildNotesIndex(site, notes, works, stats) {
  const posts = notes.posts;
  const counts = {};
  notes.subjects.forEach((subject) => { counts[subject] = 0; });
  posts.forEach((post) => {
    if (!(post.subject in counts)) counts[post.subject] = 0;
    counts[post.subject] += 1;
  });
  const categories = [];
  notes.subjects.forEach((subject) => {
    if (counts[subject] > 0 && categories.indexOf(subject) === -1) categories.push(subject);
  });
  posts.forEach((post) => {
    if (categories.indexOf(post.subject) === -1) categories.push(post.subject);
  });

  const chips = ['<button class="chip" type="button" data-category="all" aria-pressed="true">全部<span class="chip-count">' +
    posts.length + '</span></button>'].concat(categories.map((subject) =>
    '<button class="chip" type="button" data-category="' + esc(subject) + '" aria-pressed="false">' +
    esc(subject) + '<span class="chip-count">' + counts[subject] + '</span></button>'
  )).join('');

  const years = [];
  posts.forEach((post) => {
    const parts = parseDateParts(post.date);
    const year = parts ? String(parts.year) : '未标日期';
    let group = years.find((item) => item.year === year);
    if (!group) {
      group = { year, posts: [] };
      years.push(group);
    }
    group.posts.push(post);
  });

  const groupsHtml = years.map((group) => {
    const rows = group.posts.map((post) => {
      const searchText = normalizeText([post.title, post.summary, post.subject, post.categories.join(' ')].join(' '));
      return '<li><a class="post-row note-row" href="' + esc(post.slug) + '/"' +
        ' data-search="' + esc(searchText) + '"' +
        ' data-category="' + esc(post.subject) + '">' +
        '<time class="post-date" datetime="' + esc(post.date) + '">' + compactDate(post.date) + '</time>' +
        '<span class="post-body"><span class="post-row-title">' + esc(post.title) + '</span>' +
        (post.summary ? '<span class="post-row-summary">' + esc(post.summary) + '</span>' : '') +
        '</span>' +
        '<span class="post-cat">' + esc(post.subject) + '</span>' +
        '</a></li>';
    }).join('\n');
    return '<section class="year-group" data-year="' + esc(group.year) + '">' +
      '<h2 class="year-title">' + esc(group.year) + '</h2>' +
      '<ol class="post-list">' + rows + '</ol></section>';
  }).join('\n');

  const content =
    '<div class="wrap">' +
    '<header class="page-head">' +
    '<p class="page-eyebrow">ARCHIVE · 文章</p>' +
    '<h1 class="page-title">文章</h1>' +
    '<p class="page-desc">记录读过的、算过的、想明白的。按年份倒序排列，可以用关键词或分类筛选。</p>' +
    '</header>' +
    '<div class="toolbar js-only">' +
    '<div class="search-field">' +
    '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" aria-hidden="true"><circle cx="7" cy="7" r="4.3"></circle><path d="M10.3 10.3 14 14"></path></svg>' +
    '<label class="sr-only" for="notes-search">搜索文章</label>' +
    '<input class="search-input" id="notes-search" type="search" placeholder="搜索标题、分类或摘要…" autocomplete="off" spellcheck="false">' +
    '</div>' +
    '<div class="chips" id="notes-chips" role="group" aria-label="按分类筛选文章">' + chips + '</div>' +
    '<p class="result-note" id="notes-result" aria-live="polite">共 ' + posts.length + ' 篇文章</p>' +
    '</div>' +
    '<div id="notes-list">' + groupsHtml + '</div>' +
    '<div class="empty-note" id="notes-empty" hidden>' +
    '<p class="empty-note-title">没有匹配的文章</p>' +
    '<p>试试更短的关键词，或者换一个分类。</p>' +
    '<button class="text-button" id="notes-clear" type="button">清除筛选</button>' +
    '</div>' +
    '</div>';

  return renderPage({
    site, stats, depth: 1, current: 'notes', page: 'notes', bodyClass: 'page-notes',
    title: '文章 · ' + site.title,
    description: '学哲玩的文章归档：量子力学、热力学、流体力学、微分方程与物理随笔。',
    content
  });
}

/* ---------- 文章正文 ---------- */

function buildArticle(site, post, posts, stats) {
  const index = posts.findIndex((item) => item.slug === post.slug);
  const newer = index > 0 ? posts[index - 1] : null;
  const older = index >= 0 && index < posts.length - 1 ? posts[index + 1] : null;
  const prefix = relPrefix(2);

  const navParts = [];
  if (newer) {
    navParts.push('<a class="article-nav-item" href="../' + esc(newer.slug) + '/">' +
      '<span class="article-nav-label">上一篇</span>' +
      '<span class="article-nav-title">' + esc(newer.title) + '</span></a>');
  }
  if (older) {
    navParts.push('<a class="article-nav-item is-next" href="../' + esc(older.slug) + '/">' +
      '<span class="article-nav-label">下一篇</span>' +
      '<span class="article-nav-title">' + esc(older.title) + '</span></a>');
  }

  const tags = post.categories.length ? post.categories.join(' · ') : post.subject;
  const body = fixRootRelative(post.body, prefix);
  const headExtra = '<link rel="stylesheet" href="' + prefix + 'assets/js/katex/katex.min.css">\n';
  const bodyScripts =
    '<script defer src="' + prefix + 'assets/js/katex/katex.min.js"></script>\n' +
    '<script defer src="' + prefix + 'assets/js/katex/contrib/auto-render.min.js"></script>\n';

  const content =
    '<div class="wrap-narrow">' +
    '<header class="article-head">' +
    '<p class="article-kicker">' + esc(post.subject) + ' · ' + esc(post.kind) + '</p>' +
    '<h1 class="article-title">' + esc(post.title) + '</h1>' +
    '<div class="article-meta">' +
    '<time class="meta-date" datetime="' + esc(post.date) + '">' + longDate(post.date) + '</time>' +
    '<span class="meta-sep" aria-hidden="true">·</span>' +
    '<span>' + esc(tags) + '</span>' +
    '<span class="meta-sep" aria-hidden="true">·</span>' +
    '<span>约 ' + post.minutes + ' 分钟</span>' +
    '</div></header>' +
    '<article class="prose">' + body + '</article>' +
    '<nav class="article-nav" aria-label="文章导航">' + navParts.join('') + '</nav>' +
    '<a class="back-link" href="../">← 返回文章列表</a>' +
    '</div>';

  return renderPage({
    site, stats, depth: 2, current: 'notes', page: 'article', bodyClass: 'page-article',
    title: post.title + ' · ' + site.title,
    description: post.summary || post.title,
    content,
    headExtra,
    bodyScripts
  });
}

/* ---------- 作品索引 ---------- */

function buildWorksIndex(site, works, stats) {
  const published = works.published;
  const totalFiles = published.reduce((sum, project) => sum + (Number.isFinite(project.publishedFiles) ? project.publishedFiles : 0), 0);
  const totalBytes = published.reduce((sum, project) => sum + (Number.isFinite(project.publishedBytes) ? project.publishedBytes : 0), 0);
  const usedCategories = new Set(published.map((project) => project.category));

  const categoryName = {};
  const counts = {};
  works.categories.forEach((category) => {
    categoryName[category.id] = category.name;
    counts[category.id] = 0;
  });
  published.forEach((project) => {
    if (!(project.category in counts)) counts[project.category] = 0;
    counts[project.category] += 1;
  });
  const categories = [];
  works.categories.forEach((category) => {
    if (counts[category.id] > 0) categories.push(category.id);
  });
  Object.keys(counts).forEach((id) => {
    if (counts[id] > 0 && categories.indexOf(id) === -1) categories.push(id);
  });

  const chips = ['<button class="chip" type="button" data-category="all" aria-pressed="true">全部<span class="chip-count">' +
    published.length + '</span></button>'].concat(categories.map((id) =>
    '<button class="chip" type="button" data-category="' + esc(id) + '" aria-pressed="false">' +
    esc(categoryName[id] || id) + '<span class="chip-count">' + counts[id] + '</span></button>'
  )).join('');

  const demoItems = works.demoWorks.map((project) =>
    '<a class="demo-item" href="' + esc(project.demo) + '"' +
    ' data-search="' + esc(normalizeText([project.title, project.subtitle, project.summary, project.tags.join(' ')].join(' '))) + '"' +
    ' data-category="' + esc(project.category) + '">' +
    '<span class="demo-item-name">' + esc(project.title) + '</span>' +
    '<span class="demo-item-go">试玩 ↗</span>' +
    '</a>'
  ).join('\n');

  const cards = published.map((project) =>
    workCardHtml(project, works.repo, { prefix: '', anchorId: true })
  ).join('\n');

  const unpublishedItems = works.unpublished.map((project) => {
    const size = Number.isFinite(project.sourceBytes) ? project.sourceBytes : project.publishedBytes;
    const reason = project.excludeReason || project.excludeNote || '';
    return '<li class="unpublished-item">' +
      '<span class="unpublished-name">' + esc(project.title) + '</span>' +
      (reason ? '<p class="unpublished-reason">' + esc(reason) + '</p>' : '') +
      '<span class="unpublished-size">' + formatBytes(size) + '</span>' +
      '</li>';
  }).join('\n');

  const content =
    '<div class="wrap">' +
    '<header class="page-head">' +
    '<p class="page-eyebrow">WORKS · 作品</p>' +
    '<h1 class="page-title">作品</h1>' +
    '<p class="page-desc">动手做出来的东西：科研仿真、命令行工具与网页实验。可以按分类筛选，或直接搜索。</p>' +
    '</header>' +
    '<div class="stats-line" aria-label="作品统计">' +
    '<span class="stat-item">作品 <span class="stat-value">' + formatNumber(published.length) + '</span></span>' +
    '<span class="stat-item">文件 <span class="stat-value">' + formatNumber(totalFiles) + '</span></span>' +
    '<span class="stat-item">体积 <span class="stat-value">' + formatBytes(totalBytes) + '</span></span>' +
    '<span class="stat-item">分类 <span class="stat-value">' + formatNumber(usedCategories.size) + '</span></span>' +
    '</div>' +
    (works.demoWorks.length
      ? '<section class="demo-section" id="demo-section">' +
        '<div class="demo-head"><h2 class="demo-title">可在线试玩</h2>' +
        '<span class="demo-note">' + works.demoWorks.length + ' 个网页作品，点开即用</span></div>' +
        '<div class="demo-list" id="demo-list">' + demoItems + '</div>' +
        '</section>'
      : '') +
    '<div class="toolbar js-only">' +
    '<div class="search-field">' +
    '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" aria-hidden="true"><circle cx="7" cy="7" r="4.3"></circle><path d="M10.3 10.3 14 14"></path></svg>' +
    '<label class="sr-only" for="works-search">搜索作品</label>' +
    '<input class="search-input" id="works-search" type="search" placeholder="搜索作品标题、简介或标签…" autocomplete="off" spellcheck="false">' +
    '</div>' +
    '<div class="chips" id="works-chips" role="group" aria-label="按分类筛选作品">' + chips + '</div>' +
    '<div class="sort-field"><label class="sort-label" for="works-sort">排序</label>' +
    '<span class="sort-wrap"><select class="sort-select" id="works-sort">' +
    '<option value="order">默认顺序</option><option value="name">名称</option><option value="size">体积大到小</option>' +
    '</select><svg class="sort-chevron" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 6.2 8 10.2l4-4"></path></svg></span></div>' +
    '<p class="result-note" id="works-result" aria-live="polite">共 ' + published.length + ' 个作品</p>' +
    '</div>' +
    '<div class="works-section-head"><h2 class="works-section-title">全部作品</h2></div>' +
    '<div class="works-grid" id="works-grid">' + cards + '</div>' +
    '<div class="empty-note" id="works-empty" hidden>' +
    '<p class="empty-note-title">没有匹配的作品</p>' +
    '<p>试试更短的关键词，或者换一个分类。</p>' +
    '<button class="text-button" id="works-clear" type="button">清除筛选</button>' +
    '</div>' +
    '<p class="works-legacy-note"><a class="section-link" href="legacy/index.html">早期项目（Hexo 时期的 Python 工具箱）→</a></p>' +
    (works.unpublished.length
      ? '<details class="unpublished">' +
        '<summary><span>未上传的大体积产物</span><span class="unpublished-hint">' +
        works.unpublished.length + ' 项 · 体积超出仓库限制，保留在本地</span></summary>' +
        '<ul class="unpublished-list">' + unpublishedItems + '</ul>' +
        '</details>'
      : '') +
    '<p class="works-maintenance"><a href="../curate/">维护：筛选保留哪些作品 →</a></p>' +
    '</div>';

  return renderPage({
    site, stats, depth: 1, current: 'works', page: 'works', bodyClass: 'page-works',
    title: '作品 · ' + site.title,
    description: '学哲玩的作品索引：科研仿真、工具与网页实验，含可在线试玩的网页作品。',
    content
  });
}

/* ---------- 早期项目 ---------- */

function buildLegacyPage(site, legacy, stats) {
  const prefix = relPrefix(2);

  /* 预留：legacy.json 里的 tool.demo 存在且文件存在时，显示「在线试玩」 */
  function legacyDemoHref(tool) {
    const demo = trim(tool.demo);
    if (!demo) return '';
    const normalized = demo.replace(/^\.?\//, '').replace(/^\/+/, '');
    if (fileExistsInSite('works/legacy/' + normalized)) return normalized;
    const sitePath = stripWorksPrefix(demo);
    if (sitePath && fileExistsInSite('works/' + sitePath)) {
      const relative = path.posix.relative('legacy', sitePath);
      return relative && !relative.startsWith('..') ? relative : '';
    }
    return '';
  }

  const tools = legacy.tools.map((tool) => {
    const demoHref = legacyDemoHref(tool);
    const images = tool.images
      .map((image) => image.replace(/^\/+/, ''))
      .filter((image) => fileExistsInSite(image));
    let media = '';
    if (images.length) {
      const first = '<img src="' + esc(prefix + images[0]) + '" alt="' + esc(tool.name) + ' 截图" loading="lazy" decoding="async">';
      const rest = images.slice(1).map((image) =>
        '<img src="' + esc(prefix + image) + '" alt="' + esc(tool.name) + ' 截图" loading="lazy" decoding="async">'
      ).join('');
      media = '<div class="legacy-media">' + first + (rest ? '<div class="legacy-thumbs">' + rest + '</div>' : '') + '</div>';
    } else {
      media = '<div class="legacy-media"><div class="legacy-placeholder" aria-hidden="true"></div></div>';
    }
    const tech = tool.tech ? '<p class="legacy-tech">' + esc(tool.tech) + '</p>' : '';
    const badge = demoHref
      ? '<span class="legacy-badge">网页版可玩</span>'
      : '<span class="legacy-era">原程序 · 未移植</span>';
    const demoLink = demoHref
      ? '<a class="legacy-demo" href="' + esc(demoHref) + '">在线试玩 ▶</a>'
      : '';
    const sourceLink = tool.source
      ? '<a class="legacy-source" href="' + esc(tool.source) + '" target="_blank" rel="noopener noreferrer">源码 ↗</a>'
      : '';
    return '<article class="legacy-card">' +
      '<div class="legacy-head"><h2 class="legacy-name">' + esc(tool.name) + '</h2>' + badge + '</div>' +
      (tool.desc ? '<p class="legacy-desc">' + esc(tool.desc) + '</p>' : '') +
      tech +
      media +
      (demoLink || sourceLink ? '<div class="legacy-links">' + demoLink + sourceLink + '</div>' : '') +
      '</article>';
  }).join('\n');

  const statItems = [
    ['项目', legacy.stats.projects],
    ['已移植网页版', legacy.stats.webVersions],
    ['代码行数', legacy.stats.loc],
    ['技术栈', legacy.stats.stacks]
  ].filter((item) => item[1] !== undefined && item[1] !== null && item[1] !== '')
    .map((item) => '<span class="stat-item">' + esc(item[0]) + ' <span class="stat-value">' + esc(item[1]) + '</span></span>')
    .join('');

  const repoLine = legacy.repo
    ? '<p class="legacy-repo">源码仓库：<a href="' + esc(legacy.repo) + '" target="_blank" rel="noopener noreferrer">' +
      esc(legacy.repoName || legacy.repo) + '</a></p>'
    : '';

  const contact = [];
  if (legacy.contact.email) contact.push('邮箱：<a href="mailto:' + esc(legacy.contact.email) + '">' + esc(legacy.contact.email) + '</a>');
  if (legacy.contact.qq) contact.push('QQ：' + esc(legacy.contact.qq));

  const content =
    '<div class="wrap">' +
    '<header class="page-head">' +
    '<p class="page-eyebrow">LEGACY · 早期项目</p>' +
    '<h1 class="page-title">早期项目</h1>' +
    '<p class="legacy-intro">' + esc(legacy.intro || 'Hexo 时期写下的 Python 工具箱，保留截图与说明。') + '</p>' +
    repoLine +
    '</header>' +
    (statItems ? '<div class="legacy-stats" aria-label="旧项目统计">' + statItems + '</div>' : '') +
    (legacy.stats.note ? '<p class="legacy-note">' + esc(legacy.stats.note) + '</p>' : '') +
    (tools ? '<div class="legacy-grid">' + tools + '</div>' : '<div class="empty-note"><p class="empty-note-title">暂未整理旧项目内容</p><p>旧项目资料仍在整理中。</p></div>') +
    (contact.length ? '<div class="legacy-contact">' + contact.join('<span class="footer-sep">·</span>') + '</div>' : '') +
    '</div>';

  return renderPage({
    site, stats, depth: 2, current: 'works', page: 'legacy', bodyClass: 'page-legacy',
    title: '早期项目 · ' + site.title,
    description: '学哲玩早期的 Python 工具箱：OpenCV 跟踪器、DOCX2Markdown、Markdown 图片上传工具、线圈型阻尼谐振子仿真与双摆仿真。',
    content
  });
}

/* ---------- 关于 ---------- */

function buildAboutPage(site, about, stats) {
  const meaningDescriptions = {
    '学习': '记录正在学到的知识，把学习的过程留下来。',
    '哲思': '记下想明白的道理与感悟，作为思考的归档。',
    '玩笑': '也当作一个玩笑，希望它能丰富你的心情。'
  };

  const paragraphs = about.paragraphs.length
    ? about.paragraphs
    : ['这里与其说是一个博客，更像是一个自己学习过程的档案库。'];

  const introParts = paragraphs.map((paragraph, index) => {
    if (index === 0) {
      const markup = '<p class="about-lead">' + esc(paragraph) + '</p>' +
        (about.nameParts.length
          ? '<ul class="about-meanings">' + about.nameParts.map((part) =>
            '<li><span class="meaning-key">' + esc(part) + '</span>' +
            '<span class="meaning-desc">' + esc(meaningDescriptions[part] || '') + '</span></li>'
          ).join('') + '</ul>'
          : '');
      return markup;
    }
    return '<p class="about-lead">' + esc(paragraph) + '</p>';
  }).join('\n');

  const imageExists = about.image && fileExistsInSite(about.image);
  const figure = imageExists
    ? '<figure class="about-figure"><img src="../' + esc(about.image) + '" alt="' +
      esc(about.imageCaption || '生活照') + '" loading="lazy" decoding="async">' +
      (about.imageCaption ? '<figcaption>' + esc(about.imageCaption) + '</figcaption>' : '') +
      '</figure>'
    : '';

  const contact = [];
  if (about.contact.email) contact.push('邮箱：<a href="mailto:' + esc(about.contact.email) + '">' + esc(about.contact.email) + '</a>');
  if (about.contact.qq) contact.push('QQ：' + esc(about.contact.qq));
  if (about.contact.github) {
    contact.push('GitHub：<a href="' + esc(about.contact.github) + '" target="_blank" rel="noopener noreferrer">' +
      esc(about.contact.github.replace(/^https?:\/\//, '')) + '</a>');
  }

  const content =
    '<div class="wrap-narrow about-page">' +
    '<header class="article-head">' +
    '<p class="article-kicker">关于</p>' +
    '<h1 class="article-title">' + esc(about.title) + '</h1>' +
    (about.heading ? '<p class="about-greeting">' + esc(about.heading) + '</p>' : '') +
    '</header>' +
    introParts +
    figure +
    (about.note ? '<p class="about-note">' + esc(about.note) + '</p>' : '') +
    '<section class="about-contact">' +
    '<h2>联系</h2>' +
    (contact.length ? contact.map((line) => '<p>' + line + '</p>').join('\n') : '<p>—</p>') +
    '<p>旧站 Hexo 时期的 Python 工具箱保留在 <a href="../works/legacy/">早期项目</a> 里。</p>' +
    '</section>' +
    '</div>';

  return renderPage({
    site, stats, depth: 1, current: 'about', page: 'about', bodyClass: 'page-about',
    title: '关于 · ' + site.title,
    description: site.description,
    content
  });
}

/* ---------- 404 ---------- */

function build404(site, stats) {
  const content =
    '<div class="wrap-narrow"><div class="notfound">' +
    '<p class="notfound-code">404 · NOT FOUND</p>' +
    '<h1 class="notfound-title">这一页大概是被波函数隧穿掉了。</h1>' +
    '<p class="notfound-desc">你访问的地址不存在，或者它已经搬到了别处。可以顺着下面的路回去。</p>' +
    '<nav class="notfound-links" aria-label="返回站点">' +
    '<a href="index.html" data-root-link="index.html">首页</a>' +
    '<a href="notes/index.html" data-root-link="notes/index.html">文章</a>' +
    '<a href="works/index.html" data-root-link="works/index.html">作品</a>' +
    '</nav></div></div>';

  /* GitHub Pages 会在任意子路径下使用 404.html：按路径段数补 ../，保持相对链接可用 */
  const fixer = '<script>(function(){try{if(location.protocol==="file:")return;var parts=location.pathname.split("/").filter(Boolean);var prefix=new Array(parts.length+1).join("../");var links=document.querySelectorAll("[data-root-link]");for(var i=0;i<links.length;i++){links[i].setAttribute("href",prefix+links[i].getAttribute("data-root-link"));}}catch(e){}})();</script>';

  return renderPage({
    site, stats, depth: 0, current: '', page: '404', bodyClass: 'page-404',
    title: '页面未找到 · ' + site.title,
    description: '404：这一页大概是被波函数隧穿掉了。',
    content,
    bodyScripts: fixer
  });
}

/* ---------- 输出与体检 ---------- */

function writeFile(relativePath, content, written) {
  const fullPath = path.join(SITE, relativePath);
  fs.mkdirSync(path.dirname(fullPath), { recursive: true });
  fs.writeFileSync(fullPath, content, 'utf8');
  written.push({ path: relativePath, bytes: Buffer.byteLength(content, 'utf8') });
}

function auditHtml(files) {
  const externalResources = [];
  const internalLinks = new Set();
  const rootAbsolute = [];

  files.forEach((file) => {
    const html = fs.readFileSync(path.join(SITE, file.path), 'utf8');
    const withoutScripts = html.replace(/<script[\s\S]*?<\/script>/gi, '');

    /* 外部「资源」只关心会发起网络加载的 src / <link href>；站外超链接不算 */
    for (const match of withoutScripts.matchAll(/\bsrc="(https?:\/\/[^"]+)"/g)) {
      externalResources.push({ page: file.path, url: match[1] });
    }
    for (const match of withoutScripts.matchAll(/<link\b[^>]*\bhref="(https?:\/\/[^"]+)"/g)) {
      externalResources.push({ page: file.path, url: match[1] });
    }

    for (const match of withoutScripts.matchAll(/\b(?:src|href)="([^"#?]+)"/g)) {
      const url = match[1];
      if (/^(?:https?:|mailto:|data:|javascript:)/i.test(url)) continue;
      if (url.startsWith('/')) {
        rootAbsolute.push({ page: file.path, url });
        continue;
      }
      internalLinks.add(path.join(path.dirname(file.path), url).replace(/\\/g, '/'));
    }
  });

  const missing = [];
  internalLinks.forEach((target) => {
    const normalized = path.normalize(target);
    const candidates = [normalized, path.join(normalized, 'index.html')];
    if (!candidates.some((candidate) => fs.existsSync(path.join(SITE, candidate)))) {
      missing.push(target);
    }
  });

  return { externalResources, rootAbsolute, missing: missing.slice(0, 40) };
}

function main() {
  console.log('学哲玩 · 站点生成');
  console.log('  站点目录：' + SITE);

  const notes = loadNotesData();
  const works = loadWorksData();
  const legacy = loadLegacyData();
  const about = loadAboutData(notes.site);
  const stats = { posts: notes.posts.length, works: works.published.length };

  console.log('\n数据：');
  console.log('  文章：' + notes.posts.length + ' 篇（来源：' + notes.source + '）');
  console.log('  作品：已发布 ' + works.published.length + ' 个 / 未上传 ' + works.unpublished.length +
    ' 个（来源：' + works.source + '），可试玩 ' + works.demoWorks.length + ' 个');
  console.log('  精选：' + (works.featured.length ? works.featured.length + ' 个 featured' : '数据无 featured，按可试玩作品兜底'));
  console.log('  旧项目：' + legacy.tools.length + ' 个');
  const totalBytes = works.published.reduce((sum, project) =>
    sum + (Number.isFinite(project.publishedBytes) ? project.publishedBytes : 0), 0);
  console.log('  已发布作品体积合计：' + formatBytes(totalBytes));
  if (works.featuredFallback) {
    warn('作品数据里没有 featured:true，首页精选暂用可试玩作品兜底。');
  }

  const written = [];
  writeFile('index.html', buildHome(notes.site, notes.posts, works, stats, about), written);
  writeFile('notes/index.html', buildNotesIndex(notes.site, notes, works, stats), written);
  notes.posts.forEach((post) => {
    writeFile('notes/' + post.slug + '/index.html', buildArticle(notes.site, post, notes.posts, stats), written);
  });
  writeFile('works/index.html', buildWorksIndex(notes.site, works, stats), written);
  writeFile('works/legacy/index.html', buildLegacyPage(notes.site, legacy, stats), written);

  /* 作品说明页：works/<slug>/README.html（README 渲染 / summary 兜底 + 图集） */
  const docStats = { readme: 0, fallback: 0, galleryPages: 0, galleryImages: 0, missingTargets: 0 };
  works.published.forEach((project) => {
    const doc = buildWorkDocPage(notes.site, project, works, stats);
    writeFile('works/' + project.slug + '/README.html', doc.html, written);
    if (doc.hasReadme) docStats.readme += 1;
    else docStats.fallback += 1;
    if (doc.galleryCount > 0) {
      docStats.galleryPages += 1;
      docStats.galleryImages += doc.galleryCount;
    }
    docStats.missingTargets += doc.missingTargets || 0;
  });
  writeFile('curate/index.html', buildCuratePage(notes.site, works, stats), written);
  writeFile('about/index.html', buildAboutPage(notes.site, about, stats), written);
  writeFile('404.html', build404(notes.site, stats), written);

  console.log('\n作品说明页：' + works.published.length + ' 个（README 渲染 ' + docStats.readme +
    ' 个，summary 兜底 ' + docStats.fallback + ' 个）');
  console.log('图集：' + docStats.galleryPages + ' 个说明页补充了 ' + docStats.galleryImages + ' 张图片');
  if (docStats.missingTargets) {
    console.log('说明页降级：' + docStats.missingTargets + ' 个 README 本地链接/图片目标未随发布副本保留，已降级为纯文字。');
  }

  const audit = auditHtml(written);
  if (audit.rootAbsolute.length) {
    warn('生成页面里存在以 / 开头的绝对路径（' + audit.rootAbsolute.length + ' 处）：');
    audit.rootAbsolute.slice(0, 10).forEach((item) => console.log('    ' + item.page + ' → ' + item.url));
  }
  if (audit.externalResources.length) {
    warn('生成页面里存在外部资源引用（' + audit.externalResources.length + ' 处）：');
    audit.externalResources.slice(0, 10).forEach((item) => console.log('    ' + item.page + ' → ' + item.url));
  }
  if (audit.missing.length) {
    warn('生成页面里有 ' + audit.missing.length + ' 个内部链接指向不存在的文件：');
    audit.missing.forEach((target) => console.log('    ' + target));
  }

  console.log('\n生成完成：' + written.length + ' 个 HTML 文件');
  written.forEach((file) => console.log('  ' + file.path + '  (' + file.bytes + ' B)'));
  if (warnings.length) {
    console.log('\n警告 ' + warnings.length + ' 条，见上方。');
    process.exitCode = 0;
  }
}

/* 作为脚本直接运行时才构建；被测试脚本 import 时只导出渲染函数 */
const isDirectRun = (() => {
  try {
    return Boolean(process.argv[1]) &&
      path.resolve(process.argv[1]) === fileURLToPath(import.meta.url);
  } catch (error) {
    return false;
  }
})();

if (isDirectRun) main();

export {
  renderMarkdown,
  renderInline,
  parseImageSize,
  collectGalleryImages,
  buildWorkDocPage,
  buildCuratePage
};
