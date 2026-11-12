import { readFileSync } from 'node:fs';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';

// The shipped skill is also the canonical source of the MCP guide resources.
export function registerSkill(ctx) {
  const directory = fileURLToPath(new URL('./skills/window-pilot/', import.meta.url));
  const path = fileURLToPath(new URL('./skills/window-pilot/SKILL.md', import.meta.url));
  const parse = (raw) => {
    const match = /^---\r?\nname: ([\w-]+)\r?\ndescription: ([^\r\n]+)\r?\n---\r?\n/u.exec(raw);
    if (!match || match[1] !== 'window-pilot') throw new Error('Invalid bundled Window Pilot skill');
    return { name: match[1], description: match[2], content: raw.slice(match[0].length).trim() };
  };
  const { name, description } = parse(readFileSync(path, 'utf8'));
  const summary = { name, description, path, provider: 'window-pilot', source: 'bundled',
    invocation: { modelInvocable: true, userInvocable: true },
    resourceBase: { kind: 'directory', path: directory } };
  ctx.skills.registerProvider(() => ({
    name: 'window-pilot',
    list: async () => [{ ...summary, rank: 600, locator: path }],
    async get(candidate, options) {
      const current = parse(await readFile(path, { encoding: 'utf8', signal: options.signal }));
      return { ...summary, ...current };
    },
  }));
}
