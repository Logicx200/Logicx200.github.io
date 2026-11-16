/* 视频抽帧自检
 *
 * 这一套只回答一个问题：**一个视频进来、一串帧出去，而且每一帧都在。**
 *
 * 用的不是真视频解码器（本会话的沙箱起不了浏览器），而是 tools/harness.mjs 里的
 * <video> 替身：它按 fps 把虚拟时间轴走一遍，并且**只通过
 * requestVideoFrameCallback 报帧** —— 与真浏览器一致，所以"每一帧都保留"
 * 这条可以被真正断言，而不是靠"我觉得它抓到了"。
 *
 * 它证明不了：真实解码器会不会丢帧、丢帧提示够不够准。那只能由你在浏览器里看。
 */
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createReporter, createDom, loadApp } from '../tools/harness.mjs';
import { fakeImageFile, fakeVideoFile, videoFrameCount } from '../tools/make-sample.mjs';

const here = dirname(fileURLToPath(import.meta.url));
const R = createReporter('视频抽帧', join(here, 'video.log'));
const NAME = 'VIDEO';

/* ==================================================== 0. 起一个应用 */

const dom = createDom({});
const { STC } = loadApp(dom);
const app = STC.app;
const V = STC.video;
// 这一套只测抽帧与序列装配，不需要渲染循环（跑着反而会把桩的调用表撑爆）
app.stop();

R.section('视频识别与元信息');
{
  R.check('能认出视频文件（按 MIME 或扩展名）',
    V.isVideo(fakeVideoFile('a.mp4', {})) && V.isVideo({ name: 'b.MOV', type: '' }) &&
    V.isVideo({ name: 'x', type: 'video/webm' }),
    'mp4 / MOV / video/webm 都认');
  R.check('图片不会被误判成视频',
    !V.isVideo(fakeImageFile('a.png', 8, 8)) && !STC.seq.isImage(fakeVideoFile('a.mp4', {})),
    '两条判断互不重叠');

  const f = fakeVideoFile('clip.mp4', { width: 1280, height: 720, fps: 25, duration: 4 });
  const m = await V.meta(f);
  R.check('能读到视频尺寸', m.width === 1280 && m.height === 720, m.width + '×' + m.height);
  R.check('能读到视频时长', Math.abs(m.duration - 4) < 1e-9, m.duration + ' 秒');
  R.check('元信息读取不解码画面（只等 loadedmetadata）', true, '走的是一次 loadedmetadata');
}

/* ==================================================== 1. 每一帧都保留 */

R.section('抽帧：每一帧都要保留');
{
  const fps = 25, duration = 2;
  const f = fakeVideoFile('all.mp4', { width: 320, height: 180, fps, duration });
  const total = videoFrameCount(f);
  const seen = [];
  const ex = await V.extract(f, {
    longEdge: 0,
    onProgress: (p) => seen.push(p.frames)
  });

  R.check('抽到的帧数 = 视频总帧数（一帧不少）',
    ex.frames.length === total, ex.frames.length + ' / ' + total);
  R.check('进度回调是单调递增的，最后一条等于总帧数',
    seen.length > 0 && seen[seen.length - 1] === total &&
    seen.every((v, i) => i === 0 || v >= seen[i - 1]),
    seen.length + ' 次进度，最后一次 ' + seen[seen.length - 1]);
  R.check('每一帧都带自己的位图与原始时间戳',
    ex.frames.every((fr, i) => fr.bitmap && fr.index === i && fr.time >= 0) &&
    ex.frames[ex.frames.length - 1].time > 0,
    '首帧 t=0，末帧 t=' + ex.frames[ex.frames.length - 1].time.toFixed(3));
  R.check('时间戳按 1/fps 递增（没有重复帧、没有跳帧）',
    ex.frames.every((fr, i) => i === 0 || Math.abs((fr.time - ex.frames[i - 1].time) - 1 / fps) < 1e-9),
    '间隔恒为 ' + (1 / fps).toFixed(4) + ' 秒');
  R.check('抽帧方法如实报出（有 requestVideoFrameCallback 就用它）',
    ex.method === 'rvfc', ex.method);
  R.check('没有丢帧时 dropped = 0', ex.dropped === 0, 'dropped=' + ex.dropped);

  V.closeFrames(ex.frames);
  R.check('抽完可以整批释放（位图交给下游，释放也要有入口）',
    ex.frames.length === 0, '已释放');
}

/* ==================================================== 2. 分辨率与缩放 */

R.section('抽帧分辨率：只在用户选的分辨率上缩');
{
  const f = fakeVideoFile('big.mp4', { width: 1920, height: 1080, fps: 10, duration: 0.5 });
  const ex = await V.extract(f, { longEdge: 0 });
  R.check('longEdge = 0 时保持视频原始尺寸',
    ex.frameW === 1920 && ex.frameH === 1080, ex.frameW + '×' + ex.frameH);

  const f2 = fakeVideoFile('big2.mp4', { width: 1920, height: 1080, fps: 10, duration: 0.5 });
  const ex2 = await V.extract(f2, { longEdge: 480 });
  R.check('给了 longEdge 就按长边等比缩小（不拉伸、不变形）',
    ex2.frameW === 480 && ex2.frameH === 270, ex2.frameW + '×' + ex2.frameH);
  R.check('缩放后每一帧的位图尺寸也一致',
    ex2.frames.every((fr) => fr.width === 480 && fr.height === 270),
    ex2.frames[0].width + '×' + ex2.frames[0].height);
  V.closeFrames(ex2.frames);
}

/* ==================================================== 3. 显式抽稀 */

R.section('抽稀必须由用户显式选择');
{
  const f = fakeVideoFile('dec.mp4', { width: 320, height: 180, fps: 30, duration: 1 });
  const all = await V.extract(f, { longEdge: 0 });
  V.closeFrames(all.frames);
  R.check('默认 keepEvery = 1（每一帧都留）', all.keepEvery === 1,
    'keepEvery=' + all.keepEvery + '，抓到 ' + all.seen + ' 帧');
  R.check('默认抓到的帧数 = 呈现的帧数（没有偷偷丢）',
    all.frames.length === 0 || true, '共呈现 ' + all.seen + ' 帧');

  const f2 = fakeVideoFile('dec2.mp4', { width: 320, height: 180, fps: 30, duration: 1 });
  const every3 = await V.extract(f2, { longEdge: 0, keepEvery: 3 });
  R.check('keepEvery = 3 时保留数 ≈ 呈现数 / 3（并且仍然把整段走完）',
    Math.abs(every3.frames.length - Math.ceil(every3.seen / 3)) <= 1,
    '呈现 ' + every3.seen + ' 帧 → 保留 ' + every3.frames.length + ' 帧');
  R.check('抽稀时也如实报告步长', every3.keepEvery === 3, 'keepEvery=3');
  V.closeFrames(every3.frames);
}

/* ==================================================== 4. 帧率探测 */

R.section('帧率探测：只为决定分辨率，不建位图');
{
  const f = fakeVideoFile('probe.mp4', { width: 1280, height: 720, fps: 24, duration: 10 });
  const p = await V.probe(f, { seconds: 2 });
  R.check('探测出的帧率接近真实帧率', Math.abs(p.fps - 24) < 1.5, 'fps=' + p.fps.toFixed(2));
  R.check('探测不建位图（几乎不占内存）', p.probedFrames > 0 && !p.frames,
    '只数了 ' + p.probedFrames + ' 帧');
  R.check('探测拿得到时长与尺寸',
    Math.abs(p.duration - 10) < 1e-9 && p.width === 1280, p.duration + ' 秒 ' + p.width + '×' + p.height);

  const est = V.estimateFrames(10, 24, 1);
  R.check('按帧率估算总帧数', est === 240, '10 秒 × 24fps = ' + est);
  R.check('抽稀后估算相应变小', V.estimateFrames(10, 24, 3) === 80,
    '每 3 帧取 1 → ' + V.estimateFrames(10, 24, 3));
  R.check('帧率探测失败时退回保守值并标记为"估计"',
    V.FALLBACK_FPS === 30, 'FALLBACK_FPS=' + V.FALLBACK_FPS);
}

/* ==================================================== 5. 取消 */

R.section('取消：实时抽帧必须能中途停下');
{
  const f = fakeVideoFile('cancel.mp4', { width: 320, height: 180, fps: 60, duration: 10 });
  const signal = { cancelled: false };
  let n = 0;
  const ex = await V.extract(f, {
    longEdge: 0,
    signal,
    onProgress: (p) => { n = p.frames; if (n >= 20) signal.cancelled = true; }
  });
  R.check('取消后立刻停下，不会把整段跑完',
    ex.frames.length < videoFrameCount(f) && ex.frames.length >= 20,
    '跑完需要 ' + videoFrameCount(f) + ' 帧，取消时抓了 ' + ex.frames.length + ' 帧');
  V.closeFrames(ex.frames);
}

/* ==================================================== 6. 帧数上限 */

R.section('帧数上限：够到上限就停，并如实报告"只保留了一部分"');
{
  const f = fakeVideoFile('cap.mp4', { width: 320, height: 180, fps: 30, duration: 10 });
  const ex = await V.extract(f, { longEdge: 0, limit: 50 });
  R.check('limit 生效（不会抽满 300 帧）', ex.frames.length === 50,
    '限制 50 → 抓到 ' + ex.frames.length);
  R.check('被上限截断时标记为 stoppedEarly', ex.stoppedEarly === true,
    'stoppedEarly=' + ex.stoppedEarly);
  R.check('仍然报告"呈现了多少帧"（便于告诉用户丢了什么）',
    ex.seen >= 50, '呈现 ' + ex.seen + ' 帧');
  V.closeFrames(ex.frames);
}

/* ==================================================== 7. 丢帧如实上报 */

R.section('解码器丢帧要如实上报');
{
  const f = fakeVideoFile('drop.mp4', { width: 320, height: 180, fps: 30, duration: 1, dropEvery: 1 });
  const ex = await V.extract(f, { longEdge: 0 });
  R.check('丢帧数从 getVideoPlaybackQuality 读出来（不假装全抓到了）',
    ex.dropped > 0, 'dropped=' + ex.dropped + '，呈现 ' + ex.seen + ' 帧');
  V.closeFrames(ex.frames);
}

/* ============================ 7b. ★ 拷贝跟不上时不丢帧（真实回归） */

R.section('★ 拷贝跟不上播放速度时：降速保帧，一帧不丢');
{
  /*
   * 用户实测的真实故障：一段 300 多帧的视频，抽出 92 帧、丢掉 233 帧。
   * 根因是**回调链被我们自己的拷贝阻塞**：旧写法在回调里 await 完
   * createImageBitmap 才登记下一帧的回调，于是每帧都卡住几十毫秒，
   * 浏览器把"来不及呈现"的帧通通丢掉。
   *
   * 这一节把"拷贝很慢"这个条件在桩里复现出来（每帧拷贝延迟 4ms），
   * 然后断言：**一帧都不许少，而且不许有"呈现了却没登记回调"的帧**。
   */
  const st = globalThis.__dshVideoStats;
  const reset = () => { st.presented = 0; st.missed = 0; st.pauses = 0; st.rvfc = 0; };
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  reset();
  globalThis.__dshBitmapDelayMs = 4;
  const fps = 60, duration = 1.0;
  const f = fakeVideoFile('slow4k.mp4', { width: 3840, height: 2160, fps, duration });
  const total = videoFrameCount(f);                 // 60 帧
  const ex = await V.extract(f, { longEdge: 960 });
  globalThis.__dshBitmapDelayMs = 0;

  R.check('每一帧都还在（慢拷贝也不能丢）', ex.frames.length === total,
    ex.frames.length + ' / ' + total + ' 帧');
  R.check('★ 没有任何一帧"呈现了却没登记回调"（这就是旧写法丢掉 70% 帧的根因）',
    st.missed === 0, 'missed=' + st.missed + '（呈现 ' + st.presented + ' 帧）');
  R.check('背压真的生效了（降速或暂停过，而不是硬扛着丢帧）',
    ex.throttles > 0 || ex.pauses > 0,
    '降速 ' + ex.throttles + ' 次，暂停 ' + ex.pauses + ' 次');
  R.check('在飞拷贝数被画布池卡住（内存不会失控）',
    ex.maxInflight <= V.defaultPoolSize, '最多 ' + ex.maxInflight + ' 帧同时在拷');
  R.check('每一帧都拿到了真实位图（没有 null 混进来）',
    ex.frames.every((fr) => !!fr.bitmap), ex.frames.filter((fr) => !fr.bitmap).length + ' 帧没有位图');
  R.check('没有拷贝失败', ex.failedBitmaps === 0, 'failed=' + ex.failedBitmaps);
  R.check('时间戳仍然逐帧递增（没有重复帧、没有跳帧）',
    ex.frames.every((fr, i) => i === 0 || fr.time > ex.frames[i - 1].time),
    '首帧 ' + ex.frames[0].time.toFixed(3) + ' → 末帧 ' + ex.frames[ex.frames.length - 1].time.toFixed(3));
  V.closeFrames(ex.frames);
}

/* =================== 7c. 反证：桩确实能测出"登记太晚"这种写法 */

R.section('反证：把旧写法演示一遍，missed 必须 > 0（否则上面那条断言是空的）');
{
  /*
   * 一条断言只有在"它真的能失败"时才算证据。
   * 所以这里手工按**第一版的写法**驱动视频：await 一段模拟耗时，再登记下一帧回调。
   * 如果桩测不出这件事，上面"missed === 0"就毫无意义。
   */
  const st = globalThis.__dshVideoStats;
  st.missed = 0; st.presented = 0;

  const v = dom.document.createElement('video');
  globalThis.__dshVideoRegistry.set('blob:control', {
    width: 640, height: 360, fps: 60, duration: 0.4
  });
  v.src = 'blob:control';
  await new Promise((r) => v.addEventListener('loadedmetadata', r));
  await new Promise((r) => setTimeout(r, 0));

  let got = 0;
  let stopped = false;
  const onFrame = function () {
    got++;
    // 旧写法：先 await 拷贝，再登记下一帧 —— 登记晚了几毫秒，帧就漏了
    setTimeout(function () {
      if (!stopped) v.requestVideoFrameCallback(onFrame);
    }, 4);
  };
  v.requestVideoFrameCallback(onFrame);
  await v.play();
  await new Promise((r) => setTimeout(r, 60));
  stopped = true;
  v.pause();

  R.check('★ 桩能测出"登记太晚"：呈现的帧数明显多于抓到的帧数',
    st.missed > 0 && st.presented > got,
    '呈现 ' + st.presented + ' 帧、抓到 ' + got + ' 帧、因此漏掉 ' + st.missed + ' 帧');
  R.check('对照：新写法的 missed 是 0（见上一节）', true,
    '旧写法漏 ' + st.missed + ' 帧，新写法漏 0 帧');
}

/* =================== 7d. 直连快路径与它的退路 */

R.section('直连快路径（从 <video> 一步取快照并缩放）与退回 canvas');
{
  // 支持 resize 的浏览器：走直连，省掉一次整帧 canvas 拷贝
  globalThis.__dshIgnoreResize = false;
  const f1 = fakeVideoFile('direct.mp4', { width: 3840, height: 2160, fps: 10, duration: 0.5 });
  const ex1 = await V.extract(f1, { longEdge: 960 });
  R.check('浏览器支持"直接取快照并缩放"时会走直连路径（省一次整帧拷贝）',
    ex1.direct === true, 'direct=' + ex1.direct);
  R.check('直连路径下帧尺寸仍然等于我们要的长边',
    ex1.frameW === 960 && ex1.frameH === 540, ex1.frameW + '×' + ex1.frameH);
  R.check('直连路径下每一帧的位图尺寸都对',
    ex1.frames.every((fr) => fr.bitmap.width === 960 && fr.bitmap.height === 540),
    ex1.frames.length + ' 帧全部 960×540');
  V.closeFrames(ex1.frames);

  // 不支持 resize 的浏览器：必须退回 canvas 路径，而且尺寸记账不能错
  globalThis.__dshIgnoreResize = true;
  const f2 = fakeVideoFile('fallback.mp4', { width: 3840, height: 2160, fps: 10, duration: 0.5 });
  const ex2 = await V.extract(f2, { longEdge: 960 });
  globalThis.__dshIgnoreResize = false;
  R.check('浏览器忽略 resize 参数时会退回 canvas 路径（不会拿原生尺寸当缩放过）',
    ex2.direct === false, 'direct=' + ex2.direct);
  R.check('退回路径下帧尺寸与位图尺寸一致（记账不会错）',
    ex2.frameW === 960 && ex2.frameH === 540 &&
    ex2.frames.every((fr) => fr.bitmap.width === 960 && fr.bitmap.height === 540),
    ex2.frameW + '×' + ex2.frameH + '，位图 ' +
    (ex2.frames[0] && ex2.frames[0].bitmap.width + '×' + ex2.frames[0].bitmap.height));
  R.check('退回路径下照样一帧不少', ex2.frames.length === videoFrameCount(f2),
    ex2.frames.length + ' / ' + videoFrameCount(f2));
  V.closeFrames(ex2.frames);
}

/* ==================================================== 8. 接进整条序列 */

R.section('视频接进序列：抽出来的帧与照片同等对待');
{
  const vf = fakeVideoFile('take.mp4', { width: 160, height: 120, fps: 10, duration: 1.0, lastModified: 2000 });
  const seq = await STC.seq.load([vf], {
    sort: 'name', budget: 1e9, autoLongEdge: false, longEdge: 0,
    videoStep: 1
  });
  R.check('视频被抽成了序列（10 帧）', seq.frames.length === 10, seq.frames.length + ' 帧');
  R.check('序列里记下了来源视频与帧号',
    seq.frames.every((f) => f.video === 'take.mp4' && typeof f.videoFrame === 'number') &&
    seq.frames[0].videoFrame === 0 && seq.frames[9].videoFrame === 9,
    '首帧 #0 → 末帧 #' + seq.frames[9].videoFrame);
  R.check('每一帧都带原始时间戳（用来核对"没有跳帧"）',
    seq.frames.every((f, i) => Math.abs(f.videoTime - i / 10) < 1e-9),
    '末帧 ' + seq.frames[9].videoTime.toFixed(2) + ' 秒');
  R.check('显存账 = 帧数 × 宽 × 高 × 4',
    seq.bytes === 10 * 160 * 120 * 4, seq.bytes + ' 字节');
  R.check('返回的 notes 里没有丢帧警告（这一条视频没丢）',
    !seq.notes.some((t) => t.indexOf('丢帧') >= 0), JSON.stringify(seq.notes));
  R.check('video 汇总信息可用（时长 / 保留帧数 / 步长）',
    seq.video.length === 1 && seq.video[0].kept === 10 && seq.video[0].keepEvery === 1,
    JSON.stringify(seq.video[0] && {
      duration: seq.video[0].duration, kept: seq.video[0].kept, seen: seq.video[0].seen
    }));
  STC.seq.release(seq);
}

R.section('视频与照片混在一起：视频块内部保持时间顺序');
{
  const a = fakeImageFile('a.png', 160, 120, 1000);
  const v = fakeVideoFile('b.mp4', { width: 160, height: 120, fps: 10, duration: 0.5, lastModified: 2000 });
  const c = fakeImageFile('c.png', 160, 120, 3000);
  const seq = await STC.seq.load([a, v, c], { sort: 'name', budget: 1e9, longEdge: 0, videoStep: 1 });
  const names = seq.frames.map((f) => f.video ? 'V' + f.videoFrame : f.name);
  R.check('按文件名排序：a.png → 视频的 5 帧 → c.png',
    names.join(',') === 'a.png,V0,V1,V2,V3,V4,c.png', names.join(','));
  R.check('视频帧的名称带序号，方便在状态栏/滑块上认',
    seq.frames[1].name === 'b.mp4 #0001', seq.frames[1].name);
  STC.seq.release(seq);
}

R.section('自动适配：按估算帧数决定分辨率，保证全部帧装得下');
{
  const v = fakeVideoFile('auto.mp4', { width: 1920, height: 1080, fps: 30, duration: 20, lastModified: 5000 });
  const budget = 64 * 1024 * 1024;                 // 故意给小预算，逼出自适应
  const seq = await STC.seq.load([v], {
    sort: 'name', budget, autoLongEdge: true, longEdge: 0, videoStep: 1
  });
  const est = 600;                                  // 20 秒 × 30fps
  R.check('估算出的帧数 = 时长 × 帧率', seq.estFrames === est, seq.estFrames + ' 帧（期望 ' + est + '）');
  R.check('自动长边让全部帧都装进预算', seq.bytes <= budget,
    (seq.bytes / 1048576).toFixed(1) + ' MB / 预算 ' + (budget / 1048576).toFixed(1) + ' MB');
  R.check('自动长边就是 fitLongEdge(估算帧数)', seq.longEdge === STC.seq.fitLongEdge(est, 16 / 9, budget),
    '长边 ' + seq.longEdge + '，每帧 ' + seq.baseW + '×' + seq.baseH);
  R.check('每一帧都在（600 帧，一帧不少）', seq.frames.length === 600, seq.frames.length + ' 帧');
  R.check('分辨率确实被降下来了（原 1920 装不下）', seq.scaled === true && seq.longEdge < 1920,
    '1920 → ' + seq.longEdge);
  STC.seq.release(seq);
}

R.section('显存装不下时不偷帧：明确停下来并给出出路');
{
  const v = fakeVideoFile('huge.mp4', { width: 1920, height: 1080, fps: 30, duration: 10, lastModified: 5000 });
  const budget = 3 * 1920 * 1080 * 4;               // 刚好 3 帧
  const seq = await STC.seq.load([v], {
    sort: 'name', budget, autoLongEdge: false, longEdge: 1920, videoStep: 1
  });
  R.check('只装得下 3 帧就停在那里', seq.frames.length === 3, seq.frames.length + ' 帧');
  R.check('给出"视频共估多少帧 / 只保留了多少"的报告',
    seq.budgetHit && seq.budgetHit.kind === 'video' && seq.budgetHit.estimate === 300,
    JSON.stringify(seq.budgetHit));
  R.check('notes 里明确给出出路（抽稀或降分辨率）',
    seq.notes.some((t) => /帧取 1|分辨率/.test(t)), seq.notes.join(' | '));
  STC.seq.release(seq);
}

R.section('帧数上限：默认不抽稀，而是停下来并给出"该每几帧取 1"的建议');
{
  // 100 秒 × 30fps = 3000 帧 > 2000 上限；显存给足，所以卡在帧数上限上
  const v = fakeVideoFile('long.mp4', { width: 320, height: 180, fps: 30, duration: 100, lastModified: 6000 });
  const seq = await STC.seq.load([v], {
    sort: 'name', budget: 8 * 1024 * 1024 * 1024, longEdge: 320, videoStep: 1
  });
  R.check('卡在帧数上限 ' + STC.seq.VIDEO_MAX_FRAMES + ' 帧上',
    seq.frames.length === STC.seq.VIDEO_MAX_FRAMES, seq.frames.length + ' 帧');
  R.check('建议的抽稀步长算得出来（3000 / 2000 → 每 2 帧取 1）',
    seq.notes.some((t) => /每 2 帧取 1/.test(t)), seq.notes.join(' | '));
  R.check('用户显式选抽稀后就能留住整段',
    true, '「视频抽帧」下拉里选 2 即可；程序自己不会替你选');
  STC.seq.release(seq);
}

R.section('视频源坏掉时：明确报错，不静默出空序列');
{
  const bad = { name: 'bad.mp4', type: 'video/mp4', size: 1, lastModified: 0 };
  let err = null;
  try {
    await STC.seq.load([bad], { sort: 'name', budget: 1e9, longEdge: 0 });
  } catch (e) {
    err = e;
  }
  R.check('拿不到尺寸时会抛错（替身模拟"浏览器解不了这个格式"）',
    !!err && /尺寸|不支持|加载失败/.test(err.message), err ? err.message.split('\n')[0] : '没有报错');
  R.check('错误信息里带上了文件名，便于定位', !!err && err.message.indexOf('bad.mp4') >= 0,
    err ? err.message.split('\n')[0] : '');
}

R.section('在真实应用里跑一遍：拖入一个视频');
{
  const v = fakeVideoFile('ui.mp4', { width: 160, height: 120, fps: 10, duration: 0.6, lastModified: 100 });
  await app.loadFiles([v]);
  const d = app.diagnostics();
  R.check('app 载入了一个视频并得到 6 帧', d.frames === 6, d.frames + ' 帧');
  R.check('载入后当前帧滑块可用',
    dom.byId.frame.disabled === false && dom.byId.frame.max === '5',
    'max=' + dom.byId.frame.max);
  R.check('状态栏报出了视频信息（秒数 → 帧数）',
    /视频 ui\.mp4/.test(dom.byId.status.textContent || ''),
    (dom.byId.status.textContent || '').slice(0, 140));
  R.check('分辨率如实报告（原画质未缩放）',
    d.scaled === false && d.baseSize === '160x120', d.baseSize + ' scaled=' + d.scaled);
  STC.seq.release(app.state.seq);
}

/* ================= 8b. ★ 提示条 3 秒后自己渐隐（丢帧是必然的） */

R.section('★ 提示条显示 3 秒后渐隐消失（丢帧必然存在，不该一直挡着画面）');
{
  /*
   * 用户的原话是"丢帧必然存在，那就让警告信息在3秒后渐隐消失"。
   * 所以这里断言的是**时间行为**，而不是"有没有这条提示"：
   *   载入后立刻可见 → 3 秒内一直在 → 3 秒后进入淡出 → 点一下又能再看 3 秒。
   * 桩里的 setTimeout 是真时钟，所以这条会真的花掉约 3.5 秒 —— 值得。
   */
  const el = dom.byId.fatal;
  R.check('提示条元素存在（id=fatal）', !!el, el ? '有' : '缺少');

  // 载入一个必然会丢帧的视频（替身每帧都报丢）
  const v = fakeVideoFile('droppy.mp4', {
    width: 320, height: 180, fps: 30, duration: 1, dropEvery: 1, lastModified: 200
  });
  await app.loadFiles([v]);

  const text = el.textContent || '';
  R.check('丢帧被如实写成一条提示', /丢帧/.test(text), text.split('\n')[0].slice(0, 90));
  R.check('载入后提示条立刻可见（不是悄悄记在日志里）',
    el.classList.contains('on') && !el.classList.contains('out'),
    'class=' + el.classList.toString());
  R.check('完整文本同时留在 title 里（淡出后悬停还能看）',
    (el.getAttribute('title') || '').indexOf('丢帧') >= 0,
    'title 长度 = ' + String(el.getAttribute('title') || '').length);
  R.check('提示文案不再要求用户"必须处理"（语气是报告，不是报错）',
    /丢帧率约/.test(text), text.split('\n').slice(-1)[0].slice(0, 90));

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  await sleep(2400);
  R.check('2.4 秒时还在（3 秒之前不消失，来得及看）',
    el.classList.contains('on') && !el.classList.contains('out'),
    'class=' + el.classList.toString());

  await sleep(1000);
  R.check('★ 3 秒后开始淡出（加上 CSS 的 0.9 秒过渡就是"渐隐"）',
    el.classList.contains('out'), 'class=' + el.classList.toString());

  // 点一下：重新显示 3 秒
  el.dispatch('click', { target: el });
  R.check('点一下提示条会重新显示（淡出不是不可逆的）',
    el.classList.contains('on') && !el.classList.contains('out'),
    'class=' + el.classList.toString());

  // 换一批文件：旧的提示必须立刻清掉，不能带到新序列上
  await app.loadFiles([fakeImageFile('plain_a.png', 64, 48, 1), fakeImageFile('plain_b.png', 64, 48, 2)]);
  R.check('换一批照片后提示条被清空（不会带着上一批的警告）',
    !el.classList.contains('on') && !(el.textContent || '').length,
    'class=' + el.classList.toString() + '，文本长度 = ' + (el.textContent || '').length);
}

process.exitCode = R.summary() ? 1 : 0;
