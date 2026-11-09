// Actual installed Chromium + local HTTP form; no fake browser or desktop input.
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { createRequire } from 'node:module';
import { mkdir, writeFile, readFile } from 'node:fs/promises';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { resolve } from 'node:path';
import { BackgroundBrowser } from './browser-background.mjs';

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.WINDOW_PILOT_PLAYWRIGHT || 'playwright');
const executablePath = process.env.WINDOW_PILOT_BROWSER;
assert(executablePath, 'WINDOW_PILOT_BROWSER must name the installed test browser');
const evidence = resolve('.local/browser-form', `run-${Date.now()}`);
await mkdir(evidence, { recursive: true });
const records = [];
let externalRequests = 0, submitted = [], slowRequests = 0, cancelRequests = 0;
const outside = createServer((_, res) => { externalRequests++; res.end('outside'); });
outside.listen(0, '127.0.0.1'); await once(outside, 'listening');
const html = `<!doctype html><meta charset="utf-8"><title>Window Pilot local form</title>
<style>body{font:20px sans-serif;margin:48px;background:#f5f7fa;color:#182d40}label{display:block;margin:20px 0}input,button{font:inherit;padding:8px}output{display:block;margin-top:24px}</style>
<h1>后台表单验收</h1><form id="form"><label>姓名 <input name="name" value="原姓名"></label>
<label>备注 <input name="note" value="原备注"></label><label>密码 <input type="password" value="private-fixture"></label>
<button type="submit">保存表单</button></form><output id="result">尚未提交</output>
<button id="slow" onclick="location.href='/slow'">慢响应测试</button>
<button id="cancel" onclick="location.href='/cancel'">取消测试</button>
<img alt="blocked external resource" src="http://127.0.0.1:${outside.address().port}/blocked">
<img alt="blocked redirect" src="/redirect">
<script>form.onsubmit=async e=>{e.preventDefault();const data=Object.fromEntries(new FormData(form));
const r=await fetch('/submit',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
document.querySelector('#result').textContent=await r.text();};</script>`;
const server = createServer(async (req, res) => {
  if (req.url === '/slow') { slowRequests++; return; }
  if (req.url === '/cancel') { cancelRequests++; return; }
  if (req.url === '/redirect') {
    res.writeHead(302, { Location: `http://127.0.0.1:${outside.address().port}/redirected` }); res.end(); return;
  }
  if (req.url === '/submit') {
    let data = ''; for await (const part of req) data += part;
    const parsed = JSON.parse(data); submitted.push(parsed);
    res.writeHead(200, { 'Content-Type': 'text/plain; charset=utf-8' });
    res.end(`已保存：${parsed.name} / ${parsed.note}`); return;
  }
  res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' }); res.end(html);
});
server.listen(0, '127.0.0.1'); await once(server, 'listening');
const url = `http://127.0.0.1:${server.address().port}/`;
const adapter = new BackgroundBrowser({ chromium, executablePath });
let monitor, monitorExit;
const stopFile = resolve(evidence, 'monitor-stop');
const monitorOutput = resolve(evidence, 'desktop.json');
function node(state, name) { return state.nodes.find(n => n.name === name); }
async function act(state, control, action, value) {
  return adapter.act({ observation_id: state.observation_id, control_id: control.control_id, action, value });
}
try {
  await assert.rejects(adapter.open({ url: 'https://example.com', purpose: 'test' }), /LOCAL_ORIGIN/);
  records.push({ open: await adapter.open({ url, purpose: 'user-selected local background form acceptance' }) });
  if (process.env.WINDOW_PILOT_PYTHON) {
    monitor = spawn(process.env.WINDOW_PILOT_PYTHON,
      [resolve('scripts/browser-desktop-monitor.py'), String(adapter.pid), stopFile, monitorOutput],
      { windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] });
    monitorExit = once(monitor, 'exit');
  }
  let state = await adapter.observe();
  assert.equal(node(state, '姓名').value, '原姓名');
  assert.equal(state.nodes.find(n => n.password).value, null);
  assert(!JSON.stringify(state.nodes).includes('private-fixture'));
  await writeFile(resolve(evidence, 'before.png'), Buffer.from(state.image, 'base64'));
  let result = await act(state, node(state, '姓名'), 'set_value', '后台用户');
  assert.equal(result.status, 'dispatched'); records.push(result);
  await assert.rejects(act(state, node(state, '备注'), 'set_value', 'stale'), /STALE_OBSERVATION/);
  state = await adapter.observe();
  assert.equal(node(state, '姓名').value, '后台用户');
  assert.equal(node(state, '备注').value, '原备注'); // untouched control is an independent check
  result = await act(state, node(state, '备注'), 'set_value', '用户可继续使用前台电脑');
  assert.equal(result.status, 'dispatched'); records.push(result);
  state = await adapter.observe();
  result = await act(state, node(state, '保存表单'), 'click');
  assert.equal(result.status, 'dispatched'); records.push(result);
  const deadline = Date.now() + 3000;
  do { state = await adapter.observe(); if (state.document_text.includes('已保存：')) break; }
  while (Date.now() < deadline);
  assert(state.document_text.includes('已保存：后台用户 / 用户可继续使用前台电脑'));
  assert.deepEqual(submitted, [{ name: '后台用户', note: '用户可继续使用前台电脑' }]);
  assert.equal(externalRequests, 0);
  await writeFile(resolve(evidence, 'after.png'), Buffer.from(state.image, 'base64'));
  records.push({ verified_server_submissions: submitted.length, external_requests: externalRequests,
    document_text: state.document_text });
  result = await act(state, state.nodes.find(n => n.password), 'set_value', 'must-not-send');
  assert.equal(result.status, 'rejected'); assert.equal(result.action_attempted, false);
  state = await adapter.observe();
  // Actual navigation begins but server never responds: no fabricated transport result.
  result = await act(state, node(state, '慢响应测试'), 'click');
  assert.equal(result.status, 'unknown', JSON.stringify(result));
  assert.equal(slowRequests, 1); assert.equal(adapter.status.faulted, true);
  await assert.rejects(act(state, node(state, '慢响应测试'), 'click'), /INPUT_UNKNOWN/);
  assert.equal(slowRequests, 1);
  records.push({ unknown: result, no_replay_requests: slowRequests });
  await adapter.stop();
  assert.equal(adapter.status.owned_process_exited, true);
  await assert.rejects(adapter.observe(), /STOPPED/);
  await assert.rejects(adapter.open({ url, purpose: 'no restart' }), /STOPPED/);
  if (monitor) {
    await writeFile(stopFile, 'stop'); await monitorExit;
    const report = JSON.parse(await readFile(monitorOutput, 'utf8'));
    assert(report.samples > 0); assert(report.foreground_available_samples > 0, 'interactive desktop required');
    assert.equal(report.foreground_target_hits, 0); assert.equal(report.visible_target_window_hits, 0);
    records.push({ desktop: report });
  }
  const cancellation = new BackgroundBrowser({ chromium, executablePath });
  try {
    await cancellation.open({ url, purpose: 'separate in-flight cancellation test, not a retry' });
    const observed = await cancellation.observe();
    const pending = cancellation.act({ observation_id: observed.observation_id,
      control_id: node(observed, '取消测试').control_id, action: 'click' });
    const limit = Date.now() + 800;
    while (cancelRequests === 0 && Date.now() < limit) await new Promise(r => setTimeout(r, 10));
    assert.equal(cancelRequests, 1);
    assert.equal(cancellation.status.in_flight, true);
    await cancellation.stop();
    assert.equal((await pending).status, 'unknown');
    assert.equal(cancellation.status.owned_process_exited, true);
    assert.equal(cancellation.status.stopped, true);
    assert.equal(cancelRequests, 1);
    records.push({ in_flight_cancelled: true, process_exited: true });
  } finally { await cancellation.stop(); }
  console.log(JSON.stringify({ status: 'passed', evidence, checks: [
    'real form set_value twice then one submit', 'server record and rendered result agree',
    'stale observation refused', 'password action refused', 'other origin blocked',
    'real navigation timeout faults and cannot replay', 'terminal stop and cleanup', 'in-flight cancellation and process exit',
    monitor ? 'interactive desktop sampling' : 'desktop not sampled'] }));
} finally {
  await adapter.stop();
  if (monitor) { await writeFile(stopFile, 'stop'); await monitorExit; }
  await writeFile(resolve(evidence, 'results.json'), JSON.stringify({ status: adapter.status, records }, null, 2));
  server.closeAllConnections(); server.close(); outside.closeAllConnections(); outside.close();
}
