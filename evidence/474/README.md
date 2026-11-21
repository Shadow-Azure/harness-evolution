# Smoke evidence for #474

Baseline revision: 09abb40c (origin/main before the change)
Changed revision: fc6f2c17 (branch head)

Scenarios captured with a real browser against the SQLite-backed app:
- 01/03: interrupted run detail banner before/after the copy change.
- 02/04: execution log before/after the `job_recovered` event rendering.
- 05: V2 prototype run detail used as the visual reference; the prototype has no interrupted-run state, so the banner copy is the only intentional UI difference.

The fixture is deterministic and seeded with `tests/e2e/support/m5_run_list_fixture.py`. No credentials or private Feishu content are included.
