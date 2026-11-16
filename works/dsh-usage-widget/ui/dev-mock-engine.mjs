// ui/dev-mock-engine.mjs
// DEVELOPMENT FIXTURE ONLY - the launcher and widget.ps1 never use this file.
// It reproduces the stdout contract of engine/cli.mjs (same line shapes) so the
// window, the footer, the toast rules and the two status sections can be
// verified without a live DSH session.  Modes (env DSH_MOCK_MODE):
//   normal (default) - snapshot with a real balance, one running + one idle
//                      agent, one background job, then a few token events
//   status           - more agents than agentsMax and more jobs than jobsMax,
//                      long labels and commands (ellipsis), an hour-long
//                      elapsed time, a job with a progress object, a job with
//                      progress:null + progressNote, and a job whose progress
//                      object carries only a percentage
//   plain            - agents:[] and jobs:[]: both sections AND the second
//                      separator rule must disappear completely
//   bad              - no agents / jobs key at all (= an engine that does not
//                      report them yet), balance {ok:false}, an error event, a
//                      failed-balance line and a giant token count
//   exit             - normal, then exits with code 1 after 3s (crash path)
const mode = process.env.DSH_MOCK_MODE || 'normal'
const write = (object) => process.stdout.write(JSON.stringify(object) + '\n')
const tokens = (hit, miss, out) => ({ hit, miss, out })

write({ type: 'ready', at: Date.now(), pollMs: 2000, usdToCny: 7.1 })
if (mode === 'bad') write({ type: 'error', at: Date.now(), message: 'mock: balance unavailable' })

let todayCny = 2.0612
let todayUsd = 0.2903
let totalCny = 53.48
let totalUsd = 7.5328
let hit = 4500000
let miss = 640000
let out = 160000

// --- the two status arrays -------------------------------------------------
// elapsedMs and startedAt are always consistent with each other, exactly like
// the real engine keeps them.
const ago = (ms) => Date.now() - ms
const agent = (id, label, state, ms) => ({
  id, label, state, model: 'deepseek-flash', turn: 3,
  startedAt: ago(ms), elapsedMs: ms, sinceLastWriteMs: 1200,
})

const AGENTS = {
  normal: [
    agent('e90db130-1f2c-4a55-9d0e-7a1b2c3d4e5f', 'Apply widget UI feedback', 'running', 412000),
    agent('b71c04aa-2f19-4d2e-8f77-0c9a1b2c3d4e', 'Idle reviewer', 'idle', 190000),
  ],
  status: [
    agent('e90db130-1f2c-4a55-9d0e-7a1b2c3d4e5f', 'Sample agent with a much too long label that has to be ellipsised', 'running', 412000),
    agent('b71c04aa-2f19-4d2e-8f77-0c9a1b2c3d4e', 'Build widget WPF UI', 'running', 3725000),
    agent('c02d15bb-3a2b-4e3f-9a88-1d0b2c3d4e5f', 'Idle reviewer', 'idle', 190000),
    agent('d13e26cc-4b3c-4f40-ab99-2e1c3d4e5f60', 'Hidden idle one', 'idle', 90000),
    agent('e24f37dd-5c4d-4051-bc00-3f2d4e5f6071', 'Hidden idle two', 'idle', 30000),
  ],
  plain: [],
  bad: null,   // key not sent at all
}

const JOBS = {
  normal: [
    { id: 'call_00_demo1', session: 'session-mock', program: 'pwsh',
      command: 'node sim.mjs --steps 500', startedAt: ago(65000), elapsedMs: 65000,
      progress: { percent: 45.2, etaMs: 37000, source: 'size' }, progressNote: null },
  ],
  status: [
    { id: 'call_00_demo1', session: 'session-mock', program: 'pwsh',
      command: 'node sim.mjs --steps 500', startedAt: ago(65000), elapsedMs: 65000,
      progress: { percent: 45.2, etaMs: 37000, source: 'size' }, progressNote: null },
    { id: 'call_00_demo2', session: 'session-mock', program: 'node',
      command: 'node -e "for (let i = 0; i < 1e9; i++) {}" --trace-warnings --max-old-space-size=4096',
      startedAt: ago(182000), elapsedMs: 182000,
      progress: null, progressNote: '无进度输出' },
    { id: 'call_00_demo3', session: 'session-mock', program: 'python',
      command: 'python train.py --epochs 50', startedAt: ago(3725000), elapsedMs: 3725000,
      progress: { percent: 88 }, progressNote: null },
    // no progress object AND no note: the window must fall back to 进度未知
    { id: 'call_00_demo4', session: 'session-mock', program: 'rg',
      command: 'rg --files | wc -l', startedAt: ago(12000), elapsedMs: 12000,
      progress: null, progressNote: null },
  ],
  plain: [],
  bad: null,
}

function snapshot() {
  const balance =
    mode === 'bad'
      ? { ok: false, error: 'mock: could not reach the balance endpoint' }
      : { ok: true, currency: 'CNY', total: '8.47', granted: '0.00', toppedUp: '8.47', fetchedAt: Date.now() }
  const snap = {
    type: 'snapshot',
    at: Date.now(),
    peakNow: false,
    rate: 7.1,
    today: { costUsd: todayUsd, costCny: todayCny, calls: 12, tokens: tokens(hit, miss, out) },
    total: { costUsd: totalUsd, costCny: totalCny, calls: 210, sessions: 9, tokens: tokens(hit * 3, miss * 3, out * 3) },
    balance,
  }
  const agents = AGENTS[mode]
  const jobs = JOBS[mode]
  if (agents) snap.agents = agents
  if (jobs) snap.jobs = jobs
  write(snap)
}

snapshot()

const script = [
  { hit: 12345, miss: 1234, out: 2345, costCny: 0.001 },
  { hit: 0, miss: 880, out: 120, costCny: 0.00012 },
  { hit: 2100000, miss: 0, out: 0, costCny: 0.0042 },
  { hit: 1, miss: 1, out: 1, costCny: 0.0000021 },
  { hit: 98765, miss: 4321, out: 6789, costCny: 0.0009 },
  { hit: 312000, miss: 4549, out: 0, costCny: 0.0031 },
]

let step = 0
const timer = setInterval(() => {
  if (step < script.length) {
    const call = script[step]
    write({ type: 'event', at: Date.now(), session: 'mock-session', turn: 1, step, model: 'deepseek-flash', ...call })
    hit += call.hit
    miss += call.miss
    out += call.out
    todayCny += call.costCny
    totalCny += call.costCny
  } else {
    snapshot()
  }
  step += 1
  if (mode === 'bad' && step === 3) write({ type: 'error', at: Date.now(), message: 'mock: a session artifact could not be folded' })
  if (mode === 'exit' && step === 3) {
    clearInterval(timer)
    process.exitCode = 1
    process.exit(1)
  }
}, 900)
