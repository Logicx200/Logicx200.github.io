window.__ModuleLoader__.load({
  id: '@local/dsh-mood-eyes',
  factory(require) {
    const React = require('react');
    const h = React.createElement;
    const NS = 'dsh-mood-eyes';

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
        tooltip: 'DSH is feeling {mood}'
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
        tooltip: 'DSH 现在的心情：{mood}'
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
        nextGazeAt: 0,
        nextBlinkAt: 0,
        nextWinkAt: 0
      };
    }

    function MoodEyes({ useProjection, t }) {
      const projected = useProjection('dshMood');
      const mood = projected && TARGETS[projected.mood] ? projected.mood : 'neutral';
      const data = TARGETS[mood];
      const tr = typeof t === 'function' ? t : (key) => key;
      const label = tr(`mood.${mood}`);

      const engineRef = React.useRef(null);
      const faceRef = React.useRef(null);
      const leftRef = React.useRef(null);
      const rightRef = React.useRef(null);

      if (engineRef.current === null) engineRef.current = createEngine(mood);

      React.useEffect(() => {
        const engine = engineRef.current;
        engine.mood = mood;
        engine.target = cloneTarget(TARGETS[mood]);
        engine.nextWinkAt = 0;
        if (mood !== 'wink') engine.eyes[1].lidTarget = 0;
      }, [mood]);

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

        const loop = (now) => {
          const dt = Math.min(0.05, Math.max(0, (now - last) / 1000));
          last = now;
          const t = now / 1000;
          const eng = engineRef.current;

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
            x: eng.target.lean + Math.sin(t * 0.55) * 0.9,
            rot: eng.target.tilt + Math.sin(t * 0.55 + 0.6) * 0.7,
            turn: eng.target.turn + Math.sin(t * 0.55 + 1.1) * 1.8
          };
          spring(eng.face.cur, eng.face.vel, faceTarget, dt, 120, 15);

          for (let i = 0; i < 2; i += 1) {
            const eye = eng.eyes[i];
            const target = eng.target.eyes[i];
            const eyeTarget = {
              x: target.x + eng.gaze.x,
              y: target.y + eng.gaze.y,
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
          timeouts.forEach((id) => window.clearTimeout(id));
          timeouts.clear();
        };
      }, []);

      const mark = GLYPHS[mood];
      return h('div', {
        className: 'dme-root',
        'data-mood': mood,
        role: 'status',
        'aria-live': 'polite',
        'aria-label': tr('tooltip', { mood: label }),
        title: tr('tooltip', { mood: label }),
        style: { '--dme-glow': data.color }
      },
        h('style', null, CSS),
        h('span', { className: 'dme-dot', 'aria-hidden': true }),
        h('span', { className: 'dme-face-wrap', 'aria-hidden': true },
          h('span', { className: 'dme-face', ref: faceRef },
            h('span', { className: 'dme-eye', ref: leftRef }),
            h('span', { className: 'dme-eye', ref: rightRef }),
            h('span', {
              className: 'dme-glasses' + (mood === 'focus' ? ' is-on' : '')
            },
              h('i', { className: 'dme-lens' }),
              h('i', { className: 'dme-lens' }),
              h('i', { className: 'dme-bridge' })
            ),
            mark ? h('span', { className: 'dme-glyph' }, mark) : null
          )
        ),
        h('span', { className: 'dme-label' },
          h('span', { className: 'dme-brand' }, 'DSH'),
          h('span', { className: 'dme-sep' }, '·'),
          h('span', { className: 'dme-mood' }, label)
        )
      );
    }

    return {
      inject: ['slots', 'locale'],
      apply(ctx) {
        ctx.effect(() => ctx.locale.register(NS, DICT), 'dsh-mood-eyes: locale');
        ctx.slots.inject('conversation.composer.dock', () => ctx.slots.register({
          name: 'conversation.composer.dock',
          id: 'dsh-mood-eyes',
          order: 2,
          locale: NS
        }, MoodEyes));
      }
    };
  }
});
