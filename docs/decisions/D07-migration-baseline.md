# D07 — Migration baseline and upgrade policy

**Question (review F18):** the history contains development-oriented migrations —
`449cadbbefb7` deletes attempts/answers/reopen history and drops the old
template tables without moving their contents; the status migration replaces
allowed values without backfilling. Offline SQL generation (`alembic upgrade
head --sql`) fails in `f9d26d7ef36a` (it runs a query while emitting SQL).

**Decision:**

1. **Supported baseline:** the first production deployment starts from an empty
   database and runs `alembic upgrade head`. Revisions before that point are
   development history and are **not** guaranteed to preserve data on a
   populated database.
2. **From the baseline onward:** every migration must be safe on a populated
   database — data-preserving transforms, backfills where values change, no
   rewriting of already-applied revisions.
3. **Offline SQL (`--sql`) is unsupported.** Some migrations need live query
   results. Deployments run migrations online (`alembic upgrade head`) against
   the target database.
4. Test both a fresh upgrade and a supported populated upgrade against a
   disposable Postgres before release.

**Not provisional.** Revisit only if a customer database predates the baseline.
