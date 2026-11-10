import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { once } from 'node:events';
import { createRequire } from 'node:module';
import { mkdir, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { BrowserSession, withBrowserSession } from './browser-session.mjs';

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.WINDOW_PILOT_PLAYWRIGHT || 'playwright');
const options = { chromium, executablePath: process.env.WINDOW_PILOT_BROWSER };
assert(options.executablePath, 'WINDOW_PILOT_BROWSER required');
let submissions = [], slowRequests = 0;
const server = createServer(async (req, res) => {
  if (req.url === '/slow') { slowRequests++; return; }
  if (req.url === '/submit') {
    let body = ''; for await (const chunk of req) body += chunk;
    submissions.push(body); res.end('saved:' + body); return;
  }
  res.setHeader('Content-Type', 'text/html; charset=utf-8');
  res.end(`<label>Name<input name="name" value="original"></label>
    <button onclick="fetch('/submit',{method:'POST',body:document.querySelector('input').value}).then(r=>r.text()).then(t=>document.querySelector('output').textContent=t)">Save</button>
    <button onclick="location.href='/slow'">Slow</button><output>not saved</output>`);
});
server.listen(0, '127.0.0.1'); await once(server, 'listening');
const url = `http://127.0.0.1:${server.address().port}/`;
const session = new BrowserSession(options), records = [];
const evidence = resolve('.local/browser-session', `run-${Date.now()}`);
await mkdir(evidence, { recursive: true });
const control = (state, name) => state.nodes.find(n => n.name === name).control_id;
try {
  let response = await session.begin({ url, purpose: 'owned local form workflow acceptance' });
  await writeFile(resolve(evidence, 'before.png'), Buffer.from(response.state.image, 'base64'));
  response = await session.step({ control_id: control(response.state, 'Name'), action: 'set_value', value: 'background' });
  assert.equal(response.action.status, 'dispatched');
  assert.equal(response.effect_verified, false);
  assert.equal(response.state.nodes.find(n => n.name === 'Name').value, 'background');
  response = await session.step({ control_id: control(response.state, 'Save'), action: 'click' });
  assert.equal(response.action.status, 'dispatched');
  // Only read again if rendering is still pending; never click again.
  const deadline = Date.now() + 3000;
  while (!response.state.document_text.includes('saved:background') && Date.now() < deadline)
    response = await session.observe();
  assert(response.state.document_text.includes('saved:background'));
  assert.deepEqual(submissions, ['background']);
  await writeFile(resolve(evidence, 'after.png'), Buffer.from(response.state.image, 'base64'));
  records.push({ single_submission: true, observed_value: 'background', effect_verified_flag: false });
  const slow = control(response.state, 'Slow');
  response = await session.step({ control_id: slow, action: 'click' });
  assert.equal(response.action.status, 'unknown');
  assert.equal(response.input_blocked, true);
  assert.equal(slowRequests, 1);
  await assert.rejects(session.step({ control_id: slow, action: 'click' }), /INPUT_BLOCKED/);
  assert.equal(slowRequests, 1);
  records.push({ unknown: response.action, observation_status: response.observation_status, no_replay: true });
  await session.end(); await session.end();
  assert.equal(session.status.owned_process_exited, true);
  await assert.rejects(session.observe(), /SESSION_ENDED/);
  let cleanup;
  await assert.rejects(withBrowserSession(options, async owned => {
    cleanup = owned;
    await owned.begin({ url, purpose: 'callback exception cleanup' });
    throw new Error('task failed');
  }), /task failed/);
  assert.equal(cleanup.status.owned_process_exited, true);
  records.push({ idempotent_end: true, exception_cleanup: true });
  console.log(JSON.stringify({ status: 'passed', evidence, checks: records }));
} finally {
  await session.end();
  await writeFile(resolve(evidence, 'results.json'), JSON.stringify(records, null, 2));
  server.closeAllConnections(); server.close();
}
