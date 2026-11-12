// Use the shipped MCP client's schema, startup and disposal unchanged.
// Closing this native plugin disposes its MCP connection, not the admin service.
import { apply as applyMcp } from '@deepseek-ai/dsh-mcp-client';
import { registerSkill } from './skill.js';
export { Config, inject } from '@deepseek-ai/dsh-mcp-client';
export const name = 'window-pilot';

export async function apply(ctx, config) {
  // Optional on older hosts/presets; MCP resource access remains available.
  ctx.inject(['skills'], (inner) => registerSkill(inner));
  await applyMcp(ctx, config);
}
