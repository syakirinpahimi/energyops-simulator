# Frontend status

Last updated: 2026-05-27  by  frontend session 01

## Done
- Next.js 14 (App Router) + TS strict + Tailwind set up; standalone Docker build.
- API client `lib/api.ts` with JWT, error envelope, auto-401 redirect.
- Mock layer `lib/api.mock.ts` gated behind `NEXT_PUBLIC_USE_MOCKS=1`.
- WS helper `lib/ws.ts` with reconnect backoff and a mock telemetry stream.
- Components: `StatusCard`, `EnergyKpiCard`, `AlarmTable`, `TrendChart`
  (line/bar/area), `AssetTree`, `RoleBadge`, `ReportExportPanel`,
  `AuditLogTable`, `SiteSelector`, `AlarmBanner`, `StatusBadge`, `AppShell`.
- Pages: `/login`, `/dashboard`, `/sites`, `/assets/[assetId]`, `/alarms`,
  `/reports`, `/audit-log`, `/admin/users`.
- Role-aware nav + action gating per `docs/API_CONTRACT.md` permissions table.
- Vitest setup with smoke tests for permissions + RoleBadge.

## In progress / partial
- Real backend integration not yet exercised end-to-end (backend track pending).
- WS subscription model for the dashboard uses one connection per assets-list
  change; could be flattened once backend WS is live.

## TODO (next session)
- Replace manual zod-less API types with OpenAPI codegen once `/openapi.json`
  is available. (Acceptable shortcut today; aligned with `docs/API_CONTRACT.md`.)
- Add MSW-driven integration tests for the alarm ack flow.
- Replace `localStorage` JWT with httpOnly cookie via Next.js Route Handler
  once backend cookie auth lands.
- Add a per-asset gauge component for pressure/temperature.

## Open questions for the architect
- Reports `POST /api/v1/reports/energy` returns `202 { report_id, status: queued }`
  in the contract, but the `<Report>` example shows `status: "ready"` (sync).
  The frontend currently treats either as acceptable. Confirm whether MVP is
  sync-on-create or queued + poll.
- `/api/v1/reports` listing endpoint isn't formally in the contract. Frontend
  expects a list to render the recent reports table. Should this be
  `GET /api/v1/reports?kind=energy` with the standard paginated envelope?
- `/api/v1/users` listing for admin isn't in the contract either. Confirm path
  and shape (likely `Paginated<User>`).
