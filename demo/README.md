# EnergyOps demo helpers

Tiny convenience wrappers around the docker-compose stack used during
recruiter walkthroughs. Nothing here is required to run the project.

## Files

- `up.sh` / `up.ps1` - boot the stack, wait for `/health`, run the seed.
- `reset.sh` / `reset.ps1` - wipe data, re-seed, restart the simulator.
- `record.md` - notes on capturing screenshots / screen recordings.

If you are following the demo script, see [`../docs/DEMO_SCRIPT.md`](../docs/DEMO_SCRIPT.md).
