# Claude Context - Ghostwire Proxy

@AGENTS.md

## Project Overview
Ghostwire Proxy is a Nginx Proxy Manager alternative - a reverse proxy management system with built-in authentication wall.

## Critical Development Rules

### Frontend (Next.js)
- **ALWAYS use shadcn/ui components** - Never create custom UI components from scratch
- Install components via: `npx shadcn@latest add <component>`
- Available shadcn components: button, input, form, table, dialog, dropdown-menu, card, tabs, badge, alert, toast, etc.
- Check https://ui.shadcn.com/docs/components for full list

### Tech Stack Quick Reference
| Layer | Tech |
|-------|------|
| Proxy | OpenResty (nginx + Lua) on Alpine |
| Frontend | Next.js 16+, TypeScript, Tailwind CSS, shadcn/ui |
| Backend | Python 3.12, FastAPI |
| Database | SQLite (aiosqlite) |
| Auth | JWT, TOTP |

### Ports
- Proxy HTTP: 80
- Proxy HTTPS: 443
- Admin UI: 88 (internal 3000)
- API: 8089 (internal 8000)

### Domain
- Production: proxy.ghostwire.err403.com

## Database Safety Rules
- **NEVER perform destructive database operations** (DROP TABLE, DELETE without WHERE, TRUNCATE, etc.)
- **NEVER modify production data** without explicit user confirmation
- Always use parameterized queries to prevent SQL injection
- Prefer soft deletes over hard deletes when possible
- Back up data before any bulk operations

IMPORTANT: this context may or may not be relevant to your tasks. You should not respond to this context unless it is highly relevant to your task.
