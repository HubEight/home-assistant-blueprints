#!/usr/bin/env node
// Every blueprint carries its version in more than one file, and Home Assistant
// has no version field for blueprints - it lives in prose. So nothing stops the
// files from drifting apart, and a version number that lies is worse than none:
// someone reports a bug against a release that never existed in that shape.
//
// This walks every blueprint folder, pulls the version out of each file that
// states one, and fails if they disagree.
//
//   node tools/check-version.js

'use strict';

const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..');
const SEMVER = /(\d+\.\d+\.\d+)/;

// Where a version may appear. A file that states none is not an error - only a
// disagreement is. Adding a file type here is enough to cover it.
const PATTERNS = [
  { file: /\.yaml$/, find: /^\s*(?:description:.*?)?Version\s+(\d+\.\d+\.\d+)/mi },
  { file: /\.md$/, find: /^\*\*Version\s+(\d+\.\d+\.\d+)/mi },
  { file: /\.html$/, find: /^<!--.*?(\d+\.\d+\.\d+)/mi },
];

function versionIn(file) {
  const rule = PATTERNS.find((p) => p.file.test(file));
  if (!rule) return null;
  const match = fs.readFileSync(file, 'utf8').match(rule.find);
  return match ? match[1] : null;
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
  const found = fs.readdirSync(dir)
    .map((name) => ({ name, version: versionIn(path.join(dir, name)) }))
    .filter((f) => f.version);

  if (!found.length) {
    console.log(`${folder}\n  no version stated - skipped\n`);
    continue;
  }

  const versions = [...new Set(found.map((f) => f.version))];
  const agree = versions.length === 1;
  if (!agree) failed = true;

  // Point at the odd one out, not at whichever file happened to be read first:
  // the file most likely to be wrong is the one the majority disagrees with.
  // A straight tie has no majority, so nothing gets singled out.
  const count = (v) => found.filter((f) => f.version === v).length;
  const ranked = [...versions].sort((a, b) => count(b) - count(a));
  const majority = ranked.length > 1 && count(ranked[0]) > count(ranked[1]) ? ranked[0] : null;

  console.log(folder);
  for (const f of found) {
    const odd = !agree && (majority ? f.version !== majority : true);
    console.log(`  ${f.name.padEnd(30)} ${f.version}${odd ? '   <- differs' : ''}`);
  }

  // A single file stating the version cannot disagree with itself, but it also
  // means a sibling lost its version line - worth saying out loud.
  if (agree && found.length === 1) {
    console.log('  only one file states a version');
  }
  console.log('');
}

if (failed) {
  console.error('FAILED - versions disagree');
  process.exit(1);
}
console.log('ok - every blueprint agrees with itself');
