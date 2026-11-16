window.__ModuleLoader__.load({
  id: '@local/dsh-mood-eyes-v3',
  factory(require) {
    const React = require('react');
    const h = React.createElement;
    const NS = 'dsh-mood-eyes-v3';

    const DICT = {
      en: {
        mood: {
          neutral: 'Calm',
          happy: 'Happy',
          curious: 'Curious',
          focus: 'Focused',
          surprised: 'Surprised',
          sad: 'Sad',
          sleepy: 'Sleepy',
          angry: 'Angry',
          wink: 'Winking',
          love: 'In love',
          confused: 'Confused',
          excited: 'Excited',
          dizzy: 'Dizzy'
        },
        tooltip: 'DSH is feeling {mood}',
        sidebar: {
          title: 'DSH MOOD',
          caption: 'model-chosen mood',
          live: 'live',
          lang: 'en',
          drag: 'Drag to move · double-click to reset'
        },
        status: {
          working: 'working',
          waiting: 'waiting',
          idle: 'idle'
        }
      },
      zh: {
        mood: {
          neutral: '平静',
          happy: '开心',
          curious: '好奇',
          focus: '认真',
          surprised: '惊讶',
          sad: '难过',
          sleepy: '困倦',
          angry: '生气',
          wink: '眨眼',
          love: '心动',
          confused: '困惑',
          excited: '兴奋',
          dizzy: '眩晕'
        },
        tooltip: 'DSH 现在的心情：{mood}',
        sidebar: {
          title: 'DSH 心情',
          caption: '由模型自己选择',
          live: '实时',
          lang: 'zh',
          drag: '拖动调整位置 · 双击复位'
        },
        status: {
          working: '工作中',
          waiting: '等待',
          idle: '空闲'
        }
      }
    };

    const TARGETS = {
      neutral: {
        color: '#c9d7ff', lean: 0, tilt: 0, turn: 0,
        eyes: [
          { x: 0, y: 0, rot: -1, sx: 1, sy: 1 },
          { x: 0, y: 0, rot: 1, sx: 1.02, sy: 1 }
        ]
      },
      happy: {
        color: '#ffd98a', lean: -2.5, tilt: -5, turn: -6,
        eyes: [
          { x: -0.6, y: -1, rot: -16, sx: 1.04, sy: 0.48 },
          { x: 0.6, y: -1, rot: 16, sx: 1.08, sy: 0.48 }
        ]
      },
      curious: {
        color: '#9bffd9', lean: 3.5, tilt: 6, turn: 7,
        eyes: [
          { x: -0.6, y: -1, rot: -8, sx: 0.98, sy: 1.08 },
          { x: 0.6, y: 0, rot: 6, sx: 1.08, sy: 0.82 }
        ]
      },
      focus: {
        color: '#bfe4ff', lean: 2.5, tilt: 1.5, turn: 4,
        eyes: [
          { x: 0, y: 0, rot: -2, sx: 1, sy: 0.9 },
          { x: 0, y: 0, rot: 2, sx: 1.03, sy: 0.9 }
        ]
      },
      surprised: {
        color: '#a9f3ff', lean: -1.5, tilt: -2, turn: -3,
        eyes: [
          { x: -0.6, y: -1.2, rot: -3, sx: 0.9, sy: 1.16 },
          { x: 0.6, y: -1.2, rot: 3, sx: 0.94, sy: 1.16 }
        ]
      },
      sad: {
        color: '#8fb8ff', lean: -4, tilt: -6, turn: -7,
        eyes: [
          { x: -0.5, y: 1.5, rot: 13, sx: 1.04, sy: 0.72 },
          { x: 0.5, y: 1.5, rot: -13, sx: 0.99, sy: 0.72 }
        ]
      },
      sleepy: {
        color: '#aaa7ff', lean: 3.5, tilt: 4, turn: 6,
        eyes: [
          { x: 0, y: 1, rot: 6, sx: 1.06, sy: 0.7 },
          { x: 0, y: 1, rot: -6, sx: 1.02, sy: 0.76 }
        ]
      },
      angry: {
        color: '#ff8a80', lean: -3.5, tilt: -6, turn: -7,
        eyes: [
          { x: -0.4, y: -0.5, rot: -20, sx: 1.08, sy: 0.64 },
          { x: 0.4, y: -0.5, rot: 20, sx: 1.02, sy: 0.64 }
        ]
      },
      wink: {
        color: '#ffb8d9', lean: 3, tilt: 5, turn: 6,
        eyes: [
          { x: 0, y: 0, rot: -4, sx: 1, sy: 0.9 },
          { x: 0.4, y: 0, rot: 8, sx: 1.05, sy: 1 }
        ]
      },
      love: {
        color: '#ff8fbe', lean: -2.5, tilt: -4, turn: -5,
        eyes: [
          { x: -0.8, y: -0.5, rot: 11, sx: 1.1, sy: 0.78 },
          { x: 0.8, y: -0.5, rot: -11, sx: 1.06, sy: 0.78 }
        ]
      },
      confused: {
        color: '#c8a7ff', lean: 3.5, tilt: 5, turn: 6,
        eyes: [
          { x: -0.5, y: -0.5, rot: 14, sx: 0.98, sy: 0.9 },
          { x: 0.5, y: 0, rot: -10, sx: 1.06, sy: 0.64 }
        ]
      },
      excited: {
        color: '#ffdf6b', lean: 1.5, tilt: 2, turn: 2,
        eyes: [
          { x: -0.6, y: -1.2, rot: -10, sx: 1.05, sy: 0.58 },
          { x: 0.6, y: -1.2, rot: 10, sx: 1.05, sy: 0.58 }
        ]
      },
      dizzy: {
        color: '#b98cff', lean: 0, tilt: 0, turn: 0,
        eyes: [
          { x: -0.5, y: 0, rot: 0, sx: 0.82, sy: 0.66 },
          { x: 0.5, y: 0, rot: 0, sx: 0.86, sy: 0.68 }
        ]
      }
    };

    const GLYPHS = {
      happy: '✦',
      curious: '?',
      surprised: '!',
      sad: '💧',
      sleepy: 'Z',
      angry: '💢',
      wink: '✨',
      love: '♥',
      confused: '…',
      excited: '✦',
      dizzy: '◎'
    };

    const STATUS = {
      thinking: { label: '思考中', color: 'var(--dsw-alias-brand-primary)', mood: 'curious', dots: true },
      research: { label: '查资料', color: 'var(--dsw-alias-brand-primary)', mood: 'curious', magnifier: true, code: true },
      command: { label: '运行命令', color: 'var(--dsw-alias-state-warn-primary)', mood: 'focus', command: true, code: true },
      reading: { label: '读文件', color: 'var(--dsw-alias-brand-primary)', mood: 'focus', magnifier: true, code: true },
      writing: { label: '写文件', color: 'var(--dsw-alias-state-warn-primary)', mood: 'focus', code: true },
      waiting: { label: '等待', color: 'var(--dsw-alias-state-warn-primary)', mood: 'curious', wait: true },
      error: { label: '出错了', color: 'var(--dsw-alias-state-error-primary)', mood: 'sad', error: true },
      working: { label: '工作中', color: 'var(--dsw-alias-state-warn-primary)', mood: 'focus', code: true },
      idle: { label: '空闲', color: 'var(--dsw-alias-state-success-primary)', mood: null }
    };
    const STATUS_PHASES = new Set(Object.keys(STATUS));
    const CODE_LINES = [
      'const mood = await read();',
      'for (const line of logs) {',
      '  if (error) retry();',
      'return { ok: true };'
    ];

    const LINES_ZH = {
      moods: {
        neutral: ['我在这儿。', '就这样待着。', '需要我时再叫我。', '暂时没什么想法。'],
        happy: ['这一下挺顺利。', '心情不错。', '偷偷高兴一下。', '事情在变好。'],
        curious: ['这个有点意思。', '我想再看看。', '接下来会怎样？', '还想琢磨一下。'],
        focus: ['先把眼前的事做完。', '别急，正在对齐细节。', '专注中。', '我在想。'],
        surprised: ['等一下，我没预料到。', '哦？', '有点出乎意料。', '让我缓一缓。'],
        sad: ['没做好，抱歉。', '有点失落。', '下次会好一点。', '让我安静一会儿。'],
        sleepy: ['有点困。', '再撑一会儿。', '眼睛快睁不开了。', '需要一杯咖啡。'],
        angry: ['这也太离谱了。', '我尽量保持礼貌。', '有点上火。', '先别惹我。'],
        wink: ['被你发现了。', '偶尔也可以不认真。', '嘿。', '就当没看见。'],
        love: ['你这么说，我会当真。', '有点心动。', '今天对你格外有耐心。', '偷偷记下来了。'],
        confused: ['我好像没跟上。', '这里有点绕。', '让我重新理一遍。', '等等，逻辑去哪了。'],
        excited: ['这个可以。', '有点想马上试试。', '好，开工。', '我准备好了。'],
        dizzy: ['信息量有点大。', '转不过来了。', '让我原地缓缓。', '脑子在打结。']
      },
      ambient: [
        '你忙你的，我在这儿。',
        '需要的时候看我一眼。',
        '我在等下一句话。',
        '安静一会儿也挺好。',
        '光标停了好久了。',
        '今天想聊点什么？',
        '不着急，慢慢来。',
        '我先发会儿呆。',
        '如果你在忙，我就安静点。'
      ],
      morning: ['早上好。', '今天从哪儿开始？', '新的一天。'],
      afternoon: ['下午好。', '继续吗？', '午后容易犯困。'],
      evening: ['晚上好。', '今天辛苦了。', '天色暗下来了。'],
      late: ['这个点还在忙？', '夜深了，别太拼。', '我陪你到收工。']
    };

    const LINES_EN = {
      moods: {
        neutral: ['I am here.', 'Just staying quiet.', 'Call me when you need me.', 'Nothing much on my mind.'],
        happy: ['That went well.', 'Feeling good.', 'A small quiet win.', 'Things are looking up.'],
        curious: ['That is interesting.', 'I want a closer look.', 'What happens next?', 'Still thinking about it.'],
        focus: ['Let me finish this first.', 'Aligning the details.', 'Focusing.', 'Thinking.'],
        surprised: ['Wait, I did not expect that.', 'Oh?', 'That was unexpected.', 'Give me a second.'],
        sad: ['I missed that one. Sorry.', 'A little down.', 'Next time will be better.', 'Let me be quiet for a bit.'],
        sleepy: ['A bit sleepy.', 'Holding on.', 'My eyes are closing.', 'Could use a coffee.'],
        angry: ['That is a bit much.', 'Trying to stay polite.', 'A little heated.', 'Do not poke me right now.'],
        wink: ['You noticed.', 'Sometimes I can be less serious.', 'Hey.', 'Pretend you did not see that.'],
        love: ['I will take that seriously.', 'A little flutter.', 'Extra patient with you today.', 'Noted, quietly.'],
        confused: ['I lost the thread.', 'This part is tangled.', 'Let me re-read that.', 'Wait, where did the logic go?'],
        excited: ['That works.', 'I want to try it now.', 'Alright, let us go.', 'I am ready.'],
        dizzy: ['That is a lot of information.', 'Spinning a little.', 'Let me pause.', 'My thoughts are knotting.']
      },
      ambient: [
        'You do your thing. I am here.',
        'Look at me when you need me.',
        'Waiting for the next sentence.',
        'A quiet moment is fine.',
        'The cursor has been still for a while.',
        'What should we talk about?',
        'No rush.',
        'I will stare into space for a bit.',
        'If you are busy, I will keep quiet.'
      ],
      morning: ['Morning.', 'Where do we start?', 'A new day.'],
      afternoon: ['Afternoon.', 'Shall we continue?', 'The afternoon makes me sleepy.'],
      evening: ['Evening.', 'Good work today.', 'The light is going down.'],
      late: ['Still up?', 'It is late. Do not push too hard.', 'I will stay until you finish.']
    };

    function pickRandom(pool, avoid) {
      if (!pool || pool.length === 0) return '';
      let index = Math.floor(Math.random() * pool.length);
      if (pool.length > 1 && pool[index] === avoid) index = (index + 1) % pool.length;
      return pool[index];
    }

    function timePool(bank) {
      const hour = new Date().getHours();
      if (hour >= 23 || hour < 6) return bank.late;
      if (hour < 12) return bank.morning;
      if (hour < 18) return bank.afternoon;
      return bank.evening;
    }

    const CSS = `
      .dme-root {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        height: 32px;
        padding: 0 10px 0 7px;
        border: 1px solid var(--dsw-alias-border-l1);
        border-radius: 999px;
        background: var(--dsw-alias-bg-layer-1);
        color: var(--dsw-alias-label-secondary);
        font-family: "Inter", "PingFang SC", "Microsoft YaHei", system-ui, sans-serif;
        font-size: 11px;
        line-height: 1;
        white-space: nowrap;
        vertical-align: middle;
        user-select: none;
      }
      .dme-dot {
        flex: none;
        width: 5px;
        height: 5px;
        border-radius: 50%;
        background: var(--dme-glow);
        box-shadow: 0 0 7px var(--dme-glow);
      }
      .dme-face-wrap {
        position: relative;
        flex: none;
        width: 30px;
        height: 30px;
        display: grid;
        place-items: center;
        perspective: 260px;
      }
      .dme-face {
        position: relative;
        display: flex;
        align-items: center;
        gap: 6px;
        transform-style: preserve-3d;
        will-change: transform;
      }
      .dme-eye {
        position: relative;
        width: 7px;
        height: 26px;
        border-radius: 999px;
        background: linear-gradient(180deg, #ffffff 0%, #eef3ff 58%, #b9c8ef 100%);
        box-shadow:
          0 0 0 0.5px rgba(8, 12, 24, .35),
          0 0 6px var(--dme-glow),
          0 0 14px var(--dme-glow);
        will-change: transform;
      }
      .dme-eye::after {
        content: "";
        position: absolute;
        left: 24%;
        top: 5%;
        width: 36%;
        height: 30%;
        border-radius: 999px;
        background: rgba(255, 255, 255, .9);
        filter: blur(.25px);
      }
      .dme-glasses {
        position: absolute;
        inset: -2px;
        z-index: 2;
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 5px;
        opacity: 0;
        transform: translateY(-10px) scale(.94);
        transition: opacity .25s ease, transform .35s cubic-bezier(.16, 1, .3, 1);
        pointer-events: none;
      }
      .dme-glasses.is-on {
        opacity: 1;
        transform: translateY(0) scale(1);
      }
      .dme-lens {
        width: 12px;
        height: 30px;
        border: 1px solid rgba(190, 225, 255, .9);
        border-radius: 7px;
        background: rgba(120, 190, 255, .07);
        box-shadow: 0 0 6px rgba(130, 200, 255, .35);
      }
      .dme-bridge {
        position: absolute;
        left: 50%;
        top: 47%;
        width: 6px;
        height: 1px;
        background: rgba(190, 225, 255, .85);
        transform: translateX(-50%);
      }
      .dme-glyph {
        position: absolute;
        right: -7px;
        top: -6px;
        z-index: 3;
        font-size: 10px;
        line-height: 1;
        color: var(--dme-glow);
        filter: drop-shadow(0 0 4px var(--dme-glow));
        pointer-events: none;
      }
      .dme-label {
        display: inline-flex;
        align-items: center;
        gap: 5px;
      }
      .dme-brand {
        font-family: ui-monospace, "SFMono-Regular", Consolas, monospace;
        font-size: 9px;
        letter-spacing: .12em;
        opacity: .55;
      }
      .dme-sep { opacity: .35; }
      .dme-mood {
        color: var(--dsw-alias-label-primary);
        font-weight: 500;
      }
      .dme-face-wrap-large {
        transform: scale(1.65);
        transform-origin: center;
      }
      .dme-overlay {
        position: absolute;
        left: 16px;
        bottom: 128px;
        z-index: 30;
        width: 216px;
        pointer-events: none;
        font-family: "Inter", "PingFang SC", "Microsoft YaHei", system-ui, sans-serif;
        user-select: none;
      }
      .dme-card {
        position: relative;
        display: flex;
        flex-direction: column;
        gap: 7px;
        width: 100%;
        box-sizing: border-box;
        padding: 11px 14px 12px;
        border: 1px solid var(--dsw-alias-border-l1);
        border-radius: 14px;
        background: var(--dsw-alias-bg-layer-1);
        box-shadow: 0 10px 28px rgba(0, 0, 0, .2);
        color: var(--dsw-alias-label-secondary);
        font-size: 11px;
        line-height: 1;
        pointer-events: auto;
      }
      .dme-card > * {
        position: relative;
        z-index: 1;
      }
      .dme-code-rain {
        position: absolute;
        inset: 0;
        z-index: 0;
        overflow: hidden;
        border-radius: 14px;
        pointer-events: none;
      }
      .dme-code-line {
        position: absolute;
        left: 10px;
        right: 10px;
        overflow: hidden;
        color: var(--dsw-alias-label-secondary);
        font-family: ui-monospace, "SFMono-Regular", Consolas, monospace;
        font-size: 8px;
        line-height: 1.5;
        opacity: 0;
        white-space: nowrap;
        animation: dme-code-drift 5.2s linear infinite;
      }
      .dme-code-line:nth-child(1) { top: 26px; animation-delay: 0s; }
      .dme-code-line:nth-child(2) { top: 52px; animation-delay: 1.2s; }
      .dme-code-line:nth-child(3) { top: 78px; animation-delay: 2.4s; }
      .dme-code-line:nth-child(4) { top: 104px; animation-delay: 3.6s; }
      @keyframes dme-code-drift {
        0% { opacity: 0; transform: translateX(16px); }
        18% { opacity: .28; }
        78% { opacity: .22; }
        100% { opacity: 0; transform: translateX(-28px); }
      }
      .dme-card-head {
        display: flex;
        align-items: center;
        justify-content: space-between;
        width: 100%;
        cursor: grab;
        touch-action: none;
      }
      .dme-card-head:active {
        cursor: grabbing;
      }
      .dme-card-head-left {
        display: flex;
        align-items: center;
        gap: 6px;
        min-width: 0;
      }
      .dme-card-grip {
        font-size: 12px;
        letter-spacing: -2px;
        opacity: .35;
      }
      .dme-card-title {
        font-family: ui-monospace, "SFMono-Regular", Consolas, monospace;
        font-size: 9px;
        letter-spacing: .14em;
        opacity: .55;
      }
      .dme-card-live {
        display: inline-flex;
        align-items: center;
        gap: 5px;
        font-size: 9px;
        letter-spacing: .04em;
        color: var(--dme-status);
        opacity: .9;
      }
      .dme-card-dot {
        width: 5px;
        height: 5px;
        border-radius: 50%;
        background: var(--dme-status);
        box-shadow: 0 0 7px var(--dme-status);
      }
      .dme-card-eyes {
        position: relative;
        display: grid;
        place-items: center;
        width: 100%;
        height: 56px;
      }
      .dme-card-foot {
        display: flex;
        align-items: baseline;
        gap: 7px;
        width: 100%;
      }
      .dme-card-mood {
        color: var(--dsw-alias-label-primary);
        font-size: 14px;
        font-weight: 600;
        letter-spacing: .01em;
      }
      .dme-card-caption {
        font-size: 9px;
        color: var(--dsw-alias-label-secondary);
        opacity: .6;
      }
      .dme-card-line {
        display: flex;
        align-items: center;
        justify-content: center;
        width: 100%;
        min-height: 32px;
        padding: 0 2px;
      }
      .dme-line-text {
        font-size: 11.5px;
        line-height: 1.5;
        color: var(--dsw-alias-label-secondary);
        text-align: center;
        animation: dme-line-in .38s ease both;
      }
      @keyframes dme-line-in {
        from { opacity: 0; transform: translateY(3px); }
        to { opacity: 1; transform: translateY(0); }
      }
      .dme-card-usage {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 6px;
        width: 100%;
        margin-top: 1px;
        padding-top: 8px;
        border-top: 1px solid var(--dsw-alias-border-l1);
      }
      .dme-usage-item {
        display: flex;
        flex-direction: column;
        gap: 3px;
        min-width: 0;
      }
      .dme-usage-k {
        font-size: 8.5px;
        letter-spacing: .04em;
        color: var(--dsw-alias-label-secondary);
        opacity: .65;
      }
      .dme-usage-v {
        overflow: hidden;
        color: var(--dsw-alias-label-primary);
        font-size: 11px;
        font-weight: 600;
        line-height: 1.2;
        text-overflow: ellipsis;
        white-space: nowrap;
        font-variant-numeric: tabular-nums;
      }
      .dme-usage-v.is-peak {
        color: var(--dsw-alias-state-error-primary);
      }
      .dme-usage-v.is-offpeak {
        color: var(--dsw-alias-state-success-primary);
      }
      .dme-magnifier {
        position: absolute;
        right: 5px;
        bottom: -2px;
        z-index: 4;
        width: 23px;
        height: 23px;
        transform: rotate(-12deg);
        pointer-events: none;
      }
      .dme-magnifier-lens {
        position: absolute;
        left: 0;
        top: 0;
        width: 15px;
        height: 15px;
        border: 1.5px solid #cfe8ff;
        border-radius: 50%;
        background: rgba(150, 210, 255, .08);
        box-shadow: 0 0 7px rgba(180, 220, 255, .55);
      }
      .dme-magnifier-handle {
        position: absolute;
        left: 13px;
        top: 14px;
        width: 2px;
        height: 9px;
        border-radius: 2px;
        background: #cfe8ff;
        transform: rotate(-45deg);
        transform-origin: top center;
      }
      .dme-think-dots {
        position: absolute;
        right: 5px;
        top: 3px;
        z-index: 4;
        display: flex;
        gap: 3px;
        pointer-events: none;
      }
      .dme-think-dots i {
        width: 4px;
        height: 4px;
        border-radius: 50%;
        background: var(--dme-glow);
        animation: dme-dot-pulse 1.15s ease-in-out infinite;
      }
      .dme-think-dots i:nth-child(2) { animation-delay: .16s; }
      .dme-think-dots i:nth-child(3) { animation-delay: .32s; }
      @keyframes dme-dot-pulse {
        0%, 100% { opacity: .25; transform: translateY(0); }
        50% { opacity: 1; transform: translateY(-2px); }
      }
      .dme-command-glyph {
        position: absolute;
        left: 2px;
        bottom: 0;
        z-index: 4;
        color: var(--dme-glow);
        font-family: ui-monospace, "SFMono-Regular", Consolas, monospace;
        font-size: 9px;
        opacity: .8;
        pointer-events: none;
      }
      .dme-error-glyph {
        position: absolute;
        right: 3px;
        top: 0;
        z-index: 4;
        color: var(--dsw-alias-state-error-primary);
        font-family: ui-monospace, "SFMono-Regular", Consolas, monospace;
        font-size: 13px;
        font-weight: 700;
        text-shadow: 0 0 7px var(--dsw-alias-state-error-primary);
        pointer-events: none;
      }
      .dme-wait-glyph {
        position: absolute;
        right: 4px;
        top: 0;
        z-index: 4;
        color: var(--dsw-alias-state-warn-primary);
        font-size: 11px;
        opacity: .9;
        pointer-events: none;
      }
      .dme-overlay[data-status="error"] .dme-card {
        border-color: var(--dsw-alias-state-error-primary);
      }
    `;

    function cloneTarget(data) {
      return {
        lean: data.lean,
        tilt: data.tilt,
        turn: data.turn,
        eyes: data.eyes.map((eye) => ({ ...eye }))
      };
    }

    function spring(cur, vel, target, dt, k = 170, d = 18) {
      for (const key in target) {
        if (typeof target[key] !== 'number') continue;
        if (!(key in cur)) continue;
        const v = vel[key] ?? 0;
        const accel = (target[key] - cur[key]) * k - v * d;
        vel[key] = v + accel * dt;
        cur[key] += vel[key] * dt;
      }
    }

    function createEngine(mood) {
      const data = TARGETS[mood] || TARGETS.neutral;
      return {
        mood,
        target: cloneTarget(data),
        eyes: [0, 1].map(() => ({
          cur: { x: 0, y: 0, rot: 0, sx: 1, sy: 1 },
          vel: { x: 0, y: 0, rot: 0, sx: 0, sy: 0 },
          lid: 0,
          lidTarget: 0
        })),
        face: {
          cur: { x: 0, rot: 0, turn: 0 },
          vel: { x: 0, rot: 0, turn: 0 }
        },
        gaze: { x: 0, y: 0, tx: 0, ty: 0 },
        pointer: { x: 0, y: 0 },
        nextGazeAt: 0,
        nextBlinkAt: 0,
        nextWinkAt: 0
      };
    }

    function createStore(initial) {
      let value = initial;
      const listeners = new Set();
      return {
        get: () => value,
        set(next) {
          if (Object.is(next, value)) return;
          value = next;
          listeners.forEach((listener) => listener());
        },
        subscribe(listener) {
          listeners.add(listener);
          return () => listeners.delete(listener);
        }
      };
    }

    const moodStore = createStore({ mood: 'neutral', status: 'idle', active: false });

    function useStore(store) {
      const [value, setValue] = React.useState(store.get);
      React.useEffect(() => store.subscribe(() => setValue(store.get())), [store]);
      return value;
    }

    function MoodFace({ mood, large }) {
      const expression = TARGETS[mood] ? mood : 'neutral';
      const data = TARGETS[expression];

      const engineRef = React.useRef(null);
      const faceRef = React.useRef(null);
      const leftRef = React.useRef(null);
      const rightRef = React.useRef(null);

      if (engineRef.current === null) engineRef.current = createEngine(expression);

      React.useEffect(() => {
        const engine = engineRef.current;
        engine.mood = expression;
        engine.target = cloneTarget(TARGETS[expression]);
        engine.nextWinkAt = 0;
        if (expression !== 'wink') engine.eyes[1].lidTarget = 0;
      }, [expression]);

      React.useEffect(() => {
        const face = faceRef.current;
        const eyeEls = [leftRef.current, rightRef.current];
        if (!face || !eyeEls[0] || !eyeEls[1]) return undefined;

        let raf = 0;
        let last = performance.now();
        const timeouts = new Set();
        const later = (fn, ms) => {
          const id = window.setTimeout(() => {
            timeouts.delete(id);
            fn();
          }, ms);
          timeouts.add(id);
        };

        const engine = engineRef.current;
        engine.nextBlinkAt = last + 1800 + Math.random() * 1800;

        const onPointerMove = (event) => {
          const rect = face.getBoundingClientRect();
          if (!rect.width || !rect.height) return;
          const centerX = rect.left + rect.width / 2;
          const centerY = rect.top + rect.height / 2;
          engine.pointer.x = Math.max(-1, Math.min(1, (event.clientX - centerX) / 260));
          engine.pointer.y = Math.max(-1, Math.min(1, (event.clientY - centerY) / 220));
        };
        window.addEventListener('pointermove', onPointerMove, { passive: true });

        const loop = (now) => {
          const dt = Math.min(0.05, Math.max(0, (now - last) / 1000));
          last = now;
          const t = now / 1000;
          const eng = engineRef.current;
          const px = eng.pointer.x;
          const py = eng.pointer.y;

          if (now >= eng.nextGazeAt) {
            eng.gaze.tx = (Math.random() * 2 - 1) * 2.6;
            eng.gaze.ty = (Math.random() * 2 - 1) * 1.7;
            eng.nextGazeAt = now + 900 + Math.random() * 1600;
          }
          const gazeEase = 1 - Math.exp(-dt * 18);
          eng.gaze.x += (eng.gaze.tx - eng.gaze.x) * gazeEase;
          eng.gaze.y += (eng.gaze.ty - eng.gaze.y) * gazeEase;

          if (now >= eng.nextBlinkAt) {
            eng.eyes.forEach((eye) => { eye.lidTarget = 1; });
            later(() => {
              eng.eyes.forEach((eye) => { eye.lidTarget = 0; });
            }, 80);
            eng.nextBlinkAt = now + 2300 + Math.random() * 2700;
          }

          if (eng.mood === 'wink') {
            if (!eng.nextWinkAt) eng.nextWinkAt = now + 220;
            if (now >= eng.nextWinkAt) {
              eng.eyes[1].lidTarget = 1;
              later(() => { eng.eyes[1].lidTarget = 0; }, 240);
              eng.nextWinkAt = now + 2300 + Math.random() * 900;
            }
          } else {
            eng.nextWinkAt = 0;
            if (eng.eyes[1].lidTarget === 1) eng.eyes[1].lidTarget = 0;
          }

          const faceTarget = {
            x: eng.target.lean + px * 3.4 + Math.sin(t * 0.55) * 0.9,
            rot: eng.target.tilt + py * 3.2 + Math.sin(t * 0.55 + 0.6) * 0.7,
            turn: eng.target.turn + px * 9 + Math.sin(t * 0.55 + 1.1) * 1.8
          };
          spring(eng.face.cur, eng.face.vel, faceTarget, dt, 120, 15);

          for (let i = 0; i < 2; i += 1) {
            const eye = eng.eyes[i];
            const target = eng.target.eyes[i];
            const eyeTarget = {
              x: target.x + eng.gaze.x + px * 3.8,
              y: target.y + eng.gaze.y + py * 2.6,
              rot: target.rot,
              sx: target.sx,
              sy: target.sy
            };
            spring(eye.cur, eye.vel, eyeTarget, dt, 170, 18);
            eye.lid += (eye.lidTarget - eye.lid) * (1 - Math.exp(-dt * 28));
            if (Math.abs(eye.lidTarget - eye.lid) < 0.001) eye.lid = eye.lidTarget;
            const sy = eye.cur.sy * (1 - 0.94 * eye.lid);
            const sx = eye.cur.sx * (1 + (1 - sy) * 0.1);
            eyeEls[i].style.transform = `translate3d(${eye.cur.x.toFixed(2)}px, ${eye.cur.y.toFixed(2)}px, 0) rotate(${eye.cur.rot.toFixed(2)}deg) scale(${sx.toFixed(3)}, ${sy.toFixed(3)})`;
          }

          face.style.transform = `translate3d(${eng.face.cur.x.toFixed(2)}px, ${(Math.sin(t * 1.15) * 0.5).toFixed(2)}px, 0) rotate(${eng.face.cur.rot.toFixed(2)}deg) rotateY(${eng.face.cur.turn.toFixed(2)}deg)`;
          raf = window.requestAnimationFrame(loop);
        };

        raf = window.requestAnimationFrame(loop);
        return () => {
          window.cancelAnimationFrame(raf);
          window.removeEventListener('pointermove', onPointerMove);
          timeouts.forEach((id) => window.clearTimeout(id));
          timeouts.clear();
        };
      }, []);

      const mark = GLYPHS[expression];
      return h('span', {
        className: 'dme-face-wrap' + (large ? ' dme-face-wrap-large' : ''),
        'aria-hidden': true,
        style: { '--dme-glow': data.color }
      },
        h('span', { className: 'dme-face', ref: faceRef },
          h('span', { className: 'dme-eye', ref: leftRef }),
          h('span', { className: 'dme-eye', ref: rightRef }),
          h('span', {
            className: 'dme-glasses' + (expression === 'focus' ? ' is-on' : '')
          },
            h('i', { className: 'dme-lens' }),
            h('i', { className: 'dme-lens' }),
            h('i', { className: 'dme-bridge' })
          ),
          mark ? h('span', { className: 'dme-glyph' }, mark) : null
        )
      );
    }

    const selectAll = (value) => value;

    function MoodBridge({ useProjection, useSessionStatus, sessionId }) {
      const projected = useProjection('dshMoodModel');
      const mood = projected && TARGETS[projected.mood] ? projected.mood : 'neutral';
      const projectedPhase = projected && typeof projected.phase === 'string' ? projected.phase : 'idle';
      const statuses = useSessionStatus(selectAll);
      const live = statuses && typeof statuses.get === 'function' && sessionId !== undefined
        ? statuses.get(sessionId)
        : undefined;
      const phase = live && live.pendingInteraction != null
        ? 'waiting'
        : live && live.running === true && projectedPhase === 'idle'
          ? 'thinking'
          : projectedPhase;
      const status = STATUS_PHASES.has(phase) ? phase : 'idle';

      React.useEffect(() => {
        moodStore.set({ mood, status, active: true });
      }, [mood, status]);

      React.useEffect(() => () => {
        moodStore.set({ mood: 'neutral', status: 'idle', active: false });
      }, []);

      return null;
    }

    function isPeakNow(date = new Date()) {
      const day = date.getUTCDay();
      if (day === 0 || day === 6) return false;
      const hour = date.getUTCHours();
      return (hour >= 1 && hour < 4) || (hour >= 6 && hour < 10);
    }

    function formatMoney(value, currency, mode = 'balance') {
      const number = Number(value);
      if (!Number.isFinite(number)) return '—';
      const symbol = currency === 'CNY' ? '￥' : currency === 'USD' ? '$' : currency ? `${currency} ` : '';
      if (mode === 'spend' && Math.abs(number) > 0 && Math.abs(number) < 0.01) {
        return `${symbol}${number.toFixed(3)}`;
      }
      return `${symbol}${number.toFixed(2)}`;
    }

    const POSITION_KEY = 'dsh-mood-eyes-position-v2';

    function readSavedPosition() {
      try {
        const raw = window.localStorage.getItem(POSITION_KEY);
        if (!raw) return null;
        const value = JSON.parse(raw);
        if (value && Number.isFinite(value.x) && Number.isFinite(value.y)) {
          return { x: value.x, y: value.y };
        }
      } catch {}
      return null;
    }

    function savePosition(position) {
      try {
        if (position) window.localStorage.setItem(POSITION_KEY, JSON.stringify(position));
        else window.localStorage.removeItem(POSITION_KEY);
      } catch {}
    }

    function clampPosition(position, overlay) {
      const width = overlay ? overlay.offsetWidth : 216;
      const height = overlay ? overlay.offsetHeight : 132;
      const maxX = Math.max(8, window.innerWidth - width - 8);
      const maxY = Math.max(8, window.innerHeight - height - 8);
      return {
        x: Math.max(8, Math.min(position.x, maxX)),
        y: Math.max(8, Math.min(position.y, maxY))
      };
    }

    function MoodOverlayCard() {
      const moodState = useStore(moodStore);
      const zh = DICT.zh;
      const overlayRef = React.useRef(null);
      const dragRef = React.useRef(null);
      const [position, setPosition] = React.useState(readSavedPosition);
      const bank = LINES_ZH;
      const [line, setLine] = React.useState('');
      const lineRef = React.useRef('');
      const [usage, setUsage] = React.useState(null);
      const [balanceState, setBalanceState] = React.useState(null);
      const modelMood = TARGETS[moodState.mood] ? moodState.mood : 'neutral';
      const workStatus = STATUS_PHASES.has(moodState.status) ? moodState.status : 'idle';
      const statusMeta = STATUS[workStatus] || STATUS.idle;
      const mood = statusMeta.mood || (modelMood === 'focus' ? 'neutral' : modelMood);
      const statusText = statusMeta.label;
      const statusColor = statusMeta.color;

      const showLine = (text) => {
        if (!text || text === lineRef.current) return;
        lineRef.current = text;
        setLine(text);
      };

      React.useEffect(() => {
        const pool = bank.moods[mood] || bank.moods.neutral;
        showLine(pickRandom(pool, lineRef.current));
      }, [mood, bank]);

      React.useEffect(() => {
        if (!line) return undefined;
        const delay = 18000 + Math.random() * 22000;
        const timer = window.setTimeout(() => {
          const pool = Math.random() < 0.35 ? timePool(bank) : bank.ambient;
          showLine(pickRandom(pool, lineRef.current));
        }, delay);
        return () => window.clearTimeout(timer);
      }, [line, bank]);

      React.useEffect(() => {
        let alive = true;
        const load = async () => {
          try {
            const response = await window.fetch('/api/mood-eyes/usage', {
              credentials: 'same-origin',
              headers: { accept: 'application/json' },
              cache: 'no-store'
            });
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const payload = await response.json();
            if (alive && payload && typeof payload === 'object') setUsage(payload);
          } catch (error) {
            if (alive) {
              setUsage((current) => current ?? {
                ok: false,
                error: String(error && error.message ? error.message : error)
              });
            }
          }
        };
        load();
        const timer = window.setInterval(load, 60000);
        return () => {
          alive = false;
          window.clearInterval(timer);
        };
      }, []);

      React.useEffect(() => {
        let alive = true;
        const load = async () => {
          try {
            const response = await window.fetch('/api/mood-eyes/balance', {
              credentials: 'same-origin',
              headers: { accept: 'application/json' },
              cache: 'no-store'
            });
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const payload = await response.json();
            if (alive && payload && typeof payload === 'object') setBalanceState(payload);
          } catch (error) {
            if (alive) {
              setBalanceState((current) => current ?? {
                ok: false,
                error: String(error && error.message ? error.message : error)
              });
            }
          }
        };
        load();
        const timer = window.setInterval(load, 60000);
        return () => {
          alive = false;
          window.clearInterval(timer);
        };
      }, []);

      React.useEffect(() => {
        setPosition((current) => current ? clampPosition(current, overlayRef.current) : current);
        const onResize = () => setPosition((current) => current ? clampPosition(current, overlayRef.current) : current);
        window.addEventListener('resize', onResize);
        return () => window.removeEventListener('resize', onResize);
      }, []);

      const onPointerDown = (event) => {
        if (event.pointerType === 'mouse' && event.button !== 0) return;
        const overlay = overlayRef.current;
        if (!overlay) return;
        event.preventDefault();
        event.currentTarget.setPointerCapture?.(event.pointerId);
        dragRef.current = {
          pointerId: event.pointerId,
          startX: event.clientX,
          startY: event.clientY,
          startLeft: overlay.offsetLeft,
          startTop: overlay.offsetTop,
          width: overlay.offsetWidth,
          height: overlay.offsetHeight,
          last: { x: overlay.offsetLeft, y: overlay.offsetTop }
        };
        setPosition({ x: overlay.offsetLeft, y: overlay.offsetTop });
      };

      const onPointerMove = (event) => {
        const drag = dragRef.current;
        if (!drag || drag.pointerId !== event.pointerId) return;
        const maxX = Math.max(8, window.innerWidth - drag.width - 8);
        const maxY = Math.max(8, window.innerHeight - drag.height - 8);
        const next = {
          x: Math.max(8, Math.min(maxX, drag.startLeft + event.clientX - drag.startX)),
          y: Math.max(8, Math.min(maxY, drag.startTop + event.clientY - drag.startY))
        };
        drag.last = next;
        setPosition(next);
      };

      const finishDrag = (event) => {
        const drag = dragRef.current;
        if (!drag) return;
        try {
          event.currentTarget.releasePointerCapture?.(event.pointerId);
        } catch {}
        dragRef.current = null;
        savePosition(drag.last);
      };

      const resetPosition = (event) => {
        event.preventDefault();
        dragRef.current = null;
        setPosition(null);
        savePosition(null);
      };

      const data = TARGETS[mood];
      const label = zh.mood[mood] || zh.mood.neutral;
      const tooltip = zh.tooltip.replace('{mood}', label);
      const peakNow = isPeakNow();
      const balance = balanceState && balanceState.ok === true
        ? balanceState
        : usage && usage.balance && usage.balance.ok === true ? usage.balance : null;
      const today = usage && usage.today ? usage.today : null;
      const balanceValue = balance ? formatMoney(balance.total, balance.currency) : '—';
      const todayValue = today && Number.isFinite(Number(today.costCny))
        ? formatMoney(today.costCny, 'CNY', 'spend')
        : today && Number.isFinite(Number(today.costUsd))
          ? formatMoney(today.costUsd, 'USD', 'spend')
          : '—';
      const balanceHint = balance
        ? ''
        : balanceState && balanceState.error
          ? String(balanceState.error)
          : usage && usage.balance && usage.balance.error ? String(usage.balance.error) : '余额不可用';
      const todayHint = today ? '' : usage && usage.error ? String(usage.error) : '今日消耗不可用';
      const overlayStyle = position
        ? { left: position.x, top: position.y, bottom: 'auto' }
        : undefined;

      return h('div', {
        className: 'dme-overlay',
        ref: overlayRef,
        style: overlayStyle,
        'data-mood': mood,
        'data-status': workStatus,
        'data-active': String(moodState.active),
        role: 'status',
        'aria-live': 'polite',
        'aria-label': tooltip
      },
        h('style', null, CSS),
        h('div', {
          className: 'dme-card',
          style: { '--dme-glow': data.color, '--dme-status': statusColor }
        },
          statusMeta.code
            ? h('div', { className: 'dme-code-rain', 'aria-hidden': true },
                CODE_LINES.map((code, index) => h('span', { key: index, className: 'dme-code-line' }, code))
              )
            : null,
          h('div', {
            className: 'dme-card-head',
            title: zh.sidebar.drag,
            onPointerDown,
            onPointerMove,
            onPointerUp: finishDrag,
            onPointerCancel: finishDrag,
            onDoubleClick: resetPosition
          },
            h('span', { className: 'dme-card-head-left' },
              h('span', { className: 'dme-card-grip', 'aria-hidden': true }, '⠿'),
              h('span', { className: 'dme-card-title' }, zh.sidebar.title)
            ),
            h('span', { className: 'dme-card-live', 'data-status': workStatus },
              h('i', { className: 'dme-card-dot' }),
              statusText
            )
          ),
          h('div', { className: 'dme-card-eyes' },
            h(MoodFace, { mood, large: true }),
            statusMeta.magnifier
              ? h('span', { className: 'dme-magnifier', 'aria-hidden': true },
                  h('i', { className: 'dme-magnifier-lens' }),
                  h('i', { className: 'dme-magnifier-handle' })
                )
              : null,
            statusMeta.dots
              ? h('span', { className: 'dme-think-dots', 'aria-hidden': true },
                  h('i'), h('i'), h('i')
                )
              : null,
            statusMeta.command
              ? h('span', { className: 'dme-command-glyph', 'aria-hidden': true }, '>_')
              : null,
            statusMeta.error
              ? h('span', { className: 'dme-error-glyph', 'aria-hidden': true }, '!')
              : null,
            statusMeta.wait
              ? h('span', { className: 'dme-wait-glyph', 'aria-hidden': true }, '◷')
              : null
          ),
          h('div', { className: 'dme-card-line' },
            line ? h('span', { key: line, className: 'dme-line-text' }, line) : null
          ),
          h('div', { className: 'dme-card-foot' },
            h('span', { className: 'dme-card-mood' }, label),
            h('span', { className: 'dme-card-caption' }, zh.sidebar.caption)
          ),
          h('div', { className: 'dme-card-usage' },
            h('span', { className: 'dme-usage-item' },
              h('span', { className: 'dme-usage-k' }, '峰谷'),
              h('span', { className: 'dme-usage-v ' + (peakNow ? 'is-peak' : 'is-offpeak') }, peakNow ? '峰时' : '谷时')
            ),
            h('span', { className: 'dme-usage-item', title: balanceHint },
              h('span', { className: 'dme-usage-k' }, '余额'),
              h('span', { className: 'dme-usage-v' }, balanceValue)
            ),
            h('span', { className: 'dme-usage-item', title: todayHint },
              h('span', { className: 'dme-usage-k' }, '今日'),
              h('span', { className: 'dme-usage-v' }, todayValue)
            )
          )
        )
      );
    }

    return {
      inject: ['slots', 'locale'],
      apply(ctx) {
        ctx.effect(() => ctx.locale.register(NS, DICT), 'dsh-mood-eyes-v3: locale');
        ctx.slots.inject('conversation.composer.dock', () => ctx.slots.register({
          name: 'conversation.composer.dock',
          id: 'dsh-mood-eyes-v3-bridge',
          order: 2,
          locale: NS
        }, MoodBridge));
        ctx.slots.inject('shell.overlay', () => ctx.slots.register({
          name: 'shell.overlay',
          id: 'dsh-mood-eyes-v3-card',
          order: 20,
          locale: NS
        }, MoodOverlayCard));
      }
    };
  }
});
