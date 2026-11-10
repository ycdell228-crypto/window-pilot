// Model-facing workflow over the isolated browser; not yet an MCP tool.
import { BackgroundBrowser } from './browser-background.mjs';

export class BrowserSession {
  #browser; #state; #busy = false; #ended = false; #blocked = false;
  constructor(options) { this.#browser = new BackgroundBrowser(options); }
  get status() { return { ...this.#browser.status, workflow_blocked: this.#blocked, ended: this.#ended }; }
  async #exclusive(operation) {
    if (this.#ended) throw new Error('BROWSER_SESSION_ENDED');
    if (this.#busy) throw new Error('BROWSER_SESSION_BUSY');
    this.#busy = true;
    try { return await operation(); } finally { this.#busy = false; }
  }
  async begin(options) {
    return this.#exclusive(async () => {
      try {
        const session = await this.#browser.open(options);
        this.#state = await this.#browser.observe();
        return { session, state: this.#state, effect_verified: false };
      } catch (error) {
        await this.end();
        throw error;
      }
    });
  }
  async observe() {
    return this.#exclusive(async () => {
      this.#state = null;
      this.#state = await this.#browser.observe();
      return { state: this.#state, effect_verified: false, input_blocked: this.#blocked };
    });
  }
  async step({ control_id, action, value }) {
    return this.#exclusive(async () => {
      if (this.#blocked) throw new Error('BROWSER_SESSION_INPUT_BLOCKED: inspect; never replay');
      if (!this.#state) throw new Error('BROWSER_SESSION_OBSERVATION_REQUIRED');
      // The caller still chooses a control from the returned state. Never remap stale ids.
      const observation_id = this.#state.observation_id;
      this.#state = null;
      let result;
      try {
        result = await this.#browser.act({ observation_id, control_id, action, value });
      } catch (error) {
        // No second action or alternate route. A transport/validation exception needs inspection.
        this.#blocked = true;
        throw error;
      }
      if (result.status === 'unknown') this.#blocked = true;
      try {
        this.#state = await this.#browser.observe();
        return { action: result, state: this.#state, observation_status: 'ok',
          effect_verified: false, input_blocked: this.#blocked };
      } catch {
        // Preserve the actual dispatch result even if the following observation fails.
        this.#blocked = true;
        return { action: result, state: null, observation_status: 'unavailable',
          error: 'BROWSER_POST_ACTION_OBSERVATION_FAILED', effect_verified: false, input_blocked: true };
      }
    });
  }
  async end() {
    this.#ended = true; this.#state = null;
    return this.#browser.stop();
  }
}

// Hosts can use this to guarantee cleanup when their task callback throws.
export async function withBrowserSession(options, task) {
  const session = new BrowserSession(options);
  try { return await task(session); } finally { await session.end(); }
}
