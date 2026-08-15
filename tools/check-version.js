#!/usr/bin/env node
// A blueprint and its page are a pair and share a version, but they are
// separate files and Home Assistant has no version field - it lives in prose.
// Nothing stops them drifting apart, and a version number that lies is worse
// than none: someone reports a bug against a release that never existed in
// that shape.
//
// This walks every blueprint folder, collects every version each file states,
// and fails if they disagree - within a file as well as across files.
//
//   node tools/check-version.js

'use strict';

const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..');

// Where a version may be declared. Deliberately narrow: a blanket search for
// three numbers would also catch the changelog's own history (### 1.3.0) and
// the blueprint's min_version, neither of which tracks the current release.
// Every match in a file counts, not just the first - an earlier version of this
// script stopped at the first one and happily passed a page whose footer had
// fallen two releases behind.
const PATTERNS = [
  { file: /\.yaml$/, find: /(?:^|\s)Version\s+(\d+\.\d+\.\d+)/gim },
  { file: /\.md$/, find: /^\*\*Version\s+(\d+\.\d+\.\d+)/gim },
  { file: /\.html$/, find: /^\s*var VERSION\s*=\s*'(\d+\.\d+\.\d+)'/gim },
];

function versionsIn(file) {
  const rule = PATTERNS.find((p) => p.file.test(file));
  if (!rule) return [];
  const text = fs.readFileSync(file, 'utf8');
  return [...text.matchAll(rule.find)].map((m) => m[1]);
}

function blueprintFolders() {
  return fs.readdirSync(ROOT, { withFileTypes: true })
    .filter((e) => e.isDirectory() && !e.name.startsWith('.') && e.name !== 'tools')
    .map((e) => e.name)
    .sort();
}

let failed = false;

for (const folder of blueprintFolders()) {
  const dir = path.join(ROOT, folder);
  const found = [];
  for (const name of fs.readdirSync(dir).sort()) {
    for (const version of versionsIn(path.join(dir, name))) {
      found.push({ name, version });
    }
  }

  if (!found.length) {
    console.log(`${folder}\n  no version stated - skipped\n`);
    continue;
  }

  const versions = [...new Set(found.map((f) => f.version))];
  const agree = versions.length === 1;
  if (!agree) failed = true;

  // Point at the odd one out, not at whichever file happened to be read first:
  // the one most likely to be wrong is what the majority disagrees with. A
  // straight tie has no majority, so nothing gets singled out.
  const count = (v) => found.filter((f) => f.version === v).length;
  const ranked = [...versions].sort((a, b) => count(b) - count(a));
  const majority = ranked.length > 1 && count(ranked[0]) > count(ranked[1]) ? ranked[0] : null;

  console.log(folder);
  for (const f of found) {
    const odd = !agree && (majority ? f.version !== majority : true);
    console.log(`  ${f.name.padEnd(30)} ${f.version}${odd ? '   <- differs' : ''}`);
  }
  console.log('');
}

if (failed) {
  console.error('FAILED - versions disagree');
  process.exit(1);
}
console.log('ok - every blueprint agrees with itself');
