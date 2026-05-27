# Changelog

All notable changes to this project are documented here.
The format roughly follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
the project does not yet ship versioned releases.

## [Unreleased]

### Fixed
- Simulator anomaly slug mismatch: anomaly tags emitted by
  `simulator/assets.py` now use the same canonical slugs the backend
  rule engine expects (`vibration_spike`, `temperature_high`,
  `power_high`, `solar_low`, `voltage_dip`).
- Demo credentials in the README and login page pre-fill match the
  values actually written by `python -m app.seed`, so first-login
  works without consulting `.env.example`.

### Documentation
- MQTT docs aligned with the implementation: the README, ADR-0001,
  and `docs/API_CONTRACT.md` now agree on the five-segment
  `industrial/<site>/<area>/<asset>/<sensor>` topic shape and the
  `industrial/+/+/+/+` subscription filter.
- README now offers PowerShell alternatives to `make` for Windows
  users (`docker compose up --build`, `demo/up.ps1`, `demo/reset.ps1`).
- Frontend mock-mode behaviour documented: Docker demo always uses
  live backend data; `NEXT_PUBLIC_USE_MOCKS=1` is opt-in for local
  `npm run dev` only.

### Tooling
- Added a repo-root `pytest.ini` that pins
  `asyncio_default_fixture_loop_scope = function`, silencing the
  pytest-asyncio fixture loop scope deprecation warning without
  suppressing real project warnings.
- `/audit` route in the frontend redirects to the canonical
  `/audit-log` route (matches the backend endpoint and the user spec).
