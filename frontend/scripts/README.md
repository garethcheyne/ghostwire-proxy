# frontend/scripts

## ui-audit.mjs

Visits every dashboard page in a real headless browser at phone width and
reports what actually makes a small screen unusable: horizontal overflow,
elements past the right edge, tap targets under 44px, text under 12px, and
console errors. Optionally captures a full-page screenshot per page.

Findings are measured from the live rendered DOM. That matters — the bugs this
found on 2026-09-09 were not visible by reading the CSS:

- a nav scroll region sized `h-[calc(100vh-4rem)]` inside a `fixed` sheet. The
  sheet gets the *small* viewport, `100vh` is the *large* one, so the region was
  taller than its own parent and the last ~100px of the menu was clipped **with
  no scrollbar**. The bottom nav entries were simply unreachable.
- two pages that could be dragged sideways (498px and 426px wide in a 375px
  viewport), taking the sticky header to `left=-123`.
- stat cards truncating their own values — "5.57 GB" rendering as "5.57 …".

### Running it

Playwright is deliberately **not** a dependency: `npm ci` runs in the Docker
builder stage, and adding it there would pull a browser download into the image.
Install it ad hoc and revert the manifest afterwards.

```bash
cd frontend
npm i -D playwright && npx playwright install chromium

# Mint a read-only session token without needing anyone's password.
docker exec ghostwire-proxy-api python -c "
import asyncio
from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.core.security import create_access_token
from app.models.user import User
async def main():
    async with AsyncSessionLocal() as db:
        u = (await db.execute(select(User).where(User.is_active==True))).scalars().first()
        print(create_access_token(data={'sub': str(u.id)}))
asyncio.run(main())"

TOKEN=<that token> SHOTS=1 OUT=/tmp/uiaudit node scripts/ui-audit.mjs

# Leave the manifest as you found it.
git checkout -- package.json package-lock.json
```

Environment: `BASE` (default `http://localhost:88`), `WIDTH`/`HEIGHT` (default
`375x667`), `OUT` (screenshot directory), `SHOTS=1` to capture screenshots,
`TOKEN`/`REFRESH` for the session.

### Reading the output

Two findings are expected and are **not** bugs:

- `input.sr-only.peer (1x1)` — the hidden checkbox behind a styled toggle. The
  real tap target is its 44px label.
- inline links inside prose (`p a`, `td a`, a link among other words in an
  `li`). These are excluded from the 44px minimum on purpose; forcing it would
  wreck paragraph line spacing.
