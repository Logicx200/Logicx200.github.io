/**
 * Host half of DSH Mood Eyes.
 *
 * Registers a session projection that classifies the latest user/assistant text
 * into one of the eye expressions. The Client half reads the wire view through
 * `useProjection('dshMood')`.
 */

const MOOD_KEYWORDS = {
  angry: [
    '气死', '生气', '愤怒', '烦死', '太烦', '讨厌', '离谱', '什么鬼', '受够', '火大',
    'annoying', 'angry', 'furious', 'ridiculous', 'wtf', 'damn'
  ],
  sad: [
    '抱歉', '对不起', '失败', '错误', '遗憾', '可惜', '难过', '搞砸', '不行了',
    'sorry', 'failed', 'error', 'broken', 'unfortunately', 'sad'
  ],
  dizzy: [
    '晕', '循环', '递归', '绕圈', '转圈', '晕头', 'dizzy', 'loop', 'recursion', 'spin'
  ],
  sleepy: [
    '困', '想睡', '熬夜', '好累', '疲', '打盹', 'sleepy', 'tired', 'exhausted', 'zzz'
  ],
  love: [
    '爱', '喜欢', '心动', '可爱', '么么', '抱抱', 'love', 'cute', 'heart', '♥', '❤'
  ],
  surprised: [
    '竟然', '居然', '没想到', '哇', '惊讶', '突然', '天哪', 'wow', 'surprised', 'unexpected', 'amazing'
  ],
  confused: [
    '不明白', '搞不清', '困惑', '疑惑', '为什么', '怎么回事', 'confus', 'unclear', 'not sure', 'huh', 'what?', '？'
  ],
  excited: [
    '兴奋', '激动', '太棒了', '好耶', '冲', 'yay', 'woohoo', 'excited'
  ],
  wink: [
    '眨眼', '调皮', '嘿嘿', '嘿', 'wink', 'cheeky'
  ],
  curious: [
    '好奇', '看看', '研究', '探索', '试试', '想知', 'interesting', 'curious', 'explore', 'wonder'
  ],
  happy: [
    '完成', '成功', '好了', '搞定', '太棒', '不错', '很好', '可以了', '谢谢', '哈哈', '完美',
    'done', 'success', 'great', 'awesome', 'fixed', 'works', 'nice', 'happy'
  ],
  focus: [
    '实现', '检查', '安装', '运行', '调试', '分析', '处理', '修改', '写', '改', '代码', '文件',
    '构建', '验证', '配置', '插件', 'build', 'implement', 'check', 'fix', 'test', 'run',
    'debug', 'code', 'file', 'edit', 'write', 'compile', 'verify', 'plugin'
  ]
};

const USER_WEIGHTS = {
  angry: 2.4,
  sad: 2.2,
  dizzy: 1.4,
  sleepy: 1.4,
  love: 2.2,
  surprised: 1.6,
  confused: 2,
  curious: 1.2,
  happy: 1.2,
  excited: 1.6,
  wink: 1.6,
  focus: 0.6
};

const ASSISTANT_WEIGHTS = {
  angry: 1,
  sad: 1.2,
  dizzy: 1,
  sleepy: 1,
  love: 1.2,
  surprised: 1,
  confused: 1,
  curious: 1,
  happy: 1.4,
  excited: 1.3,
  wink: 1.1,
  focus: 1.4
};

const passthroughSchema = {
  parse: (value) => value,
  safeParse: (value) => ({ success: true, data: value })
};

function messageText(message) {
  const content = message && message.content;
  if (!Array.isArray(content)) return '';
  let text = '';
  for (const block of content) {
    if (block && block.type === 'text' && typeof block.text === 'string') {
      text += block.text + '\n';
    }
  }
  return text;
}

function classify(text, role) {
  if (typeof text !== 'string' || text.trim() === '') return null;
  const lower = text.toLowerCase();
  const weights = role === 'user' ? USER_WEIGHTS : ASSISTANT_WEIGHTS;
  let bestMood = null;
  let bestScore = 0;

  for (const [mood, words] of Object.entries(MOOD_KEYWORDS)) {
    let score = 0;
    for (const word of words) {
      if (!word) continue;
      const first = lower.indexOf(word);
      if (first < 0) continue;
      const count = lower.split(word).length - 1;
      score += Math.min(count, 3) * (weights[mood] || 1);
      // A hit at the very end is often the actual conclusion of a reply.
      if (first >= lower.length - word.length - 2) score += 0.35;
    }
    if (score > bestScore) {
      bestScore = score;
      bestMood = mood;
    }
  }

  return bestScore >= 1 ? bestMood : null;
}

const projection = {
  key: 'dshMood',
  stateVersion: 1,
  stateSchema: passthroughSchema,
  init: () => ({ mood: 'neutral', seq: -1 }),
  apply(state, event) {
    switch (event.type) {
      case 'turn/start': {
        if (state.mood === 'focus') return state;
        return { ...state, mood: 'focus', seq: event.seq };
      }
      case 'user/message': {
        const mood = classify(messageText(event.data), 'user');
        if (mood && mood !== state.mood) return { ...state, mood, seq: event.seq };
        return state;
      }
      case 'assistant/message': {
        const mood = classify(messageText(event.data.message), 'assistant');
        if (mood && mood !== state.mood) return { ...state, mood, seq: event.seq };
        return state;
      }
      case 'turn/end': {
        const kind = event.data && event.data.reason && event.data.reason.kind;
        if (kind === 'error') {
          return state.mood === 'sad' ? state : { ...state, mood: 'sad', seq: event.seq };
        }
        if (kind === 'max-tokens' || kind === 'interrupted') {
          return state.mood === 'surprised' ? state : { ...state, mood: 'surprised', seq: event.seq };
        }
        if (state.mood === 'focus') {
          return { ...state, mood: 'happy', seq: event.seq };
        }
        return state;
      }
      default:
        return state;
    }
  },
  wire: {
    viewSchema: passthroughSchema,
    view: (state) => ({ mood: state.mood, seq: state.seq })
  }
};

export const inject = ['sessionProjections'];

export function apply(ctx) {
  ctx.effect(
    () => ctx.sessionProjections.register(projection),
    'dsh-mood-eyes: conversation mood projection'
  );
}
