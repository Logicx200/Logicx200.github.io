# Engine notes

## Provenance of the reused modules

`usage.mjs`, `session-store.mjs` and `zstd.mjs` are **byte-for-byte copies** of the
validated modules in `dsh-usage-dashboard/src/`, so their module docs and behaviour
are untouched (this is why their `@module` tags still read `dsh-usage-dashboard/...`).
The parenthetical provenance is recorded here rather than edited into the files.

| file | sha256 (identical in both trees) |
| --- | --- |
| `usage.mjs` | `B70301A9A688177534A3151CE3235D4BB3DD066DF6DBD7FF09800E2DE78F931F` |
| `session-store.mjs` | `E2AB244102D236F8AB06BBC26013D7CA3997AF3FD501CBA0BF48C2F5BB714EEA` |
| `zstd.mjs` | `19A0C149D2FE0565A652FF3C3310C4B1C9AAA8E3DCC7FA1467BBEBA5DB2E4233` |

Re-sync with `Copy-Item ..\dsh-usage-dashboard\src\<file> .` if the dashboard module is
ever fixed; the engine deliberately carries no local edits.

## What the engine adds

- `balance.mjs` — reads the `DEEPSEEK_API_KEY` ref out of `$DSH_HOME/.credentials.yaml`,
  calls `GET https://api.deepseek.com/user/balance`, and returns a never-throwing
  `{ ok, currency, total, granted, toppedUp, fetchedAt } | { ok: false, error }`.
- `cli.mjs` — folds every session artifact, prices it, and streams NDJSON on stdout:
  one `ready` line, then a `snapshot` per poll, plus one `event` line per newly
  observed model call, plus `error` lines for recoverable failures.
- `activity.mjs` — the live half of the snapshot: `agents` (delegating sessions and
  whether their newest turn is still open) and `jobs` (tool calls with no result
  yet, plus whatever progress is genuinely observable).

`test/` holds self-contained checks; all of them write scratch only under `test/.tmp/`:

| check | what it proves |
| --- | --- |
| `node test/balance.test.mjs` | balance parsing, caching and failure shapes |
| `node test/synthetic.test.mjs` | baseline fold, one event per new call |
| `node test/activity.test.mjs` | live agents/jobs against a synthetic home, both progress sources, and that a finished job leaves the array |
| `node test/contract.test.mjs` | every pre-existing snapshot and event field is unchanged over the real logs |
| `node test/agent-evidence.mjs` | the `turn/start`/`turn/end` evidence behind each real agent row |
| `node test/stream-check.mjs [s]` | the live NDJSON stream: `ready`, snapshots, events |

## The two live arrays

Both are present on **every** snapshot, empty rather than absent, so a reader never
has to test for the key. `config.json`'s `agentsMax` / `jobsMax` are the widget's
drawing caps and are deliberately *not* read by the engine.

```json
"agents":[{"id":"e90db130-…","label":"Apply widget UI feedback","state":"running",
           "model":"deepseek-flash","turn":1,"startedAt":1790696560833,
           "elapsedMs":477067,"sinceLastWriteMs":1498932}]
"jobs":[{"id":"call_00_…","session":"session-f48203ef-…","program":"pwsh",
         "command":"node sim.mjs --steps 500","startedAt":1790695900650,
         "elapsedMs":65000,"progress":{"percent":45.2,"etaMs":37000,"source":"log"},
         "progressNote":null}]
```

## Decisions the live-state work left open

11. **`label` falls back to the session id**, and `model` to the newest
    `request/header`/`request/context` model, falling back to `null`. The label is
    the `subagent/descriptor`'s `label`; the model prefers the descriptor's
    `agentModel` because that is the route the delegating agent actually spawned.
12. **`turn` for an idle agent is the number of `turn/start` records**, because
    `turn/end` clears the "current turn" but the row still wants to name the last
    turn that ran. `elapsedMs` for an idle agent is that last turn's own duration
    (`turn/end.time - turn/start.time`), and `0` for a log with no closed turn —
    never `now - startedAt`, which would report an epoch-sized number.
13. **Durations are integers.** `elapsedMs` and `sinceLastWriteMs` are rounded;
    `session-store` reports `mtimeMs` as a float on Windows, and a fractional
    "write 1234.5 ms ago" is noise no widget can use.
14. **Agents are exactly the `delegationDepth > 0` sessions.** A lead session
    (depth 0) is never an agent even when its turn is open, so a workspace with a
    single running lead shows `agents: []`. Measured on this machine: real
    subagents are depth 1, and a session with no turn records at all folds to
    `idle` with `turn` 0 rather than to `running`.
15. **The correlation id lives at `data.message.toolCallId`** (with
    `data.message.source.callId` beside it) in the log format this build reads, not
    at `data.toolCallId`. `resultCallId()` accepts all four spellings, so a format
    move cannot silently turn every finished call into a phantom job. Getting this
    wrong is invisible-but-fatal: with the wrong key, *every* call in the home
    looks unmatched.
16. **Unmatched calls are not only background jobs.** A call in flight in a
    *running* session is unmatched too, so `jobs` includes ordinary reads and
    writes for as long as they take. This is what the brief specified (and the
    only trace a job has), but it is worth knowing that on a busy machine most
    unmatched calls are short-lived foreground calls, not jobs.
17. **`jobsMax` (engine-side `activityJobsMax`, default 200) bounds the payload.**
    It is not a UI cap like the config's `jobsMax`: this home really does carry
    hundreds of unmatched calls, and streaming all of them every poll would cost
    megabytes for rows no UI draws. The cap keeps the *oldest* calls — the
    longest-running, which is what the brief calls the most interesting — and is
    overridable in `config.json`.
18. **Progress is measured between two observed samples, not since the job
    started.** A program that is silent for five seconds and then prints `5%` has a
    real rate of 5% per interval; charging it for the startup produced ETAs roughly
    3× too long when measured against a writer that moves 1%/s. `etaMs` is
    therefore `null` until a second sample exists (and once `percent` is 100).
19. **Detection runs on the raw command, display runs on the capped line.** The
    120-character cap truncated a trailing `> "…out.log"` and the escaped quotes of
    a JSON argument string made a quoted redirect look like the literal path
    `\"out.log\"`. `probeProgress` therefore reads the command straight out of the
    parsed arguments, and `renderCommand` is only for display.
20. **A file-descriptor redirect is not an output path.** `2>&1` and `2>$null` name
    streams, so the redirect scan skips a target matching `&\d+`. `$null` is *not*
    skipped: a bare `> $null` in PowerShell is a real redirect to the null device,
    and `detectOutputPath` reports it so the caller can drop it.
21. **`progressNote` prefers "nothing to observe" over "the path I guessed at does
    not exist".** A command with no recognisable output path simply has no
    observable progress; reporting an ENOENT for a path derived from a redirect to
    `nul` reads like an engine fault. The specific file error is still used when a
    candidate path *was* detected and could not be read.
22. **`HEAD` result caching**: a success is cached for the job's lifetime (sealed),
    a failure for 60 s and then re-tried, so a host that publishes
    `Content-Length` late is picked up without hammering one that never will.
    Probe cost is bounded by `TAIL_BYTES` (512 KiB) per candidate file per poll,
    and there is no probe at all when no candidate path is detected.
23. **Activity folds are memoized per artifact** on `path|mtime|size`, so a session
    that is not growing costs a map lookup rather than a zstd decode. `cli.mjs`
    lists artifacts a second time (via `listSessionArtifacts`) because
    `readAllSessions` returns only a *count*, and `session-store.mjs` stays
    byte-identical to the dashboard's copy.

## Decisions the spec left open

1. **Line order inside one poll** — `snapshot` is written first, then the events for
   the calls that snapshot already contains, oldest first (ties broken by session id,
   turn, step). The first poll is the baseline and therefore produces only the
   snapshot, which is what makes the first stdout lines of a fresh run
   `ready`, `snapshot`, `snapshot`, ...
2. **Cost precision** — `costUsd` / `costCny` are emitted at full double precision
   (e.g. `7.6030239959999975`), never pre-rounded: a single 1-token cache hit is
   worth ~3e-9 USD and rounding in the engine would erase real differences. The UI
   owns formatting.
3. **`today` is a UTC day**, because `usage.mjs#dayKey` is UTC; the engine inherits it
   rather than inventing a local-time boundary that would disagree with the dashboard.
4. **`total.sessions` counts sessions that have at least one priced call**, inherited
   from `buildDashboard` (`recent` is only populated for sessions with samples). A
   freshly created session with no calls yet is visible in the event stream but not in
   the session count until its first call.
5. **Balance caching** — successes are cached for `balanceMs` (config); failures are
   cached for a separate, shorter window (`DEFAULT_RETRY_MS = 5s`, not configurable by
   the widget config) so a network fault is not re-attempted on every poll but a
   recovery is still visible within seconds. The keys are never logged or echoed; the
   error strings name the file or the HTTP status only.
6. **Error de-duplication** — a `{"type":"error"}` line is emitted once per distinct
   failure (per artifact+message, per sweep message, and once per change of balance
   error). Otherwise a persistently unreadable artifact would print an error line on
   every poll forever.
7. **`--config` resolution** — an absolute path is used as given; a relative path is
   resolved against the working directory first and against the engine directory
   second, so both `--config config.json` (cwd) and the documented default
   `../config.json` (engine-relative) behave as expected. A missing or malformed config
   is reported as an `error` line and the engine continues on the defaults.
8. **Unusable config values fall back per key** (`pollMs` must be an integer ≥ 50,
   `balanceMs` ≥ 1000, `usdToCny` ≥ 0, `defaultModel` a non-empty string), so one bad
   key cannot disable the widget.
9. **The seen-set grows for the process lifetime.** Ids are `sessionId:turn:step` and
   only ever added; a long-running widget accumulates a few hundred bytes per call,
   which is the price of never re-emitting an old call.
10. **Signals** — `SIGINT`/`SIGTERM` stop the poll chain and let the process drain its
    stdout, so a redirected stream is never truncated. Nothing extra is written to
    stdout on shutdown, and stderr stays empty unless the stream itself breaks.
