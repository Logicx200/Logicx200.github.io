# 桌宠工作状态协议 · Pet Work-State Protocol

The contract between the Live2D pet and DSH's current work state. Two consumers
must never disagree about it: `state.mjs` (the model, this directory) and the
renderer that draws the pet plus the top-right label.

- Model: `pet/state.mjs` — pure, synchronous, Node built-ins only, no I/O, no
  timers, no wall clock. One observation in, one state out.
- Test: `pet/test/state.test.mjs` — 214 checks on the state model, exits
  non-zero on failure.
- Test: `pet/test/state-cli.test.mjs` — 23 checks on the CLI's pure pieces
  (argument parsing, the ASCII-cwd rule, the NDJSON fold), exits non-zero on
  failure.
- Reality check: `pet/state-cli.mjs` — runs the real engine once and prints the
  state.

Everything the integration needs is in this file. You should not have to open
the source to render a state; if this document and `state.mjs` ever disagree,
`state.mjs` wins and this file is the bug.

---

## 1. The output

```js
import { computeState } from './state.mjs'

const result = computeState({
  snapshot,      // the engine's latest {"type":"snapshot",…} object, or null
  lastEventAt,   // ms timestamp of the most recent {"type":"event",…}, or null
  dshRunning,    // true | false | null/undefined — the widget's Test-DshRunning
  now,           // ms, the poll time (pass Date.now() in the integration)
})

// {
//   state:  'team',        // stable lower-case enum — the renderer switches on THIS
//   label:  '团队协作',     // top-right corner text, <= 6 chars
//   color:  '#56D4DD',     // that label's colour, #RRGGBB
//   detail: '运行 2 个智能体 · Define the pet work-state model and colours',
//   pose:   'team',        // semantic animation hint, NOT a filename
//   reason: '2 agents running',   // why this state won, for logs/debugging
//   source: 'snapshot',           // 'snapshot' | 'none' — where the state came from
// }
```

`state`, `label`, `color` and `pose` for a given state are **frozen**: the
renderer may hard-code its switch, and the colours must not drift. `detail` and
`reason` are informational; `detail` is `''` when there is nothing worth saying.

`pose` is deliberately semantic. A teammate is fetching the model and may end up
with Chinese or English motion/expression names; the integration maps
`idle|busy|team|sleepy|happy|offline` onto real assets later. The model layer
never names a file.

---

## 2. The state table

Priority runs top to bottom; **the first row whose trigger holds wins** and
exactly one state is ever returned. Since task-7 the eleven states are
**activity categories** ("她正在干什么"), not abstract moods: the tool the agent
invoked decides the face and the word. All eleven labels and all eleven colours
are pairwise distinct.

| # | `state` | `label` | `color` | `pose` | Exact trigger |
|---|---|---|---|---|---|
| 1 | `offline` | 离线 | `#8B949E` | `offline` | `dshRunning === false` |
| 2 | `stale` | 数据过期 | `#D2A8FF` | `sleepy` | snapshot absent, `snapshot.at` not finite, or `now - snapshot.at > 45 000 ms` |
| 3 | `error` | 出错了 | `#F85149` | `gloomy` | a `tool/result` with `error`/`isError` less than **1 600 ms** old, **or** a `turn/end` with `reason.kind === 'error'` less than 3 200 ms old |
| 4 | `celebrating` | 收工啦 | `#E3B341` | `happy` | `turn/end` with `reason.kind === 'completed'` (or absent) less than **3 000 ms** old |
| 5 | `listening` | 听主人说 | `#79C0FF` | `starry` | a `user/message` with `source.kind === 'user'` less than **2 600 ms** old |
| 6 | `team` | 团队协作 | `#56D4DD` | `team` | **≥ 2** agents with `state === 'running'` (or `'busy'`) |
| 7 | `reading` | 查资料 | `#58A6FF` | `reading` | newest tool call (no result yet, < 60 s old) is a read tool — `read`/`grep`/`web_search`/`web_fetch`/`skill`/… , including the unmatched-tool fallback |
| 8 | `writing` | 写文件 | `#F0883E` | `scribble` | newest in-flight tool is `write` / `edit` / `todo_write` |
| 9 | `running` | 跑命令 | `#FFA657` | `sleeves` | newest in-flight tool is a shell tool (`pwsh`/`bash`/…), **or** `snapshot.jobs.length >= 1` |
| 10 | `thinking` | 想事情 | `#A5D6FF` | `thinking` | a turn is producing (`assistant` step open), one running agent wrote within 30 s, or `lastEventAt` within 30 000 ms |
| 11 | `idle` | 空闲 | `#9DA7B3` | `idle` | fallback — DSH up, nothing happening |

`peak` **used to be a state and no longer is**: peak/off-peak pricing is the
panel footer's story, not "what she is doing". `snapshot.peakNow` is still in the
snapshot and may return as a 12th badge (REACTIONS-SPEC §2 keeps it as an
optional slot); it deliberately does **not** enter the label rotation.

Colour contrast against `#1B1F27` (the panel's background; 86 % opacity over a
desktop is the conservative bound for light text), WCAG 2.1 relative luminance:

| state | ratio | verdict |
|---|---|---|
| `offline` `#8B949E` | 5.37 : 1 | AA (≥ 4.5) |
| `stale` `#D2A8FF` | 8.48 : 1 | AAA |
| `error` `#F85149` | 4.93 : 1 | AA |
| `celebrating` `#E3B341` | 8.48 : 1 | AAA |
| `listening` `#79C0FF` | 8.49 : 1 | AAA |
| `team` `#56D4DD` | 9.32 : 1 | AAA |
| `reading` `#58A6FF` | 6.54 : 1 | AA |
| `writing` `#F0883E` | 6.52 : 1 | AA |
| `running` `#FFA657` | 8.53 : 1 | AAA |
| `thinking` `#A5D6FF` | 10.74 : 1 | AAA |
| `idle` `#9DA7B3` | 6.77 : 1 | AAA |

**Reserved colours.** The panel already spends `#7EE787` (green) on cache
**hit** and `#FF7B72` (red) on cache **miss**. The pet must never use either, or
a green whale would read as "cache hit". Both are banned by
`RESERVED_COLORS` and asserted absent by the test. `error` deliberately uses the
GitHub "danger" red `#F85149` (4.93 : 1) rather than borrowing `#FF7B72`: it is
visibly red, far enough from the panel's miss-red to be distinguishable side by
side, and it keeps the panel's two semantic colours untouched.

### Why these colours

| state | hue | reading |
|---|---|---|
| `team` | cyan `#56D4DD` | a cool, "connected" accent; cyan is unused elsewhere on the panel |
| `running` | orange `#FFA657` | the panel's job rows are neutral; orange says "a program is chewing" without borrowing red |
| `reading` | blue `#58A6FF` | the panel's own accent family, "reading something" |
| `writing` | amber `#F0883E` | a warmer orange than `running`: pen on paper, never red |
| `listening` | light blue `#79C0FF` | the old `working` blue, now "the user is talking" |
| `thinking` | pale blue `#A5D6FF` | the calmest of the blues: nothing is moving yet |
| `celebrating` | warm gold `#E3B341` | reads as "price/attention"-free celebration, close to no other state |
| `error` | red `#F85149` | unmistakable, and not the panel's miss-red |
| `idle` | steel `#9DA7B3` | the panel's dim grey; visibly calmer than everything else |
| `stale` | violet `#D2A8FF` | unmistakably "something is wrong with the feed" |
| `offline` | darker grey `#8B949E` | deliberately *less* prominent than `idle`: no app, no news |

---

## 3. Priority order and why

```
offline > stale > error > celebrating > listening > team
        > reading > writing > running > thinking > idle
```

This keeps the brief's own reading — offline > 团队协作 > 后台任务 > 干活中 >
峰时 > 空闲 — and inserts `stale` **once**, directly below `offline`, plus the
three one-shot tiers above `team`. The reasoning, row by row:

1. **`offline` first.** If DSH is not running there is no work by definition, and
   the panel hides itself anyway. Nothing may outrank it, so `dshRunning === false`
   short-circuits everything, even a snapshot still full of running agents.
2. **`stale` second — as a validity gate.** Every signal below it is read *out of
   the snapshot*. A frame older than 45 s, or no frame at all, means the engine
   died and the widget is painting a memory. The brief's hard requirement is that
   "stale data must not read as working"; the only way to guarantee that for
   *all* snapshot-derived states is to check freshness before using any of them.
   It sits below `offline` because "the app is gone" is stronger and
   `dshRunning` comes from outside the snapshot.
   *When `dshRunning` is unknown* (older caller, `undefined`/`null`), the model
   also requires a fresh snapshot before believing anything, so an unknown
   process state plus a dead engine degrades to `stale`, never to a false
   `team`/`busy`/`working`.
3. **`team` over `busy`.** A live agent turn is DSH's own strongest statement that
   it is working; jobs are tools *within* such a turn. Two or more running agents
   is genuinely 团队协作 — and showing the collaboration when it exists is the
   pet's whole point.
   *Refinement the brief left open:* "团队" needs a team. Exactly **one** running
   agent is not collaboration, so it falls through to `busy`/`working`, where its
   own merits still get it on screen (a fresh write makes it 干活中). A single
   dormant agent with no job and no events reads as 空闲 — honest, and it stops
   an abandoned turn from pinning the pet at "working" forever.
4. **`busy` over `working`.** Both are truthful at once when a job runs and an
   event is recent; the priority must break the tie. A background job is a real,
   verifiable process with a `startedAt`, an `elapsedMs` and often a measured
   percentage — it is *still consuming resources right now*. An `event` is a
   settle-time log sample: the engine only emits it once the model call has been
   written to the log, so 干活中 is the laggier signal and can linger for up to
   30 s after work stopped. 后台任务 also carries the more useful `detail`.
5. **`working` over `peak`.** 干活中 means tokens exist; 峰时 is only pricing
   context. Work always outranks a price band.
6. **`peak` over `idle`.** `peakNow` while otherwise quiet changes what the panel
   is spending, so it deserves its own colour rather than blending into 空闲 —
   but only when nothing is happening, exactly as the brief requires.
7. **`idle` last.** The fallback: DSH up, no agent, no job, no recent tokens.

---

## 4. Constants

| constant | value | purpose | why this number |
|---|---|---|---|
| `EVENT_RECENT_MS` | `30 000` | an `event` this fresh means 干活中 | The engine polls every 2 s, but an event is emitted when a call is *settled*, typically 5–60 s apart. 25 s would flicker to 空闲 during a normal long response; 30 s rides over one slow call. Named `event` is the only honest "tokens just landed" signal, so the number should be generous but sub-minute. |
| `SNAPSHOT_STALE_MS` | `45 000` | older than this, the frame is disbelieved → 数据过期 | 15 missed 2 s polls, so a slow fold or a suspended laptop does not flicker the pet. Tight enough that a dead engine stops painting activity in under a minute. |
| `AGENT_ACTIVE_MS` | `30 000` | a running agent with no write for this long contributes no activity | Matches the event window: one clock for "recent" keeps the model explainable. `sinceLastWriteMs` is the only freshness an agent row carries. |
| `ASSUME_ACTIVE_WHEN_AGE_MISSING` | `true` | an agent row with no `sinceLastWriteMs` counts as active | A newer engine that omits the field must not be punished into 空闲. |
| `JOB_STOPPING_MS` | `15 000` | a job stuck in `stopping` longer than this is called out | A `stopping` job still occupies the machine; after 15 s it is worth showing in `detail`. |
| `DETAIL_MAX_CHARS` | `64` | hard cap on `detail` | Keeps one line inside the pet area at the panel's 12–14 px font. |
| `PANEL_BACKGROUND` | `#1B1F27` | contrast reference | The pet area's background. |
| `RESERVED_COLORS` | `#7EE787`, `#FF7B72` | never used | Cache hit / miss already own them. |

Also exported: `PET_STATES` (the table), `STATE_PRIORITY`, `STATE_VALUES`,
`POSE_VALUES`, `pillFor(state)`, `priorityOf(state)`, `formatProgress`,
`selectState`, `normalizeObservation`, `jobFacts`, `agentFacts`, `describe`.

---

## 5. Input defensiveness (edge cases)

The model never throws. Every one of these is covered by the test:

| input | result | note |
|---|---|---|
| `agents: []` / `jobs: []` | `idle` (or `peak`) | empty is a fact, not an error |
| `agents` / `jobs` key missing entirely | 0 rows | an older engine that omits the arrays cannot break the pet |
| `agents` not an array, or rows are `null`/numbers | 0 usable rows | non-object rows are dropped |
| `agents` present, all `state:"idle"` | falls through | idle agents are not activity |
| `snapshot` missing / not an object | `stale` | 未收到引擎快照 |
| `snapshot.at` missing or not a number | `stale` | an undatable frame cannot be trusted |
| snapshot older than 45 s | `stale` | **even if it shows running agents and jobs** |
| `dshRunning: false` | `offline` | outranks a snapshot full of running agents |
| `dshRunning` `undefined`/`null` + fresh snapshot | inferred from the snapshot | unknown ≠ offline; a fresh frame with jobs still says 后台任务 |
| `dshRunning` unknown + no fresh snapshot | `stale` | never a guessed `offline`, never a stale `working` |
| `job.status === 'stopping'` | still `busy` | a stopping job still occupies the machine; long stops are noted in `detail` |
| `lastEventAt` older than 30 s | ignored | stale events must not read as working |
| `lastEventAt` in the future (clock skew) | ignored | a future stamp is not evidence of future work |
| `peakNow` not exactly `true` (e.g. `"yes"`) | not peak | strict boolean, so a wire format change cannot fake 峰时 |
| agent `sinceLastWriteMs` missing | assumed active | see §4 |
| agent `sinceLastWriteMs > 30 000` | that agent contributes nothing | a wedged turn reads as 空闲, not 干活中 |
| agent `label` blank/whitespace | `智能体` placeholder | |
| one agent running, no job, no event, fresh write | `working` | the single-agent case is not 团队协作 |
| `computeState()` with no argument at all | `stale` | total input loss is a stale feed |

`now` is required for a meaningful answer. When omitted it falls back to the
snapshot's own `at` (and then `0`), so the function stays deterministic and never
reaches for `Date.now()` — the *caller* owns the clock.

---

## 6. How the integration consumes this

The widget's poll loop (≈ 2 s) already holds everything needed:

```js
// widget-side state, kept across polls
let lastSnapshot = null
let lastEventAt = null      // ms of the newest {"type":"event"} seen on the stream

// on each parsed engine line:
//   msg.type === 'snapshot'  ->  lastSnapshot = msg
//   msg.type === 'event'     ->  lastEventAt = msg.at      // do NOT clear it on snapshot;
//                                                          // keep the newest until it ages out
// on each poll tick:
const pet = computeState({
  snapshot: lastSnapshot,
  lastEventAt,
  dshRunning: Test-DshRunning,   // the existing helper
  now: Date.now(),
})
```

Notes for the renderer:

- **Switch on `pet.state`**, never on the label or the colour. The label is
  presentation and may be re-worded; the enum is the contract.
- **Label placement (the renderer's side of the contract, agreed with the panel):**
  the label sits at the **top-right of the character's measured bounding box** and
  is **right-aligned with the panel's own right-aligned text** — `labelRight` equals
  the panel's published content right edge within 1 px (`pet/renderer/panel-geometry.json`),
  and `labelTop` sits **10–14 px below the bottom edge of the panel text line above
  it**; `detail` follows on the next line with the same right edge. Two inequalities
  always hold: `labelTop >= modelTop` and `labelRight <= modelRight`. The old
  wording ("top-right of the pet area") is superseded: the window is 340×340 with a
  lot of transparent margin, so anchoring to the *character* is what keeps the text
  on the whale instead of floating in empty space.
- **Fixed width, no jitter (task-7):** all labels are 2–4 Chinese characters, so the
  text box is `min-width: 4em`, `text-align: right`, `font-variant-numeric:
  tabular-nums`, one font size (14 px/1.25, weight 600) and `detail` 11 px/1.3 in the
  same monospace stack. The box width therefore never changes when the word changes,
  and the left edge cannot wobble. Colour/opacity transitions only — never width,
  transform or position.
- **Pose:** map the eleven poses (`offline sleepy team starry thinking reading
  scribble sleeves happy gloomy idle`) onto the model's expressions and motions; the
  reaction layer in `pet/renderer/reactions.js` owns that mapping, and its rules
  (priority, interrupt, fallback, the idle brain) are specified in
  `pet/REACTIONS-SPEC.md §3–§4`.
- **The `--once` cold poll has no history**, so a freshly started widget reports
  `stale` until its first snapshot lands and never reports activity from an event it
  has not seen. If the integration wants a hot start it can seed `lastEventAt`
  from the last event of its previous session — but a cold widget must not fake
  activity.
- **Layout to avoid:** do not reuse `#7EE787` / `#FF7B72` for the pet or its
  label; the pet's colours are the eleven in §2.
- **Reaction inputs** arrive in two files, both written by the engine:
  `state.json` (this contract) and `signals.json` (the raw facts behind it: newest
  tool name/phase/ok/error/summary, turn reason/ms/tokens, whether a step is open,
  `lastUserAt`/`lastUserText`, `idleMs`). The page never reads the session logs
  itself — "one log reader" is the engine.

---

## 7. Verification

```powershell
# bundled Node, a fixed ASCII cwd, absolute paths
& "<node>" "F:\dsh-usage-widget\pet\test\state.test.mjs"     # exit 0, 214 checks
& "<node>" "F:\dsh-usage-widget\pet\test\state-cli.test.mjs" # exit 0, 23 checks
& "<node>" "F:\dsh-usage-widget\pet\state-cli.mjs" --detail  # against the live engine
& "<node>" "F:\dsh-usage-widget\pet\state-cli.mjs" --json   # raw observation + result
```

`state-cli.mjs` spawns `node engine\cli.mjs --once --config <abs>` from
`%TEMP%` (an **ASCII** working directory) and prints which source the state came
from. The Chinese-path trap is real: a `工作区` path handed to a Node subprocess
through the legacy code page becomes six U+FFFD, so the child's cwd is always
ASCII and every path argument is absolute. The engine resolves its own imports
from its file path, so this is safe. The CLI never writes to the widget's files.

Real output against the live engine (2026-09-30, DSH running, two pet teammates
mid-turn). The `detail` names whichever agent wrote most recently, so it changes
between polls while `state` does not:

```
engine   F:\dsh-usage-widget\engine\cli.mjs
cwd      C:\Users\x1503\AppData\Local\Temp  (ASCII; avoids the Chinese-path subprocess trap)
config   F:\dsh-usage-widget\config.json

state    team
label    团队协作  #56D4DD  pose=team
detail   运行 2 个智能体 · Define the pet work-state model and colours
why      2 agents running
source   snapshot · jobs=1 (source=bridge), agents=12 · snapshot fresh · events this run=0
```

A poll four seconds later, unchanged state and a fresher `detail`:

```
state    team
label    团队协作  #56D4DD  pose=team
detail   运行 2 个智能体 · Prove transparent Live2D rendering and land the ass…
why      2 agents running
source   snapshot · jobs=1 (source=bridge), agents=12 · snapshot fresh · events this run=0
```

---

## 8. Decisions this protocol made where the brief was open

1. **Added a seventh state, `stale` (数据过期).** The brief demanded that an
   absurdly old snapshot must not read as "working" but only listed six states;
   folding staleness into `idle` would have hidden a dead engine, and folding it
   into a live state would defeat the requirement. It gets its own label, colour
   and `sleepy` pose.
2. **`team` means ≥ 2 running agents.** One running agent is not collaboration;
   it reaches the screen as 干活中 when it is actually writing, 后台任务 when a job
   is running, and 空闲 when it is a dormant turn.
3. **A running agent is only activity while `sinceLastWriteMs <= 30 s`.** This is
   what makes "agents present but all idle" and "a wedged open turn" behave.
4. **`stopping` jobs still count as 后台任务**, with `stopping` surfaced in
   `detail` after 15 s.
5. **Unknown `dshRunning` is inferred, not assumed offline**, but requires a
   fresh snapshot — so an unknown caller can never resurrect a dead engine.
6. **`detail` always sets a real job's progress text** (e.g. `45.2% 剩余 00:37`),
   matching the panel's existing job rows so the two cannot disagree, and appends
   `日志源` when `jobsSource === 'logs'` (progress is unknown on that path) and
   `+N` when more jobs exist.
7. **Seven colours were chosen outside the panel's semantic pairs**, all clearing
   WCAG AA on the panel background; cyan/orange/blue/gold/steel/violet/grey.
8. **`reason` and `source` are extra output fields** beyond the requested five,
   for logs and for the CLI's "which source" line. They are additive and never
   replace the contract fields.
9. **`state-cli.mjs` reports `stale` on a cold `--once` run** when DSH is up:
   one poll has no event history, so there is nothing that could honestly say
   干活中. `--json` shows the empty stream so a human can confirm that.
