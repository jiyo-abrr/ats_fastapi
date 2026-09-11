# Architecture — conventions and deliberate exceptions

Companion to [../CLAUDE.md](../CLAUDE.md) (which has the full domain-by-domain
detail). This file is the short statement of *which rules actually apply* —
written to resolve review finding F07 ("multiple competing architectural
contracts").

## Two paths

### Write / use-case path — one transaction owner

A business operation that changes data has exactly one place that commits.

- **Router** extracts plain values from the request (never passes
  `UploadFile`/`Request` into a service), calls one service or use case, maps
  the result to a response schema.
- **Service** holds business decisions. Constructed with repositories + a
  `UnitOfWork`. Operates on `entities` (plain dataclasses), never ORM models,
  never FastAPI types. Raises named domain exceptions from its
  `exceptions.py` — never `HTTPException`, never a raw `app.core.exceptions`
  base.
- **Repository** stages changes (`add`/`delete`/query) and maps ORM ↔ entity.
  It does **not** commit.
- **UnitOfWork** flushes/commits/rolls back the request's session.
- **Cross-domain writes** go through a **use case** in `app/use_cases/` (e.g.
  `apply_to_job` — application + assessment attempts, one commit) or a
  composition-root script (`app/scripts/*` sweeps). Domain services never
  import each other.

### Read / query path — projections allowed

List and reporting endpoints may bypass the entity layer for *query
construction only*:

- List routes build a `QueryBuilder(Model)` / `Select` directly against
  `models.py` and paginate with `apaginate(..., transformer=repo.map_many)` —
  rows still funnel through `_to_entity`.
- `ApplicationRepository.list_for_review` / `list_for_applicant` and
  `ApplicationService.list_*` return a raw `Select` the router paginates. The
  service method exists purely as a layering boundary (router never imports the
  repository).
- Cross-domain read composition happens **at the router** (e.g.
  `/applications/assessment-scorecard` reads applications + assessments +
  evaluations). The composed domains never depend back.

## Deliberate exceptions (do not "fix" these)

| Exception | Where | Why |
| --- | --- | --- |
| `analytics/` imports other domains' `models.py` directly | `analytics/repository.py` | It is the single read-only reporting layer, owns no writes and no entities; a reporting method per domain that only analytics calls would be worse. |
| `RolePermissionRepository` does not extend `BaseRepository` | `rbac/` | Composite PK doesn't fit the single-`id` `get_by_id` contract. |
| `assessments/` and `interviews/` are grouping namespaces / multi-service domains | those packages | `assessments/` groups 3 independent template domains + attempts; `interviews/` has two cohesive services (scheduling + availability) that share a call path. |
| Polymorphic `template_id` / `question_id` with no FK | `assessments/attempts/models.py` | Points into one of 3 independent template tables; Postgres has no "FK to one of several tables". There is **no referential integrity** across this boundary — `_require_template` only *detects* a missing template on the read/write paths that call it and turns it into a 404 (`MissingAssessmentTemplateError`). It does not block deleting a referenced template or preserve a question's meaning after an edit. Snapshotting the template at issuance is the tracked fix (`docs/decisions/D03`). |
| `rate_limit` raises `HTTPException` directly | `core/rate_limit.py` | Infra at the HTTP boundary, not a domain rule. |

## Known gaps (tracked, not yet conforming)

- **`interviews/` and `evaluations/` write paths** still take `AsyncSession`
  and query/commit directly — they have no `repository.py`/`entities.py` yet
  (Phase 2/3 of the extraction, gated on the integration harness). New work in
  those domains should move toward the write path above, not extend the
  session-in-service style.
- **No integration or real-app API tests.** See
  [maintainability-review.md](maintainability-review.md) F06.
