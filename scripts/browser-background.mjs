// Experimental local-site adapter. No desktop input, user profile, or headed fallback.
// Deliberately not wired into the MCP executor until shared stop/ownership is integrated.
import { randomUUID } from 'node:crypto';

const selector = 'input,textarea,button,select';
const textTypes = new Set(['text', 'search', 'email', 'url', 'tel']);
function fail(code) { throw new Error(code); }
function localUrl(value) {
  const url = new URL(value);
  if (url.protocol !== 'http:' || url.hostname !== '127.0.0.1' || !url.port || url.username || url.password)
    fail('BROWSER_LOCAL_ORIGIN_REQUIRED');
  return url;
}

// Runs in the page to read a single control. Never supplied by the caller.
function describe(element) {
  const rect = element.getBoundingClientRect();
  const type = (element.type || '').toLowerCase();
  const password = type === 'password';
  return {
    tag: element.tagName.toLowerCase(), type,
    name: password ? '[password]' : (Array.from(element.labels || []).map(x => x.innerText).join(' ') ||
      element.getAttribute('aria-label') || element.innerText || element.name || '').trim().slice(0, 256),
    disabled: !!element.disabled, read_only: !!element.readOnly, password,
    value: password ? null : String(element.value || '').slice(0, 2048),
    value_truncated: !password && String(element.value || '').length > 2048,
    checked: !!element.checked,
    bounds: { x: rect.x, y: rect.y, width: rect.width, height: rect.height },
    connected: element.isConnected,
  };
}

export class BackgroundBrowser {
  #chromium; #executable; #server; #browser; #context; #page; #origin;
  #observation; #handles = []; #busy = false; #terminal = false; #faulted = false;
  #epoch = 0; #opened = false;
  constructor({ chromium, executablePath }) {
    this.#chromium = chromium;
    this.#executable = executablePath;
  }
  get pid() { return this.#server?.process().pid ?? null; }
  get status() { return { opened: this.#opened, stopped: this.#terminal, faulted: this.#faulted,
    in_flight: this.#busy, mode: 'isolated_headless_browser', shared_executor: false,
    owned_process_exited: this.#server ? this.#server.process().exitCode !== null || this.#server.process().signalCode !== null : null }; }
  #running(input = false) {
    if (this.#terminal) fail('BROWSER_STOPPED: no resume or automatic restart');
    if (input && this.#faulted) fail('BROWSER_INPUT_UNKNOWN: inspect; never replay');
  }
  async #exclusive(fn) {
    if (this.#busy) fail('BROWSER_OPERATION_IN_FLIGHT');
    this.#busy = true;
    try { return await fn(); } finally { this.#busy = false; }
  }
  async open({ url, purpose }) {
    const target = localUrl(url);
    if (typeof purpose !== 'string' || !purpose.trim() || purpose.length > 300)
      fail('BROWSER_TASK_PURPOSE_REQUIRED: caller statement, not authorization proof');
    return this.#exclusive(async () => {
      this.#running(true);
      if (this.#opened) fail('BROWSER_ALREADY_OPEN');
      this.#opened = true;
      this.#origin = target.origin;
      try {
        this.#server = await this.#chromium.launchServer({ executablePath: this.#executable,
          headless: true, host: '127.0.0.1', timeout: 10000 });
        this.#running();
        this.#browser = await this.#chromium.connect(this.#server.wsEndpoint());
        this.#context = await this.#browser.newContext({ viewport: { width: 1024, height: 768 },
          acceptDownloads: false, serviceWorkers: 'block', permissions: [] });
        await this.#context.route('**/*', async route => {
          const destination = new URL(route.request().url());
          if (destination.origin !== this.#origin) return route.abort('blockedbyclient');
          try {
            // Do not let a local 30x response silently forward a request outside scope.
            const response = await route.fetch({ maxRedirects: 0, timeout: 5000 });
            if (response.status() >= 300 && response.status() < 400) await route.abort('blockedbyclient');
            else await route.fulfill({ response });
          } catch { await route.abort('failed').catch(() => {}); }
        });
        // A local page cannot open a second browser protocol connection through WebSockets.
        await this.#context.routeWebSocket('**/*', socket => socket.close());
        this.#page = await this.#context.newPage();
        this.#context.on('page', page => { if (page !== this.#page) void page.close(); });
        this.#page.on('dialog', dialog => { void dialog.dismiss(); });
        this.#page.on('download', download => { void download.cancel(); });
        this.#page.on('framenavigated', frame => {
          if (frame === this.#page.mainFrame()) { this.#epoch++; this.#observation = null; }
        });
        await this.#page.goto(target.href, { waitUntil: 'domcontentloaded', timeout: 5000 });
        this.#running();
        this.#scope();
        return { ...this.status, pid: this.pid, origin: this.#origin, purpose_is_authorization: false };
      } catch {
        await this.stop();
        fail('BROWSER_OPEN_FAILED: owned process closed; no automatic retry');
      }
    });
  }
  #scope() {
    if (!this.#page || this.#page.isClosed() || new URL(this.#page.url()).origin !== this.#origin)
      fail('BROWSER_PAGE_SCOPE_CHANGED');
  }
  async #discardHandles() {
    const old = this.#handles; this.#handles = [];
    await Promise.allSettled(old.map(handle => handle.dispose()));
  }
  async observe() {
    return this.#exclusive(async () => {
      this.#running(); this.#scope(); this.#observation = null;
      await this.#discardHandles();
      const epoch = this.#epoch;
      const handles = await this.#page.$$(selector);
      this.#handles = handles.slice(0, 128);
      await Promise.allSettled(handles.slice(128).map(handle => handle.dispose()));
      const nodes = [];
      for (const handle of this.#handles) nodes.push(await handle.evaluate(describe));
      const document_text = await this.#page.locator('body').innerText({ timeout: 1000 });
      const screenshot = await this.#page.screenshot({ type: 'png', timeout: 3000 });
      this.#running(); this.#scope();
      if (epoch !== this.#epoch) fail('BROWSER_OBSERVATION_CHANGED');
      const id = randomUUID();
      this.#observation = { id, epoch, time: performance.now(), nodes };
      return { observation_id: id, atomic_snapshot: false, read_only: true,
        url: this.#page.url(), document_text: document_text.slice(0, 8192),
        document_text_truncated: document_text.length > 8192, controls_truncated: handles.length > 128,
        nodes: nodes.map((node, i) => ({ ...node, control_id: `${id}:${i}`,
          actions: node.password || node.disabled || node.read_only ? [] :
            (node.tag === 'textarea' || (node.tag === 'input' && textTypes.has(node.type)) ? ['set_value'] :
              (node.tag === 'button' || ['submit', 'button', 'reset', 'checkbox', 'radio'].includes(node.type) ? ['click'] : [])) })),
        image: screenshot.toString('base64'), image_mime_type: 'image/png',
        text_policy: 'password value omitted; page text may echo content; screenshot is not redacted',
        mode: 'isolated_headless_browser', input_faulted: this.#faulted };
    });
  }
  async act({ observation_id, control_id, action, value }) {
    if (!['set_value', 'click'].includes(action)) fail('BROWSER_ACTION_UNSUPPORTED');
    if (action === 'set_value' && (typeof value !== 'string' || value.length > 2048 || value.includes('\0')))
      fail('BROWSER_INVALID_VALUE');
    if (action === 'click' && value !== undefined) fail('BROWSER_UNEXPECTED_VALUE');
    return this.#exclusive(async () => {
      this.#running(true); this.#scope();
      const snapshot = this.#observation;
      if (!snapshot || snapshot.id !== observation_id || snapshot.epoch !== this.#epoch || performance.now() - snapshot.time > 30000)
        fail('BROWSER_STALE_OBSERVATION');
      const index = snapshot.nodes.findIndex((_, i) => control_id === `${snapshot.id}:${i}`);
      if (index < 0) fail('BROWSER_CONTROL_NOT_IN_OBSERVATION');
      this.#observation = null; // Consume before validation or browser dispatch; never reuse.
      let attempted = false;
      try {
        const element = this.#handles[index];
        const current = await element.evaluate(describe);
        if (JSON.stringify(current) !== JSON.stringify(snapshot.nodes[index]) || !current.connected)
          fail('BROWSER_CONTROL_CHANGED');
        if (current.password || current.disabled || current.read_only) fail('BROWSER_CONTROL_REFUSED');
        if (action === 'set_value' && !(current.tag === 'textarea' || (current.tag === 'input' && textTypes.has(current.type))))
          fail('BROWSER_SET_VALUE_UNSUPPORTED');
        if (action === 'click' && !(current.tag === 'button' || ['submit', 'button', 'reset', 'checkbox', 'radio'].includes(current.type)))
          fail('BROWSER_CLICK_UNSUPPORTED');
        this.#running(true); this.#scope();
        if (snapshot.epoch !== this.#epoch) fail('BROWSER_OBSERVATION_CHANGED');
        attempted = true;
        if (action === 'set_value') await element.fill(value, { timeout: 1000 });
        else await element.click({ timeout: 1000 });
        this.#running(); this.#scope();
        return { status: 'dispatched', effect: 'unverified', action_attempted: true,
          execution_method: action === 'set_value' ? 'playwright_element_fill' : 'playwright_element_click',
          next: 'observe and verify actual page result; never replay' };
      } catch (error) {
        if (attempted) this.#faulted = true;
        return { status: attempted ? 'unknown' : 'rejected', action_attempted: attempted,
          effect: attempted ? 'unverified' : 'not_sent',
          error: attempted ? 'BROWSER_ACTION_OUTCOME_UNKNOWN: no retry or restart' :
            (String(error.message).startsWith('BROWSER_') ? error.message : 'BROWSER_VALIDATION_FAILED'),
          observation_consumed: true };
      }
    });
  }
  async stop() {
    this.#terminal = true; this.#observation = null; this.#epoch++;
    // Terminal, idempotent session stop; allowed even while a browser action is pending.
    const server = this.#server;
    if (server) {
      let timer;
      try { await Promise.race([server.close(), new Promise((_, reject) => {
        timer = setTimeout(() => reject(new Error('close deadline')), 3000);
      })]); } catch { await server.kill(); } finally { clearTimeout(timer); }
    }
    return { ...this.status, cleanup: 'owned_browser_closed' };
  }
}
