# Safe Compose implementation checkpoints

Initial revision: `bbc4cdb445c283dd53c3d2cfa122cccea9ad05cd` (main).
Existing changes in DockerControlCenter.py, tests/test_store_catalog_features.py,
AGENTS.md and local dependency folders belong to the user and are excluded.
The initial status and patch are saved locally in build/safe-compose-local/.

Technical plan:

1. A: discover projects through existing Docker labels; add a separate tab and
   durable SQLite operations/settings with monitoring and automation OFF.
2. B: let Compose CLI normalize complete file sets; semantic three-way comparison
   works on resolved models. Never apply a generic YAML merge. Hash all inputs;
   require locally pinned sources and explicit, bounded write grants.
3. C: classify database/image/schema risks separately. Start with a narrow
   stateless deployment adapter and SQLite backup/isolated restore verification.
   Unknown databases and production migrations fail closed.
4. D: use JobManager, ScheduleStore and existing report/notification transports;
   persist stages before Docker mutations, never resume uncertain deployments.
5. E: fixture and fake-Docker tests, existing regression suite, documentation and
   the single catalog entry; publish only after validation.

The catalog maintenance workflow also changes metadata of other apps and can
force-update a candidate branch/open a PR. Its unrestricted dispatch is outside
the requested single-entry scope and must not be triggered automatically.

Checkpoints and actual validation results are recorded below as work completes.

- A completed: project discovery, PL/EN tab and six-theme integration, private
  SQLite settings/history and persistent project locks. Legacy configuration
  files and desktop changes are preserved.
- B completed: Compose CLI normalization, field-level three-way review,
  two-way-only handling without BASE, secret-free public diffs, complete input
  and runtime hashes, source pinning, dry-run and exact-file write grants.
- C completed within explicit limits: stateless-v1 image deployment/rollback,
  SQLite online backup and isolated structural restore verification. Production
  migrations, general config changes and database deployments remain blocked.
- D completed: existing JobManager/scheduler loop/calendar and notification
  transports reused. Uncertain restarts hold locks and block Docker mutations.
- E local validation: full updater Linux suite, original desktop regression
  suite (137 tests including installer restart), real Compose CLI normalization,
  Linux ownership/CAS/undo tests and fake-Docker transaction/rollback tests.
  Headless browser checks cover PL/EN, six accents, desktop/mobile, actual field
  diffs and disabled unsafe actions; no JavaScript page errors.
- Catalog: exactly the eight requested text/feature fields in the updater entry;
  `extra` and every other entry unchanged by this implementation. Existing image
  workflow is unchanged. No desktop release or tag changes.

Publication and final test counts are reported in the task's final report.
