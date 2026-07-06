<template>
  <!-- Top-right action buttons teleported into App.vue's header. -->
  <Teleport to="#page-actions">
    <n-popover trigger="hover">
      <template #trigger>
        <n-button
          quaternary
          circle
          :disabled="turns.length === 0"
          :loading="summarizing"
          @click="summarize"
        >
          <template #icon>
            <n-icon :size="18" :component="SummaryIcon" />
          </template>
        </n-button>
      </template>
      {{ t('talk.actions.summarize') }}
    </n-popover>

    <n-popover trigger="hover">
      <template #trigger>
        <n-button quaternary circle :type="debugOpen ? 'primary' : undefined" @click="debugOpen = !debugOpen">
          <template #icon>
            <n-icon :size="18" :component="DebugIcon" />
          </template>
        </n-button>
      </template>
      {{ t('talk.actions.debug') }}
    </n-popover>
  </Teleport>

  <!-- Push-style side-by-side layout: .talk-main holds the original talk-root
       content (centered, max 760), and when debug is open .log-panel expands on
       the right and SQUEEZES .talk-main rather than overlaying it. On narrow
       screens (<1024px) .log-panel becomes an absolute overlay instead. -->
  <div class="talk-shell" :class="{ 'log-open': debugOpen }">
    <div class="talk-main">
    <!-- Status header -->
    <div class="status-row">
      <div class="status-left">
        <span class="status-dot" :class="`status-dot--${statusTone}`"></span>
        <n-text :depth="status === 'recording' ? 1 : 2" class="status-text">
          {{ statusText }}
        </n-text>
      </div>
      <div class="defaults-line">
        <div class="ptt-toggle">
          <n-switch v-model:value="pttEnabled" size="small" />
          <n-text depth="2" class="ptt-label">{{ t('talk.ptt.toggle') }}</n-text>
        </div>
        <!-- Idle/ended + config loaded → editable engine/lang/voice selectors.
             Connecting/recording → the read-only metaChips (reflecting the active
             `selection`). tech_design §3.3. -->
        <template v-if="(status === 'idle' || status === 'ended') && session.config">
          <!-- Engine: freely selectable (cross-filtered only by language). -->
          <n-select
            v-model:value="selection.engine"
            size="small"
            :options="engineOptions"
            :placeholder="t('talk.selectors.engine')"
            :aria-label="t('talk.selectors.engine')"
            class="sel sel-engine"
          />
          <!-- Language: cross-filtered by the chosen engine's capability. -->
          <n-select
            v-model:value="selection.lang"
            size="small"
            :options="langOptions"
            :placeholder="t('talk.selectors.language')"
            :aria-label="t('talk.selectors.language')"
            class="sel sel-lang"
          />
          <!-- Pipeline → Provider + Voice (the previously-missing 三段式音色). -->
          <template v-if="selection.engine === 'pipeline'">
            <n-select
              v-model:value="selection.provider"
              size="small"
              :options="providerOptions"
              :placeholder="t('talk.selectors.provider')"
              :aria-label="t('talk.selectors.provider')"
              class="sel sel-provider"
            />
            <n-select
              v-model:value="selection.voice"
              size="small"
              :options="pipelineVoiceOptions"
              :placeholder="t('talk.selectors.voice')"
              :aria-label="t('talk.selectors.voice')"
              class="sel sel-voice"
            />
            <n-select
              v-model:value="selection.model"
              size="small"
              clearable
              :options="modelOptions"
              :placeholder="t('talk.selectors.model')"
              :aria-label="t('talk.selectors.model')"
              class="sel sel-model"
            />
          </template>
          <!-- Nova Sonic → single Voice select; provider/model hidden. -->
          <n-select
            v-else-if="selection.engine === 'nova-sonic'"
            v-model:value="selection.novaVoice"
            size="small"
            :options="novaVoiceOptions"
            :placeholder="t('talk.selectors.voice')"
            :aria-label="t('talk.selectors.voice')"
            class="sel sel-voice"
          />
        </template>
        <template v-else-if="metaChips.length">
          <StatChip
            v-for="chip in metaChips"
            :key="chip.key"
            :tone="chip.tone"
            :dot="false"
          >
            <n-icon :size="13" :component="chip.icon" class="chip-icon" />
            {{ chip.value }}
          </StatChip>
        </template>
        <n-text v-else depth="3" style="font-size: 12px;">
          {{ t('common.loading') }}
        </n-text>
        <n-popover trigger="hover">
          <template #trigger>
            <n-icon :size="15" :component="InfoIcon" class="info-icon" />
          </template>
          <i18n-t keypath="talk.defaultsHint" tag="span">
            <template #adminLink>
              <a href="/admin/" target="_blank">{{ t('talk.defaultsHintAdminLabel') }}</a>
            </template>
          </i18n-t>
        </n-popover>
      </div>
    </div>

    <!-- Big circle button with live recording waveform ring -->
    <div class="circle-wrap">
      <div class="circle-stage">
        <!-- Waveform ring (Web Audio AnalyserNode → canvas), only while recording -->
        <canvas
          ref="waveCanvas"
          class="wave-canvas"
          :class="{ active: status === 'recording' }"
          width="280"
          height="280"
          aria-hidden="true"
        ></canvas>
        <button
          class="circle-btn"
          :class="{ recording: status === 'recording', connecting: status === 'connecting' }"
          :disabled="status === 'connecting'"
          @click="onCircleClick"
        >
          <n-icon class="circle-icon" :size="40" :component="status === 'recording' ? StopIcon : MicIcon" />
          <span class="circle-label">
            {{
              status === 'idle' || status === 'ended'
                ? t('talk.button.start')
                : status === 'connecting'
                  ? t('talk.button.connecting')
                  : t('talk.button.stop')
            }}
          </span>
        </button>
      </div>
    </div>

    <!-- Push-to-Talk hold button (only when PTT on + recording) -->
    <div v-if="pttEnabled && status === 'recording'" class="ptt-hold-wrap">
      <button
        class="ptt-hold-btn"
        :class="{ holding: pttHolding }"
        @pointerdown="startHold"
        @pointerup="endHold"
        @pointercancel="endHold"
        @pointerleave="endHold"
      >
        <n-icon :size="18" :component="MicIcon" />
        <span>{{ pttHolding ? t('talk.ptt.holding') : t('talk.ptt.holdToTalk') }}</span>
      </button>
      <n-text depth="3" class="ptt-hint">{{ t('talk.ptt.spaceHint') }}</n-text>
    </div>

    <!-- Transcript stream -->
    <div class="transcript-wrap">
      <n-scrollbar ref="scrollRef" style="max-height: 100%;">
        <div class="stream">
          <div
            v-for="(turn, i) in turns"
            :key="i"
            class="msg"
            :class="[turn.role, { partial: turn.partial }]"
          >
            <div class="msg-avatar" :class="turn.role">
              <n-icon :size="16" :component="turn.role === 'user' ? UserIcon : BotIcon" />
            </div>
            <div class="msg-body">
              <div class="msg-meta">
                <span class="msg-who">
                  {{ turn.role === 'user' ? t('talk.bubbles.whoUser') : t('talk.bubbles.whoBot') }}
                </span>
                <span v-if="turnClock(turn)" class="msg-ts">{{ turnClock(turn) }}</span>
                <span v-if="turn.partial" class="msg-state">{{ t('talk.bubbles.partial') }}</span>
              </div>
              <div class="msg-text">
                {{ turn.text }}<span v-if="turn.partial" class="caret">▍</span>
              </div>
            </div>
          </div>
          <div v-if="turns.length === 0" class="empty">
            <n-icon :size="40" :component="MicIcon" class="empty-icon" />
            <n-text depth="3">{{ t('talk.bubbles.empty') }}</n-text>
          </div>
        </div>
      </n-scrollbar>
    </div>
    </div>
    <!-- /.talk-main -->

    <!-- Right-side push-style debug log panel (replaces the old overlay
         n-drawer). DebugDrawer renders directly inside; close button sets
         debugOpen=false. The top-right header debug icon toggles debugOpen. -->
    <aside v-if="debugOpen" class="log-panel">
      <div class="log-panel-head">
        <n-text strong class="log-panel-title">{{ t('talk.drawerTitle') }}</n-text>
        <n-button
          quaternary
          circle
          size="small"
          :aria-label="t('talk.drawerClose')"
          @click="debugOpen = false"
        >
          <template #icon>
            <n-icon :size="16" :component="CloseIcon" />
          </template>
        </n-button>
      </div>
      <div class="log-panel-body">
        <DebugDrawer :events="events" />
      </div>
    </aside>
  </div>
  <!-- /.talk-shell -->

  <!-- Summary dialog -->
  <n-modal
    v-model:show="summaryOpen"
    preset="card"
    :title="t('talk.summary.title')"
    style="width: 720px;"
    :mask-closable="true"
  >
    <div v-if="summaryHtml" class="summary-md" v-html="summaryHtml" />
    <n-text v-else depth="3">{{ t('talk.summary.generating') }}</n-text>
  </n-modal>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue';
import {
  NText,
  NButton,
  NPopover,
  NScrollbar,
  NModal,
  NIcon,
  NSwitch,
  NSelect,
  useMessage,
} from 'naive-ui';
import {
  Microphone as MicIcon,
  StopFilledAlt as StopIcon,
  DocumentTasks as SummaryIcon,
  Tools as DebugIcon,
  Close as CloseIcon,
  Information as InfoIcon,
  User as UserIcon,
  Bot as BotIcon,
  Chip as EngineIcon,
  Language as LangIcon,
  Catalog as ScenarioIcon,
  VolumeUp as VoiceIcon,
} from '@vicons/carbon';
import { useI18n } from 'vue-i18n';
import { useRoute } from 'vue-router';
import { storeToRefs } from 'pinia';
import { marked } from 'marked';
import DOMPurify from 'dompurify';

import { useSession } from '../stores/session.js';
import {
  Recorder,
  Player,
  gateFrame,
  deriveMicOpen,
  shouldEnterTalking,
  readPtt,
  writePtt,
  readTalkSel,
  writeTalkSel,
} from '../audio.js';
import {
  langsForEngine,
  voicesForProvLang,
  novaVoices,
  enginesFor,
  reconcileSelection,
  seedPrevFromLaunch,
  launchParamsFromSelection,
  mergeDemoFirst,
} from '../talkConfig.js';
import { openTalkWs, pickLaunchQuery } from '../ws.js';
import { api } from '../api.js';
import DebugDrawer from './DebugDrawer.vue';
import StatChip from '../components/ui/StatChip.vue';

const message = useMessage();
const { t } = useI18n();
const route = useRoute();
const session = useSession();
const { turns, events, status, defaultsLine } = storeToRefs(session);

// The launch config currently driving the call (from a demo's ?scenario=&lang=...
// query). Empty {} = manual /talk start (global defaults). Kept as a ref so that
// "stop then start again" reuses the same demo config instead of falling back to
// the global default. Set in onMounted when the route carries a scenario.
const activeLaunchCfg = ref({});

// ---------------------------------------------------------------------------
// Engine / language / voice selection (tech_design §3). `config` is the live
// /api/config snapshot from the session store. `selection` is reactive and
// fully reconciled against config (every field always valid). It is seeded in
// onMounted AFTER session.loadConfig() — until then it holds harmless empties
// and the template only renders selectors once config is loaded.
// ---------------------------------------------------------------------------
const config = computed(() => session.config);

const selection = reactive({
  engine: '',
  lang: '',
  provider: '',
  voice: '',
  novaVoice: '',
  model: '', // pipeline LLM; '' = inherit global DEFAULT_MODEL (server-side)
});

// Guard so the reactive selection watchers (engine/lang/provider revalidation
// + persistence) don't fire while we are programmatically (re)seeding it.
let seeded = false;

// Option lists derived from the pure helpers (never reimplement logic here).
const engineOptions = computed(() =>
  enginesFor(config.value).map((e) => ({ label: e.label, value: e.id })),
);
const langOptions = computed(() =>
  langsForEngine(config.value, selection.engine).map((l) => ({ label: l.label, value: l.id })),
);
const providerOptions = computed(() =>
  (config.value?.providers || []).map((p) => ({ label: p.label, value: p.id })),
);
const pipelineVoiceOptions = computed(() =>
  voicesForProvLang(config.value, selection.provider, selection.lang).map((v) => ({
    label: v.label,
    value: v.id,
  })),
);
const novaVoiceOptions = computed(() =>
  novaVoices(config.value).map((v) => ({
    label: `${v.label} · ${v.gender || ''}${v.polyglot ? ' · polyglot' : ''}`,
    value: v.id,
  })),
);
// LLM (model) options for the pipeline engine — from /api/config's `models`
// ([{id,label,bedrock_id}]). '' = inherit the global default (clearable select).
const modelOptions = computed(() =>
  (config.value?.models || []).map((m) => ({ label: m.label || m.id, value: m.id })),
);

// Seed the selection from persisted localStorage + config (single source of
// correctness = reconcileSelection). Called once config is loaded. Guarded so it
// doesn't trip the field watchers below.
function seedSelection(prev) {
  seeded = false;
  Object.assign(selection, reconcileSelection(prev, config.value));
  seeded = true;
}

// On engine change → full reconcile (auto-corrects lang/provider/voice to a
// combo valid for the new engine). On provider/lang change (pipeline) →
// revalidate just the pipeline voice against the new provider+lang list.
watch(
  () => selection.engine,
  () => {
    if (!seeded) return;
    Object.assign(selection, reconcileSelection(selection, config.value));
  },
);
watch(
  [() => selection.provider, () => selection.lang],
  () => {
    if (!seeded || selection.engine !== 'pipeline') return;
    const pvList = voicesForProvLang(config.value, selection.provider, selection.lang).map(
      (v) => v.id,
    );
    if (!pvList.includes(selection.voice)) {
      const c = config.value || {};
      const dflt = c.default_voices?.[selection.provider];
      selection.voice = dflt && pvList.includes(dflt) ? dflt : pvList[0] || '';
    }
  },
);

// Persist the selection to localStorage on any change (mirrors the vb.ptt
// writePtt watch; all localStorage access stays in the component via audio.js
// helpers, never in talkConfig.js).
watch(
  selection,
  (sel) => {
    if (!seeded) return;
    writeTalkSel(sel);
  },
  { deep: true },
);

const debugOpen = ref(false);
const summaryOpen = ref(false);
const summarizing = ref(false);
const summaryHtml = ref('');
const scrollRef = ref(null);
const waveCanvas = ref(null);

// ---------------------------------------------------------------------------
// Push-to-Talk (PTT) — tech_design §2. Default OFF (hands-free, current
// behavior). Frontend-only: when held-released, the recorder callback sends an
// equal-length silence frame (gateFrame) so the server VAD ends the turn via its
// existing stop_secs. No PTT flag is sent to the backend.
// ---------------------------------------------------------------------------
const pttEnabled = ref(readPtt()); // persisted toggle (localStorage key vb.ptt)
const pttHolding = ref(false); // is the user currently holding to talk

// micOpen: PTT off → always true (forward raw frames, identical to current).
// PTT on → true only while holding. Reactive so the recorder callback reads the
// freshest value every frame; toggling mid-recording takes effect immediately.
const micOpen = computed(() => deriveMicOpen(pttEnabled.value, pttHolding.value));

// Persist toggle changes; releasing/holding state is transient (not persisted).
watch(pttEnabled, (v) => {
  writePtt(v);
  // Leaving PTT mode must never leave us stuck "not holding" while gated.
  if (!v) pttHolding.value = false;
});

let ws = null;
let recorder = null;
let player = null;

const statusText = computed(() => {
  switch (status.value) {
    case 'idle':
    case 'ended':
      return t('talk.status.ready');
    case 'connecting':
      return t('talk.status.connecting');
    case 'recording':
      return t('talk.status.recording');
    default:
      return '';
  }
});

// Semantic tone for the status dot (visual only).
const statusTone = computed(() => {
  switch (status.value) {
    case 'recording':
      return 'recording';
    case 'connecting':
      return 'connecting';
    default:
      return 'idle';
  }
});

// engine / language / voice / scenario meta as StatChips, shown while
// connecting/recording (the selectors collapse to these read-only chips). They
// reflect the ACTIVE `selection` (the engine/lang/voice we actually launched
// with) — not c.default_engine — so the chips match what the running call uses
// (reviewer note 1). The scenario chip still comes from the demo launch cfg.
const metaChips = computed(() => {
  const c = session.config;
  if (!c) return [];
  const cfg = activeLaunchCfg.value || {};
  const chips = [];
  if (selection.engine) {
    chips.push({ key: 'engine', value: selection.engine, tone: 'info', icon: EngineIcon });
  }
  if (selection.lang) {
    chips.push({ key: 'lang', value: selection.lang, tone: 'default', icon: LangIcon });
  }
  // Engine-appropriate voice (pipeline voice vs nova voice).
  const voice = selection.engine === 'nova-sonic' ? selection.novaVoice : selection.voice;
  if (voice) {
    chips.push({ key: 'voice', value: voice, tone: 'default', icon: VoiceIcon });
  }
  const scenario = cfg.scenario || c.default_demo || c.default_scenario;
  if (scenario) {
    chips.push({ key: 'scenario', value: scenario, tone: 'accent', icon: ScenarioIcon });
  }
  return chips;
});

// Per-turn arrival clock, derived from the turn's own `t` timestamp stamped by
// the store at push time. Deriving from `turn.t` (rather than a parallel index
// array) keeps the timestamp glued to its bubble even when the sliding window
// head-drops the oldest turns — no misalignment.
function fmtClock(d) {
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}
function turnClock(turn) {
  return turn && turn.t ? fmtClock(new Date(turn.t)) : '';
}

// --- PTT hold controls (pointer + spacebar) ----------------------------------
// The hold button drives pttHolding directly. pointerleave/cancel also release,
// so dragging the pointer off the button can't get stuck in "talking".
function startHold() {
  pttHolding.value = true;
}
function endHold() {
  pttHolding.value = false;
}

// Spacebar long-press while PTT is on and we're recording. event.repeat is
// filtered (shouldEnterTalking) so the OS key-repeat doesn't re-trigger; the
// keydown is preventDefault'd so the page doesn't scroll.
function onKeyDown(e) {
  if (!shouldEnterTalking(e)) return;
  e.preventDefault();
  pttHolding.value = true;
}
function onKeyUp(e) {
  if (e.code === 'Space' || e.key === ' ' || e.key === 'Spacebar') {
    e.preventDefault();
    pttHolding.value = false;
  }
}

let keyListenersOn = false;
function addKeyListeners() {
  if (keyListenersOn) return;
  window.addEventListener('keydown', onKeyDown);
  window.addEventListener('keyup', onKeyUp);
  keyListenersOn = true;
}
function removeKeyListeners() {
  if (!keyListenersOn) return;
  window.removeEventListener('keydown', onKeyDown);
  window.removeEventListener('keyup', onKeyUp);
  keyListenersOn = false;
  pttHolding.value = false; // never leave holding latched after detaching
}

// Keyboard listener is mounted ONLY while PTT is on AND we're recording; any
// other combination tears it down (and resets holding). Covers: stop recording,
// toggle PTT off mid-recording, and component unmount (via cleanup()).
watch(
  [pttEnabled, status],
  ([enabled, s]) => {
    if (enabled && s === 'recording') addKeyListeners();
    else removeKeyListeners();
  },
  { immediate: true },
);

onMounted(async () => {
  try {
    await session.loadConfig();
  } catch (e) {
    message.error(t('talk.errors.loadConfig', { msg: e.message }));
  }
  // Demo one-click launch (tech_design §4): if we arrived with ?scenario=...
  // (from a demo's "start talk" button), capture the whitelisted launch query and
  // auto-start the call. A direct /talk visit (no scenario) keeps current behavior
  // — the user clicks the big center button manually. Mic-permission failure is
  // handled by startCall's existing try/catch (graceful fallback to idle).
  //
  const cfg = pickLaunchQuery(route.query);
  if (cfg.scenario) {
    activeLaunchCfg.value = cfg;
  }
  // Seed the reactive selection from the URL launch query layered over persisted
  // localStorage, reconciled against the freshly-loaded config. URL launch params
  // win over localStorage which wins over config defaults — so the top chips /
  // selectors reflect what the actual call uses, not stale global defaults
  // (tech_design §2-§3). A manual /talk visit (empty cfg) leaves the persisted
  // seed unchanged → byte-identical to the old manual start that sent {}.
  seedSelection(seedPrevFromLaunch(readTalkSel(), cfg));

  if (cfg.scenario) {
    await startCall();
  }
});

onBeforeUnmount(() => {
  stopWaveform();
  cleanup();
});

// ---------------------------------------------------------------------------
// Recording waveform ring (visualization only — does NOT touch audio.js capture).
//
// Prefers reusing the mic MediaStream that audio.js's Recorder already opened
// (exposed as `recorder.micStream`); we attach our own read-only AnalyserNode to
// a fresh AudioContext so we never reconfigure the capture graph. If for any
// reason that stream is unavailable we fall back to an independent read-only
// getUserMedia() purely for the visual, coexisting with the real capture.
// Everything is torn down the moment recording ends.
// ---------------------------------------------------------------------------
let waveCtx = null;
let waveAnalyser = null;
let waveSource = null;
let waveOwnStream = null; // only set when we had to open our own stream
let waveRaf = 0;

async function startWaveform() {
  if (waveCtx) return; // already running
  try {
    let stream = recorder && recorder.micStream;
    if (!stream) {
      // Fallback: independent read-only stream just for the visualization.
      waveOwnStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      stream = waveOwnStream;
    }
    waveCtx = new AudioContext();
    waveSource = waveCtx.createMediaStreamSource(stream);
    waveAnalyser = waveCtx.createAnalyser();
    waveAnalyser.fftSize = 256;
    waveAnalyser.smoothingTimeConstant = 0.7;
    // Read-only: analyser is NOT connected to destination, so nothing is heard
    // and the real capture graph in audio.js is untouched.
    waveSource.connect(waveAnalyser);
    drawWaveform();
  } catch {
    // Visualization is best-effort; never break recording if it fails.
    stopWaveform();
  }
}

function drawWaveform() {
  const canvas = waveCanvas.value;
  if (!canvas || !waveAnalyser) return;
  const ctx = canvas.getContext('2d');
  const W = canvas.width;
  const H = canvas.height;
  const cx = W / 2;
  const cy = H / 2;
  const baseR = 104; // just outside the 200px button radius (scaled to canvas)
  const bins = waveAnalyser.frequencyBinCount;
  const freq = new Uint8Array(bins);

  const css = (name) =>
    getComputedStyle(document.documentElement).getPropertyValue(name).trim();

  const render = () => {
    if (!waveAnalyser) return;
    waveAnalyser.getByteFrequencyData(freq);
    ctx.clearRect(0, 0, W, H);

    const primary = css('--vb-primary') || '#0972D3';
    const accent = css('--vb-accent') || '#FF9900';

    // Average level → soft pulsing glow ring.
    let sum = 0;
    for (let i = 0; i < bins; i++) sum += freq[i];
    const level = sum / bins / 255; // 0..1

    ctx.save();
    ctx.globalAlpha = 0.18 + level * 0.32;
    ctx.beginPath();
    ctx.arc(cx, cy, baseR + level * 14, 0, Math.PI * 2);
    ctx.lineWidth = 2 + level * 6;
    ctx.strokeStyle = primary;
    ctx.stroke();
    ctx.restore();

    // Radial bars around the ring driven by the spectrum.
    const barCount = 64;
    for (let i = 0; i < barCount; i++) {
      const v = freq[Math.floor((i / barCount) * bins)] / 255; // 0..1
      const len = 4 + v * 26;
      const ang = (i / barCount) * Math.PI * 2 - Math.PI / 2;
      const r0 = baseR + 4;
      const x0 = cx + Math.cos(ang) * r0;
      const y0 = cy + Math.sin(ang) * r0;
      const x1 = cx + Math.cos(ang) * (r0 + len);
      const y1 = cy + Math.sin(ang) * (r0 + len);
      ctx.beginPath();
      ctx.moveTo(x0, y0);
      ctx.lineTo(x1, y1);
      ctx.lineWidth = 2.5;
      ctx.strokeStyle = v > 0.6 ? accent : primary;
      ctx.globalAlpha = 0.35 + v * 0.55;
      ctx.lineCap = 'round';
      ctx.stroke();
    }
    ctx.globalAlpha = 1;

    waveRaf = requestAnimationFrame(render);
  };
  render();
}

function stopWaveform() {
  if (waveRaf) {
    cancelAnimationFrame(waveRaf);
    waveRaf = 0;
  }
  if (waveSource) {
    try { waveSource.disconnect(); } catch { /* ignore */ }
    waveSource = null;
  }
  waveAnalyser = null;
  if (waveCtx) {
    try { waveCtx.close(); } catch { /* ignore */ }
    waveCtx = null;
  }
  if (waveOwnStream) {
    waveOwnStream.getTracks().forEach((tr) => tr.stop());
    waveOwnStream = null;
  }
  const canvas = waveCanvas.value;
  if (canvas) {
    const ctx = canvas.getContext('2d');
    if (ctx) ctx.clearRect(0, 0, canvas.width, canvas.height);
  }
}

// Start/stop the visualization in lock-step with the recording status. This is
// a passive observer of the existing state machine — it never mutates `status`.
watch(status, (s) => {
  if (s === 'recording') startWaveform();
  else stopWaveform();
});

async function onCircleClick() {
  if (status.value === 'recording') {
    cleanup();
    status.value = 'ended';
    return;
  }
  if (status.value === 'connecting') return;
  await startCall();
}

// Open a Talk session. The per-session launch query is built demo-first
// (tech_design §6): the session `selection` (engine/lang/voice — engine-
// appropriate) provides the base, and the active demo launch cfg's explicit
// (non-empty) engine/voice/provider WIN over it (demo > session > default).
// `scenario` always comes from the demo cfg; a tools/MCP-forced pipeline engine
// in the demo cfg also wins here. A manual /talk start (empty activeLaunchCfg)
// → pure session selection, byte-identical to the previous {} path.
// Everything below (reset / status transitions / recorder / player / ws handlers)
// is unchanged from the original onCircleClick start branch.
async function startCall() {
  const sessionParams = launchParamsFromSelection(selection, {});
  const cfg = mergeDemoFirst(sessionParams, activeLaunchCfg.value);
  session.reset();
  status.value = 'connecting';
  try {
    player = new Player();
    ws = await openTalkWs(cfg);
    ws.onopen = async () => {
      try {
        recorder = new Recorder();
        await recorder.start((pcmBuf) => {
          if (!(ws && ws.readyState === 1)) return;
          // micOpen.value is read fresh per frame; PTT-released → silence frame.
          ws.send(gateFrame(pcmBuf, micOpen.value));
        });
        status.value = 'recording';
      } catch (e) {
        message.error(t('talk.errors.mic', { msg: e.message }));
        cleanup();
        status.value = 'idle';
      }
    };
    ws.onmessage = (e) => {
      if (typeof e.data === 'string') {
        try {
          handleEvent(JSON.parse(e.data));
        } catch {
          /* ignore */
        }
        return;
      }
      if (player) player.feed(e.data);
    };
    ws.onclose = () => {
      cleanup();
      if (status.value !== 'idle') status.value = 'ended';
    };
    ws.onerror = () => {
      message.error(t('talk.errors.ws'));
      cleanup();
      status.value = 'idle';
    };
  } catch (e) {
    message.error(t('talk.errors.start', { msg: e.message }));
    cleanup();
    status.value = 'idle';
  }
}

function handleEvent(evt) {
  session.appendEvent(evt);
  switch (evt.type) {
    case 'asr_partial':
      session.pushTurn({ role: 'user', text: evt.text || '', partial: true });
      break;
    case 'asr_final':
      session.pushTurn({ role: 'user', text: evt.text || '', partial: false });
      break;
    case 'llm_delta': {
      // Append to last bot bubble (or create one)
      const last = turns.value[turns.value.length - 1];
      if (last && last.role === 'bot' && last.partial) {
        last.text += evt.text || '';
      } else {
        session.pushTurn({ role: 'bot', text: evt.text || '', partial: true });
      }
      break;
    }
    case 'llm_end': {
      const last = turns.value[turns.value.length - 1];
      if (last && last.role === 'bot' && last.partial) {
        if (evt.text) last.text = evt.text;
        last.partial = false;
      }
      break;
    }
    case 'user_speaking':
      // Barge-in: clear queued bot audio
      if (evt.value === true && player) player.clear();
      break;
    default:
      break;
  }
  scrollToBottom();
}

function scrollToBottom() {
  nextTick(() => {
    const sb = scrollRef.value;
    if (sb && sb.scrollTo) sb.scrollTo({ top: 1e9, behavior: 'smooth' });
  });
}

function cleanup() {
  // Detach PTT keyboard listeners and unlatch holding whenever the session tears
  // down — the status watch also covers this, but cleanup can run before status
  // flips (e.g. ws.onclose), so do it explicitly here too (idempotent).
  removeKeyListeners();
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
  if (player) {
    player.clear();
    player = null;
  }
}

async function summarize() {
  if (turns.value.length === 0) return;
  summarizing.value = true;
  summaryHtml.value = '';
  summaryOpen.value = true;
  try {
    const turnsForApi = turns.value
      .filter((t) => !t.partial && t.text.trim())
      .map((t) => ({ who: t.role, text: t.text }));
    const lang = session.config?.default_language || 'zh-CN';
    const r = await api.summary({
      turns: turnsForApi,
      lang,
    });
    const md = r.summary || '';
    summaryHtml.value = DOMPurify.sanitize(marked.parse(md));
  } catch (e) {
    // Surface as styled HTML inside the summary modal. The translated string
    // is plain text from the bundle (no markup); only the wrapping <p> + style
    // lives in this template.
    const safeMsg = DOMPurify.sanitize(t('talk.summary.failed', { msg: e.message }));
    summaryHtml.value = `<p style="color: #f55;">${safeMsg}</p>`;
  } finally {
    summarizing.value = false;
  }
}

watch(turns, scrollToBottom, { deep: true });
</script>

<style scoped>
/* --- Push-style side-by-side shell --- */
.talk-shell {
  display: flex;
  height: 100%;
  /* relative so the narrow-screen .log-panel can absolutely position against
     the shell rather than the viewport. */
  position: relative;
}

/* Original talk-root content lives here. Centered + max-width 760 so that when
   the log panel is closed the conversation area is visually identical to the
   pre-T3 layout. flex:1 + min-width:0 lets it be squeezed by the log panel
   without overflow when the panel expands. */
.talk-main {
  flex: 1;
  min-width: 0;
  max-width: 760px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: var(--vb-space-lg);
  height: 100%;
}

/* Right-side log panel — expands and squeezes .talk-main (does NOT overlay). */
.log-panel {
  width: 420px;
  flex: none;
  border-left: 1px solid var(--vb-border);
  transition: width 0.2s;
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  background: var(--vb-surface);
}

.log-panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--vb-space-sm);
  padding: var(--vb-space-sm) var(--vb-space-md);
  border-bottom: 1px solid var(--vb-border);
  flex: none;
}

.log-panel-title {
  font-size: 14px;
}

.log-panel-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: var(--vb-space-md);
}

/* Narrow screens: the panel can't afford to squeeze the (already small) talk
   area, so it floats as an absolute overlay over the right edge instead. */
@media (max-width: 1023px) {
  .log-panel {
    position: absolute;
    right: 0;
    top: 0;
    height: 100%;
    box-shadow: var(--vb-shadow-popover);
    z-index: 10;
  }
}

/* --- Status row --- */
.status-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--vb-space-xs) 0;
  flex-wrap: wrap;
  gap: var(--vb-space-sm);
}

.status-left {
  display: inline-flex;
  align-items: center;
  gap: var(--vb-space-sm);
}

.status-text {
  font-size: 16px;
}

.status-dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  flex: none;
  background: var(--vb-text-tertiary);
}

.status-dot--idle {
  background: var(--vb-text-tertiary);
}

.status-dot--connecting {
  background: var(--vb-warning);
  animation: dot-blink 1s ease-in-out infinite;
}

.status-dot--recording {
  background: var(--vb-error);
  box-shadow: 0 0 0 0 rgba(217, 21, 21, 0.4);
  animation: dot-pulse 1.4s ease-out infinite;
}

@keyframes dot-blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}

@keyframes dot-pulse {
  0% { box-shadow: 0 0 0 0 rgba(217, 21, 21, 0.4); }
  100% { box-shadow: 0 0 0 8px rgba(217, 21, 21, 0); }
}

.defaults-line {
  display: inline-flex;
  gap: var(--vb-space-sm);
  align-items: center;
  flex-wrap: wrap;
}

/* Inline engine/lang/voice selectors. Sensible per-field widths so the row
   stays compact; .defaults-line already flex-wraps on narrow screens. */
.sel-wrap {
  display: inline-flex;
}
.sel {
  width: 130px;
}
.sel-engine {
  width: 140px;
}
.sel-voice {
  width: 200px;
}

.chip-icon {
  margin-right: 4px;
  vertical-align: -2px;
}

.info-icon {
  color: var(--vb-text-tertiary);
  cursor: help;
}

/* --- Push-to-Talk --- */
.ptt-toggle {
  display: inline-flex;
  align-items: center;
  gap: var(--vb-space-xs);
}

.ptt-label {
  font-size: 12px;
}

.ptt-hold-wrap {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--vb-space-sm);
  margin-top: calc(-1 * var(--vb-space-md));
}

.ptt-hold-btn {
  display: inline-flex;
  align-items: center;
  gap: var(--vb-space-sm);
  padding: 10px 22px;
  border-radius: var(--vb-radius-lg);
  border: 1px solid var(--vb-border);
  background: var(--vb-surface);
  color: var(--vb-primary);
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  user-select: none;
  -webkit-user-select: none;
  touch-action: none;
  transition: transform 0.1s, background 0.15s, color 0.15s, border-color 0.15s;
}

.ptt-hold-btn.holding {
  background: var(--vb-primary);
  color: var(--vb-on-primary);
  border-color: var(--vb-primary);
  transform: scale(0.98);
}

.ptt-hint {
  font-size: 11px;
}

/* --- Big circle button + waveform ring --- */
.circle-wrap {
  display: flex;
  justify-content: center;
  padding: var(--vb-space-lg) 0;
}

.circle-stage {
  position: relative;
  width: 280px;
  height: 280px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.wave-canvas {
  position: absolute;
  inset: 0;
  width: 280px;
  height: 280px;
  pointer-events: none;
  opacity: 0;
  transition: opacity 0.25s ease;
}

.wave-canvas.active {
  opacity: 1;
}

.circle-btn {
  position: relative;
  z-index: 1;
  width: 176px;
  height: 176px;
  border-radius: 50%;
  border: 1px solid var(--vb-border);
  background: var(--vb-surface);
  color: var(--vb-primary);
  font-weight: 600;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--vb-space-md);
  box-shadow: var(--vb-shadow-card);
  transition: transform 0.15s, box-shadow 0.15s, background 0.2s, color 0.2s, border-color 0.2s;
}

.circle-btn:hover:not(:disabled) {
  transform: scale(1.03);
  box-shadow: var(--vb-shadow-popover);
  border-color: var(--vb-primary);
}

.circle-btn.recording {
  background: var(--vb-primary);
  color: var(--vb-on-primary);
  border-color: var(--vb-primary);
  box-shadow: var(--vb-shadow-popover);
}

.circle-btn.connecting {
  opacity: 0.6;
  cursor: wait;
}

.circle-btn:disabled {
  cursor: not-allowed;
}

.circle-icon {
  line-height: 1;
}

.circle-label {
  font-size: 15px;
}

/* --- Transcript stream --- */
.transcript-wrap {
  flex: 1;
  min-height: 240px;
  border-radius: var(--vb-radius-lg);
  background: var(--vb-surface);
  border: 1px solid var(--vb-border);
  padding: var(--vb-space-md) var(--vb-space-sm);
  overflow: hidden;
}

.stream {
  display: flex;
  flex-direction: column;
  gap: var(--vb-space-lg);
  padding: var(--vb-space-md);
}

.msg {
  display: flex;
  gap: var(--vb-space-md);
  align-items: flex-start;
}

.msg-avatar {
  flex: none;
  width: 30px;
  height: 30px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--vb-border);
}

.msg-avatar.user {
  background: var(--vb-primary);
  color: var(--vb-on-primary);
  border-color: var(--vb-primary);
}

.msg-avatar.bot {
  background: var(--vb-surface-alt);
  color: var(--vb-text-secondary);
}

.msg-body {
  flex: 1;
  min-width: 0;
}

.msg-meta {
  display: flex;
  align-items: center;
  gap: var(--vb-space-sm);
  margin-bottom: 2px;
}

.msg-who {
  font-size: 12px;
  font-weight: 600;
  color: var(--vb-text-secondary);
}

.msg-ts {
  font-size: 11px;
  color: var(--vb-text-tertiary);
  font-variant-numeric: tabular-nums;
}

.msg-state {
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--vb-accent);
  border: 1px solid var(--vb-accent);
  border-radius: var(--vb-radius-sm);
  padding: 0 5px;
  line-height: 1.4;
}

.msg-text {
  font-size: 14px;
  line-height: 1.55;
  color: var(--vb-text);
  word-break: break-word;
  white-space: pre-wrap;
}

.msg.partial .msg-text {
  color: var(--vb-text-secondary);
}

.caret {
  display: inline-block;
  margin-left: 1px;
  color: var(--vb-primary);
  animation: caret-blink 1s step-end infinite;
}

@keyframes caret-blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}

.empty {
  text-align: center;
  padding: var(--vb-space-xxl) 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--vb-space-md);
}

.empty-icon {
  color: var(--vb-text-tertiary);
  opacity: 0.5;
}

/* --- Summary markdown --- */
.summary-md :deep(h1),
.summary-md :deep(h2),
.summary-md :deep(h3) {
  margin: 12px 0 8px;
}

.summary-md :deep(p) {
  margin: 8px 0;
  line-height: 1.6;
}

.summary-md :deep(ul),
.summary-md :deep(ol) {
  margin: 8px 0;
  padding-left: 24px;
}

.summary-md :deep(code) {
  background: var(--vb-surface-alt);
  padding: 1px 4px;
  border-radius: var(--vb-radius-sm);
  font-family: var(--vb-font-mono);
}
</style>
