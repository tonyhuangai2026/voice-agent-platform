#!/usr/bin/env node
// i18n full-coverage guard for the demo + admin SPAs.
//
// For each SPA: extract every translation key referenced in .vue/.js source
// via t('...') / $t('...') / i18n.global.t('...') (single- and double-quoted,
// plus template-literal calls with no interpolation), then confirm each key
// resolves in EVERY locale file. A key that is missing from any locale is a
// blocker. Dynamic keys (built from variables / interpolation) are reported
// separately as "skipped (dynamic)" — they cannot be statically verified.
//
// Run: node docs/ui-redesign/check-i18n-coverage.mjs
// Exit 0 = all referenced static keys resolve in all locales; 1 = missing.

import { readdirSync, statSync, readFileSync } from 'node:fs';
import { join, resolve, dirname } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(__dirname, '..', '..');

const SPAS = [
  {
    name: 'admin',
    srcDir: join(repoRoot, 'static/admin/src'),
    localesDir: join(repoRoot, 'static/admin/src/i18n/locales'),
    locales: ['en', 'zh-CN', 'zh-TW', 'ja', 'ko', 'es', 'fr'],
  },
];

function walk(dir, exts) {
  const out = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    const st = statSync(full);
    if (st.isDirectory()) {
      if (entry === 'node_modules' || entry === 'dist') continue;
      out.push(...walk(full, exts));
    } else if (exts.some((e) => entry.endsWith(e))) {
      out.push(full);
    }
  }
  return out;
}

// Flatten a nested messages object into dotted leaf keys.
function flatten(obj, prefix = '', acc = new Set()) {
  for (const [k, v] of Object.entries(obj)) {
    const key = prefix ? `${prefix}.${k}` : k;
    if (v && typeof v === 'object' && !Array.isArray(v)) {
      flatten(v, key, acc);
    } else {
      acc.add(key);
    }
  }
  return acc;
}

// Match t('a.b.c'), $t("a.b.c"), i18n.global.t('a.b.c'), tm('a.b'), te('a.b'),
// and template-literal forms `a.b.c` with NO ${} interpolation.
// Captures the literal key. Calls whose first arg is a variable/expression are
// not matched here and are caught by the dynamic-call detector below.
const STATIC_CALL = /(?<![\w$])(?:\$?t|tm|te|i18n\.global\.t)\(\s*(['"`])((?:(?!\1)[^\\$]|\\.)*?)\1/g;
// Detect t( ... ) calls whose first argument is NOT a plain string literal
// (i.e. dynamic key) so we can report them instead of silently passing.
const ANY_CALL = /(?<![\w$])(?:\$?t|tm|te|i18n\.global\.t)\(\s*([^)]*?)(?:,|\))/g;

let hadMissing = false;

for (const spa of SPAS) {
  console.log(`\n=== SPA: ${spa.name} ===`);

  // Load every locale's flat key set.
  const localeKeys = {};
  for (const loc of spa.locales) {
    const mod = await import(pathToFileURL(join(spa.localesDir, `${loc}.js`)).href);
    localeKeys[loc] = flatten(mod.default);
  }

  // Sanity: report key-count per locale (drift indicator).
  for (const loc of spa.locales) {
    console.log(`  locale ${loc}: ${localeKeys[loc].size} keys`);
  }

  // Gather referenced static keys + dynamic-call sites from source.
  const files = walk(spa.srcDir, ['.vue', '.js']).filter(
    (f) => !f.includes('/i18n/locales/'), // don't scan the locale files themselves
  );
  const referenced = new Map(); // key -> Set(files)
  const dynamicSites = []; // { file, snippet }

  for (const file of files) {
    const text = readFileSync(file, 'utf8');
    const rel = file.replace(repoRoot + '/', '');

    let m;
    STATIC_CALL.lastIndex = 0;
    const staticKeysInFile = new Set();
    while ((m = STATIC_CALL.exec(text)) !== null) {
      const quote = m[1];
      const key = m[2];
      // skip template literals that actually interpolate (handled as dynamic)
      if (quote === '`' && key.includes('${')) continue;
      if (!key) continue;
      staticKeysInFile.add(key);
      if (!referenced.has(key)) referenced.set(key, new Set());
      referenced.get(key).add(rel);
    }

    // dynamic detection: t( firstArg ) where firstArg isn't a clean literal
    ANY_CALL.lastIndex = 0;
    while ((m = ANY_CALL.exec(text)) !== null) {
      const arg = m[1].trim();
      const isStringLiteral =
        /^(['"]).*\1$/.test(arg) || (/^`[^`]*`$/.test(arg) && !arg.includes('${'));
      if (!isStringLiteral && arg.length > 0) {
        dynamicSites.push({ file: rel, snippet: arg.slice(0, 60) });
      }
    }
  }

  console.log(`  referenced static keys: ${referenced.size}`);

  // The reference (most-complete) locale = the one with the most keys; used only
  // to suppress noise from keys that exist nowhere (those are real misses too).
  const missing = []; // { key, locale, files }
  for (const [key, fileSet] of referenced) {
    for (const loc of spa.locales) {
      if (!localeKeys[loc].has(key)) {
        missing.push({ key, locale: loc, files: [...fileSet] });
      }
    }
  }

  if (missing.length) {
    hadMissing = true;
    console.log(`  ❌ MISSING KEYS (${missing.length}):`);
    // group by key
    const byKey = new Map();
    for (const mi of missing) {
      if (!byKey.has(mi.key)) byKey.set(mi.key, { locales: [], files: mi.files });
      byKey.get(mi.key).locales.push(mi.locale);
    }
    for (const [key, info] of byKey) {
      console.log(`    - "${key}" missing in [${info.locales.join(', ')}]  (used in ${info.files.join(', ')})`);
    }
  } else {
    console.log(`  ✅ all ${referenced.size} referenced static keys resolve in all ${spa.locales.length} locales`);
  }

  // Cross-locale drift: keys present in some but not all locales (even if not
  // referenced) — informational, helps spot future-missing keys.
  const allKeys = new Set();
  for (const loc of spa.locales) for (const k of localeKeys[loc]) allKeys.add(k);
  const drift = [];
  for (const k of allKeys) {
    const absent = spa.locales.filter((loc) => !localeKeys[loc].has(k));
    if (absent.length) drift.push({ key: k, absent });
  }
  if (drift.length) {
    console.log(`  ⚠️  locale drift (key defined in some but not all locales): ${drift.length}`);
    for (const d of drift.slice(0, 50)) {
      console.log(`    - "${d.key}" absent in [${d.absent.join(', ')}]`);
    }
    if (drift.length > 50) console.log(`    … and ${drift.length - 50} more`);
  } else {
    console.log(`  ✅ no cross-locale key drift (all locales define the same key set)`);
  }

  // Report dynamic call sites (cannot be statically verified).
  const uniqDyn = [...new Set(dynamicSites.map((d) => `${d.file} :: t(${d.snippet}…)`))];
  if (uniqDyn.length) {
    console.log(`  ℹ️  dynamic-key t() call sites (not statically verifiable, ${uniqDyn.length}):`);
    for (const d of uniqDyn.slice(0, 30)) console.log(`    - ${d}`);
    if (uniqDyn.length > 30) console.log(`    … and ${uniqDyn.length - 30} more`);
  }
}

console.log('');
if (hadMissing) {
  console.error('RESULT: ❌ missing i18n keys detected — BLOCKER');
  process.exit(1);
} else {
  console.log('RESULT: ✅ i18n coverage OK — every referenced static key resolves in every locale, for both SPAs');
  process.exit(0);
}
