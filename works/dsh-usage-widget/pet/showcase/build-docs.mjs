/**
 * build-docs.mjs —— 用 11 张实拍图与 states.json 生成展示文档。
 *
 *   pet/showcase/展示文档.html   自包含：图片全部 base64 内嵌、零外链、零脚本外链
 *   pet/showcase/README.md       纯文字索引（逐状态：标签/颜色/触发字段/她的反应）
 *
 * 用法：node pet/showcase/build-docs.mjs
 */
import { readFileSync, writeFileSync, statSync, existsSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = dirname(fileURLToPath(import.meta.url))
const states = JSON.parse(readFileSync(join(HERE, 'states.json'), 'utf8'))

/** 每个状态：她的表情 / 动作 / 台词（与 pet/renderer/reactions.js 的 ACT 表一致）。 */
const REACTION = {
  offline: {
    face: '阴暗 `gloomy`（无道具）',
    motion: '不打任何动作；不播音乐、不冒台词',
    say: '—',
  },
  stale: {
    face: '闭眼口水 `drool`（睡着）',
    motion: '安静待机；不打动作',
    say: '—',
  },
  error: {
    face: '阴暗 `gloomy`，**1.6 s**，且不叠任何别的东西',
    motion: '不播动作（大锤 `aidale` 永久禁用）',
    say: '「（脸黑了）这个工具报错了：<工具名> · <错误码>」',
  },
  celebrating: {
    face: '开心兴奋 `excited` + 随机一个装饰：猫猫贴纸 / 兔兔贴纸 / 情绪花花 / 心跳',
    motion: '纯 CSS 蹦一下（`qBounce`，不碰模型参数）',
    say: '「都弄好了…」等 3 句轮换 + 统计行「12.3s · 41380 tokens」',
  },
  listening: {
    face: '星星眼 `starry`',
    motion: '不打动作',
    say: '气泡里放主人原话（截 60 字）',
  },
  team: {
    face: '平常脸（`null`）+ 板子 + 笔',
    motion: '不打动作',
    say: '「（招手）叫个分身来帮忙」等 3 句轮换',
  },
  reading: {
    face: '三副眼镜随机（圆 34% / 方 28% / 不戴 28% / 椭圆 10%）+ 板子 + 笔；**设备类工具**（`web_search`/`web_fetch`/`browser`/`search_*`）另外**掏出小设备（`openLid` 定格）**',
    motion: '设备类播 `openLid`，播完把参数抽成定格层保持住（框架没有 `hold`）',
    say: '「（凑近看）先读一下这份」「（掏手机）上网查一下」等，脚注为参数摘要',
  },
  writing: {
    face: '认真脸（`null`）+ 板子 + 笔',
    motion: '不打动作（「奋笔疾书」**没有专属素材**，见缺口 2）',
    say: '「好，人家写出来」「（奋笔疾书）写上了」等',
  },
  running: {
    face: '认真脸（`null`）+ 板子 + 笔',
    motion: '不打动作（「挽袖子」**没有专属素材**，见缺口 2）',
    say: '「（挽袖子）跑个命令试试」等',
  },
  thinking: {
    face: '平常脸（`null`）+ 板子 + 笔；主人明确要求「想事就是平常脸」，**不用呆滞眼**',
    motion: '不打动作；逐字输出时口型 `ParamMouthOpenY` 按正弦开合',
    say: '—',
  },
  idle: {
    face: '平常脸（`null`）→ 久闲：换表情几秒（吐舌/调皮/问号/脸红/星星眼随机）、换视线、自言自语、喊饿；>99 s 打哈欠、>180 s 睡着（闭眼口水）',
    motion: '不打动作（**`idle.motion3.json` 已停用**：它是猫爪摆手+爱心循环，见缺口 4）',
    say: '「（发呆）…」「人家在呢」「…要不要喝点水？」「（肚子叫）有点饿了…」',
  },
}

const rows = []
let embedded = 0
let missing = []
for (const s of states) {
  const png = join(HERE, `state-${s.state}.png`)
  if (!existsSync(png)) { missing.push(png); continue }
  const b64 = readFileSync(png).toString('base64')
  embedded += 1
  const size = statSync(png).size
  const r = REACTION[s.state] ?? { face: '—', motion: '—', say: '—' }
  rows.push({ ...s, b64, size, reaction: r })
}

// ---------------------------------------------------------------- README.md ---
const md = []
md.push('# 桌宠 11 个活动状态 · 实拍索引')
md.push('')
md.push('> 生成：`pet/showcase/build-docs.mjs`（图片：`pet/showcase/state-<state>.png`，11 张，同一裁剪区域 436×545）')
md.push('> 采集方式：生产看板照常运行，用页面已有的强制状态通道（`postMessage({type:\'pet-force\'})`）只替换状态值，')
md.push('> 桌宠窗口仍是平时那个窗口、平时那个位置；拍完立即解除强制，恢复生产轮询。')
md.push('')
md.push('| # | `state` | 中文标签 | 颜色 | pose | 触发信号（日志字段） | 她的表情 / 动作 | 图 |')
md.push('|---|---|---|---|---|---|---|---|')
states.forEach((s, i) => {
  const r = REACTION[s.state] ?? {}
  const cell = (t) => String(t).replace(/\|/g, '\\|').replace(/\n/g, ' ')
  md.push(`| ${i + 1} | \`${s.state}\` | ${s.label} | \`${s.color}\` | \`${s.pose}\` | ${cell(s.trigger)} | ${cell(r.face)} | \`state-${s.state}.png\` |`)
})
md.push('')
md.push('## 每个状态细节')
md.push('')
for (const s of states) {
  const r = REACTION[s.state] ?? {}
  md.push(`### ${s.label} · \`${s.state}\` · \`${s.color}\``)
  md.push('')
  md.push(`- 触发信号：${s.trigger}`)
  md.push(`- 引擎给出的 reason：\`${s.reason}\``)
  md.push(`- detail 行：${s.detail ? `\`${s.detail}\`` : '（空）'}`)
  md.push(`- 表情 / 道具：${r.face}`)
  md.push(`- 动作：${r.motion}`)
  md.push(`- 台词：${r.say}`)
  md.push(`- 截图：\`state-${s.state}.png\``)
  md.push('')
}
md.push('## 已知缺口（如实标注，没有美化）')
md.push('')
const GAPS = [
  '**桌宠全程穿透**：这是既定偏好（宿主设 `WS_EX_TRANSPARENT`；实测窗口内 11 个探测点全部落到下层窗口，读数见 `pet/host/task13-passthrough.txt`）。她的动作与表情只由**事件与参数通道**驱动，没有任何指针入口。',
  '**`奋笔疾书` / `挽袖子` / `走路般摆动` 没有素材**：不伪造。写文件用认真脸 + 板子/笔 + 台词「（奋笔疾书）写上了」；跑命令同理用「（挽袖子）跑个命令试试」；`走路般摆动` 完全不实现。',
  '**没有 token 级流式信号**：DSH 会话日志里没有任何 `agent/assistant-stream` 记录（25 个 artifact 实测 0 条），所以引擎只发「一个 assistant 步骤开着」的紧凑信号，**逐字冒字由页面按时间自己做**（60 ms 一个字 ≈ 16 字/秒）。',
  '**黑脸 1.6 s，但状态窗口取 3.2 s**：引擎按 2 s 折叠会话日志，1.6 s 的窗口可能整段落在两次轮询之间 → 标签永远不显示「出错了」。所以**脸仍然只黑 1.6 s**（`REACTIONS-SPEC` §3.3 的原值），状态窗口放宽到 3.2 s 保证可见。',
  '**`ask_user_question` 归到「想事情」**：11 个活动类别里没有「问你」这一档，所以状态取 `thinking`，表情仍用具象的 `question`（问号）+ 台词「（歪头）这个得问问主人」。',
  '**`peak` 峰时不再是状态**：峰谷是看板页脚的职责，已从标签轮转删除（spec 里保留为可选第 12 档，不实现）。',
  '**快工具的脸延后 2.5 s**：引擎 2 s 折叠，`read`/`edit` 这类工具被看到时往往已经是 `result`；若只在 `call` 阶段挂脸，眼镜/笔/手机几乎永远不出现，所以成功结果也挂 2.5 s 该活动的脸，然后回落到 state.json 的 base。',
  '**`idle.motion3.json` 不播**：它其实是「猫爪摆手 + 爱心」循环（`Meta.Loop=true`），原作者已停用；页面不再传 `idleMotionGroup`（框架默认组名 `Idle` 在模型里不存在 → 永不自动播）。`aidale`（大锤砸）与 `bubble`（吹泡泡糖）双拦。',
]
GAPS.forEach((g, i) => md.push(`${i + 1}. ${g}`))
md.push('')
md.push('## 授权（派生作品）')
md.push('')
md.push('模型素材 **CC BY-NC-SA 4.0**（署名—非商业性使用—相同方式共享），版权归 **上善无形 / ZipZipPipe / 氵六青**。')
md.push('本次补 `FileReferences.Expressions`（44 条）与 `Groups[LipSync].Ids = ["ParamMouthOpenY"]` 属于**对模型的改编**，')
md.push('因此 `pet/model/c_0120.model3.json` 是**派生作品**：个人 / 给朋友的小范围自用可以；')
md.push('一旦对外分发**必须** ① 保留三位署名、② **不得商用**、③ 以相同协议（CC BY-NC-SA 4.0）发布、④ 注明修改内容。')
md.push('**不能只挂仓库的 MIT。** 详见 `pet/model/LICENSES/DERIVATIVE-model3-json.md`。')
md.push('')
writeFileSync(join(HERE, 'README.md'), md.join('\n'), 'utf8')

// ------------------------------------------------------------ 展示文档.html ---
const esc = (t) => String(t).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
const inline = (t) => esc(t).replace(/`([^`]+)`/g, '<code>$1</code>').replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')

const html = []
html.push('<!DOCTYPE html>')
html.push('<html lang="zh-CN"><head><meta charset="utf-8">')
html.push('<title>鲸鱼娘 · 11 个活动状态实拍</title>')
html.push('<style>')
html.push(':root{--bg:#12151b;--card:#1b1f27;--line:#2a313d;--fg:#e6edf3;--dim:#9da7b3}')
html.push('*{box-sizing:border-box}')
html.push('body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.6 "Microsoft YaHei",system-ui,sans-serif}')
html.push('header{padding:26px 22px 10px;border-bottom:1px solid var(--line)}')
html.push('h1{margin:0 0 6px;font-size:22px}')
html.push('h2{margin:0 0 4px;font-size:19px}')
html.push('.sub{color:var(--dim);font-size:13px}')
html.push('main{padding:18px 22px 60px;max-width:1180px;margin:0 auto}')
html.push('.state{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px 18px;margin:18px 0}')
html.push('.head{display:flex;align-items:center;gap:12px;flex-wrap:wrap}')
html.push('.sw{width:22px;height:22px;border-radius:6px;border:1px solid rgba(255,255,255,.18)}')
html.push('.hex{font:13px/1 ui-monospace,Consolas,monospace;color:var(--dim)}')
html.push('.cols{display:grid;grid-template-columns:minmax(320px,436px) 1fr;gap:18px;align-items:start;margin-top:12px}')
html.push('.cols img{width:100%;height:auto;border-radius:8px;border:1px solid var(--line);display:block}')
html.push('dl{margin:0}')
html.push('dt{color:var(--dim);font-size:12px;letter-spacing:.04em;text-transform:uppercase;margin-top:10px}')
html.push('dd{margin:2px 0 0}')
html.push('code{background:#0e1116;border:1px solid var(--line);border-radius:5px;padding:1px 5px;font:12.5px/1.5 ui-monospace,Consolas,monospace}')
html.push('.gaps{background:#1b1f27;border:1px solid var(--line);border-radius:12px;padding:16px 18px;margin:26px 0}')
html.push('.gaps li{margin:8px 0}')
html.push('.lic{background:#1b1f27;border:1px solid var(--line);border-radius:12px;padding:16px 18px}')
html.push('@media (max-width:820px){.cols{grid-template-columns:1fr}}')
html.push('</style></head><body>')
html.push('<header><h1>鲸鱼娘 · 11 个活动状态实拍</h1>')
html.push(`<div class="sub">同一裁剪区域 436&times;545（看板主体 + 人物），由 <code>pet/showcase/build-docs.mjs</code> 生成 · 图片 ${embedded} 张全部 base64 内嵌 · 零外链</div></header>`)
html.push('<main>')
for (const s of rows) {
  const r = s.reaction
  html.push('<section class="state">')
  html.push(`<div class="head"><span class="sw" style="background:${esc(s.color)}"></span><h2>${esc(s.label)}</h2><code>${esc(s.state)}</code><span class="hex">${esc(s.color)}</span><span class="hex">pose: ${esc(s.pose)}</span></div>`)
  html.push('<div class="cols">')
  html.push(`<img alt="${esc(s.label)} 状态实拍" src="data:image/png;base64,${s.b64}">`)
  html.push('<dl>')
  html.push(`<dt>触发信号（日志字段）</dt><dd>${inline(s.trigger)}</dd>`)
  html.push(`<dt>引擎给出的 reason</dt><dd><code>${esc(s.reason)}</code></dd>`)
  html.push(`<dt>标签 / detail 行</dt><dd>${esc(s.label)}${s.detail ? ` · <code>${esc(s.detail)}</code>` : ' · （detail 为空）'}</dd>`)
  html.push(`<dt>她的表情 / 道具</dt><dd>${inline(r.face)}</dd>`)
  html.push(`<dt>动作</dt><dd>${inline(r.motion)}</dd>`)
  html.push(`<dt>台词</dt><dd>${inline(r.say)}</dd>`)
  html.push(`<dt>截图</dt><dd><code>pet/showcase/state-${esc(s.state)}.png</code> · ${Math.round(s.size / 1024)} KB</dd>`)
  html.push('</dl></div></section>')
}
html.push('<section class="gaps"><h2>已知缺口（如实标注，没有美化）</h2><ol>')
for (const g of GAPS) html.push(`<li>${inline(g)}</li>`)
html.push('</ol></section>')
html.push('<section class="lic"><h2>授权（派生作品）</h2>')
html.push('<p>模型素材 <strong>CC BY-NC-SA 4.0</strong>（署名—非商业性使用—相同方式共享），版权归 <strong>上善无形 / ZipZipPipe / 氵六青</strong>。本页展示的模型元数据补了 <code>FileReferences.Expressions</code>（44 条）与 <code>Groups[LipSync].Ids = ["ParamMouthOpenY"]</code>，属于<strong>对模型的改编</strong>，因此 <code>pet/model/c_0120.model3.json</code> 是<strong>派生作品</strong>：个人 / 给朋友的小范围自用可以；一旦对外分发必须 ① 保留三位署名、② <strong>不得商用</strong>、③ 以相同协议（CC BY-NC-SA 4.0）发布、④ 注明修改内容。<strong>不能只挂仓库的 MIT。</strong></p>')
html.push('<p class="sub">详见 <code>pet/model/LICENSES/DERIVATIVE-model3-json.md</code> 与 <code>pet/REACTIONS-SPEC.md</code> §12。</p>')
html.push('</section></main></body></html>')

const htmlPath = join(HERE, '展示文档.html')
writeFileSync(htmlPath, html.join('\n'), 'utf8')
console.log(`embedded images : ${embedded}/${states.length}`)
if (missing.length) console.log('MISSING:', missing.join(', '))
console.log(`html            : ${htmlPath} (${Math.round(statSync(htmlPath).size / 1024)} KB)`)
console.log(`readme          : ${join(HERE, 'README.md')} (${Math.round(statSync(join(HERE, 'README.md')).size / 1024)} KB)`)
console.log('external refs   : ' + ((/src="(?!data:)/.test(html.join('\n')) || /href="http/.test(html.join('\n'))) ? 'FOUND (bad)' : 'none'))
