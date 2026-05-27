# Recording the demo

A few notes for capturing the walkthrough mentioned in
`../docs/DEMO_SCRIPT.md`.

## Window layout

- Browser: 1280x800, no extensions visible.
- Terminal: monospace, 14pt+, dark theme.
- Keep the docker-compose `ps` output visible in a side terminal so the
  reviewer can confirm the services are alive.

## Captures

Drop the screenshots into `../docs/screenshots/` using the names already
referenced in the README:

- `01-login.png`           - login screen with seeded operator email.
- `02-dashboard.png`       - dashboard with the OPEN alarm banner.
- `03-asset-detail.png`    - Pump P-101 detail page with vibration trend.
- `04-alarm-ack.png`       - alarm side-panel with the ack note typed in.
- `05-energy-report.png`   - reports page with PDF download triggered.
- `06-audit-log.png`       - audit-log page with `alarm.ack` entry.

For a moving demo, a 30-second screen recording at 1080p as MP4 or GIF
works well embedded in the README under the screenshots table.

## Reset

Run `./reset.sh` (or `reset.ps1` on Windows) between takes so the OPEN
pump alarm comes back and the audit log is empty.
