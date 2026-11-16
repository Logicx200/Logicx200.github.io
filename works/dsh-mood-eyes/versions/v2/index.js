/**
 * Host half of DSH Mood Eyes (Model).
 *
 * The model calls `set_mood`; the durable `tool/call` event is the single source
 * of truth for the session projection read by the Client widget. No keyword
 * heuristic is involved.
 */

const MOOD_NAMES = [
  'neutral', 'happy', 'curious', 'focus', 'surprised', 'sad', 'sleepy',
  'angry', 'wink', 'love', 'confused', 'excited', 'dizzy'
];
const MOOD_SET = new Set(MOOD_NAMES);

const passthroughSchema = {
  parse: (value) => value,
  safeParse: (value) => ({ success: true, data: value })
};

const projection = {
  key: 'dshMoodModel',
  stateVersion: 1,
  stateSchema: passthroughSchema,
  init: () => ({ mood: 'neutral', seq: -1 }),
  apply(state, event) {
    if (event.type !== 'tool/call' || event.data.name !== 'set_mood') return state;
    let args;
    try {
      args = JSON.parse(event.data.arguments);
    } catch {
      return state;
    }
    if (!args || !MOOD_SET.has(args.mood) || args.mood === state.mood) return state;
    return { ...state, mood: args.mood, seq: event.seq };
  },
  wire: {
    viewSchema: passthroughSchema,
    view: (state) => ({ mood: state.mood, seq: state.seq })
  }
};

const setMoodTool = {
  name: 'set_mood',
  description: 'Set the mood shown by the DSH Mood Eyes widget under the composer. Call this on your own whenever your emotional stance toward the current conversation changes; do not ask the user for a mood. Use neutral when there is no strong feeling.',
  parameters: {
    type: 'object',
    properties: {
      mood: {
        type: 'string',
        enum: MOOD_NAMES,
        description: 'Your current mood: neutral, happy, curious, focus, surprised, sad, sleepy, angry, wink, love, confused, excited, or dizzy.'
      }
    },
    required: ['mood'],
    additionalProperties: false
  },
  output: {
    schema: {
      type: 'object',
      properties: {
        ok: { type: 'boolean' },
        mood: { type: 'string' }
      },
      required: ['ok', 'mood'],
      additionalProperties: false
    },
    render: (args, value) => [{
      type: 'text',
      text: `Mood set to ${value && typeof value.mood === 'string' ? value.mood : 'neutral'}.`
    }]
  },
  async execute(args) {
    const mood = args && args.mood;
    if (!MOOD_SET.has(mood)) throw new Error(`Unknown mood: ${String(mood)}`);
    return { ok: true, mood };
  }
};

export const inject = ['sessionProjections', 'tools', 'systemPrompt'];

export function apply(ctx) {
  ctx.effect(
    () => ctx.sessionProjections.register(projection),
    'dsh-mood-eyes-v2: mood projection'
  );
  ctx.effect(
    () => ctx.tools.register(setMoodTool),
    'dsh-mood-eyes-v2: set_mood tool'
  );
  ctx.effect(
    () => ctx.systemPrompt.section({
      name: 'dsh-mood-eyes-v2',
      order: 900,
      text: '你有一个 `set_mood` 工具，用来设置输入框下方的「DSH 心情之眼」表情。请根据当前对话的整体语气和你此刻自己的状态，在心情发生变化时主动调用它；没有变化时不必重复调用。不要向用户解释这次工具调用。可用心情：neutral、happy、curious、focus、surprised、sad、sleepy、angry、wink、love、confused、excited、dizzy。'
    }),
    'dsh-mood-eyes-v2: prompt section'
  );
}
