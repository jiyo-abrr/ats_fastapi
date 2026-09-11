# Maintainability review — what's left

Companion to [maintainability-review.md](maintainability-review.md) and
[maintainability-review-progress.md](maintainability-review-progress.md).

**Everything tracked in the review is done.** F01–F29 are all ✅ (F12 and F19
kept a small, deliberately-scoped remainder noted below; nothing else has an
open remainder). All 9 product decisions (D01–D09) are recorded, and the
ones with code implications are implemented. See
`maintainability-review-progress.md` for the full batch-by-batch change log
(18 batches) if you need the history of how a specific finding was closed.

**F07 — done ✅ (batch 17–18), the last item.** Both `interviews/` and
`evaluations/` now follow the standard entities/repository pattern — see
CLAUDE.md's domain notes and `docs/architecture.md`, whose "Known gaps"
section is now empty. `docs/architecture.md` is the short reference for the
write/read path rules and the deliberate exceptions (projection reads,
`analytics/`, etc.) if you're deciding where new code in either domain
should live.

## Small, deliberately-scoped remainders

These aren't deferred work — they're intentional stopping points, called out
so nobody mistakes them for oversights:

- **F12** — bounded-read protects the résumé upload from unbounded memory use
  (`app/core/uploads.py`); no orphaned-MinIO-object compensation if an upload
  is interrupted after the object lands but before the DB row commits. Low
  likelihood, low blast radius (an unreferenced object, not data loss).
- **F19** — README/architecture/decisions docs and the CI workflow
  (`.github/workflows/ci.yml`) are in place and clean locally; actually
  seeing it green on a hosted GitHub Actions runner still needs a push,
  which nobody has done yet (no remote is configured — see CLAUDE.md's Git
  section).
- **F21** — request-correlation IDs are done (`X-Request-ID`, echoed into the
  500 body and log line); a full metrics/observability framework was
  explicitly out of scope for this review.

## Current verification snapshot (batch 18)

286 tests pass (258 unit + 28 integration), `ruff check` / `ruff format
--check` clean, `alembic check` clean.
