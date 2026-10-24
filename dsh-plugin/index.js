// Use the shipped MCP client's schema, startup and disposal unchanged.
// Closing this native plugin disposes its MCP connection, not the admin service.
export { Config, inject, apply } from '@deepseek-ai/dsh-mcp-client';
export const name = 'window-pilot';
