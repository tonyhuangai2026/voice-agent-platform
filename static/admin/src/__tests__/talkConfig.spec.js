import { describe, it, expect } from 'vitest';
import {
  langsForEngine,
  voicesForProvLang,
  novaVoices,
  enginesFor,
  reconcileSelection,
  seedPrevFromLaunch,
  launchParamsFromSelection,
  stripEmpty,
  mergeDemoFirst,
  guestPrefillFromDemo,
  guestLinkBody,
  guestLaunchQuery,
} from '../talkConfig.js';

// Pure-helper unit tests (tech_design §6). DOM-free — no mount, no localStorage.
// Fixture mirrors the real GET /api/config shape (tech_design §0/§2):
//  - engines: [{id,label}]
//  - languages: [{id,label,engines:[]}]   (per-engine capability list)
//  - providers: [{id,label}]
//  - voices_by_provider: { minimax:[{id,label,language}], polly:[...] }
//  - nova_sonic_voices: [{id,label,gender,locale,polyglot}]
//  - default_* scalars + default_voices.{minimax,polly}
const CONFIG = {
  engines: [
    { id: 'pipeline', label: 'Three-stage (pipeline)' },
    { id: 'nova-sonic', label: 'Nova Sonic' },
  ],
  languages: [
    // pipeline-only (Nova Sonic can't speak Chinese — see nova_sonic_no_chinese memory)
    { id: 'zh-CN', label: '简体中文', engines: ['pipeline'] },
    { id: 'zh-HK', label: '廣東話', engines: ['pipeline'] },
    // ja pipeline-only too
    { id: 'ja-JP', label: '日本語', engines: ['pipeline'] },
    // en-US in BOTH engines
    { id: 'en-US', label: 'English (US)', engines: ['pipeline', 'nova-sonic'] },
    // fr-FR nova-only
    { id: 'fr-FR', label: 'Français', engines: ['nova-sonic'] },
  ],
  providers: [
    { id: 'minimax', label: 'MiniMax' },
    { id: 'polly', label: 'Amazon Polly' },
  ],
  voices_by_provider: {
    minimax: [
      { id: 'mm-zh-f', label: 'MiniMax 中文女', language: 'zh-CN' },
      { id: 'mm-zh-m', label: 'MiniMax 中文男', language: 'zh-CN' },
      { id: 'mm-en-f', label: 'MiniMax EN female', language: 'en-US' },
    ],
    polly: [
      { id: 'Zhiyu', label: 'Polly Zhiyu', language: 'zh-CN' },
      { id: 'Joanna', label: 'Polly Joanna', language: 'en-US' },
    ],
  },
  nova_sonic_voices: [
    { id: 'matthew', label: 'Matthew', gender: 'male', locale: 'en-US', polyglot: false },
    { id: 'tiffany', label: 'Tiffany', gender: 'female', locale: 'en-US', polyglot: true },
  ],
  models: [
    { id: 'nova-2-lite', label: 'nova-2-lite', bedrock_id: 'us.amazon.nova-2-lite-v1:0' },
    { id: 'nova-lite', label: 'nova-lite', bedrock_id: 'us.amazon.nova-lite-v1:0' },
  ],
  default_engine: 'pipeline',
  default_language: 'zh-CN',
  default_provider: 'minimax',
  default_voices: { minimax: 'mm-zh-f', polly: 'Zhiyu' },
  default_nova_sonic_voice: 'matthew',
};

describe('langsForEngine', () => {
  it('nova-sonic excludes zh/ja, includes en-US and fr-FR', () => {
    const ids = langsForEngine(CONFIG, 'nova-sonic').map((l) => l.id);
    expect(ids).toEqual(['en-US', 'fr-FR']);
    expect(ids).not.toContain('zh-CN');
    expect(ids).not.toContain('zh-HK');
    expect(ids).not.toContain('ja-JP');
  });

  it('pipeline includes zh/ja and en-US, excludes nova-only fr-FR', () => {
    const ids = langsForEngine(CONFIG, 'pipeline').map((l) => l.id);
    expect(ids).toEqual(['zh-CN', 'zh-HK', 'ja-JP', 'en-US']);
    expect(ids).not.toContain('fr-FR');
  });

  it('en-US appears in both engine lists', () => {
    expect(langsForEngine(CONFIG, 'pipeline').map((l) => l.id)).toContain('en-US');
    expect(langsForEngine(CONFIG, 'nova-sonic').map((l) => l.id)).toContain('en-US');
  });

  it('null-safe: missing config / languages → []', () => {
    expect(langsForEngine(undefined, 'pipeline')).toEqual([]);
    expect(langsForEngine({}, 'pipeline')).toEqual([]);
    expect(langsForEngine({ languages: [{ id: 'x' }] }, 'pipeline')).toEqual([]); // no engines key
  });
});

describe('voicesForProvLang', () => {
  it('returns only voices whose language matches the requested lang', () => {
    const ids = voicesForProvLang(CONFIG, 'minimax', 'zh-CN').map((v) => v.id);
    expect(ids).toEqual(['mm-zh-f', 'mm-zh-m']);
  });

  it('falls back to the full provider list when no voice matches the lang', () => {
    // minimax has no fr-FR voice → full minimax list
    const ids = voicesForProvLang(CONFIG, 'minimax', 'fr-FR').map((v) => v.id);
    expect(ids).toEqual(['mm-zh-f', 'mm-zh-m', 'mm-en-f']);
  });

  it('returns [] for missing config / missing provider', () => {
    expect(voicesForProvLang(undefined, 'minimax', 'zh-CN')).toEqual([]);
    expect(voicesForProvLang({}, 'minimax', 'zh-CN')).toEqual([]);
    expect(voicesForProvLang(CONFIG, 'nope', 'zh-CN')).toEqual([]);
  });
});

describe('novaVoices', () => {
  it('returns the nova_sonic_voices list', () => {
    expect(novaVoices(CONFIG).map((v) => v.id)).toEqual(['matthew', 'tiffany']);
  });
  it('null-safe → []', () => {
    expect(novaVoices(undefined)).toEqual([]);
    expect(novaVoices({})).toEqual([]);
  });
});

describe('enginesFor', () => {
  it('returns all engines (no tools→pipeline coupling)', () => {
    expect(enginesFor(CONFIG).map((e) => e.id)).toEqual(['pipeline', 'nova-sonic']);
  });
  it('returns nova-sonic for a tool demo (Nova Sonic supports tools)', () => {
    // enginesFor takes only config; a demo having tools no longer filters it.
    expect(enginesFor(CONFIG).map((e) => e.id)).toContain('nova-sonic');
  });
  it('null-safe → []', () => {
    expect(enginesFor(undefined)).toEqual([]);
  });
});

describe('reconcileSelection', () => {
  it('(a) empty prev → all config defaults', () => {
    const sel = reconcileSelection({}, CONFIG, {});
    expect(sel).toEqual({
      engine: 'pipeline',
      lang: 'zh-CN',
      provider: 'minimax',
      voice: 'mm-zh-f',
      novaVoice: 'matthew',
      model: '', // no persisted model → inherit (empty)
    });
  });

  it('(b) persisted nova-sonic + zh-CN lang → lang auto-corrected to a nova-valid lang', () => {
    const sel = reconcileSelection(
      { engine: 'nova-sonic', lang: 'zh-CN', novaVoice: 'tiffany' },
      CONFIG,
      {}
    );
    expect(sel.engine).toBe('nova-sonic');
    // zh-CN is not valid for nova-sonic → must be corrected to a nova lang
    expect(langsForEngine(CONFIG, 'nova-sonic').map((l) => l.id)).toContain(sel.lang);
    expect(sel.lang).not.toBe('zh-CN');
    // default_language (zh-CN) isn't nova-valid either → first nova lang = en-US
    expect(sel.lang).toBe('en-US');
    expect(sel.novaVoice).toBe('tiffany'); // valid persisted nova voice preserved
  });

  it('(c) persisted nova-sonic is kept (no forcePipeline pin)', () => {
    // Even for a tool demo, Nova Sonic is a valid choice: a persisted
    // nova-sonic + nova-valid lang survives reconciliation unchanged.
    const sel = reconcileSelection(
      { engine: 'nova-sonic', lang: 'en-US', novaVoice: 'tiffany' },
      CONFIG
    );
    expect(sel.engine).toBe('nova-sonic');
    expect(sel.lang).toBe('en-US');
    expect(sel.novaVoice).toBe('tiffany');
  });

  it('(d) stale voice not in provider list → corrected to default/first', () => {
    const sel = reconcileSelection(
      { engine: 'pipeline', lang: 'zh-CN', provider: 'minimax', voice: 'ghost-voice' },
      CONFIG,
      {}
    );
    // default_voices.minimax (mm-zh-f) is valid for zh-CN → used
    expect(sel.voice).toBe('mm-zh-f');
  });

  it('(d2) stale voice + provider default not valid for lang → first of filtered list', () => {
    // lang en-US: minimax default (mm-zh-f, a zh-CN voice) is NOT in the en-US
    // filtered list → fall to first filtered voice (mm-en-f).
    const sel = reconcileSelection(
      { engine: 'pipeline', lang: 'en-US', provider: 'minimax', voice: 'ghost' },
      CONFIG,
      {}
    );
    expect(sel.voice).toBe('mm-en-f');
  });

  it('(e) missing provider → default/first', () => {
    const sel = reconcileSelection(
      { engine: 'pipeline', lang: 'zh-CN', provider: 'nonexistent' },
      CONFIG,
      {}
    );
    expect(sel.provider).toBe('minimax'); // default_provider
  });

  it('(e2) provider absent + no default_provider → first provider', () => {
    const cfg = { ...CONFIG, default_provider: undefined };
    const sel = reconcileSelection({ engine: 'pipeline', lang: 'zh-CN' }, cfg, {});
    expect(sel.provider).toBe('minimax'); // first in providers list
  });

  it('null-safe: empty config → no throw, fields fall to first/undefined', () => {
    expect(() => reconcileSelection({}, {}, {})).not.toThrow();
    expect(() => reconcileSelection(undefined, undefined, {})).not.toThrow();
    const sel = reconcileSelection({}, {}, {});
    expect(sel).toHaveProperty('engine');
    expect(sel).toHaveProperty('lang');
    expect(sel).toHaveProperty('provider');
    expect(sel).toHaveProperty('voice');
    expect(sel).toHaveProperty('novaVoice');
  });

  it('reconcileSelection(prev, config) keeps a valid persisted nova-sonic', () => {
    const sel = reconcileSelection({ engine: 'nova-sonic', lang: 'en-US' }, CONFIG);
    expect(sel.engine).toBe('nova-sonic');
  });

  // T3 model reconcile: valid persisted model kept; unknown/absent → '' (inherit),
  // NEVER forced to a default (distinct from voice).
  it('(model-a) valid persisted model is kept', () => {
    const sel = reconcileSelection(
      { engine: 'pipeline', lang: 'zh-CN', provider: 'minimax', voice: 'mm-zh-f', model: 'nova-lite' },
      CONFIG,
    );
    expect(sel.model).toBe('nova-lite');
  });

  it('(model-b) unknown persisted model → cleared to inherit (empty)', () => {
    const sel = reconcileSelection(
      { engine: 'pipeline', lang: 'zh-CN', model: 'ghost-model' },
      CONFIG,
    );
    expect(sel.model).toBe('');
  });

  it('(model-c) absent model → inherit (empty), not a default', () => {
    const sel = reconcileSelection({ engine: 'pipeline', lang: 'zh-CN' }, CONFIG);
    expect(sel.model).toBe('');
  });
});

describe('seedPrevFromLaunch', () => {
  it('pipeline URL voice → routed to .voice (not .novaVoice)', () => {
    const prev = seedPrevFromLaunch(
      {},
      {
        engine: 'pipeline',
        lang: 'zh-HK',
        voice: 'Cantonese_ProfessionalHost（F)',
        provider: 'minimax',
      },
    );
    expect(prev.engine).toBe('pipeline');
    expect(prev.lang).toBe('zh-HK');
    expect(prev.provider).toBe('minimax');
    expect(prev.voice).toBe('Cantonese_ProfessionalHost（F)');
    expect('novaVoice' in prev).toBe(false);
  });

  it('URL model is carried onto prev (chips/selectors reflect the launched model)', () => {
    const prev = seedPrevFromLaunch({}, { engine: 'pipeline', model: 'nova-lite' });
    expect(prev.model).toBe('nova-lite');
  });

  it('nova URL voice → routed to .novaVoice, .voice untouched', () => {
    const prev = seedPrevFromLaunch({}, { engine: 'nova-sonic', voice: 'tiffany' });
    expect(prev.engine).toBe('nova-sonic');
    expect(prev.novaVoice).toBe('tiffany');
    expect('voice' in prev).toBe(false);
  });

  it('URL keys win over persisted (engine/lang precedence)', () => {
    const prev = seedPrevFromLaunch(
      { engine: 'nova-sonic', lang: 'en-US' },
      { engine: 'pipeline', lang: 'zh-HK' },
    );
    expect(prev.engine).toBe('pipeline');
    expect(prev.lang).toBe('zh-HK');
  });

  it('omitted URL keys keep the persisted values', () => {
    const prev = seedPrevFromLaunch(
      { engine: 'nova-sonic', provider: 'polly', voice: 'mm-en-f', lang: 'en-US' },
      { lang: 'zh-HK' },
    );
    expect(prev.lang).toBe('zh-HK'); // URL-provided
    expect(prev.engine).toBe('nova-sonic'); // persisted kept
    expect(prev.provider).toBe('polly'); // persisted kept
    expect(prev.voice).toBe('mm-en-f'); // persisted kept (no URL voice)
  });

  it('empty launchCfg → deep-equals persisted (manual /talk unchanged)', () => {
    const persisted = {
      engine: 'pipeline',
      lang: 'zh-CN',
      provider: 'minimax',
      voice: 'mm-zh-f',
      novaVoice: 'matthew',
    };
    expect(seedPrevFromLaunch(persisted, {})).toEqual(persisted);
    expect(seedPrevFromLaunch(persisted, undefined)).toEqual(persisted);
    // returns a copy, not the same reference
    expect(seedPrevFromLaunch(persisted, {})).not.toBe(persisted);
  });

  it('null-safe: missing persisted + empty launchCfg → {}', () => {
    expect(seedPrevFromLaunch(undefined, undefined)).toEqual({});
    expect(seedPrevFromLaunch(null, {})).toEqual({});
  });

  it('EDGE: URL voice with NO engine (URL or persisted) → .voice (else branch), .novaVoice untouched', () => {
    const prev = seedPrevFromLaunch({}, { voice: 'X' });
    expect(prev.voice).toBe('X');
    expect('novaVoice' in prev).toBe(false);
    expect('engine' in prev).toBe(false);
  });

  describe('end-to-end through reconcileSelection', () => {
    it('the example pipeline URL yields a pipeline/zh-HK/Cantonese selection', () => {
      // Extend the shared fixture with a zh-HK minimax voice so the example URL
      // voice is valid; reconcileSelection must then preserve it verbatim.
      const cfg = {
        ...CONFIG,
        languages: [
          ...CONFIG.languages.filter((l) => l.id !== 'zh-HK'),
          { id: 'zh-HK', label: '廣東話', engines: ['pipeline'] },
        ],
        voices_by_provider: {
          ...CONFIG.voices_by_provider,
          minimax: [
            ...CONFIG.voices_by_provider.minimax,
            { id: 'Cantonese_ProfessionalHost（F)', label: 'Cantonese Host F', language: 'zh-HK' },
          ],
        },
      };
      const launch = {
        engine: 'pipeline',
        lang: 'zh-HK',
        voice: 'Cantonese_ProfessionalHost（F)',
        provider: 'minimax',
      };
      const prev = seedPrevFromLaunch({}, launch);
      const sel = reconcileSelection(prev, cfg);
      expect(sel.engine).toBe('pipeline');
      expect(sel.lang).toBe('zh-HK');
      expect(sel.provider).toBe('minimax');
      expect(sel.voice).toBe('Cantonese_ProfessionalHost（F)');
    });

    it('an invalid nova-sonic+zh-HK URL self-corrects to a nova-valid lang', () => {
      const prev = seedPrevFromLaunch({}, { engine: 'nova-sonic', lang: 'zh-HK' });
      const sel = reconcileSelection(prev, CONFIG);
      expect(sel.engine).toBe('nova-sonic'); // engine from URL preserved
      // zh-HK is pipeline-only → must be corrected to a nova-valid lang
      expect(langsForEngine(CONFIG, 'nova-sonic').map((l) => l.id)).toContain(sel.lang);
      expect(sel.lang).not.toBe('zh-HK');
    });
  });
});

describe('launchParamsFromSelection', () => {
  it('nova-sonic path → emits voice (=novaVoice), NO provider/model/minimax_model', () => {
    const sel = {
      engine: 'nova-sonic',
      lang: 'en-US',
      provider: 'minimax',
      voice: 'mm-en-f',
      novaVoice: 'tiffany',
    };
    const p = launchParamsFromSelection(sel, { scenario: 'general' });
    expect(p.engine).toBe('nova-sonic');
    expect(p.lang).toBe('en-US');
    expect(p.voice).toBe('tiffany'); // novaVoice, not the pipeline voice
    expect('provider' in p).toBe(false);
    expect('model' in p).toBe(false);
    expect('minimax_model' in p).toBe(false);
    expect(p.scenario).toBe('general'); // baseCfg preserved
  });

  it('nova-sonic path strips provider/model/minimax_model that baseCfg carried', () => {
    const sel = { engine: 'nova-sonic', lang: 'en-US', novaVoice: 'matthew' };
    const p = launchParamsFromSelection(sel, {
      provider: 'polly',
      model: 'm1',
      minimax_model: 'mm1',
      scenario: 'x',
    });
    expect('provider' in p).toBe(false);
    expect('model' in p).toBe(false);
    expect('minimax_model' in p).toBe(false);
    expect(p.voice).toBe('matthew');
    expect(p.scenario).toBe('x');
  });

  it('pipeline path → emits provider + voice', () => {
    const sel = {
      engine: 'pipeline',
      lang: 'zh-CN',
      provider: 'minimax',
      voice: 'mm-zh-f',
      novaVoice: 'matthew',
    };
    const p = launchParamsFromSelection(sel, { scenario: 'it-helpdesk' });
    expect(p.engine).toBe('pipeline');
    expect(p.lang).toBe('zh-CN');
    expect(p.provider).toBe('minimax');
    expect(p.voice).toBe('mm-zh-f');
    expect(p.scenario).toBe('it-helpdesk'); // baseCfg.scenario preserved
  });

  it('preserves baseCfg.scenario and default baseCfg ({}) does not throw', () => {
    const sel = { engine: 'pipeline', lang: 'en-US', provider: 'polly', voice: 'Joanna' };
    const p = launchParamsFromSelection(sel);
    expect(p).toEqual({ engine: 'pipeline', lang: 'en-US', provider: 'polly', voice: 'Joanna' });
  });

  it('does not mutate the passed baseCfg object', () => {
    const base = { scenario: 'general', provider: 'polly' };
    launchParamsFromSelection({ engine: 'nova-sonic', lang: 'en-US', novaVoice: 'matthew' }, base);
    expect(base).toEqual({ scenario: 'general', provider: 'polly' }); // untouched
  });

  // T3: pipeline path emits a non-empty model; '' (inherit) omits the key.
  it('pipeline path emits model when selection.model is set', () => {
    const sel = { engine: 'pipeline', lang: 'zh-CN', provider: 'minimax', voice: 'mm-zh-f', model: 'nova-lite' };
    const p = launchParamsFromSelection(sel, { scenario: 'x' });
    expect(p.model).toBe('nova-lite');
  });

  it("pipeline path omits model when selection.model is '' (inherit)", () => {
    const sel = { engine: 'pipeline', lang: 'zh-CN', provider: 'minimax', voice: 'mm-zh-f', model: '' };
    const p = launchParamsFromSelection(sel, { scenario: 'x' });
    expect('model' in p).toBe(false);
  });
});

describe('stripEmpty', () => {
  it('drops null / undefined / empty-string values, keeps the rest', () => {
    expect(
      stripEmpty({ a: 'x', b: null, c: undefined, d: '', e: 'y', f: 0, g: false }),
    ).toEqual({ a: 'x', e: 'y', f: 0, g: false });
  });
  it('null-safe → {}', () => {
    expect(stripEmpty(undefined)).toEqual({});
    expect(stripEmpty(null)).toEqual({});
    expect(stripEmpty({})).toEqual({});
  });
});

describe('mergeDemoFirst', () => {
  it('demo-set keys WIN over the session selection (demo > session)', () => {
    const sessionParams = {
      engine: 'pipeline',
      lang: 'zh-CN',
      provider: 'minimax',
      voice: 'mm-zh-f',
    };
    const demoCfg = {
      scenario: 'd1',
      engine: 'nova-sonic',
      voice: 'matthew',
    };
    const out = mergeDemoFirst(sessionParams, demoCfg);
    // demo engine + voice win; provider/lang inherited from the session.
    expect(out.engine).toBe('nova-sonic');
    expect(out.voice).toBe('matthew');
    expect(out.provider).toBe('minimax');
    expect(out.lang).toBe('zh-CN');
    expect(out.scenario).toBe('d1');
  });

  it('a demo that sets none of engine/voice/provider inherits the session selection', () => {
    const sessionParams = { engine: 'pipeline', lang: 'en-US', provider: 'polly', voice: 'Joanna' };
    // Only scenario from the demo; engine/voice/provider null/absent → inherit.
    const out = mergeDemoFirst(sessionParams, { scenario: 'd2', engine: null, voice: null });
    expect(out).toEqual({
      engine: 'pipeline',
      lang: 'en-US',
      provider: 'polly',
      voice: 'Joanna',
      scenario: 'd2',
    });
  });

  it('empty demoCfg → pure session selection (manual /talk, unchanged)', () => {
    const sessionParams = { engine: 'pipeline', lang: 'zh-CN', provider: 'minimax', voice: 'mm-zh-f' };
    expect(mergeDemoFirst(sessionParams, {})).toEqual(sessionParams);
  });

  it('null/empty demo values do NOT clobber the session (demo-unset inherits)', () => {
    const sessionParams = { engine: 'pipeline', voice: 'mm-zh-f' };
    const out = mergeDemoFirst(sessionParams, { engine: '', voice: undefined, scenario: 's' });
    expect(out.engine).toBe('pipeline');
    expect(out.voice).toBe('mm-zh-f');
    expect(out.scenario).toBe('s');
  });
});

// Guard: the false tools→pipeline coupling (and its misleading "engine locked"
// tooltip) is fully removed. No source file under src/ may reference the removed
// i18n key anymore (tech_design §3/§4). The search token is assembled at runtime
// so this spec itself does NOT contain the literal key — a plain
// `grep <key> static/admin/src` returns truly zero, including this file.
describe('removed engine-lock i18n key is unreferenced', () => {
  it('grep over the whole src tree finds zero occurrences', () => {
    const fs = require('fs');
    const path = require('path');
    const token = 'engine' + 'LockedHint'; // never appears as a literal in source
    const srcDir = path.resolve(__dirname, '..'); // __tests__ → src
    const hits = [];
    const walk = (dir) => {
      for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
        const full = path.join(dir, entry.name);
        if (entry.isDirectory()) {
          walk(full);
        } else if (/\.(js|vue|ts)$/.test(entry.name)) {
          if (fs.readFileSync(full, 'utf8').includes(token)) {
            hits.push(full);
          }
        }
      }
    };
    walk(srcDir);
    expect(hits).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// Guest-link full-config helpers (tech_design §3, T2). Three pure mappings that
// the UsersView generate-link modal + GuestLanding consume; kept DOM-free so
// the prefill / body-assembly / forward-query behavior is unit-testable without
// mounting either view.
// ---------------------------------------------------------------------------

describe('guestPrefillFromDemo (modal prefill from GET /api/admin/demos/{id})', () => {
  it('carries the demo detail engine/voice/provider/lang for prefill', () => {
    // Shape mirrors _demo_detail_with_tools: flat top-level keys (+ extras we ignore).
    const detail = {
      id: 'it-helpdesk',
      label: 'IT Help Desk',
      engine: 'pipeline',
      provider: 'minimax',
      voice: 'Cantonese_ProfessionalHost（F)',
      lang: 'zh-HK',
      kb_chars: 1234,
      tools: ['ticket'],
    };
    expect(guestPrefillFromDemo(detail)).toEqual({
      engine: 'pipeline',
      provider: 'minimax',
      voice: 'Cantonese_ProfessionalHost（F)',
      lang: 'zh-HK',
    });
  });

  it('omits empty / null fields (a demo that sets only some config)', () => {
    expect(
      guestPrefillFromDemo({ lang: 'en-US', engine: null, voice: '', provider: 'polly' }),
    ).toEqual({ lang: 'en-US', provider: 'polly' });
  });

  it('an empty / undefined detail yields {} so the modal fields go blank', () => {
    expect(guestPrefillFromDemo(undefined)).toEqual({});
    expect(guestPrefillFromDemo(null)).toEqual({});
    expect(guestPrefillFromDemo({})).toEqual({});
  });
});

describe('guestLinkBody (createGuestLink request body)', () => {
  it('includes the non-empty lang/engine/voice/provider alongside ttl + scenario', () => {
    const body = guestLinkBody({
      ttl: 60,
      scenario: 'it-helpdesk',
      lang: 'zh-HK',
      engine: 'pipeline',
      voice: 'Cantonese_ProfessionalHost（F)',
      provider: 'minimax',
    });
    expect(body).toEqual({
      ttl_minutes: 60,
      scenario: 'it-helpdesk',
      lang: 'zh-HK',
      engine: 'pipeline',
      voice: 'Cantonese_ProfessionalHost（F)',
      provider: 'minimax',
    });
  });

  it('an empty scenario with no overrides → body with just ttl (no config keys)', () => {
    const body = guestLinkBody({ ttl: 30, scenario: null, lang: null, engine: '', voice: undefined });
    expect(body).toEqual({ ttl_minutes: 30 });
    for (const k of ['scenario', 'lang', 'engine', 'voice', 'provider']) {
      expect(body).not.toHaveProperty(k);
    }
  });

  it('carries only the subset that is set (partial overrides)', () => {
    expect(guestLinkBody({ ttl: 120, scenario: 'demo', engine: 'nova-sonic' })).toEqual({
      ttl_minutes: 120,
      scenario: 'demo',
      engine: 'nova-sonic',
    });
  });
});

describe('guestLaunchQuery (GuestLanding → Talk forward query)', () => {
  it('a full-config guest-login response → query carries all five keys', () => {
    const res = {
      username: 'guest',
      role: 'guest',
      scenario: 'it-helpdesk',
      lang: 'zh-HK',
      engine: 'pipeline',
      voice: 'Cantonese_ProfessionalHost（F)',
      provider: 'minimax',
    };
    expect(guestLaunchQuery(res)).toEqual({
      scenario: 'it-helpdesk',
      lang: 'zh-HK',
      engine: 'pipeline',
      voice: 'Cantonese_ProfessionalHost（F)',
      provider: 'minimax',
    });
  });

  it('a scenario-only (old) token response → only scenario', () => {
    const res = { username: 'guest', role: 'guest', scenario: 'demo', lang: null, engine: null, voice: null, provider: null };
    expect(guestLaunchQuery(res)).toEqual({ scenario: 'demo' });
  });

  it('a bare response (no scenario, no config) → undefined query', () => {
    expect(guestLaunchQuery({ username: 'guest', role: 'guest' })).toBeUndefined();
    expect(guestLaunchQuery({ scenario: null, lang: null })).toBeUndefined();
    expect(guestLaunchQuery(null)).toBeUndefined();
  });
});
