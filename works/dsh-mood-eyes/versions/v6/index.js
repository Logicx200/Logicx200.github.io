/**
 * Host half of DSH Mood Eyes (Activity).
 *
 * `set_mood` provides the model's self-reported mood; standard session events
 * provide the live activity phase (thinking, research, command, read, write,
 * waiting, error, idle). Both are folded into one durable projection.
 */

const MOOD_NAMES = [
  'neutral', 'happy', 'curious', 'focus', 'surprised', 'sad', 'sleepy',
  'angry', 'wink', 'love', 'confused', 'excited', 'dizzy'
];
const MOOD_SET = new Set(MOOD_NAMES);

const RESEARCH_TOOLS = new Set(['web_search', 'web_fetch', 'cordis_inspect_list', 'cordis_inspect_query']);
const COMMAND_TOOLS = new Set(['pwsh', 'bash']);
const READING_TOOLS = new Set(['read', 'grep', 'glob', 'read_image', 'job_output', 'job_list']);
const WRITING_TOOLS = new Set(['write', 'edit']);

const passthroughSchema = {
  parse: (value) => value,
  safeParse: (value) => ({ success: true, data: value })
};

function toolPhase(name) {
  if (RESEARCH_TOOLS.has(name)) return 'research';
  if (COMMAND_TOOLS.has(name)) return 'command';
  if (READING_TOOLS.has(name)) return 'reading';
  if (WRITING_TOOLS.has(name)) return 'writing';
  return 'working';
}

function withPhase(state, phase, seq) {
  return state.phase === phase ? state : { ...state, phase, seq };
}

const projection = {
  key: 'dshMoodModel',
  stateVersion: 3,
  stateSchema: passthroughSchema,
  init: () => ({ mood: 'neutral', seq: -1, phase: 'idle' }),
  apply(state, event) {
    if (event.type === 'tool/call' && event.data.name === 'set_mood') {
      let args;
      try {
        args = JSON.parse(event.data.arguments);
      } catch {
        return state;
      }
      if (!args || !MOOD_SET.has(args.mood) || args.mood === state.mood) return state;
      return { ...state, mood: args.mood, seq: event.seq };
    }

    switch (event.type) {
      case 'turn/start':
      case 'step/start':
      case 'assistant/attempt':
      case 'assistant/message':
        return withPhase(state, 'thinking', event.seq);
      case 'tool/call':
        return withPhase(state, toolPhase(event.data.name), event.seq);
      case 'tool/result':
        return state.phase === 'error' ? state : withPhase(state, 'thinking', event.seq);
      case 'turn/end': {
        const kind = event.data && event.data.reason && event.data.reason.kind;
        return withPhase(state, kind === 'error' ? 'error' : 'idle', event.seq);
      }
      case 'user/message':
        return state.phase === 'error' ? withPhase(state, 'thinking', event.seq) : state;
      default:
        return state;
    }
  },
  wire: {
    viewSchema: passthroughSchema,
    view: (state) => ({ mood: state.mood, seq: state.seq, phase: state.phase })
  }
};

const setMoodTool = {
  name: 'set_mood',
  description: 'Set the mood shown by the DSH Mood Eyes widget. Call this on your own whenever your emotional stance toward the current conversation changes; do not ask the user for a mood. Use neutral when there is no strong feeling.',
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
    'dsh-mood-eyes-v6: activity projection'
  );
  ctx.effect(
    () => ctx.tools.register(setMoodTool),
    'dsh-mood-eyes-v6: set_mood tool'
  );
  ctx.effect(
    () => ctx.systemPrompt.section({
      name: 'dsh-mood-eyes-v6',
      order: 900,
      text: '你有一个 `set_mood` 工具，用来设置「DSH 心情之眼」的表情。请根据当前对话的整体语气和你此刻自己的状态，在心情发生变化时主动调用它；没有变化时不必重复调用。不要向用户解释这次工具调用。可用心情：neutral、happy、curious、focus、surprised、sad、sleepy、angry、wink、love、confused、excited、dizzy。'
    }),
    'dsh-mood-eyes-v6: prompt section'
  );
}
