# EnergyOps Frontend (Next.js)

SCADA-inspired industrial dashboard. Original UI � not affiliated with Schneider, Siemens, or GE.

## Stack
- Next.js 14 (App Router) + TypeScript (strict)
- Tailwind CSS for styling (no UI kit)
- Recharts for time-series visualisation
- Vitest + Testing Library for component tests

## Local development

```bash
cd frontend
cp .env.example .env.local
npm install
npm run dev
# http://localhost:3000
```

`NEXT_PUBLIC_USE_MOCKS=1` (default in `.env.example`) makes the app self-contained
so you can drive the UI before the backend is online. Disable it once the FastAPI
service is reachable.

## Scripts

| Script               | Purpose                                     |
|----------------------|---------------------------------------------|
| `npm run dev`        | Next.js dev server on `:3000`               |
| `npm run build`      | Production build (standalone output)        |
| `npm run start`      | Run production build                        |
| `npm run typecheck`  | `tsc --noEmit` strict typecheck             |
| `npm run lint`       | `next lint`                                 |
| `npm run test`       | Vitest component tests                      |

## Environment

| Variable                     | Default                  | Purpose                          |
|------------------------------|--------------------------|----------------------------------|
| `NEXT_PUBLIC_API_BASE_URL`   | `http://localhost:8000`  | FastAPI base URL (REST)          |
| `NEXT_PUBLIC_WS_URL`         | `ws://localhost:8000`    | WebSocket origin                 |
| `NEXT_PUBLIC_USE_MOCKS`      | `1`                      | Set `0`/unset for live backend   |

## Pages

| Route                  | Roles                          |
|------------------------|--------------------------------|
| `/login`               | Public                         |
| `/dashboard`           | All roles                      |
| `/sites`               | All roles                      |
| `/assets/[assetId]`    | All roles (engineer+ extras)   |
| `/alarms`              | All roles                      |
| `/reports`             | manager, admin                 |
| `/audit-log`           | engineer, manager, admin       |
| `/admin/users`         | admin                          |

## Components

`StatusCard`, `EnergyKpiCard`, `AlarmTable`, `TrendChart`, `AssetTree`,
`RoleBadge`, `ReportExportPanel`, `AuditLogTable`, `SiteSelector`, `AlarmBanner`,
`StatusBadge` (`StatusDot`/`StatusChip`), `AppShell`.

## API client

`lib/api.ts` is the single network entrypoint:
- Reads `NEXT_PUBLIC_API_BASE_URL`
- Attaches the JWT from `localStorage` (set on login)
- Surfaces typed `ApiRequestError`
- Auto-redirects to `/login` on `401`
- Routes through `lib/api.mock.ts` when `NEXT_PUBLIC_USE_MOCKS=1`

WebSocket helper in `lib/ws.ts` mirrors the same flag and auto-reconnects with
exponential backoff up to 30s.

## Demo flow (mocks)

1. Visit `/login`. Click the **operator** quick-login (or sign in directly).
2. Land on `/dashboard`. Watch live tiles update against the WS mock.
3. Banner shows the **Pump P-101 vibration** alarm. Click "Open alarm panel".
4. Acknowledge the alarm with a note.
5. Visit `/audit-log`. The acknowledgement is recorded.
6. Switch role to `manager` (mock-mode role picker, top right). Visit `/reports`
   and generate an energy report.

## Tests

`npm run test` runs a small set of component tests in `__tests__/`. Coverage
is intentionally focused on pure rendering + permission helpers.

## Definition of done

- [x] Pages above render
- [x] Live ticks via WS mock or backend
- [x] Role-aware navigation + action gating
- [x] Lint, typecheck, build clean
- [x] Dockerfile + `.env.example`
