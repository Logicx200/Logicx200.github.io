/* ==========================================================================
   学哲玩 · 站点交互（纯原生 JS，零依赖、零网络请求）
   只做增强：主题切换、文章/作品搜索筛选排序、KaTeX 渲染、图片失效降级。
   无 JS 时页面内容仍可正常阅读。
   ========================================================================== */

(function () {
  'use strict';

  var THEME_KEY = 'xz-theme';

  /* ----------------------------------------------------------------------
     基础工具
     ---------------------------------------------------------------------- */

  function ready(fn) {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', fn);
    } else {
      fn();
    }
  }

  function $(selector, scope) {
    return (scope || document).querySelector(selector);
  }

  function $all(selector, scope) {
    return Array.prototype.slice.call((scope || document).querySelectorAll(selector));
  }

  function normalize(value) {
    if (typeof value !== 'string') return '';
    try {
      return value.normalize('NFKC').toLocaleLowerCase('zh-CN');
    } catch (error) {
      return value.toLowerCase();
    }
  }

  function isTypingTarget(target) {
    if (!target) return false;
    var tag = (target.tagName || '').toLowerCase();
    return tag === 'input' || tag === 'textarea' || tag === 'select' ||
      target.isContentEditable === true;
  }

  /* 关键词匹配：空格分词，全部命中才算匹配 */
  function matches(haystack, query) {
    if (!query) return true;
    var terms = query.split(/\s+/);
    for (var i = 0; i < terms.length; i += 1) {
      if (terms[i] && haystack.indexOf(terms[i]) === -1) return false;
    }
    return true;
  }

  /* ----------------------------------------------------------------------
     主题切换（初始值由 <head> 内联脚本设置，避免闪烁）
     ---------------------------------------------------------------------- */

  function readStoredTheme() {
    try {
      var value = localStorage.getItem(THEME_KEY);
      return value === 'light' || value === 'dark' ? value : '';
    } catch (error) {
      return '';
    }
  }

  function systemTheme() {
    if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
      return 'dark';
    }
    return 'light';
  }

  function applyTheme(theme, persist) {
    var value = theme === 'dark' ? 'dark' : 'light';
    document.documentElement.setAttribute('data-theme', value);
    $all('[data-theme-toggle]').forEach(function (button) {
      button.setAttribute('aria-label', value === 'dark' ? '切换到浅色模式' : '切换到暗色模式');
      button.setAttribute('title', value === 'dark' ? '浅色' : '暗色');
    });
    if (persist) {
      try {
        localStorage.setItem(THEME_KEY, value);
      } catch (error) { /* localStorage 不可用时静默降级 */ }
    }
  }

  function initTheme() {
    var current = document.documentElement.getAttribute('data-theme');
    applyTheme(current === 'dark' ? 'dark' : 'light', false);

    $all('[data-theme-toggle]').forEach(function (button) {
      button.addEventListener('click', function () {
        var next = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
        applyTheme(next, true);
      });
    });

    if (window.matchMedia) {
      var media = window.matchMedia('(prefers-color-scheme: dark)');
      var onChange = function (event) {
        if (readStoredTheme()) return;
        applyTheme(event.matches ? 'dark' : 'light', false);
      };
      if (typeof media.addEventListener === 'function') {
        media.addEventListener('change', onChange);
      } else if (typeof media.addListener === 'function') {
        media.addListener(onChange);
      }
    }
  }

  /* ----------------------------------------------------------------------
     图片失效降级
     - 作品封面：图片加载失败时隐藏 <img>，露出渐变 + 首字占位
     - 正文图片：加载失败时直接隐藏，避免破图图标
     ---------------------------------------------------------------------- */

  function initImageFallbacks() {
    $all('img[data-cover]').forEach(function (image) {
      image.addEventListener('error', function () {
        var frame = image.closest('.work-cover');
        if (frame) frame.classList.add('is-missing');
        image.style.display = 'none';
      });
    });

    $all('.prose img').forEach(function (image) {
      image.addEventListener('error', function () {
        image.style.display = 'none';
      });
    });
  }

  /* ----------------------------------------------------------------------
     通用：搜索框快捷键 "/" 聚焦、Esc 清空
     ---------------------------------------------------------------------- */

  function bindSearchShortcut(input, clear) {
    if (!input) return;
    document.addEventListener('keydown', function (event) {
      if (event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey) return;
      if (event.key === '/' && !isTypingTarget(event.target)) {
        event.preventDefault();
        input.focus();
        input.select();
        return;
      }
      if (event.key === 'Escape' && document.activeElement === input) {
        if (input.value) {
          input.value = '';
          clear();
        } else {
          input.blur();
        }
      }
    });
  }

  /* ----------------------------------------------------------------------
     文章列表：关键词搜索 + 分类筛选
     ---------------------------------------------------------------------- */

  function initNotesFilter() {
    var root = $('[data-page="notes"]');
    if (!root) return;

    var input = $('#notes-search');
    var chips = $('#notes-chips');
    var result = $('#notes-result');
    var empty = $('#notes-empty');
    var emptyClear = $('#notes-clear');
    var groups = $all('.year-group', root);
    var rows = $all('.note-row', root);
    if (!input || !chips || !rows.length) return;

    var state = { query: '', category: 'all' };

    function apply() {
      var total = rows.length;
      var visible = 0;
      var visibleByGroup = {};

      rows.forEach(function (row) {
        var ok = (state.category === 'all' || row.getAttribute('data-category') === state.category) &&
          matches(row.getAttribute('data-search') || '', state.query);
        row.hidden = !ok;
        if (ok) {
          visible += 1;
          var group = row.closest('.year-group');
          if (group) {
            var year = group.getAttribute('data-year');
            visibleByGroup[year] = (visibleByGroup[year] || 0) + 1;
          }
        }
      });

      groups.forEach(function (group) {
        var year = group.getAttribute('data-year');
        group.hidden = !visibleByGroup[year];
      });

      if (result) {
        if (state.query || state.category !== 'all') {
          result.textContent = '显示 ' + visible + ' / ' + total + ' 篇';
        } else {
          result.textContent = '共 ' + total + ' 篇文章';
        }
      }
      if (empty) empty.hidden = visible > 0;
    }

    function clear() {
      state.query = '';
      state.category = 'all';
      input.value = '';
      $all('.chip', chips).forEach(function (chip) {
        chip.setAttribute('aria-pressed', chip.getAttribute('data-category') === 'all' ? 'true' : 'false');
      });
      apply();
    }

    input.addEventListener('input', function () {
      state.query = normalize(input.value.trim());
      apply();
    });

    chips.addEventListener('click', function (event) {
      var chip = event.target.closest('.chip');
      if (!chip || !chips.contains(chip)) return;
      var category = chip.getAttribute('data-category');
      if (!category || category === state.category) return;
      state.category = category;
      $all('.chip', chips).forEach(function (item) {
        item.setAttribute('aria-pressed', item === chip ? 'true' : 'false');
      });
      apply();
    });

    if (emptyClear) {
      emptyClear.addEventListener('click', function () {
        clear();
        input.focus();
      });
    }

    bindSearchShortcut(input, clear);
    apply();
  }

  /* ----------------------------------------------------------------------
     作品索引：关键词搜索 + 分类筛选 + 排序
     ---------------------------------------------------------------------- */

  function initWorksFilter() {
    var root = $('[data-page="works"]');
    if (!root) return;

    var input = $('#works-search');
    var chips = $('#works-chips');
    var sort = $('#works-sort');
    var result = $('#works-result');
    var empty = $('#works-empty');
    var emptyClear = $('#works-clear');
    var grid = $('#works-grid');
    var demoSection = $('#demo-section');
    var demoItems = $all('.demo-item', root);
    var cards = $all('.work-card', grid || root);
    if (!input || !chips || !cards.length) return;

    var state = { query: '', category: 'all', sort: 'order' };
    var total = cards.length;

    function updateDemo(visibleCategories) {
      if (!demoSection) return;
      var domVisible = 0;
      demoItems.forEach(function (item) {
        var ok = (state.category === 'all' || item.getAttribute('data-category') === state.category) &&
          matches(item.getAttribute('data-search') || '', state.query);
        item.hidden = !ok;
        if (ok) domVisible += 1;
      });
      demoSection.hidden = domVisible === 0;
    }

    function apply() {
      var visible = [];
      cards.forEach(function (card) {
        var ok = (state.category === 'all' || card.getAttribute('data-category') === state.category) &&
          matches(card.getAttribute('data-search') || '', state.query);
        card.hidden = !ok;
        if (ok) visible.push(card);
      });

      /* 排序：默认顺序 / 名称 / 体积大到小；排序只重排可见卡片 */
      if (grid) {
        if (state.sort === 'size') {
          visible.sort(function (a, b) {
            return (Number(b.getAttribute('data-size')) || 0) - (Number(a.getAttribute('data-size')) || 0) ||
              (Number(a.getAttribute('data-order')) || 0) - (Number(b.getAttribute('data-order')) || 0);
          });
        } else if (state.sort === 'name') {
          visible.sort(function (a, b) {
            return String(a.getAttribute('data-title') || '').localeCompare(
              String(b.getAttribute('data-title') || ''), 'zh-CN', { numeric: true, sensitivity: 'base' });
          });
        } else {
          visible.sort(function (a, b) {
            return (Number(a.getAttribute('data-order')) || 0) - (Number(b.getAttribute('data-order')) || 0);
          });
        }
        var fragment = document.createDocumentFragment();
        visible.forEach(function (card) { fragment.appendChild(card); });
        grid.appendChild(fragment);
      }

      updateDemo();

      if (result) {
        if (state.query || state.category !== 'all') {
          result.textContent = '显示 ' + visible.length + ' / ' + total + ' 个作品';
        } else {
          result.textContent = '共 ' + total + ' 个作品';
        }
      }
      if (empty) empty.hidden = visible.length > 0;
    }

    function clear() {
      state.query = '';
      state.category = 'all';
      input.value = '';
      $all('.chip', chips).forEach(function (chip) {
        chip.setAttribute('aria-pressed', chip.getAttribute('data-category') === 'all' ? 'true' : 'false');
      });
      apply();
    }

    input.addEventListener('input', function () {
      state.query = normalize(input.value.trim());
      apply();
    });

    chips.addEventListener('click', function (event) {
      var chip = event.target.closest('.chip');
      if (!chip || !chips.contains(chip)) return;
      var category = chip.getAttribute('data-category');
      if (!category || category === state.category) return;
      state.category = category;
      $all('.chip', chips).forEach(function (item) {
        item.setAttribute('aria-pressed', item === chip ? 'true' : 'false');
      });
      apply();
    });

    if (sort) {
      sort.addEventListener('change', function () {
        state.sort = sort.value;
        apply();
      });
    }

    if (emptyClear) {
      emptyClear.addEventListener('click', function () {
        clear();
        input.focus();
      });
    }

    bindSearchShortcut(input, clear);
    apply();
  }

  /* ----------------------------------------------------------------------
     文章正文：KaTeX auto-render（自托管，加载失败不影响正文阅读）
     ---------------------------------------------------------------------- */

  function initMath() {
    var content = $('.prose');
    if (!content) return;

    function render() {
      if (typeof window.renderMathInElement !== 'function') return;
      try {
        window.renderMathInElement(content, {
          delimiters: [
            { left: '$$', right: '$$', display: true },
            { left: '\\[', right: '\\]', display: true },
            { left: '\\(', right: '\\)', display: false },
            { left: '$', right: '$', display: false }
          ],
          throwOnError: false,
          strict: false,
          ignoredTags: ['script', 'noscript', 'style', 'textarea', 'pre', 'code']
        });
      } catch (error) {
        /* 渲染失败时保留原始文本，不打断阅读 */
        if (window.console && typeof window.console.warn === 'function') {
          window.console.warn('[学哲玩] 公式渲染失败：', error);
        }
      }
    }

    /* KaTeX 脚本用 defer 加载，可能晚于 site.js 执行：已就绪则立即渲染，否则等 load */
    if (typeof window.renderMathInElement === 'function') {
      render();
    } else {
      window.addEventListener('load', render);
    }
  }

  /* ----------------------------------------------------------------------
     启动
     ---------------------------------------------------------------------- */

  ready(function () {
    initTheme();
    initImageFallbacks();
    initNotesFilter();
    initWorksFilter();
    initMath();
  });
})();
