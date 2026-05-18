#!/usr/bin/env node
/**
 * Test: verify Greek line search works correctly.
 * Simulates the lines-tab.js search flow.
 * Run: node test_lines_search.js
 */

const fs = require('fs');

// Load utils.js functions
const TOKEN_RE = /[\p{L}]+(?:[᾽'][\p{L}]+)?/gu;

function normalizeTerm(term) {
  return String(term || '').normalize('NFC').toLowerCase().replace(/\s+/g, ' ').trim();
}

function tokenizeLineText(text) {
  const m = String(text || '').normalize('NFC').toLowerCase().match(TOKEN_RE);
  return m ? m : [];
}

function getLineNgrams(tokens, n) {
  const out = [];
  for (let i = 0; i <= tokens.length - n; i++) {
    out.push(tokens.slice(i, i + n).join(' '));
  }
  return out;
}

// Load line data
const allLines = JSON.parse(fs.readFileSync('docs/lines/all_lines.json', 'utf8'));

// Test cases
const tests = [
  { query: 'καὶ', mode: 'exact', n: 1, minExpected: 100 },
  { query: 'αὐτὰρ', mode: 'exact', n: 1, minExpected: 100 },
  { query: 'μῆνιν', mode: 'exact', n: 1, minExpected: 1 },
  // NFD input (decomposed) — simulates browser copy-paste
  { query: 'καὶ'.normalize('NFD'), mode: 'exact', n: 1, minExpected: 100, label: 'καὶ (NFD input)' },
  { query: 'αὐτὰρ'.normalize('NFD'), mode: 'exact', n: 1, minExpected: 100, label: 'αὐτὰρ (NFD input)' },
  // Regex
  { query: 'καὶ', mode: 'regex', n: 1, minExpected: 100 },
  { query: '^μῆνιν$', mode: 'regex', n: 1, minExpected: 1 },
  // Bigram
  { query: 'καὶ τὰ', mode: 'exact', n: 2, minExpected: 1 },
];

let passed = 0;
let failed = 0;

for (const test of tests) {
  const label = test.label || test.query;
  const n = test.n;

  let matchCount = 0;

  if (test.mode === 'exact') {
    const queryTokens = normalizeTerm(test.query).split(/\s+/).filter(Boolean).slice(0, n);
    const queryNgram = queryTokens.join(' ');

    if (!queryNgram) {
      console.log(`FAIL: "${label}" — queryNgram is empty after normalization`);
      failed++;
      continue;
    }

    for (const line of allLines) {
      const tokens = tokenizeLineText(line.text);
      const ngrams = getLineNgrams(tokens, n);
      for (const ng of ngrams) {
        if (ng === queryNgram) {
          matchCount++;
          break;
        }
      }
    }
  } else if (test.mode === 'regex') {
    const pattern = new RegExp(normalizeTerm(test.query), 'i');
    for (const line of allLines) {
      const tokens = tokenizeLineText(line.text);
      const ngrams = getLineNgrams(tokens, n);
      for (const ng of ngrams) {
        if (pattern.test(ng)) {
          matchCount++;
          break;
        }
      }
    }
  }

  if (matchCount >= test.minExpected) {
    console.log(`PASS: "${label}" (${test.mode}, n=${n}) — ${matchCount} lines matched (≥${test.minExpected})`);
    passed++;
  } else {
    console.log(`FAIL: "${label}" (${test.mode}, n=${n}) — ${matchCount} lines matched (expected ≥${test.minExpected})`);
    failed++;
  }
}

console.log(`\n${passed} passed, ${failed} failed out of ${tests.length} tests`);
process.exit(failed > 0 ? 1 : 0);
