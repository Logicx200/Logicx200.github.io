/* =========================================================
   红外仿真项目 · 实时进度看板
   每 2 秒拉取同目录 progress.json；失败时保留内存 + localStorage 上次数据
   无第三方依赖，无外部网络请求
   ========================================================= */
(() => {
  "use strict";

  const POLL_INTERVAL = 2000;
  const FETCH_TIMEOUT = 6000;
  const MAX_LOGS = 30;
  const MAX_ARTIFACTS = 4;
  const CACHE_KEY = "ir-progress-dashboard.cache.v1";
  const THEME_KEY = "ir-progress-dashboard.theme.v1";
  const RING_CIRCUMFERENCE = 578.05;
  const SVG_NS = "http://www.w3.org/2000/svg";

  const STATUS = {
    pending: { label: "待启动" },
    running: { label: "进行中" },
    done: { label: "已完成" },
    blocked: { label: "受阻" },
  };

  const LEVELS = {
    info: { code: "INFO" },
    warn: { code: "WARN" },
    done: { code: "DONE" },
  };

  const reduceMotion = window.matchMedia
    ? window.matchMedia("(prefers-reduced-motion: reduce)").matches
    : false;

  const state = {
    data: null,
    previousData: null,
    lastSignature: null,
    lastSuccessAt: null,
    lastFetchAt: null,
    fetchInFlight: false,
    hasRendered: false,
    noDataRendered: false,
    cacheSaved: false,
    noticeKey: null,
    isFile: window.location.protocol === "file:",
    pollTimer: null,
  };

  const els = {};
  const numberFrames = new WeakMap();

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }

  function init() {
    cacheElements();
    initTheme();
    bindEvents();

    const cached = loadCache();
    if (cached) {
      state.data = cached.data;
      state.previousData = null;
      state.lastSignature = JSON.stringify(cached.data);
      state.hasRendered = true;
      state.lastSuccessAt = cached.savedAt ? new Date(cached.savedAt) : null;
      renderDashboard(cached.data, null);
      setConnection("cache", "缓存数据", "正在同步");
      if (state.lastSuccessAt && !Number.isNaN(state.lastSuccessAt.getTime())) {
        setText(els.lastSync, formatClock(state.lastSuccessAt));
        els.lastSync.title = `页面读取缓存：${formatFullDate(state.lastSuccessAt)}`;
        setText(els.footerSync, formatClock(state.lastSuccessAt));
      }
    }

    if (state.isFile) {
      enterFileMode();
    } else {
      if (!cached) {
        setConnection("connecting", "正在连接", "每 2 秒刷新");
      }
      fetchProgress();
      state.pollTimer = window.setInterval(fetchProgress, POLL_INTERVAL);
      console.info(`[进度看板] 自动刷新已启动，间隔 ${POLL_INTERVAL}ms`);
    }

    updateEtaCountdown();
    window.setInterval(updateEtaCountdown, 30000);

    document.addEventListener("visibilitychange", () => {
      if (!document.hidden && !state.isFile) {
        fetchProgress();
      }
    });

    window.addEventListener("online", () => {
      if (!state.isFile) {
        fetchProgress();
      }
    });
  }

  function cacheElements() {
    const ids = [
      "liveCard", "connLabel", "liveHint", "lastUpdated", "lastSync", "themeToggle",
      "notice", "noticeTitle", "noticeText", "noticeCommand",
      "projectTitle", "versionChip", "overallOrbit", "overallPercent", "ringFill",
      "stageHeading", "overallLabel", "etaText", "etaCountdown", "versionText",
      "doneMilestones", "totalMilestones", "phaseFill", "phaseMarker", "phaseCaption",
      "countRunning", "countDone", "countBlocked", "countPending",
      "nextAction", "focusText", "workstreamCount", "workstreamGrid",
      "timelineCount", "milestoneList", "logCount", "logList", "footerSync",
    ];
    ids.forEach((id) => {
      els[id] = document.getElementById(id);
    });
  }

  function bindEvents() {
    if (els.themeToggle) {
      els.themeToggle.addEventListener("click", toggleTheme);
    }
  }

  /* ------------------------- 主题 ------------------------- */

  function initTheme() {
    const saved = readStorage(THEME_KEY);
    applyTheme(saved === "light" ? "light" : "dark", false);
  }

  function toggleTheme() {
    const current = document.documentElement.getAttribute("data-theme") === "light" ? "light" : "dark";
    applyTheme(current === "light" ? "dark" : "light", true);
  }

  function applyTheme(theme, persist) {
    document.documentElement.setAttribute("data-theme", theme);
    const metaThemeColor = document.getElementById("themeColor");
    if (metaThemeColor) {
      metaThemeColor.setAttribute("content", theme === "light" ? "#eef4fa" : "#070b12");
    }
    if (els.themeToggle) {
      const label = theme === "light" ? "切换到深色主题" : "切换到浅色主题";
      els.themeToggle.setAttribute("aria-label", label);
      els.themeToggle.setAttribute("title", label);
    }
    if (persist) {
      writeStorage(THEME_KEY, theme);
    }
  }

  /* ------------------------- 数据拉取 ------------------------- */

  class DashboardError extends Error {
    constructor(kind, message, status) {
      super(message);
      this.name = "DashboardError";
      this.kind = kind;
      this.status = status;
    }
  }

  async function fetchProgress() {
    if (state.isFile || state.fetchInFlight) {
      return;
    }

    state.fetchInFlight = true;
    const controller = new AbortController();
    let timedOut = false;

    const timer = window.setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, FETCH_TIMEOUT);

    try {
      const response = await fetch(`progress.json?_=${Date.now()}`, {
        cache: "no-store",
        headers: { Accept: "application/json" },
        signal: controller.signal,
      });

      if (!response.ok) {
        const kind = response.status === 404 ? "missing" : "http";
        throw new DashboardError(kind, `HTTP ${response.status}`, response.status);
      }

      const raw = await response.text();
      let data;
      try {
        data = JSON.parse(raw);
      } catch (error) {
        throw new DashboardError("parse", "progress.json 不是合法 JSON");
      }

      assertValidProgress(data);
      handleProgressPayload(data);
    } catch (error) {
      if (!state.isFile) {
        let normalized;
        if (timedOut) {
          normalized = new DashboardError("timeout", "读取 progress.json 超时");
        } else if (error instanceof DashboardError) {
          normalized = error;
        } else if (error && error.name === "AbortError") {
          normalized = new DashboardError("timeout", "读取已取消");
        } else {
          normalized = new DashboardError("network", error && error.message ? error.message : "网络错误");
        }
        handleFetchError(normalized);
      }
    } finally {
      window.clearTimeout(timer);
      state.fetchInFlight = false;
    }
  }

  function handleProgressPayload(data) {
    const now = new Date();
    const previous = state.data;
    const signature = JSON.stringify(data);
    const changed = !state.hasRendered || signature !== state.lastSignature;

    state.data = data;
    state.lastSuccessAt = now;
    state.lastFetchAt = now;
    state.lastSignature = signature;

    if (changed) {
      renderDashboard(data, previous);
      state.hasRendered = true;
      state.noDataRendered = false;
      saveCache(data);
      state.cacheSaved = true;
    } else {
      updateEtaCountdown();
    }

    setConnection("live", "实时同步", "每 2 秒刷新");
    updateSyncClock(now);
    hideNotice();
  }

  function updateSyncClock(now) {
    const clock = formatClock(now);
    setText(els.lastSync, clock);
    setText(els.footerSync, clock);
    if (els.lastSync) {
      els.lastSync.title = `最近一次成功拉取：${formatFullDate(now)}`;
    }
  }

  /* ------------------------- 错误与空态 ------------------------- */

  function handleFetchError(error) {
    const hasData = Boolean(state.data);
    const kind = error.kind || "network";
    const retained = hasData
      ? ` 当前继续显示 ${state.lastSuccessAt ? formatClock(state.lastSuccessAt) : "上次"} 的数据，恢复连接后会自动更新。`
      : "";

    let title = "暂时无法读取进度";
    let text = "读取 progress.json 失败，将自动重试。";
    let command = "";

    if (kind === "missing") {
      title = "未找到 progress.json";
      text = "本地服务已连接，但看板目录中没有找到 progress.json。请确认文件与 index.html 位于同一目录，保存后会自动重试。";
      command = "python update_progress.py --show";
    } else if (kind === "parse") {
      title = "progress.json 解析失败";
      text = "文件不是合法 JSON，可能正在写入或格式有误。已保留上一次成功数据，下一次自动刷新会重试。";
    } else if (kind === "schema") {
      title = "progress.json 结构不完整";
      text = "文件缺少必要的 meta / overall / workstreams 字段，或字段类型不正确。已保留上一次成功数据。";
    } else if (kind === "timeout") {
      title = "读取进度超时";
      text = "读取 progress.json 超过 6 秒，请检查本地服务状态。看板会在 2 秒后自动重试。";
    } else if (kind === "http") {
      title = "本地服务返回异常";
      text = `HTTP 服务返回 ${error.status || "错误状态"}，请检查 python -m http.server 的运行日志。看板会自动重试。`;
    } else {
      title = "无法连接本地 HTTP 服务";
      text = "请确认本地静态服务仍在运行，并从 http://localhost:8766/ 打开本页。文件保存后会自动恢复同步。";
      command = "python -m http.server 8766";
    }

    showNotice("error", title, text + retained, command);
    setConnection(hasData ? "offline" : "error", hasData ? "连接中断" : "连接失败", "自动重试中");
    setText(els.lastSync, "重试中…");
    setText(els.footerSync, "等待重连");
    if (els.lastSync) {
      els.lastSync.title = state.lastSuccessAt
        ? `上次成功同步：${formatFullDate(state.lastSuccessAt)}`
        : "尚未成功同步";
    }

    if (!hasData && !state.noDataRendered) {
      renderNoData("暂时无法读取 progress.json，看板正在每 2 秒自动重试，请查看上方提示。");
      state.noDataRendered = true;
    }
  }

  function renderNoData(message) {
    if (els.stageHeading) {
      els.stageHeading.textContent = "等待数据";
    }
    if (els.overallLabel) {
      els.overallLabel.textContent = "尚未成功读取 progress.json。";
    }
    if (els.nextAction) {
      els.nextAction.textContent = "等待数据恢复后再显示下一步安排。";
    }
    if (els.workstreamGrid) {
      els.workstreamGrid.setAttribute("aria-busy", "false");
      els.workstreamGrid.replaceChildren(
        createEmptyState("暂无工作流数据", message)
      );
    }
    if (els.milestoneList) {
      els.milestoneList.replaceChildren(
        createEmptyState("暂无里程碑数据", "请确认数据文件包含 milestones 数组。")
      );
    }
    if (els.logList) {
      els.logList.replaceChildren(
        createEmptyState("暂无日志", "请确认数据文件包含 log 数组。")
      );
    }
  }

  function enterFileMode() {
    setConnection("file", "需 HTTP 访问", "受浏览器限制");
    setText(els.lastSync, "未同步");

    const notice = state.data
      ? "检测到 file:// 打开方式，浏览器会阻止读取 progress.json，无法实时刷新。当前显示的是本地缓存，请改用本地 HTTP 服务访问。"
      : "浏览器会阻止 file:// 页面读取 progress.json。请在本目录启动本地 HTTP 服务后访问对应地址，才能看到实时数据。";

    showNotice(
      "warning",
      "请通过本地 HTTP 服务打开看板",
      notice,
      "python -m http.server 8766  →  http://localhost:8766/"
    );

    if (!state.data) {
      renderNoData("当前为 file:// 打开方式，浏览器安全策略阻止读取 progress.json。请按上方提示通过本地 HTTP 服务访问。");
      state.noDataRendered = true;
    }
  }

  /* ------------------------- 渲染总入口 ------------------------- */

  function renderDashboard(data, previousData) {
    renderMeta(data, previousData);
    renderOverall(data);
    renderWorkstreams(data, previousData);
    renderMilestones(data);
    renderLogs(data, previousData);
    updateEtaCountdown();
  }

  function renderMeta(data, previousData) {
    const meta = isRecord(data.meta) ? data.meta : {};
    const overall = isRecord(data.overall) ? data.overall : {};

    const project = asText(meta.project, "");
    if (project) {
      setText(els.projectTitle, project);
      document.title = `${project} · 实时进度看板`;
    }

    const version = asText(meta.version, "—");
    setText(els.versionChip, `版本 ${version}`);
    setText(els.versionText, version);
    if (els.versionChip) {
      els.versionChip.title = `数据版本 ${version}`;
    }

    setText(els.stageHeading, asText(meta.stage, "阶段待更新"));

    const overallLabel = asText(overall.label, "");
    const summary = asText(meta.summary, "");
    const heroSummary = summary
      ? `${overallLabel ? `总体状态：${overallLabel}。` : ""}${summary}`
      : overallLabel || "总体状态待更新";
    setText(els.overallLabel, heroSummary);

    const updatedAt = asText(meta.updated_at, "—");
    const parsedUpdated = parseDate(meta.updated_at);
    setText(els.lastUpdated, parsedUpdated ? formatShortStamp(parsedUpdated) : updatedAt);
    if (els.lastUpdated) {
      els.lastUpdated.title = updatedAt;
      if (parsedUpdated) {
        els.lastUpdated.setAttribute("datetime", parsedUpdated.toISOString());
      } else {
        els.lastUpdated.removeAttribute("datetime");
      }
    }

    const workstreams = normalizeWorkstreams(data.workstreams);
    const running = workstreams.find((ws) => normalizeStatus(ws.status) === "running");
    const pending = workstreams.find((ws) => normalizeStatus(ws.status) === "pending");

    let nextAction = asText(meta.next_action, "");
    if (!nextAction) {
      if (running) {
        const owner = asText(running.owner, "");
        nextAction = `${running.name || running.id || "当前工作流"}${owner ? `（负责人 ${owner}）` : ""}：${asText(running.note, "正在推进")}`;
      } else if (pending) {
        nextAction = `下一项待启动：${pending.name || pending.id || "未命名工作流"}`;
      } else {
        nextAction = "暂无进行中的工作流，等待下一步安排。";
      }
    }
    setText(els.nextAction, nextAction);
    if (els.nextAction) {
      els.nextAction.title = nextAction;
    }

    let focus = asText(meta.focus, "");
    if (!focus) {
      focus = running
        ? `${asText(running.name || running.id, "当前工作流")} · ${asText(running.owner, "待分配")}`
        : "等待工作流启动";
    }
    setText(els.focusText, focus);
    if (els.focusText) {
      els.focusText.title = focus;
    }

    const milestones = normalizeMilestones(data.milestones);
    const done = milestones.filter((item) => item.done).length;
    setText(els.doneMilestones, String(done));
    setText(els.totalMilestones, String(milestones.length));

    // 若页面在未渲染任何数据前收到此函数调用，则清除 loading 提示计数
    setText(els.workstreamCount, `${workstreams.length} 条`);
  }

  function renderOverall(data) {
    const overall = isRecord(data.overall) ? data.overall : {};
    const percent = clampPercent(overall.percent);
    const rounded = Math.round(percent);

    animateNumber(els.overallPercent, rounded);

    if (els.overallOrbit) {
      els.overallOrbit.setAttribute("aria-label", `总体进度 ${rounded}%`);
    }
    if (els.ringFill) {
      els.ringFill.style.strokeDashoffset = String(RING_CIRCUMFERENCE * (1 - percent / 100));
    }
    if (els.phaseFill) {
      els.phaseFill.style.width = `${percent}%`;
    }
    if (els.phaseMarker) {
      els.phaseMarker.style.left = `${percent}%`;
    }

    let caption = "升级流程等待启动";
    if (percent >= 100) {
      caption = "正式报告流程已完成";
    } else if (percent >= 85) {
      caption = "进入报告交付与 PDF 校对阶段";
    } else if (percent >= 50) {
      caption = "升级工作已过半，继续收拢结果与文档";
    } else if (percent > 0) {
      caption = "升级流程已启动，当前处于前期建设阶段";
    }
    setText(els.phaseCaption, caption);
  }

  function renderWorkstreams(data, previousData) {
    const workstreams = normalizeWorkstreams(data.workstreams);
    const isFirstRender = !previousData || !Array.isArray(previousData.workstreams);
    const previousPercents = new Map();

    if (previousData && Array.isArray(previousData.workstreams)) {
      previousData.workstreams.forEach((ws) => {
        if (isRecord(ws) && ws.id != null) {
          previousPercents.set(String(ws.id), clampPercent(ws.percent));
        }
      });
    }

    const counts = { pending: 0, running: 0, done: 0, blocked: 0 };
    workstreams.forEach((ws) => {
      counts[normalizeStatus(ws.status)] += 1;
    });

    const total = workstreams.length;
    updateStat(els.countRunning, "running", counts.running, total);
    updateStat(els.countDone, "done", counts.done, total);
    updateStat(els.countBlocked, "blocked", counts.blocked, total);
    updateStat(els.countPending, "pending", counts.pending, total);
    setText(els.workstreamCount, `${total} 条`);

    if (!els.workstreamGrid) {
      return;
    }

    els.workstreamGrid.setAttribute("aria-busy", "false");
    if (!total) {
      els.workstreamGrid.replaceChildren(
        createEmptyState("暂无工作流", "progress.json 中的 workstreams 为空，请通过 update_progress.py 写入。")
      );
      return;
    }

    const fragment = document.createDocumentFragment();
    workstreams.forEach((ws, index) => {
      const id = ws.id != null ? String(ws.id) : String(index);
      const previousPercent = previousPercents.has(id) ? previousPercents.get(id) : 0;
      fragment.appendChild(createWorkstreamCard(ws, index, previousPercent, isFirstRender));
    });

    els.workstreamGrid.replaceChildren(fragment);

    // 下一帧再设置目标宽度，让进度条从上一版本的值平滑过渡
    window.requestAnimationFrame(() => {
      if (!els.workstreamGrid) {
        return;
      }
      els.workstreamGrid.querySelectorAll(".progress-fill").forEach((fill) => {
        fill.style.width = fill.dataset.targetWidth || "0%";
      });
    });
  }

  function createWorkstreamCard(ws, index, previousPercent, isFirstRender) {
    const status = normalizeStatus(ws.status);
    const percent = clampPercent(ws.percent);
    const rounded = Math.round(percent);
    const id = ws.id != null ? String(ws.id) : String(index);
    const name = asText(ws.name, id ? `工作流 ${id}` : "未命名工作流");
    const owner = asText(ws.owner, "待分配");
    const note = asText(ws.note, "暂无备注");
    const artifacts = Array.isArray(ws.artifacts)
      ? ws.artifacts.filter((item) => typeof item === "string" && item.trim())
      : [];

    const card = document.createElement("article");
    card.className = `ws-card status-${status}`;
    card.style.setProperty("--i", String(index));
    card.setAttribute(
      "aria-label",
      `${name}，${STATUS[status].label}，完成度 ${rounded}%`
    );

    if (isFirstRender && !reduceMotion) {
      card.classList.add("is-entering");
    }

    const top = createElement("div", "ws-top");
    const indexEl = createElement(
      "span",
      "ws-index",
      `${String(index + 1).padStart(2, "0")} / ${id || "—"}`
    );
    indexEl.title = `工作流 ID：${id || "—"}`;
    const badge = createElement("span", "status-badge", STATUS[status].label);
    top.append(indexEl, badge);

    const title = createElement("h3", "ws-title", name);
    title.title = name;

    const ownerEl = createElement("div", "ws-owner");
    ownerEl.append(createIcon("user"), createElement("span", "", owner));
    ownerEl.title = `负责人：${owner}`;

    const noteEl = createElement("p", "ws-note", note);
    noteEl.title = note;

    const progress = createElement("div", "ws-progress");
    const progressHead = createElement("div", "ws-progress-head");
    progressHead.append(
      createElement("span", "", "完成度"),
      createElement("strong", "", `${rounded}%`)
    );

    const bar = createElement("div", "progress-bar");
    bar.setAttribute("role", "progressbar");
    bar.setAttribute("aria-valuemin", "0");
    bar.setAttribute("aria-valuemax", "100");
    bar.setAttribute("aria-valuenow", String(rounded));
    bar.setAttribute("aria-label", `${name} 完成度`);

    const fill = createElement("span", "progress-fill");
    fill.style.width = `${previousPercent}%`;
    fill.dataset.targetWidth = `${percent}%`;
    bar.appendChild(fill);
    progress.append(progressHead, bar);

    const artifactWrap = createElement("div", "ws-artifacts");
    const artifactLabel = createElement(
      "span",
      "ws-artifacts-label",
      artifacts.length ? `产物文件 / ${artifacts.length}` : "产物文件"
    );
    const artifactList = document.createElement("ul");
    artifactList.className = "artifact-list";

    if (!artifacts.length) {
      artifactList.appendChild(createElement("li", "artifact-empty", "暂无产物"));
    } else {
      artifacts.slice(0, MAX_ARTIFACTS).forEach((artifact) => {
        const item = document.createElement("li");
        item.className = "artifact-chip";
        item.title = artifact;
        item.append(createIcon("file"), createElement("span", "artifact-name", basename(artifact)));
        artifactList.appendChild(item);
      });
      if (artifacts.length > MAX_ARTIFACTS) {
        const more = createElement("li", "artifact-more", `+${artifacts.length - MAX_ARTIFACTS}`);
        more.title = artifacts.join("\n");
        artifactList.appendChild(more);
      }
    }
    artifactWrap.append(artifactLabel, artifactList);

    card.append(top, title, ownerEl, noteEl, progress, artifactWrap);
    return card;
  }

  function updateStat(element, key, value, total) {
    if (!element) {
      return;
    }
    animateNumber(element, value);
    const card = element.closest(".stat-card");
    if (!card) {
      return;
    }
    const bar = card.querySelector(".stat-bar i");
    if (bar) {
      const ratio = total > 0 ? (value / total) * 100 : 0;
      bar.style.width = `${Math.max(ratio, value > 0 ? 8 : 0)}%`;
    }
  }

  function renderMilestones(data) {
    const milestones = normalizeMilestones(data.milestones);
    const doneCount = milestones.filter((item) => item.done).length;
    const nextIndex = milestones.findIndex((item) => !item.done);
    const now = Date.now();

    setText(els.timelineCount, `${doneCount}/${milestones.length} 已完成`);

    if (!els.milestoneList) {
      return;
    }

    if (!milestones.length) {
      els.milestoneList.replaceChildren(
        createEmptyState("暂无里程碑", "可在 progress.json 的 milestones 中添加计划节点。")
      );
      return;
    }

    const fragment = document.createDocumentFragment();
    milestones.forEach((item, index) => {
      const isDone = Boolean(item.done);
      const isNext = !isDone && index === nextIndex;
      const date = parseDate(item.time);
      const overdue = !isDone && date && date.getTime() < now;

      const li = document.createElement("li");
      li.className = "ms-item";
      if (isDone) {
        li.classList.add("done");
      } else if (isNext) {
        li.classList.add("is-next");
      }
      if (overdue) {
        li.classList.add("is-overdue");
      }

      const marker = createElement("span", "ms-marker");
      marker.appendChild(createIcon(isDone ? "check" : "flag"));
      marker.setAttribute("aria-hidden", "true");

      const content = createElement("div", "ms-content");
      const metaRow = createElement("div", "ms-time");

      const rawTime = asText(item.time, "时间待定");
      const timeNode = document.createElement(date ? "time" : "span");
      timeNode.textContent = date ? formatMilestoneTime(date) : rawTime;
      timeNode.title = rawTime;
      if (date) {
        timeNode.setAttribute("datetime", date.toISOString());
      }
      metaRow.appendChild(timeNode);

      let stateLabel = "计划中";
      if (isDone) {
        stateLabel = "已完成";
      } else if (isNext) {
        stateLabel = "下一步";
      } else if (overdue) {
        stateLabel = "待更新";
      }
      const stateBadge = createElement("span", "ms-state", stateLabel);
      metaRow.appendChild(stateBadge);

      const title = createElement("h3", "ms-title", asText(item.title, "未命名里程碑"));
      title.title = title.textContent;
      const detail = createElement("p", "ms-detail", asText(item.detail, ""));
      if (!detail.textContent) {
        detail.hidden = true;
      }

      content.append(metaRow, title);
      if (!detail.hidden) {
        content.appendChild(detail);
      }
      li.append(marker, content);
      fragment.appendChild(li);
    });

    els.milestoneList.replaceChildren(fragment);
  }

  function renderLogs(data, previousData) {
    const logs = normalizeLogs(data.log);
    const previousKeys = new Set();
    if (previousData) {
      normalizeLogs(previousData.log).forEach((item) => {
        previousKeys.add(logKey(item));
      });
    }

    const shown = logs.slice(-MAX_LOGS).reverse();
    setText(
      els.logCount,
      logs.length > MAX_LOGS ? `最近 ${MAX_LOGS} / ${logs.length} 条` : `${logs.length} 条 · 最新在上`
    );

    if (!els.logList) {
      return;
    }

    if (!shown.length) {
      els.logList.replaceChildren(
        createEmptyState("暂无日志", "update_progress.py --log 写入的日志会实时显示在这里。")
      );
      return;
    }

    const fragment = document.createDocumentFragment();
    shown.forEach((entry) => {
      const level = LEVELS[entry.level] ? entry.level : "info";
      const li = document.createElement("li");
      li.className = `log-entry level-${level}`;
      const key = logKey(entry);
      if (previousData && !previousKeys.has(key) && !reduceMotion) {
        li.classList.add("is-new");
      }

      const date = parseDate(entry.time);
      const time = document.createElement(date ? "time" : "span");
      time.className = "log-time";
      time.textContent = formatLogTime(entry.time);
      time.title = asText(entry.time, "");
      if (date) {
        time.setAttribute("datetime", date.toISOString());
      }

      const levelEl = createElement("span", "log-level", LEVELS[level].code);
      const text = createElement("p", "log-text", asText(entry.text, "—"));
      text.title = text.textContent;

      li.append(time, levelEl, text);
      fragment.appendChild(li);
    });

    els.logList.replaceChildren(fragment);
  }

  /* ------------------------- 连接状态 / 提示 ------------------------- */

  function setConnection(stateName, label, hint) {
    if (!els.liveCard) {
      return;
    }
    els.liveCard.dataset.state = stateName;
    setText(els.connLabel, label);
    setText(els.liveHint, hint || "每 2 秒刷新");
  }

  function showNotice(kind, title, text, command) {
    if (!els.notice) {
      return;
    }
    const resolvedCommand = command || "";
    const key = `${kind}|${title}|${text}|${resolvedCommand}`;
    if (state.noticeKey === key && !els.notice.hidden) {
      return;
    }
    state.noticeKey = key;
    els.notice.dataset.kind = kind;
    setText(els.noticeTitle, title);
    setText(els.noticeText, text);
    setText(els.noticeCommand, resolvedCommand);
    els.noticeCommand.hidden = !resolvedCommand;
    els.notice.hidden = false;
  }

  function hideNotice() {
    if (!els.notice || state.isFile) {
      return;
    }
    if (!els.notice.hidden) {
      els.notice.hidden = true;
    }
    state.noticeKey = null;
  }

  /* ------------------------- ETA / 元数据辅助 ------------------------- */

  function updateEtaCountdown() {
    if (!els.etaText || !els.etaCountdown) {
      return;
    }
    if (!state.data) {
      return;
    }

    const meta = isRecord(state.data.meta) ? state.data.meta : {};
    const rawEta = asText(meta.eta, "待确认");
    const eta = parseDate(meta.eta);

    if (!eta) {
      setText(els.etaText, rawEta);
      setText(els.etaCountdown, "未提供有效时间");
      els.etaText.title = rawEta;
      els.etaCountdown.title = rawEta;
      return;
    }

    setText(els.etaText, formatEtaTime(eta));
    els.etaText.title = rawEta;
    setText(els.etaCountdown, humanizeRemaining(eta.getTime() - Date.now()));
    els.etaCountdown.title = `预计完成时间：${formatFullDate(eta)}`;
  }

  /* ------------------------- 通用 DOM 工具 ------------------------- */

  function createElement(tag, className, text) {
    const element = document.createElement(tag);
    if (className) {
      element.className = className;
    }
    if (text !== undefined && text !== null) {
      element.textContent = String(text);
    }
    return element;
  }

  function createIcon(name, className) {
    const svg = document.createElementNS(SVG_NS, "svg");
    svg.setAttribute("class", className || "icon");
    svg.setAttribute("aria-hidden", "true");
    const use = document.createElementNS(SVG_NS, "use");
    use.setAttribute("href", `#i-${name}`);
    svg.appendChild(use);
    return svg;
  }

  function createEmptyState(title, message) {
    const wrap = createElement("div", "empty-state");
    wrap.append(
      createIcon("info"),
      createElement("strong", "", title),
      createElement("p", "", message)
    );
    return wrap;
  }

  function setText(element, text) {
    if (element) {
      element.textContent = text;
    }
  }

  function animateNumber(element, target) {
    if (!element) {
      return;
    }
    const finish = Math.max(0, Math.round(Number(target) || 0));
    const prior = Number(element.dataset.numberValue);
    const start = Number.isFinite(prior) ? prior : 0;
    element.dataset.numberValue = String(finish);

    if (numberFrames.has(element)) {
      window.cancelAnimationFrame(numberFrames.get(element));
      numberFrames.delete(element);
    }

    if (reduceMotion || start === finish) {
      element.textContent = String(finish);
      return;
    }

    const startedAt = performance.now();
    const duration = 600;
    const step = (now) => {
      const progress = Math.min(1, (now - startedAt) / duration);
      const eased = 1 - Math.pow(1 - progress, 3);
      element.textContent = String(Math.round(start + (finish - start) * eased));
      if (progress < 1) {
        numberFrames.set(element, window.requestAnimationFrame(step));
      } else {
        element.textContent = String(finish);
        numberFrames.delete(element);
      }
    };
    numberFrames.set(element, window.requestAnimationFrame(step));
  }

  /* ------------------------- 数据规范化 ------------------------- */

  function assertValidProgress(data) {
    if (!isRecord(data)) {
      throw new DashboardError("schema", "progress.json 根节点必须是对象");
    }
    if (!isRecord(data.meta)) {
      throw new DashboardError("schema", "缺少 meta 对象");
    }
    if (!isRecord(data.overall)) {
      throw new DashboardError("schema", "缺少 overall 对象");
    }
    if (!Array.isArray(data.workstreams)) {
      throw new DashboardError("schema", "缺少 workstreams 数组");
    }
    if (data.milestones != null && !Array.isArray(data.milestones)) {
      throw new DashboardError("schema", "milestones 必须是数组");
    }
    if (data.log != null && !Array.isArray(data.log)) {
      throw new DashboardError("schema", "log 必须是数组");
    }
  }

  function normalizeWorkstreams(value) {
    if (!Array.isArray(value)) {
      return [];
    }
    return value
      .filter((item) => isRecord(item))
      .map((item) => ({
        ...item,
        id: item.id != null ? String(item.id) : "",
        name: asText(item.name, ""),
        percent: clampPercent(item.percent),
        status: normalizeStatus(item.status),
        owner: asText(item.owner, ""),
        note: asText(item.note, ""),
        artifacts: Array.isArray(item.artifacts)
          ? item.artifacts.filter((artifact) => typeof artifact === "string" && artifact.trim())
          : [],
      }));
  }

  function normalizeMilestones(value) {
    if (!Array.isArray(value)) {
      return [];
    }
    return value
      .filter((item) => isRecord(item))
      .map((item) => ({
        time: item.time,
        title: item.title,
        detail: item.detail,
        done: Boolean(item.done),
      }));
  }

  function normalizeLogs(value) {
    if (!Array.isArray(value)) {
      return [];
    }
    return value
      .filter((item) => isRecord(item) && item.text != null)
      .map((item) => ({
        time: item.time,
        level: LEVELS[item.level] ? item.level : "info",
        text: String(item.text),
      }));
  }

  function normalizeStatus(value) {
    const status = typeof value === "string" ? value.toLowerCase() : "pending";
    return STATUS[status] ? status : "pending";
  }

  function logKey(entry) {
    return `${asText(entry.time, "")}\u0000${asText(entry.level, "")}\u0000${asText(entry.text, "")}`;
  }

  function clampPercent(value) {
    const parsed = typeof value === "number" ? value : Number.parseFloat(value);
    if (!Number.isFinite(parsed)) {
      return 0;
    }
    return Math.min(100, Math.max(0, parsed));
  }

  function isRecord(value) {
    return Boolean(value) && typeof value === "object" && !Array.isArray(value);
  }

  function asText(value, fallback) {
    if (value === undefined || value === null) {
      return fallback;
    }
    const text = String(value).trim();
    return text || fallback;
  }

  function basename(filePath) {
    const normalized = String(filePath).replace(/\\/g, "/");
    const parts = normalized.split("/").filter(Boolean);
    return parts.length ? parts[parts.length - 1] : normalized;
  }

  /* ------------------------- 时间工具 ------------------------- */

  function pad2(value) {
    return String(value).padStart(2, "0");
  }

  function parseDate(value) {
    if (value === undefined || value === null) {
      return null;
    }
    const text = String(value).trim();
    if (!text) {
      return null;
    }

    if (/^\d{4}-\d{2}-\d{2}$/.test(text)) {
      const [year, month, day] = text.split("-").map(Number);
      return new Date(year, month - 1, day, 23, 59, 59);
    }

    const normalized = text.replace(" ", "T");
    const parsed = new Date(normalized);
    return Number.isNaN(parsed.getTime()) ? null : parsed;
  }

  function formatClock(date) {
    return `${pad2(date.getHours())}:${pad2(date.getMinutes())}:${pad2(date.getSeconds())}`;
  }

  function formatFullDate(date) {
    return `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())} ${pad2(date.getHours())}:${pad2(date.getMinutes())}:${pad2(date.getSeconds())}`;
  }

  function formatShortStamp(date) {
    return `${pad2(date.getMonth() + 1)}-${pad2(date.getDate())} ${pad2(date.getHours())}:${pad2(date.getMinutes())}:${pad2(date.getSeconds())}`;
  }

  function formatEtaTime(date) {
    return `${pad2(date.getMonth() + 1)}-${pad2(date.getDate())} ${pad2(date.getHours())}:${pad2(date.getMinutes())}`;
  }

  function formatMilestoneTime(date) {
    return `${pad2(date.getMonth() + 1)}-${pad2(date.getDate())} ${pad2(date.getHours())}:${pad2(date.getMinutes())}`;
  }

  function formatLogTime(value) {
    const date = parseDate(value);
    if (!date) {
      return asText(value, "—");
    }
    const today = new Date();
    const sameDay =
      date.getFullYear() === today.getFullYear() &&
      date.getMonth() === today.getMonth() &&
      date.getDate() === today.getDate();
    return sameDay
      ? formatClock(date)
      : `${pad2(date.getMonth() + 1)}-${pad2(date.getDate())} ${pad2(date.getHours())}:${pad2(date.getMinutes())}`;
  }

  function humanizeRemaining(diffMs) {
    if (!Number.isFinite(diffMs)) {
      return "未提供有效时间";
    }
    if (diffMs <= 0) {
      const overdue = Math.abs(diffMs);
      const days = Math.floor(overdue / 86400000);
      const hours = Math.floor((overdue % 86400000) / 3600000);
      if (days > 0) {
        return `已超期 ${days} 天${hours > 0 ? ` ${hours} 小时` : ""}`;
      }
      if (hours > 0) {
        return `已超期约 ${hours} 小时`;
      }
      return "已到预计完成时间";
    }

    const days = Math.floor(diffMs / 86400000);
    const hours = Math.floor((diffMs % 86400000) / 3600000);
    const minutes = Math.floor((diffMs % 3600000) / 60000);

    if (days > 0) {
      return `剩余 ${days} 天 ${hours} 小时`;
    }
    if (hours > 0) {
      return `剩余 ${hours} 小时 ${minutes} 分`;
    }
    return `剩余 ${Math.max(1, minutes)} 分钟`;
  }

  /* ------------------------- 缓存 ------------------------- */

  function loadCache() {
    const raw = readStorage(CACHE_KEY);
    if (!raw) {
      return null;
    }
    try {
      const payload = JSON.parse(raw);
      if (!isRecord(payload) || !payload.data) {
        return null;
      }
      assertValidProgress(payload.data);
      return {
        data: payload.data,
        savedAt: Number(payload.savedAt) || null,
      };
    } catch (error) {
      removeStorage(CACHE_KEY);
      return null;
    }
  }

  function saveCache(data) {
    try {
      writeStorage(
        CACHE_KEY,
        JSON.stringify({
          data,
          savedAt: Date.now(),
        })
      );
    } catch (error) {
      // localStorage 不可用或空间已满时静默降级为仅内存保留
    }
  }

  function readStorage(key) {
    try {
      return window.localStorage.getItem(key);
    } catch (error) {
      return null;
    }
  }

  function writeStorage(key, value) {
    try {
      window.localStorage.setItem(key, value);
    } catch (error) {
      // Ignore private mode / quota failures.
    }
  }

  function removeStorage(key) {
    try {
      window.localStorage.removeItem(key);
    } catch (error) {
      // Ignore.
    }
  }
})();
