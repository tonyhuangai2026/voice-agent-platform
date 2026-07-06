<template>
  <div class="asr-test-root">
    <!-- Controls + explanatory note -->
    <div class="asr-head">
      <div class="asr-controls">
        <button
          class="asr-btn"
          :class="{ recording }"
          :disabled="connecting"
          data-test="asr-toggle"
          @click="onToggle"
        >
          <n-icon :size="20" :component="recording ? StopIcon : MicIcon" />
          <span>{{ recording ? 'Stop' : connecting ? 'Connecting…' : 'Start' }}</span>
        </button>

        <!-- Optional: stream B identify-multiple vs identify-language mode. -->
        <div class="asr-mode">
          <n-text depth="2" class="asr-mode-label">B mode</n-text>
          <n-switch
            v-model:value="bMultiple"
            :disabled="recording || connecting"
            size="small"
          >
            <template #checked>multiple</template>
            <template #unchecked>single</template>
          </n-switch>
        </div>

        <!-- Stream B partial-results-stability: lower = faster partials, more
             rewrites. A always stays at stock "high"; this tunes only B. -->
        <div class="asr-mode">
          <n-text depth="2" class="asr-mode-label">B 稳定度</n-text>
          <n-select
            v-model:value="bStability"
            :options="ASR_STABILITY_OPTIONS"
            :disabled="recording || connecting"
            size="small"
            style="width: 168px"
            data-test="asr-stability"
          />
        </div>

        <span class="asr-status" :class="`asr-status--${statusTone}`" data-test="asr-status">
          {{ statusText }}
        </span>
      </div>

      <n-text depth="3" class="asr-note" data-test="asr-note">
        测试工具:同一段语音同时跑两路 Transcribe 对比粤英混说识别。仅测 STT,不影响正式通话。
      </n-text>
    </div>

    <!-- Two side-by-side transcript panes, one per Transcribe stream. -->
    <div class="asr-panes">
      <section
        v-for="s in ASR_STREAMS"
        :key="s"
        class="asr-pane"
        :data-test="`asr-pane-${s}`"
      >
        <header class="asr-pane-head">{{ paneTitle[s] }}</header>
        <div class="asr-pane-body">
          <div
            v-for="(line, i) in panes[s].lines"
            :key="i"
            class="asr-line"
            :class="{
              interim: line.kind === 'interim',
              final: line.kind === 'final',
              error: line.kind === 'error',
            }"
          >
            <span v-if="line.kind === 'error'" class="asr-line-tag">error</span>
            <span v-else-if="line.lang" class="asr-line-tag">{{ line.lang }}</span>
            {{ line.kind === 'error' ? line.error : line.text }}
          </div>
          <!-- Live interim line for this stream (greyed, not yet finalized). -->
          <div
            v-if="panes[s].interim"
            class="asr-line interim live"
            :data-test="`asr-interim-${s}`"
          >
            <span v-if="panes[s].interim.lang" class="asr-line-tag">{{ panes[s].interim.lang }}</span>
            {{ panes[s].interim.text }}
          </div>
          <div v-if="!panes[s].lines.length && !panes[s].interim" class="asr-empty">
            <n-text depth="3">—</n-text>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref, computed, onBeforeUnmount } from 'vue';
import { NText, NIcon, NSwitch, NSelect, useMessage } from 'naive-ui';
import { Microphone as MicIcon, StopFilledAlt as StopIcon } from '@vicons/carbon';

import { Recorder } from '../audio.js';
import { openAsrTestWs } from '../ws.js';
import {
  ASR_STREAMS,
  ASR_B_MODE_DEFAULT,
  ASR_B_STABILITY_DEFAULT,
  ASR_STABILITY_OPTIONS,
  routeAsrMessage,
} from '../asrTest.js';

const message = useMessage();

// Pane titles per the AC. A = single zh-HK, B = multi zh-HK+en-US.
const paneTitle = {
  A: 'A · 单语言 zh-HK',
  B: 'B · 多语言 zh-HK+en-US',
};

// One state object per stream: an array of finalized/error `lines` plus a single
// transient `interim` line (replaced as partials arrive, promoted to a final
// line on is_final). Reactive so the template re-renders on every message.
const panes = reactive({
  A: { lines: [], interim: null },
  B: { lines: [], interim: null },
});

const recording = ref(false);
const connecting = ref(false);
// Stream B multi-language toggle → &mode=multiple|single on the WS (optional).
const bMultiple = ref(ASR_B_MODE_DEFAULT === 'multiple');
// Stream B partial-results-stability → &stability=low|medium|high on the WS.
const bStability = ref(ASR_B_STABILITY_DEFAULT);

const statusTone = computed(() =>
  recording.value ? 'recording' : connecting.value ? 'connecting' : 'idle',
);
const statusText = computed(() =>
  recording.value ? 'recording' : connecting.value ? 'connecting' : 'ready',
);

let ws = null;
let recorder = null;

// Apply one routed message to its pane. Exposed for the vitest (it injects a
// fake message and asserts it lands in the right pane and NOT the other).
function applyMessage(raw) {
  const r = routeAsrMessage(raw);
  if (!r) return;
  const pane = panes[r.stream];
  if (!pane) return;
  if (r.kind === 'error') {
    pane.interim = null;
    pane.lines.push({ kind: 'error', error: r.error });
  } else if (r.kind === 'final') {
    pane.interim = null;
    pane.lines.push({ kind: 'final', text: r.text, lang: r.lang });
  } else {
    pane.interim = { kind: 'interim', text: r.text, lang: r.lang };
  }
}
// Expose to tests via the component instance.
defineExpose({ applyMessage, panes });

function resetPanes() {
  panes.A.lines = [];
  panes.A.interim = null;
  panes.B.lines = [];
  panes.B.interim = null;
}

async function onToggle() {
  if (recording.value) {
    cleanup();
    return;
  }
  if (connecting.value) return;
  await start();
}

async function start() {
  resetPanes();
  connecting.value = true;
  try {
    // mode + stability are only meaningful for stream B; backend ignores them for A.
    const params = {
      mode: bMultiple.value ? 'multiple' : 'single',
      stability: bStability.value,
    };
    ws = await openAsrTestWs(params);
    ws.onopen = async () => {
      try {
        recorder = new Recorder();
        // Mirror TalkView's recorder callback: forward PCM frames while the WS
        // is open. STT-only — no PTT gating, no playback.
        await recorder.start((pcmBuf) => {
          if (ws && ws.readyState === 1) ws.send(pcmBuf);
        });
        connecting.value = false;
        recording.value = true;
      } catch (e) {
        message.error(`麦克风启动失败:${e.message}`);
        cleanup();
      }
    };
    ws.onmessage = (e) => {
      if (typeof e.data !== 'string') return; // ASR test sends JSON text only
      try {
        applyMessage(JSON.parse(e.data));
      } catch {
        /* ignore malformed frame */
      }
    };
    ws.onclose = () => {
      cleanup();
    };
    ws.onerror = () => {
      message.error('ASR 测试连接出错');
      cleanup();
    };
  } catch (e) {
    message.error(`启动失败:${e.message}`);
    cleanup();
  }
}

function cleanup() {
  connecting.value = false;
  recording.value = false;
  if (recorder) {
    recorder.stop();
    recorder = null;
  }
  if (ws) {
    try {
      if (ws.readyState <= 1) ws.close();
    } catch {
      /* ignore */
    }
    ws = null;
  }
}

onBeforeUnmount(cleanup);
</script>

<style scoped>
.asr-test-root {
  display: flex;
  flex-direction: column;
  gap: var(--vb-space-lg);
  height: 100%;
  min-height: 0;
}

.asr-head {
  display: flex;
  flex-direction: column;
  gap: var(--vb-space-sm);
}

.asr-controls {
  display: flex;
  align-items: center;
  gap: var(--vb-space-md);
  flex-wrap: wrap;
}

.asr-btn {
  display: inline-flex;
  align-items: center;
  gap: var(--vb-space-sm);
  padding: 8px 18px;
  border-radius: var(--vb-radius-lg);
  border: 1px solid var(--vb-border);
  background: var(--vb-surface);
  color: var(--vb-primary);
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s, color 0.15s, border-color 0.15s;
}

.asr-btn.recording {
  background: var(--vb-error);
  color: var(--vb-on-primary, #fff);
  border-color: var(--vb-error);
}

.asr-btn:disabled {
  opacity: 0.6;
  cursor: wait;
}

.asr-mode {
  display: inline-flex;
  align-items: center;
  gap: var(--vb-space-xs);
}

.asr-mode-label {
  font-size: 12px;
}

.asr-status {
  font-size: 13px;
  color: var(--vb-text-tertiary);
}

.asr-status--recording {
  color: var(--vb-error);
}

.asr-status--connecting {
  color: var(--vb-warning);
}

.asr-note {
  font-size: 12px;
  line-height: 1.5;
}

.asr-panes {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--vb-space-md);
}

.asr-pane {
  display: flex;
  flex-direction: column;
  min-height: 0;
  border: 1px solid var(--vb-border);
  border-radius: var(--vb-radius-lg);
  background: var(--vb-surface);
  overflow: hidden;
}

.asr-pane-head {
  flex: none;
  padding: var(--vb-space-sm) var(--vb-space-md);
  border-bottom: 1px solid var(--vb-border);
  font-size: 13px;
  font-weight: 600;
  color: var(--vb-text-secondary);
  background: var(--vb-surface-alt);
}

.asr-pane-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: var(--vb-space-md);
  display: flex;
  flex-direction: column;
  gap: var(--vb-space-xs);
}

.asr-line {
  font-size: 14px;
  line-height: 1.5;
  word-break: break-word;
  white-space: pre-wrap;
}

.asr-line.final {
  color: var(--vb-text);
}

.asr-line.interim {
  color: var(--vb-text-tertiary);
}

.asr-line.error {
  color: var(--vb-error);
}

.asr-line-tag {
  display: inline-block;
  margin-right: 6px;
  padding: 0 5px;
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  border: 1px solid var(--vb-border);
  border-radius: var(--vb-radius-sm);
  color: var(--vb-text-tertiary);
  vertical-align: 1px;
}

.asr-empty {
  text-align: center;
  padding: var(--vb-space-lg) 0;
}

@media (max-width: 767px) {
  .asr-panes {
    grid-template-columns: 1fr;
  }
}
</style>
