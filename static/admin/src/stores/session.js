import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import { api } from '../api.js';

// 显示层滑动窗口：transcript 只保留最近 MAX_TURNS 轮，防长对话拖坏 DOM。
// 仅影响前端展示，不影响后端 LLM context。
export const MAX_TURNS = 50;

/**
 * 把 turns 数组裁剪到 <= max（从头部丢弃最旧的，原地 splice）。
 * 返回被丢弃的条数；当 length <= max 时返回 0 且数组不变。
 * 纯函数（接收数组、返回丢弃数），不依赖 Pinia/Vue 运行时，便于单测。
 * @param {Array} arr
 * @param {number} max
 * @returns {number} dropped count
 */
export function trimTurns(arr, max = MAX_TURNS) {
  if (arr.length <= max) return 0;
  const drop = arr.length - max;
  arr.splice(0, drop);
  return drop;
}

export const useSession = defineStore('session', () => {
  /** [{role: 'user'|'bot', text, partial?: bool, t?: number}] — Talk transcript */
  const turns = ref([]);
  /** All EventBroadcaster events for the active call (Talk debug drawer + Monitor). */
  const events = ref([]);
  /** /api/config snapshot fetched at startup. */
  const config = ref(null);
  /** 'idle' | 'connecting' | 'recording' | 'ended' */
  const status = ref('idle');
  /** Optional error toast text (last failure). */
  const lastError = ref('');

  const defaultsLine = computed(() => {
    if (!config.value) return '';
    const demo = config.value.default_demo || config.value.default_scenario;
    return `${config.value.default_engine} · ${config.value.default_language} · ${demo}`;
  });

  async function loadConfig() {
    if (config.value) return config.value;
    config.value = await api.config();
    return config.value;
  }

  /**
   * Append (or merge into) a transcript bubble.
   * `partial` text from the same role is replaced; finals push a new bubble.
   */
  function pushTurn({ role, text, partial = false }) {
    const last = turns.value[turns.value.length - 1];
    if (partial && last && last.role === role && last.partial) {
      last.text = text;
      return;
    }
    if (!partial && last && last.role === role && last.partial) {
      last.text = text;
      last.partial = false;
      return;
    }
    // New bubble: stamp arrival time + apply the display-layer sliding window.
    // Only this push branch grows the array, so trimming lives here (the
    // partial-merge branches above mutate the last bubble in place and return
    // early without trimming).
    turns.value.push({ role, text, partial, t: Date.now() });
    trimTurns(turns.value);
  }

  function appendEvent(evt) {
    events.value.push({ ...evt, _ts: Date.now() });
    if (events.value.length > 1000) events.value.splice(0, events.value.length - 1000);
  }

  function reset() {
    turns.value = [];
    events.value = [];
    status.value = 'idle';
    lastError.value = '';
  }

  return {
    turns,
    events,
    config,
    status,
    lastError,
    defaultsLine,
    loadConfig,
    pushTurn,
    appendEvent,
    reset,
  };
});
