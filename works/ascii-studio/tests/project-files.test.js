'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.resolve(__dirname, '..');

test('start.cmd uses Windows CRLF line endings and stays ASCII-only', () => {
  const file = path.join(ROOT, 'start.cmd');
  const bytes = fs.readFileSync(file);

  assert.ok(bytes.length > 0, 'start.cmd should not be empty');
  assert.equal(bytes[0], 0x40, 'start.cmd should begin with @echo off');

  // A UTF-8 BOM or non-ASCII bytes can confuse the legacy cmd parser on
  // Chinese Windows installations. Keep this launcher strictly ASCII.
  for (let i = 0; i < bytes.length; i++) {
    assert.ok(bytes[i] < 128, 'non-ASCII byte in start.cmd at offset ' + i);
  }

  // Batch files need CRLF. LF-only files can be split incorrectly by cmd.exe
  // (especially around parentheses and `echo.` lines).
  for (let i = 0; i < bytes.length; i++) {
    if (bytes[i] !== 0x0a) continue;
    assert.ok(i > 0 && bytes[i - 1] === 0x0d, 'bare LF at offset ' + i);
  }

  const text = bytes.toString('ascii');
  assert.ok(text.startsWith('@echo off\r\n'), 'expected @echo off with CRLF');
  assert.ok(text.includes('node server.js\r\n'), 'start.cmd should start server.js');
  assert.ok(text.includes(':nonode\r\n'), 'start.cmd should have a friendly Node.js check');
});
