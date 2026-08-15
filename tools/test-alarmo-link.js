#!/usr/bin/env node
// Exercises the logic inside alarmo-link.html without a browser: which mode the
// fragment selects, ID generation, how the link is assembled and taken apart
// again, the three copy paths, and language selection.
//
// The page is a single file with no build step, so the script block is pulled
// straight out of the HTML and run in a sandbox against a hand-rolled DOM. That
// keeps the page dependency-free while still leaving a check behind: the sort
// of thing that "I looked at it in the browser" cannot cover - a comma inside a
// name, a malformed percent-escape, a second language preference.
//
//   node tools/test-alarmo-link.js

'use strict';

const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const PAGE = path.join(__dirname, '..', 'alarmo-link', 'alarmo-link.html');
const html = fs.readFileSync(PAGE, 'utf8');
const block = html.match(/<script>([\s\S]*?)<\/script>/);
assert.ok(block, 'no <script> block in ' + PAGE);
const SRC = block[1];

// The stubs below mirror the markup. If an element or a data-i18n key is added
// to the page without being added here, the run fails rather than silently
// skipping it.

// Elements the markup gives an id
const IDS = ['panel', 'status', 'arm', 'disarm', 'setup', 'result',
             'arm-id', 'disarm-id', 'link', 'copy', 'generate',
             'copy-arm', 'copy-disarm', 'panel-title', 'alarm-name', 'alarm-lang',
             'version'];
// Translated elements that have no id
const EXTRA = ['h1-setup', 'hint', 'label-arm', 'label-disarm', 'label-link'];

// [element, i18n key] - must match the markup
const I18N = [
  ['arm', 'arm'], ['disarm', 'disarm'],
  ['h1-setup', 'setupTitle'], ['hint', 'setupHint'], ['generate', 'generate'],
  ['label-arm', 'labelArm'], ['label-disarm', 'labelDisarm'],
  ['label-link', 'labelLink'], ['copy', 'copyLink'],
];
const I18N_LABEL = [
  ['copy-arm', 'copyArmLabel'], ['copy-disarm', 'copyDisarmLabel'],
];

function element() {
  const classes = new Set();
  return {
    hidden: true, textContent: '', className: '', title: '', aria: '',
    classList: {
      add: (c) => classes.add(c),
      remove: (c) => classes.delete(c),
      has: (c) => classes.has(c),
    },
    setAttribute(k, v) { if (k === 'aria-label') this.aria = v; },
  };
}

function run(hash, languages = ['en-US'], onFetch) {
  const els = {};
  for (const id of [...IDS, ...EXTRA]) els[id] = element();
  const root = {};
  const clipboard = [];
  els['alarm-name'].value = '';
  const options = [];
  els['alarm-lang'].value = '';
  els['alarm-lang'].appendChild = (o) => options.push(o);
  const doc = {
    createElement: () => ({ value: '', textContent: '' }),
    title: 'Alarm',
    documentElement: root,
    getElementById: (id) => els[id],
    querySelectorAll: (sel) => {
      const i18n = sel === '[data-i18n]';
      const attr = i18n ? 'data-i18n' : 'data-i18n-label';
      return (i18n ? I18N : I18N_LABEL).map(([elKey, key]) => {
        els[elKey].getAttribute = (a) => (a === attr ? key : null);
        return els[elKey];
      });
    },
    createRange: () => ({ selectNodeContents() {} }),
  };

  vm.runInNewContext(SRC, {
    location: { hash, origin: 'https://ha.example.com', pathname: '/local/alarmo-link.html' },
    crypto,
    setTimeout,
    fetch: onFetch || (() => Promise.resolve({ ok: true })),
    navigator: {
      languages,
      // Synchronously resolving thenable, so the test needs no await
      clipboard: { writeText: (t) => { clipboard.push(t); return { then: (ok) => ok() }; } },
    },
    document: doc,
    window: { getSelection: () => ({ removeAllRanges() {}, addRange() {} }) },
  });

  return { els, root, clipboard, doc, options };
}

// --- Which mode the fragment selects -------------------------------------------------------------
for (const [hash, mode] of [
  ['', 'setup'],
  ['#', 'setup'],
  ['#onlyone', 'setup'],
  ['#a,', 'setup'],
  ['#,b', 'setup'],
  ['#a,b', 'panel'],
  ['#a,b,c', 'panel'],   // third value is the name
]) {
  const { els } = run(hash);
  assert.strictEqual(els[mode].hidden, false, `hash ${JSON.stringify(hash)} -> ${mode}`);
  const other = mode === 'setup' ? 'panel' : 'setup';
  assert.strictEqual(els[other].hidden, true, `hash ${JSON.stringify(hash)} zeigt ${other}`);
}
console.log('mode selection: ok');

// --- ID generation ----------------------------------------------------------
const ALPHABET = /^[A-Za-z0-9_-]{32}$/;
const { els } = run('');
const seen = new Set();
for (let i = 0; i < 500; i++) {
  els.generate.onclick();
  const a = els['arm-id'].textContent;
  const d = els['disarm-id'].textContent;
  assert.match(a, ALPHABET, 'arm ID shape');
  assert.match(d, ALPHABET, 'disarm ID shape');
  assert.notStrictEqual(a, d, 'arm and disarm must differ');
  seen.add(a).add(d);
}
assert.strictEqual(seen.size, 1000, 'all 1000 IDs distinct');
console.log('ID generation: ok  (1000 IDs, 32 chars each, all distinct)');

// --- Even spread over the alphabet (no modulo bias) -----------------
const counts = new Map();
for (const id of seen) for (const c of id) counts.set(c, (counts.get(c) || 0) + 1);
assert.strictEqual(counts.size, 64, 'every one of the 64 characters occurs');
const exp = (1000 * 32) / 64;
const worst = Math.max(...[...counts.values()].map((n) => Math.abs(n - exp) / exp));
assert.ok(worst < 0.35, `skewed: ${(worst * 100).toFixed(1)}% off expected`);
console.log(`spread: ok  (worst character ${(worst * 100).toFixed(1)}% off expected)`);

// --- Assembling the link ------------------------------------------------------------
els.generate.onclick();
assert.strictEqual(
  els.link.textContent,
  `https://ha.example.com/local/alarmo-link.html#${els['arm-id'].textContent},${els['disarm-id'].textContent}`,
  'link is origin + pathname + fragment'
);
assert.strictEqual(els.result.hidden, false, 'result block becomes visible');
console.log('link assembly: ok');

// --- Copying --------------------------------------------------------------
{
  const { els, clipboard } = run('');
  els.generate.onclick();
  els['copy-arm'].onclick();
  els['copy-disarm'].onclick();
  els.copy.onclick();
  assert.deepStrictEqual(clipboard, [
    els['arm-id'].textContent,
    els['disarm-id'].textContent,
    els.link.textContent,
  ], 'each button copies its own field');
  assert.ok(els['copy-arm'].classList.has('ok'), 'icon confirms with a tick');
  assert.strictEqual(els.copy.textContent, 'Copied', 'link button confirms with a label');
  console.log('copying: ok  (2 icons + link button, each its own value)');
}

// --- Name carried by the link -----------------------------------------------------
{
  // with no name the heading is left alone
  const plain = run('#A,B');
  assert.strictEqual(plain.els['panel-title'].textContent, '');
  assert.strictEqual(plain.doc.title, 'Alarm');

  // with a name: heading and tab title
  for (const [encoded, expected] of [
    ['Wohnung', 'Wohnung'],
    ['B%C3%BCro', 'Büro'],                    // umlaut
    ['Haus%2C%20Garage', 'Haus, Garage'],     // a comma inside splits nothing
    ['%F0%9F%8F%A0%20Zuhause', '🏠 Zuhause'], // emoji
  ]) {
    const { els, doc } = run('#A,B,' + encoded);
    assert.strictEqual(els['panel-title'].textContent, expected, encoded);
    assert.strictEqual(doc.title, expected, 'tab title ' + encoded);
    assert.strictEqual(els.panel.hidden, false, 'buttons still there');
  }

  // a malformed escape must not take the page down
  const broken = run('#A,B,%E0%A4%A');
  assert.strictEqual(broken.els.panel.hidden, false, 'buttons survive a broken name');
  assert.strictEqual(broken.els['panel-title'].textContent, '', 'falls back to the default');

  console.log('name from the link: ok  (umlaut, comma, emoji, malformed escape)');
}

// --- Name reaches the generated link -----------------------------------------
{
  const { els } = run('', ['de-DE']);
  assert.strictEqual(els['alarm-name'].placeholder, 'Alarm', 'placeholder set');

  els.generate.onclick();
  const without = els.link.textContent;
  assert.strictEqual(without.split(',').length, 2, 'two values when unnamed');

  els['alarm-name'].value = '  Haus, Müller  ';   // padding and a comma
  els.generate.onclick();
  const parts = els.link.textContent.split('#')[1].split(',');
  assert.strictEqual(parts.length, 3, 'three values when named');
  assert.strictEqual(decodeURIComponent(parts[2]), 'Haus, Müller', 'trimmed and encoded');

  // round trip: the generated link must label the button page correctly
  const back = run('#' + els.link.textContent.split('#')[1]);
  assert.strictEqual(back.els['panel-title'].textContent, 'Haus, Müller');
  console.log('name in the generated link: ok  (round trip generate -> open)');
}

// --- Language selection from the browser ------------------------------------------------------------
for (const [languages, lang, armText] of [
  [['en-US'], 'en', '🔒 Arm'],
  [['de-DE', 'en'], 'de', '🔒 Scharf schalten'],
  [['de'], 'de', '🔒 Scharf schalten'],
  [['DE-de'], 'de', '🔒 Scharf schalten'],          // Grossschreibung
  [['fr-FR'], 'en', '🔒 Arm'],                      // unbekannt -> Englisch
  [['fr-FR', 'de-DE'], 'de', '🔒 Scharf schalten'], // zweite Wahl zaehlt
]) {
  const { els, root } = run('', languages);
  assert.strictEqual(root.lang, lang, `${languages} -> lang=${lang}`);
  assert.strictEqual(els.arm.textContent, armText, `${languages} -> button label`);
  assert.ok(els.hint.textContent.length > 40, 'hint text filled in');
  assert.ok(els['copy-arm'].aria.length > 5, 'aria-label filled in');
  assert.strictEqual(els['copy-arm'].title, lang === 'de' ? 'Kopieren' : 'Copy');
}
console.log('language selection: ok  (en, de, fallback, second preference)');

// --- Language in the link is optional and beats the browser -----------------
{
  // browser German, link forces English
  const forced = run('#A,B,,en', ['de-DE']);
  assert.strictEqual(forced.els.arm.textContent, '🔒 Arm', 'link beats browser');
  assert.strictEqual(forced.root.lang, 'en');
  assert.strictEqual(forced.els['panel-title'].textContent, '', 'empty name slot');

  // browser English, link forces German, with a name
  const both = run('#A,B,Wohnung,de', ['en-US']);
  assert.strictEqual(both.els.arm.textContent, '🔒 Scharf schalten');
  assert.strictEqual(both.els['panel-title'].textContent, 'Wohnung');

  // upper case, and an unknown code
  assert.strictEqual(run('#A,B,,DE', ['en-US']).root.lang, 'de', 'DE == de');
  assert.strictEqual(run('#A,B,,xx', ['en-US']).root.lang, 'en', 'unknown -> browser');
  assert.strictEqual(run('#A,B,,xx', ['de-DE']).root.lang, 'de', 'unknown -> browser');

  // with no fourth value the browser still decides
  assert.strictEqual(run('#A,B,Wohnung', ['de-DE']).root.lang, 'de');
  console.log('language in the link: ok  (forced, empty name, unknown, fallback)');
}

// --- All four combinations, generated and opened again --------------------
{
  for (const [name, chosen, expectName, expectLang] of [
    ['',        '',   '',        'de'],  // neither -> browser
    ['Wohnung', '',   'Wohnung', 'de'],
    ['',        'en', '',        'en'],
    ['Wohnung', 'en', 'Wohnung', 'en'],
  ]) {
    const { els, options } = run('', ['de-DE']);
    assert.deepStrictEqual(options.map((o) => o.value), ['', 'en', 'de'],
      'dropdown built from STRINGS');
    els['alarm-name'].value = name;
    els['alarm-lang'].value = chosen;
    els.generate.onclick();

    const back = run('#' + els.link.textContent.split('#')[1], ['de-DE']);
    assert.strictEqual(back.els['panel-title'].textContent, expectName,
      `name for (${name}|${chosen})`);
    assert.strictEqual(back.root.lang, expectLang, `language for (${name}|${chosen})`);
    assert.strictEqual(back.els.panel.hidden, false, 'buttons present');
  }
  console.log('four combinations: ok  (round trip generate -> open)');
}

// --- The file states its version once, and shows it on the setup screen -----
{
  const stated = SRC.match(/^\s*var VERSION\s*=\s*'(\d+\.\d+\.\d+)'/m);
  assert.ok(stated, 'no VERSION constant in the page');
  assert.strictEqual(SRC.match(/var VERSION\s*=/g).length, 1,
    'VERSION must be stated once - a second one can disagree with the first');

  const setup = run('');
  assert.strictEqual(setup.els.version.textContent, 'Alarmo Link ' + stated[1],
    'setup screen shows the version');

  // The button page is used in a hurry by someone who did not install this.
  const panel = run('#A,B');
  assert.strictEqual(panel.els.version.textContent, '', 'button page shows no version');
  console.log(`version: ok  (stated once as ${stated[1]}, setup only)`);
}

// --- Status messages reach the surface, in the chosen language ---------
// fetch resolves asynchronously, so let a tick pass after each click.
const settle = () => new Promise((r) => setTimeout(r, 0));

(async () => {
  const ok = run('#A,B', ['de-DE']);
  ok.els.arm.onclick();
  assert.strictEqual(ok.els.status.textContent, 'Einen Moment ...', 'interim message');
  assert.ok(ok.els.arm.disabled, 'button locked while sending');
  await settle();
  assert.strictEqual(ok.els.status.textContent, 'Scharfschalten gesendet');
  assert.ok(!ok.els.arm.disabled, 'button released afterwards');

  ok.els.disarm.onclick();
  await settle();
  assert.strictEqual(ok.els.status.textContent, 'Unscharfschalten gesendet');

  const fail = run('#A,B', ['de-DE'], () => Promise.reject(new Error('x')));
  fail.els.arm.onclick();
  await settle();
  assert.strictEqual(fail.els.status.textContent, 'Hat nicht geklappt - bitte anrufen');
  assert.strictEqual(fail.els.status.className, 'err');

  // an HTTP error must surface just like a dropped connection
  const http = run('#A,B', ['de-DE'], () => Promise.resolve({ ok: false, status: 404 }));
  http.els.arm.onclick();
  await settle();
  assert.strictEqual(http.els.status.textContent, 'Hat nicht geklappt - bitte anrufen');

  console.log('status messages: ok  (success, network failure, HTTP 404 - German)');
  console.log('\nall green');
})();
