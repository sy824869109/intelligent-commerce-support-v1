// Exercise the compiler, bundler and real browser without implementing an application.
import assert from 'node:assert/strict';
import ts from 'typescript';
import { build } from 'vite';
import { chromium } from '@playwright/test';
import { version, reactive } from 'vue';
import { createPinia } from 'pinia';
import { createMemoryHistory, createRouter } from 'vue-router';
import axios from 'axios';

assert.equal(version, '3.5.42');
assert.equal(reactive({ value: 1 }).value, 1);
assert.ok(createPinia());
assert.ok(createRouter({ history: createMemoryHistory(), routes: [] }));
assert.equal(typeof axios.get, 'function');
const result = ts.transpileModule('const n: number = 42;', {
  compilerOptions: { target: ts.ScriptTarget.ES2022 },
});
assert.ok(result.outputText.includes('42'));
await build({
  configFile: false,
  logLevel: 'error',
  build: { write: false, lib: { entry: new URL('./fixture.ts', import.meta.url).pathname.replace(/^\/(.:)/, '$1'), formats: ['es'] } },
});
const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage();
  await page.setContent('<h1>Environment ready</h1>');
  assert.equal(await page.locator('h1').textContent(), 'Environment ready');
} finally { await browser.close(); }
console.log('Frontend environment PASS: Vue, Pinia, Router, Axios, TypeScript, Vite, Chromium');
