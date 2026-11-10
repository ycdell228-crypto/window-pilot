// Private JSON-lines bridge. Dependency paths are trusted host configuration, never page input.
import { createRequire } from 'node:module';
import { BrowserSession } from './browser-session.mjs';
const require = createRequire(import.meta.url);
const { chromium } = require(process.env.WINDOW_PILOT_PLAYWRIGHT || 'playwright');
if (!process.env.WINDOW_PILOT_BROWSER) throw new Error('BROWSER_EXECUTABLE_REQUIRED');
const session = new BrowserSession({ chromium, executablePath: process.env.WINDOW_PILOT_BROWSER });
const pending = new Set();
let closing = false, buffer = Buffer.alloc(0);
const limit = 65536;
function reply(value) {
  if (!closing && !process.stdout.destroyed) process.stdout.write(JSON.stringify(value) + '\n');
}
async function close() {
  if (closing) return;
  closing = true; process.stdin.pause();
  await session.end().catch(() => {});
  await Promise.allSettled([...pending]);
  await session.end().catch(() => {});
  // EOF may arrive during launch; await launch cleanup before allowing process exit.
  process.stdin.destroy();
}
async function request(line) {
  let id = null;
  try {
    const req = JSON.parse(line.toString('utf8'));
    if (!req || typeof req.id !== 'string' || req.id.length > 64 ||
        !['begin', 'observe', 'step', 'end', 'status'].includes(req.operation) ||
        !req.args || typeof req.args !== 'object' || Array.isArray(req.args))
      throw new Error('BROWSER_INVALID_REQUEST');
    id = req.id;
    const allowed = { begin: ['url', 'purpose'], step: ['control_id', 'action', 'value'], observe: [], end: [], status: [] };
    if (Object.keys(req.args).some(key => !allowed[req.operation].includes(key)))
      throw new Error('BROWSER_INVALID_ARGUMENT');
    const result = req.operation === 'status' ? session.status : await session[req.operation](req.args);
    reply({ id, ok: true, result });
  } catch (error) {
    // Never echo provider text, URLs, submitted text or stack traces across the bridge.
    const code = /^BROWSER_[A-Z_]+/.exec(String(error.message))?.[0] || 'BROWSER_WORKER_OPERATION_FAILED';
    reply({ id, ok: false, error: code, input_state: 'inspect_before_any_further_input' });
  }
}
process.stdin.on('data', chunk => {
  if (closing) return;
  buffer = Buffer.concat([buffer, chunk]);
  let newline;
  while ((newline = buffer.indexOf(10)) >= 0) {
    if (newline > limit) { void close(); return; }
    const line = buffer.subarray(0, newline); buffer = buffer.subarray(newline + 1);
    const job = request(line); pending.add(job); job.finally(() => pending.delete(job));
  }
  if (buffer.length > limit) void close();
});
process.stdin.on('end', () => { void close(); });
process.stdin.on('error', () => { void close(); });
process.stdout.on('error', () => { void close(); });
process.on('SIGTERM', () => { void close(); });
