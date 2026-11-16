# dsh-usage-dashboard

Token-usage and spend accounting for the DeepSeek Harness Web GUI, rendered as a
resident page in the right sidebar plus a live chip in the conversation header.

Nothing in the harness records money. What it does record, in every durable
session log, is each model call's provider-reported token bucket. This plugin
folds those logs, prices each call at its own timestamp against DeepSeek's
published peak/off-peak rate card, and shows the result.

---

## What you see

**Conversation-header chip** — `今日 $0.27` with a green (off-peak) or red
(peak) dot. It is always visible for the open session, and clicking it opens the
dashboard.

**Right-sidebar page** — the tab type `usage-dashboard`, titled 用量与花费 /
*Usage & Spend*. Reachable from:

- the header chip,
- the sidebar's guide page (its capsule carries a small bar-chart glyph),
- or by opening the guide in any pane.

The page shows:

| Block | What it answers |
|---|---|
| Four headline metrics | Total spend (and its exact value), total tokens split hit / miss / output, cache-hit rate, model-call count |
| Daily spend | One stacked column per day, peak over off-peak, so a day's cost and its rate mix are one glance |
| Daily tokens | Cache hit / miss / output stacked per day, on one scale |
| By UTC hour | Where the spend lands on the clock, with the two peak blocks coloured |
| By model | Call count and the four token columns per route, with a share bar |
| By session | Newest first, with title, workspace, last activity, tokens and cost |
| By workspace | Only when more than one workspace has usage |

A refresh button forces a fresh sweep; otherwise the page re-reads the server
every minute and the server re-sweeps at most every `ttlMs` (15 s).

---

## How the numbers are produced

**Source.** `$DSH_HOME/sessions/<workspace>/<session-id>/session.v<N>.jsonl.zstd`.
The number is the log *format* version, and it moves: 0.2.0-rc.2 writes `v4`
while sessions created before that change keep their `v3` file. Discovery takes
the **highest version present** in a session directory, because a migrated
session's newer artifact is the complete successor rather than a tail — measured
on 0.2.0-rc.2, a migrated session's v4 file carried every v3 line *plus* the
lines written after the migration, and a re-encoded session carried the same
records in 58% of the bytes. Folding both would double-count.

Each artifact is a container of independently decodable Zstandard frames; the
container is unchanged between v3 and v4. Node's one-shot `zstdDecompressSync`
stops at the first frame, so `src/zstd.mjs` walks the frame structure and decodes
each frame in turn. A read that races the writer's rewrite observes a torn final
frame and drops exactly that frame, so the accounting always describes durable
bytes.

**Fold.** `src/usage.mjs` reduces each log to one sample per `(turn, step)`:

- token bucket from `assistant/message` → `data.usage`
  (`inputTokens` = cache-miss prompt, `cacheReadTokens` = cache-hit prompt,
  `outputTokens` = completion including reasoning);
- route from the `request/header` / `request/context` envelope in force, with
  `message.source` as the tie-breaker;
- timestamps from the event's own `time`.

A retried step **replaces** its sample instead of adding a second one, because
the log records the final attempt. The fold was validated against the harness's
own `session_projcache` projections: for the sessions it has been checked against,
the folded totals agree with the `tokenUsage` projection to within the bytes
written after the projection cache was last refreshed.

**Price.** `PRICE_CARD` in `src/usage.mjs`, USD per 1M tokens:

| Route | Cache hit | Cache miss | Output |
|---|---|---|---|
| `deepseek-flash` (V4.1-Flash) | 0.003 | 0.15 | 0.60 |
| `deepseek-v4-flash` | 0.003 | 0.15 | 0.60 |
| `deepseek-v4-flash-vision-exp` | 0.003 | 0.15 | 0.60 |
| `deepseek-v4-pro` | 0.022 | 0.66 | 1.98 |

These are the **off-peak** rates; peak is exactly double. Peak runs Monday to
Friday in two UTC blocks, `01:00–04:00` and `06:00–10:00`; every other hour,
and all of Saturday and Sunday, bill off-peak. Each call is priced at its own
timestamp, so a single session can mix both rates. The legacy `v4-flash` ids
are billed at the flash card, matching DeepSeek's migration note that those
requests are served by V4.1-Flash.

An unknown route is priced at the flash off-peak card and reported in
`unpricedModels`, which the page prints as a caveat rather than hiding the gap.

**Known limits.**

- Chinese public holidays are off-peak per DeepSeek's policy but have no
  published machine-readable calendar, so they are not modelled and those days
  are billed here at peak.
- Days are bucketed in **UTC**, matching the rate-card windows. A session that
  runs across local midnight in Asia/Shanghai therefore lands in the same UTC
  day as the hours before it.

---

## Layout

```
dsh-usage-dashboard/
  package.json          dual-face declaration: main = host, exports["./client"] = browser,
                        dsh.client.platform = "web", dsh.bundle.patch = cordis.patch.yml
  cordis.patch.yml      the one loader row this bundle contributes
  src/index.mjs         host half: memoized sweep + GET /api/usage-dashboard/stats
  src/usage.mjs         pricing, peak windows, per-session fold, dashboard model
  src/session-store.mjs session-artifact discovery (highest log version wins) and reading
  src/zstd.mjs          concatenated-frame Zstandard reader
  lib/client.js         browser half, authored in the module-loader form the
                        shell executes (no build step): tab type, tab body,
                        header chip, inline-SVG charts
  scripts/preview.mjs   text report straight from the logs
  scripts/host-check.mjs run the real route handler against a stub context
  scripts/client-check.mjs render the real bundle against the real payload
  scripts/bundle-check.mjs bundle integrity: UTF-8, copy, SVG geometry
  scripts/mint-cookie.mjs mint the browser session cookie for raw HTTP probes
  scripts/dump-index.mjs read the live boot manifest: this plugin's bundle URL,
                        every script src on the page, every mention of the plugin
  scripts/verify-live.mjs end-to-end proof against a running GUI
  scripts/restart-web.mjs bring a down GUI back up (no-op when one answers)
  RESTART.cmd           restart the packaged desktop application
```

### The route

`GET /api/usage-dashboard/stats`

Registered as an **exact** Fetch route on the shared `/api` channel via
`ctx.connection.fetch.register`, so it inherits the carrier's Host/Origin trust
checks and browser-session cookie authentication unchanged. `?refresh=1`
bypasses the TTL.

The response carries `totals`, `coverage`, `today`, `days` (last 60), `models`,
`workspaces`, `hours` (24 buckets), `sessions`, `priceCard`, `unpricedModels`,
`peakNow`, and a `source` block naming the artifact count, byte count, sweep
duration, and any per-file read failures.

### The client half

`lib/client.js` is written in the module-loader form the shell executes directly —
there is no build step — and takes exactly three seats: the sidebar tab type, its
body in `sidebar.right.pane.tab`, and the header chip in
`conversation.session.header.actions`.

Two rules shape it:

- **Compact first.** The right sidebar's width belongs to the shell, and its
  default is large: the shell's own layout code computes
  `layoutInfo.rightbar ?? viewport * .45` — 45 % of the window — and no width
  value is persisted anywhere this plugin can read or write it. The page must
  therefore read well in a narrow pane: base font 12 px, metric values 16 px,
  `320 x 104` viewBox charts, tighter padding, `repeat(2, minmax(0, 1fr))` grids
  that collapse to one column under a container query, `table-layout: fixed` with
  ellipsising name cells, and **no `min-width` on the root**, so the content can
  never widen the pane it was given.
- **A seat may never hurt the shell.** Both seats are strict-session-scoped, and
  the shell rethrows a slot *assembly* error past the boundaries it owns — an
  ordinary render error in a slot entry is contained, but a bad one can cost a
  whole region. So each seat is wrapped in a local `SlotGuard` class boundary that
  renders nothing if anything beneath it throws, and the payload is normalised
  once before it is read. A malformed response costs the dashboard its own
  content and nothing else.

`scripts/client-check.mjs` mounts that bundle with a deliberately minimal React,
so it supplies a `Component` class and renders class components through an
instance — otherwise the guard could not be exercised at all.

---

## Install, in the desktop profile

The packaged application boots `$DSH_HOME/profiles/desktop` — confirmed from its
own launch command line
(`… /index.js "D:\DeepSeek Harness\resources\app.asar\dsh" C:\Users\<you>\.dsh\profiles\desktop …`)
and from the desktop-only bundles visible in the live composition. That is the
profile a plugin has to join; the older `web` profile wiring does nothing here.

Already done on this machine; recorded here so it is reproducible.

```powershell
# 1. the package lives in the workspace and is linked into the profile
New-Item -ItemType Directory -Force "$env:USERPROFILE\.dsh\profiles\desktop\node_modules"
New-Item -ItemType Junction `
  -Path  "$env:USERPROFILE\.dsh\profiles\desktop\node_modules\dsh-usage-dashboard" `
  -Target "F:\DeepSeek工作区\dsh-usage-dashboard"

# 2. the profile names it as a bundle layer
#    $DSH_HOME/profiles/desktop/package.json -> dsh.profile.bundles += "dsh-usage-dashboard"
```

`$DSH_HOME/profiles/desktop/cordis.patch.yml` must **not** insert the
`usage-dashboard` row as well: the package's own `cordis.patch.yml` already
contributes it, and the Loader rejects a duplicate entry id outright. Use that
file only for id-targeted `- id: usage-dashboard` config overrides — and note
that an override whose values equal the defaults is a no-op the loader does not
even consider a change.

### A new bundle layer composes live; edited host source does not

On 0.2.0-rc.2 the running application **recomposes when the ordered
`dsh.profile.bundles` list changes**. This was measured here: appending the entry
above brought the plugin up in an already-running GUI with no restart —

- the host row appeared within seconds (`include:usage-dashboard`),
- `/api/usage-dashboard/stats` began answering 200,
- the client half was injected and the header chip appeared **without a page
  reload**.

What does **not** reload is the host half's own source. Node caches the imported
module by resolved URL and the loader neither re-imports nor cache-busts it:
after editing `src/*.mjs`, toggling the bundle entry off and on again leaves the
previously imported code running (measured — the route kept reporting the old
artifact count through a 404/200 cycle). **A change to host logic therefore needs
the host process restarted**, which is what `RESTART.cmd` does.

Two more constraints worth knowing before editing the profile:

- The desktop profile is off-limits to the CLI: `dsh --profile desktop` refuses
  with *managed exclusively by the Electron application* (a hard-coded check on
  the literal name). To dry-run the composition, copy the profile directory under
  another name and dump that — the bundled `@deepseek-ai/dsh-base` and
  `@deepseek-ai/dsh-web-app` layers resolve from the app install either way.
- Restarting the **application** is not the same as restarting a `dsh web`
  server. The desktop host is a child process of the Electron shell and owns the
  GUI port; `RESTART.cmd` replaces the whole application.

## Verify without the GUI

```powershell
node scripts/preview.mjs               # text report over every session log
node scripts/host-check.mjs            # route handler, response shape, cross-totals
node scripts/client-check.mjs          # mounts the real bundle and renders it
node scripts/bundle-check.mjs          # bundle integrity: UTF-8, copy, geometry
```

> **Do not edit `lib/client.js` through a shell text round-trip.** It is UTF-8
> with no build step, so `Get-Content -Raw` / `Set-Content` (which decode as the
> system code page on Windows) silently mojibake every Chinese string. That
> happened once here and `node --check` still reported a syntax error rather
> than the real damage. Use a UTF-8-aware editor or the file tools, and run
> `bundle-check.mjs` afterwards — it asserts the copy and the chart geometry
> survived.

## Verify the live GUI

```powershell
node scripts/verify-live.mjs --url http://127.0.0.1:19387/ --log live-report.txt
```

Polls the GUI for readiness, then proves the whole chain from outside the server:
the composed boot manifest names the plugin, the plugin's client half is served,
and the authenticated stats route answers with real accounting whose per-day,
per-model, and per-session costs each sum to the reported total. It mints the
same signed browser session cookie the GUI writes on its root token exchange, so
no browser is needed. `scripts/restart-web.mjs` is the companion that brings a
down GUI back up when it is down; it is a no-op whenever something already
answers.

Two details here are easy to get wrong, and both cost real debugging time on
0.2.0-rc.2:

- **The bundle probe follows the boot manifest.** A client half is *not* served
  at a per-package path. The shell batches modules behind
  `plugins/??<comma-separated list>&rev=<hash>`, and this plugin's exact URL is
  an entry in `globalThis["__DSH_BOOT__"]`. Probing
  `/plugins/dsh-usage-dashboard/client.js` directly answers 404 even when the
  plugin is perfectly composed — which looks exactly like a failed install.
- **The minted cookie must expire in under 30 days.** The carrier accepts a
  29-day `expiresAt` and rejects a 30-day one with an opaque 401 on every
  authenticated route. Both minting scripts here therefore use 29 days.

## Uninstall

Remove `dsh-usage-dashboard` from `dsh.profile.bundles` in the desktop profile's
`package.json`, delete the junction under the profile's `node_modules`, and
restart. A removal composes live like an addition, but stopping the host half's
route takes a restart. Nothing else is written: the plugin owns no storage of its
own, and the dashboard state is browser-memory only.
