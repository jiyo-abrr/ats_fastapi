# ATS FastAPI — structure, cleanliness, and maintainability review

Original review: **10 September 2026**, against commit **`5469231`** (`refactor: extract interviews and evaluations into their own domains`).

**Second comprehensive review: 10 September 2026, against the current working tree, including the 55 staged files present when the second review began.** HEAD is still `5469231`; the staged remediation is not part of that commit. The current assessment below supersedes historical statements in the original review.

Both review passes are documentation-only. The second pass preserves the pre-existing code changes and Git staging; it updates this report and the companion [progress notes](maintainability-review-progress.md).

## Second review — current assessment

**The staged changes improve the structure and address several real defects. The code is easier to maintain than at the first review, but the remediation is not complete.** Keep the modular monolith. The highest remaining risks are concurrent state changes, interview reservation integrity, and mutable assessment history. Passing lint and more unit tests do not yet verify those guarantees.

The new `ApplyToJob` use case removes the normal API path's two separate commits. Password hashing/verification is offloaded. A missing template now produces a domain error. Pending interview selection handles zero-slot requests. Redis counter creation and expiry run in one script. Documentation and CI configuration now exist. These are meaningful improvements and should not be reported as unchanged defects.

However, some progress entries marked complete cover only a subset of the original finding. In particular, F05, F10, F13, F16, F19, and F21 still have work outstanding. F03's duration-edit bypass also remains unchanged despite a progress note proposing to fix it now.

### What the second pass verified

| Check | Current result and limits |
| --- | --- |
| Full existing suite | **221 passed**, 22 warnings, 4.37 seconds. Sixteen more cases than the original baseline. |
| Ruff lint | **Passed.** |
| Ruff format | **Passed: 213 files already formatted.** This check includes supported Markdown examples, so it is not a count of Python source files. |
| ORM mapper configuration / OpenAPI | **Passed:** 33 tables and 76 paths. No database connection or application lifespan was started. |
| Real route with mocked I/O: malformed numeric question config | **HTTP 500**, `{"detail":"Internal server error"}`; validation still raises `TypeError`. |
| Real route with mocked I/O: Unicode résumé filename | **HTTP 500**, same generic response; header construction raises `UnicodeEncodeError`. |
| Reopen service probe | An expired attempt with a **withdrawn, past-deadline parent** is still reset and committed. |
| Assessment final-question timeout probe | Returns `status="in_progress"`, `current_question=None`, and performs no completion transition. |
| Evaluation schema probes | Unknown dimensions and dimensions in the wrong category still pass. Duplicate dimensions within a category and duplicate application IDs now have validators. |
| Interview probes | Past manual slots pass validation; a manual request can book a time outside its offered slots through `starts_at`; duplicate date overrides produced four slots with only two distinct starts. |
| Availability validation probe | `end="24:59"` is accepted, despite the database requiring minutes at or below 1440. |
| Export contract inspection | The only business query parameter is **`job_post_id`**. There is no status filter or background-export action on this endpoint. |
| Use-case failure probe | Attempt-staging failure produces **zero explicit rollback calls** from `ApplyToJob`; see the transaction note below for why this does not reintroduce the original normal-request partial commit. |
| Query inspection | Pending-selection SQL now correctly excludes confirmed requests without requiring a slot row. Confirmed-calendar SQL still has no parent-application status predicate. |

The temporary probes used synthetic values and process-local mocks. No test files were added, no application code was edited, and no PostgreSQL/Redis/MinIO data was read or changed. Existing unit tests were run using the local configuration. No live concurrency, migration execution, memory/load benchmark, browser workflow, or hosted CI run was performed. The existing 22 test warnings remain; secret values are not included in these notes.

### Reassessment of the original 21 findings

“Implemented” means the code addresses the specific original behavior, with the stated verification limits. “Partial” means the original finding must remain open. The companion progress table has been corrected to reflect this distinction.

| Finding | Second-pass status | Notes |
| --- | --- | --- |
| F01 — atomic issuance | **Implemented for the API path; DB verification pending** | Both services receive `commit=False`; one UoW commits. Staging-failure rollback ownership and the test's description need clarification. |
| F02 — transition races | **Open** | No conditional state updates, version checks, or row locks added to the state transitions. |
| F03 — interview overlaps | **Open** | Different-start overlap races and editing a selected interview's duration remain possible. `set_request()` has not changed. |
| F04 — assessment history | **Partial** | Missing-template handling improves the error, but does not prevent deletion, preserve question meaning, or validate missing questions. |
| F05 — parent eligibility | **Partial** | Start/answer now enforce status and deadline. `reopen()` does not use the guard and can supersede answers on terminal applications. Concurrent changes still fall under F02. |
| F06 — tests | **Partial** | New unit cases and CI improve the baseline. There are still no real database or committed real-app route tests. Interview service behavior is still not covered by the existing interview test modules. |
| F07 — boundaries | **Partial** | The cross-domain use case and architecture document help. Session-based interview/evaluation services, ORM leakage, and exceptions to the stated layering remain. |
| F08 — per-row queries | **Open** | Job-post mapping still performs five extra queries per row; other mapping/review loops are unchanged. |
| F09 — unbounded work | **Partial** | The pack has a 200-applicant cap, but see F26. Booking queries remain unbounded by horizon; “latest” helpers still load history before discarding older rows. |
| F10 — validation | **Partial, not done** | Deadline invariants and auth field widths improved. Numeric question bounds still cause 500s; timers, salary constraints, other string limits, and extension-reason bounds remain incomplete. |
| F11 — password execution/length | **Implemented for HTTP auth** | Signup/HR-create validate before upload; hashing and login verification use the threadpool. Overlong login is rejected as invalid credentials, not `PasswordTooLongError`. CLI hashing still lacks friendly length validation. |
| F12 — upload lifecycle | **Partial** | Duplicate-email inserts have a response mapping. The full upload is still read first, orphan cleanup is absent, and constraint translation is too broad (F27). Concurrent profile-email updates remain unhandled. |
| F13 — evaluation vocabulary | **Partial, not done** | Duplicate dimensions in one category are rejected. Vocabulary/category validation, database uniqueness, and text bounds are still missing. |
| F14 — latest evaluation | **Original ambiguity addressed** | Duplicate application IDs in a payload are rejected and all inspected selectors use `(created_at DESC, id DESC)`. UUID order is a deterministic tie policy, not import chronology. Retry/version semantics remain a design follow-up. |
| F15 — pending interview action | **Implemented; DB test pending** | The new query includes self-scheduled requests with zero slots. Inspected compiled SQL confirms the inner-join defect is gone. |
| F16 — job ownership | **Partial** | Opt-in configuration and a per-tick advisory lock help. Direct CLI jobs bypass that lock; batching, shutdown/cancellation verification, and health visibility remain (F29). |
| F17 — counter TTL | **Atomic fix implemented; Redis test pending** | Lua closes the new-key interruption window. Old keys already lacking TTL are not repaired. Fail-open behavior on Redis errors is a deliberate new operational choice. |
| F18 — migrations | **Policy documented; execution unverified** | D07 explicitly supports an empty first-production baseline and online execution only. Offline failure is now an acknowledged limitation, not an unsupported promise. Fresh/populated upgrade tests are still needed. |
| F19 — docs/CI | **Substantially improved, still partial** | README, architecture, decisions, workflow, and formatting are present. Some progress claims and architectural assertions exceed the code; CI was not run on the hosted runner. |
| F20 — duplication | **Open** | Template behavior and evaluation dimension lists remain duplicated. |
| F21 — configuration/lifecycle | **Partial, not done** | Admin settings now read `.env` correctly. Client cleanup, readiness/job health, revoked-token cleanup, and operational instrumentation remain unchanged. |

### Notes on the fixes themselves

**Transaction ownership needs an accurate contract.** In [apply_to_job.py:46](../app/use_cases/apply_to_job.py#L46), both staging calls are outside the `try`; only `IntegrityError` during the final commit triggers the explicit rollback. [test_apply_to_job.py:38](../tests/unit/use_cases/test_apply_to_job.py#L38) is named as a rollback test, but only asserts that commit was not called. The progress log's “rollback on any failure” statement is therefore incorrect.

The normal FastAPI dependency uses `async with AsyncSessionLocal()` in [database.py:28](../app/core/database.py#L28), so closing the request session rolls back its uncommitted transaction. **Do not describe F01 as still having the original two-commit bug.** Instead, decide whether the use case guarantees rollback itself or requires an enclosing transaction scope. Verify that contract with real persistence, including a caller that catches an error and reuses the session. Prefer an explicit enclosing unit of work as composition grows; `commit: bool` is a workable transitional mechanism but makes it easy for future callers to choose the wrong ownership mode.

**Read-time errors are not referential integrity.** [architecture.md](architecture.md) says polymorphic integrity is enforced by `_require_template`. That helper only detects a missing template when certain reads/writes use it. It does not block deletes, preserve old prompts, check that old questions exist, or establish a database relationship. D03's more cautious description is accurate; align the architecture statement with it.

**Reopen is still an assessment mutation.** [attempts/service.py:316](../app/domains/assessments/attempts/service.py#L316) only specifically blocks a disqualified parent. The second probe confirmed that a withdrawn parent can have its old answers superseded, attempt reset, and reopen record committed. Subsequent answering is blocked by the new guard, leaving a reopened attempt that cannot be continued. Apply an explicit reopen-eligibility rule, and cover denied/success/failed/withdrawn, missing templates, and past deadlines in tests. This is the remaining F05 defect, not a separate new finding.

**Product decisions are not implemented merely because an ADR exists.** D01's published-only public visibility and D04's restrict-delete policy are still not enforced: job GET routes remain public and unrestricted by status, and job deletion still cascades through applications. Keep those entries visibly pending. No decisions were newly made or implemented during this review.

**The test suite proves less than some names imply.** The rollback test does not assert rollback; `test_same_dimension_across_categories_is_fine` uses two different dimensions, so it does not test the named same-dimension case. Existing interview tests cover schemas/helpers rather than the services. Favor behavior and persistence assertions over method names or forwarding assertions when closing the findings.

### Additional findings from the second pass

The IDs continue the original list. These are newly documented observations, not necessarily regressions introduced by the staged fixes.

#### F22 — Medium: an attempt can have no next question without a usable completion path

**Evidence:** [attempts/service.py:200](../app/domains/assessments/attempts/service.py#L200), [attempts/service.py:241](../app/domains/assessments/attempts/service.py#L241), [attempts/service.py:466](../app/domains/assessments/attempts/service.py#L466), and [attempts/router.py](../app/domains/assessments/attempts/router.py).

When the last question's own timer elapses, `_compute_current_question()` returns no current question. The read endpoint does not complete the attempt. The probe returned `in_progress` with `current_question=None`. Completion is possible by calling the question-start endpoint again with a question ID, even though there is no current question to start; there is no explicit finalize endpoint. A client following the current-question response can become stuck until the overall timer expires or the application is disqualified. With no overall timer, only the outer deadline will eventually resolve it through disqualification.

An empty template has a related problem: the publish gate checks that all three template IDs exist, not that they contain questions. Its attempt starts with no discoverable question ID and is not automatically complete.

**Recommendation:** define the outcome for a fully consumed sequence, including timed-out questions and zero-question templates. Expose an explicit, idempotent finalization action or perform the transition through a documented existing mutation/sweep. Do not silently turn GET into a write as a convenience. Reject empty templates at publish if they are invalid for the product.

**Acceptance checks:** last-question timeout, every question skipped, empty template issuance, and no-overall-timer variants reach a documented terminal state without inventing a question ID.

#### F23 — Medium: interview selection does not enforce its advertised mode or past-time rule

**Evidence:** [interviews/schemas.py:50](../app/domains/interviews/schemas.py#L50) and [interviews/scheduling_service.py:204](../app/domains/interviews/scheduling_service.py#L204).

The schema helper is named `_dedupe_and_check_future`, but it does not check the future. A manual slot dated in the year 2000 passed validation. Selecting an existing `slot_id` checks membership and overlap but not whether that time is now in the past.

Separately, the `starts_at` branch does not require `request.self_scheduled`. A service probe with `self_scheduled=False` booked an available time that was not among HR's offered slots. The mode is currently a presentation field rather than an enforced choice between offered slots and open availability.

**Recommendation:** enforce the selected booking mode if manual offers are intended to be restrictive; otherwise document that the applicant may always use open availability. Validate that a newly confirmed time is still bookable at selection time, not only when HR authors the request. Define how idempotent confirmation of an already-selected historical slot should behave. Add service tests, not just schema tests.

#### F24 — Medium: availability accepts invalid end-of-day times and emits duplicate slots

**Evidence:** [interviews/schemas.py:13](../app/domains/interviews/schemas.py#L13), [interviews/availability_service.py:115](../app/domains/interviews/availability_service.py#L115), and [interviews/availability_service.py:406](../app/domains/interviews/availability_service.py#L406).

`_hhmm_to_minutes()` permits hour 24 with any minute through 59. `24:59` becomes 1499, beyond the database's `end_minute <= 1440` constraint. It is accepted by request validation; an attempted save reaches an unhandled constraint failure instead of a useful input error. The valid boundary should distinguish an end of `24:00` from invalid `24:01` and later values.

Recurring windows and date overrides also accept duplicate/overlapping entries. Slot generation appends every matching interval and sorts, without normalization or deduplication. Two identical date overrides produced **four returned slots but only two distinct start times** in a mocked service probe.

**Recommendation:** validate exact time boundaries before persistence and normalize or reject duplicate/overlapping windows under a documented precedence rule. Emit unique booking instants. Include real database checks for boundary constraints and pure/service cases for duplicate windows.

#### F25 — Medium: valid Unicode résumé filenames break download responses

**Evidence:** [applications/router.py:225](../app/domains/applications/router.py#L225), particularly the `Content-Disposition` header at line 236.

The uploaded filename is embedded directly in a quoted HTTP header. A filename such as `张伟.pdf` is valid input for storage, but constructing the response raises `UnicodeEncodeError` because the raw header value cannot be encoded by the response implementation. This was reproduced as **HTTP 500 through the real download route**, with only auth/storage service dependencies mocked.

**Recommendation:** generate a safe ASCII fallback filename and a properly encoded UTF-8 `filename*` parameter. Sanitize quotes and control characters instead of interpolating the original filename. Test Unicode, quotes, whitespace, and control characters while preserving normal ASCII downloads.

#### F26 — Medium: the export cap creates a dead end and still allows a large memory footprint

**Evidence:** [evaluations/router.py:45](../app/domains/evaluations/router.py#L45), [evaluations/pack.py:22](../app/domains/evaluations/pack.py#L22), and [D05](decisions/D05-export-limits.md).

For more than 200 applicants, the error suggests narrowing by pipeline status or requesting a background export. OpenAPI and the handler show neither facility exists: the only business query parameter is `job_post_id`, and the application query always uses `statuses=None`. A job above the cap has no supported subset-export path through this endpoint.

The cap is checked **after** all applicant rows are fetched. For an allowed job, 200 resumes at the accepted 5 MiB size already represent **1,000 MiB of raw resume bytes**, before ZIP output, query objects, and compression buffers. This is a calculated upper workload, not a measured peak. The cap improves the old unlimited-resume case but does not demonstrate a suitable resource bound.

**Recommendation:** add a usable subset/chunk export contract or accurate error guidance; limit the initial selection in SQL; enforce a total-byte budget; offload compression and measure memory. Keep F09 and D05 partial until the actual supported deployment has a tested bound.

#### F27 — Medium: broad integrity-error translation reports the wrong business failure

**Evidence:** [apply_to_job.py:54](../app/use_cases/apply_to_job.py#L54), [auth/service.py:140](../app/domains/auth/service.py#L140), and [applications/service.py:119](../app/domains/applications/service.py#L119).

Every `IntegrityError` at these boundaries is mapped to either duplicate application or duplicate email, regardless of the violated constraint. In the new use case, an assessment constraint failure at commit is therefore reported as “already have an active application.” A missing required value or unrelated foreign-key failure is not a duplicate-email conflict either.

The profile-email update path still has a get-then-update race without the new signup/create error handling. Two concurrent edits can pass the uniqueness pre-check and produce an unhandled unique-key failure.

**Recommendation:** classify the known database constraint by its identifier and translate only that expected conflict. Preserve unexpected failures for diagnostics through the normal generic error boundary. Apply the duplicate-email policy consistently to update as well as create. Test unrelated FK/not-null failures separately from unique-key conflicts.

#### F28 — Medium, policy-dependent: terminal applications can continue occupying interview capacity

**Evidence:** [interviews/availability_service.py:350](../app/domains/interviews/availability_service.py#L350), [interviews/scheduling_service.py:339](../app/domains/interviews/scheduling_service.py#L339), and [applications/service.py](../app/domains/applications/service.py).

Withdrawal/status changes do not clear or cancel a selected interview. Availability and overlap queries include all selected slots without joining/filtering the application's status. Upcoming/calendar queries join applications but do not filter their status either. Consequently, a future selected slot for a withdrawn application can still block another applicant and appear on the upcoming calendar until HR separately deletes the request.

**Recommendation:** decide whether withdrawal/terminal decisions cancel future reservations automatically or require an explicit HR cancellation workflow. Model reservation state independently enough to retain history while releasing capacity, then make calendar and conflict queries agree. This is a verified query/lifecycle gap; its intended business resolution requires the product rule.

#### F29 — Medium: the advisory lock does not protect standalone sweep entry points

**Evidence:** [core/scheduler.py:31](../app/core/scheduler.py#L31), [scripts/expire_overdue_assessment_attempts.py:26](../app/scripts/expire_overdue_assessment_attempts.py#L26), and [scripts/disqualify_overdue_applications.py:31](../app/scripts/disqualify_overdue_applications.py#L31).

The lock is acquired only by `_run_periodic_jobs()`. Running either documented `python -m app.scripts...` entry point does not acquire it. A manual run or a future Airflow task can overlap an active scheduler tick. D06 says the lock remains relevant to manual overlap, but those callers currently bypass it.

**Recommendation:** centralize the protected job execution path so every supported caller observes the same lock scope. If only the paired sweep may run concurrently safely, expose that contract explicitly and use a consistent acquisition order. Test two callers, exceptions, and cancellation/unlock behavior against PostgreSQL. Also verify rollout sets `SCHEDULER_ENABLED` where required: installations using an older environment file inherit the new default-off behavior.

### Remaining maintenance notes

- **Old rate-limit keys:** the new Lua script attaches TTL only when the incremented count equals one. It will not repair a pre-existing key with a higher count and no TTL. Plan a narrowly scoped repair/reset of those rate-limit keys or heal missing TTLs in the script; do not clear unrelated Redis data.
- **Stable pagination:** application lists order by `created_at` only and generic list queries have no explicit default order in the routers. A unique tie-breaker/default ordering would make page membership more predictable. This does not by itself fix concurrent offset-pagination drift.
- **Indexes need query evidence:** the existing partial application index starts with `job_post_id`; applicant-only history queries, overdue scans, and history tables filtered by parent ID deserve query-plan review. Do not add an index to every FK without checking the actual query and write costs.
- **Question validation still needs set semantics:** multiple-choice answers count entries rather than unique selections; duplicated selections can satisfy a minimum. Validate numeric types/finite values and feasible selection bounds together with F10 instead of expanding the untyped config convention.
- **History and metrics definitions remain important:** the original note about `overdue_assessments` counting passed deadlines without checking unfinished attempts still applies. The snapshot and evaluation-version decisions should precede any stronger promise that analytics represents immutable historical decisions.
- **Testability should guide the next extraction:** isolate slot generation and state decisions into typed, I/O-free operations; keep SQL in tested persistence/query boundaries. Avoid adding more forwarding layers simply to make folder contents uniform.

### Revised next steps

1. **Do not close F02–F05 based on the current unit suite.** Add the targeted database/service harness and address transition/booking invariants, immutable assessment history, and reopen eligibility.
2. **Fix the directly reproduced client failures:** numeric question validation, Unicode download headers, invalid availability boundaries, and the export cap's unusable guidance/path.
3. **Test complete workflows:** application staging failure and rollback, final-question timeout, offered-versus-open slot selection, duration edits, cancellation/capacity release, and protected manual sweeps.
4. **Finish the selected product policies:** D01 visibility and D04 deletion restrictions still need code. Keep F13 vocabulary/category/database integrity and F21 resource lifecycle visibly partial.
5. **Then reduce cost and friction:** batch reads, bound export bytes, measure query plans, and consolidate genuinely shared template rules.

## Original review — historical baseline

The remainder preserves the first review for traceability. Its counts, statuses, and source line numbers describe `5469231` before the staged fixes and should be read together with the second-pass status table above. Historical line links may now land near changed code; second-pass references target the reviewed working tree.

## Overall assessment

**The repository has a sensible, maintainable foundation, but its implementation is not consistently clean yet. Keep the domain-based modular monolith and improve its boundaries incrementally. A rewrite, microservices split, or wholesale directory reorganization would not address the main problems.**

The folder layout makes features easy to locate. Authentication, applications, jobs, assessments, interviews, evaluations, and analytics have recognizable ownership. Dependency injection, centralized domain errors, explicit API versioning, and fast unit tests are useful foundations.

The greatest risks are behavioral: a business operation can commit halfway through; concurrent requests can overwrite valid state; assessments depend on mutable questions; and substantial database behavior has no integration tests. These risks make future changes difficult to trust even when the files look organized and lint passes.

| Area | Assessment | Main reason |
| --- | --- | --- |
| Feature organization | Good | Clear vertical slices; recent interview/evaluation extraction improves navigation. |
| Naming and readability | Generally good | Descriptive modules and small CRUD services; several larger modules combine responsibilities. |
| Architectural consistency | Mixed | Entity/repository/UoW pattern coexists with services that directly query and commit ORM models. |
| Transaction and concurrency safety | Needs priority work | Cross-service partial commits and read/check/write races. |
| Data integrity and history | Needs priority work | Mutable assessment definitions and incomplete evaluation constraints. |
| Testing | Useful foundation, insufficient breadth | 205 passing tests, but database queries and important workflows remain untested. |
| Performance as data grows | Needs targeted work | Per-row database queries and entire exports retained in memory. |
| Documentation and operations | Incomplete | Empty README, architectural guidance that has drifted, no checked-in CI workflow. |

## Scope and verification

The review covered application composition, core infrastructure, domain dependencies, service/repository boundaries, request validation, representative CRUD paths, assessment workflows, interview scheduling, evaluation import/export, analytics queries, migrations, scripts, and the existing tests. It is a repository-level engineering review, not a production load test or an exhaustive security audit.

The application contains **153 Python files and 13,080 physical lines**, including scripts and empty package markers. There are **17 test modules**, **15 migration files**, **33 registered ORM tables**, and **76 OpenAPI paths**. These counts describe size, not quality or coverage.

| Check | Result |
| --- | --- |
| `.venv/bin/pytest -q` | **205 passed**, 22 warnings, 3.62 seconds. |
| `.venv/bin/ruff check .` | **Passed.** |
| `.venv/bin/ruff format --check .` | **Failed:** 9 files would be reformatted; 183 already formatted. One of the nine is Markdown containing a Python example. |
| Import app and generate OpenAPI | **Passed**, without starting the server or lifespan scheduler. |
| SQLAlchemy `configure_mappers()` | **Passed.** This does not verify the deployed database schema. |
| Alembic revision graph | One head: **`a1c7e2f4d8b3`**. |
| Alembic offline SQL generation, equivalent to `upgrade head --sql` | **Failed** in `f9d26d7ef36a`: an online row lookup receives `None` in offline mode and calls `.scalar_one()`. |
| Temporary, in-memory validation probes | Confirmed invalid numeric config failures, acceptance of negative/zero deadline extensions, acceptance of unknown/duplicate evaluation dimensions, and a 73-byte password error. |
| Temporary service probe with mocked repositories | Confirmed assessment start is allowed for an owner whose parent application is withdrawn and past its assessment deadline. |

No live database, Redis, or MinIO operations were performed. Migrations, seed scripts, scheduler jobs, and destructive commands were not executed against a database. Concurrency findings below come from the source and constraints, not a two-connection runtime reproduction. No coverage percentage was measured. Dependency vulnerability scanning and frontend behavior were outside scope.

The test warnings include two test-client deprecations and 20 JWT key-length warnings from the local test configuration. Secret values are not reproduced here.

## What is already working well

1. **Domain-based organization fits this application.** Related code lives together, and `assessments/` is a useful grouping namespace. Splitting interviews and evaluations out of applications is a reasonable direction.
2. **API composition is explicit.** [app/api/v1.py](../app/api/v1.py) assembles domain routers, while [app/main.py](../app/main.py) handles application setup. Empty `__init__.py` files avoid hidden initialization logic.
3. **Domain exceptions have a consistent response boundary.** [app/core/exception_handlers.py](../app/core/exception_handlers.py) maps errors centrally and avoids returning internal exception details to clients.
4. **Several important permissions are centralized.** [app/domains/rbac/dependencies.py](../app/domains/rbac/dependencies.py) supplies reusable permission checks. Application reads reuse owner-or-permission checks, returning 404 for another applicant's record.
5. **The entity/repository pattern provides useful test seams.** Many services can exercise business decisions without a database. Repositories generally stage changes rather than owning commits.
6. **Database constraints already protect important invariants.** Examples include the partial unique index for non-withdrawn applications, one attempt per application/template type, and one live answer per question. These are stronger guarantees than service checks alone.
7. **Some query paths already use sensible projections and batching.** Application lists avoid loading complete related entities; evaluation detail loading batches score retrieval; analytics is explicitly a read-only reporting boundary.
8. **Some history is intentionally preserved.** Resume keys are captured on applications, assessment reopens supersede answers, and deadline extensions record an actor and reason. Extend this discipline to the gaps below.
9. **The lockfile and tooling are present.** `uv.lock`, a Python version file, pytest configuration, and Ruff provide a reproducible starting point. The current lint result is clean.
10. **Evaluation packaging is separated from I/O.** [app/domains/evaluations/pack.py](../app/domains/evaluations/pack.py) takes loaded data and builds an artifact without database or storage access. Its size alone is not a design defect; much of it is embedded document content.

## Prioritized findings

**High** means a material workflow, data-integrity, or concurrency risk. **Medium** means a concrete defect or a substantial maintenance/scaling weakness. **Low** means cleanup or a smaller operational improvement. These are engineering priorities, not security severity scores.

### F01 — High: application creation is not one atomic operation

**Evidence:** [applications/router.py:46](../app/domains/applications/router.py#L46), [applications/service.py:62](../app/domains/applications/service.py#L62), and [attempts/service.py:70](../app/domains/assessments/attempts/service.py#L70).

`create_application()` calls `ApplicationService.create()`, which commits the application. It then calls `create_attempts_for_application()`, which commits separately. Sharing the same request session does not make these two commits atomic.

**Failure scenario:** the first commit succeeds, then attempt creation fails or the process stops. The application remains, retrying application creation conflicts with its unique index, and there is no normal retry path that completes the missing attempts. `is_application_fully_assessed()` also treats zero attempts as complete, so the broken state can escape the overdue sweep.

**Recommendation:** introduce an application-level use case that stages the application and required attempts, flushes when needed, and commits once. Make retry/recovery semantics explicit. Do not solve this merely by moving the existing two calls to another file.

**Verification needed:** inject a failure after the application is staged and prove that neither application nor attempts persist; verify retries cannot create partial or duplicate workflows.

### F02 — High: state transitions are vulnerable to concurrent overwrites

**Evidence:** [applications/service.py:183](../app/domains/applications/service.py#L183), [applications/repository.py:42](../app/domains/applications/repository.py#L42), [attempts/repository.py:104](../app/domains/assessments/attempts/repository.py#L104), and [attempts/service.py:285](../app/domains/assessments/attempts/service.py#L285).

Transitions read a state, validate it, and later write a new state without an expected-state condition, row lock, or version check. The database check constraints allow individual status values; they do not enforce the transition graph.

**Failure scenarios:** withdrawal competes with HR advancement; a deadline extension competes with disqualification; an answer completes an attempt while a sweep marks it expired. Depending on timing, the last write can overwrite a newer decision. The sweep's claim of an idempotent no-op after advancement is not a concurrency guarantee.

**Recommendation:** use conditional updates with affected-row checks or a consistent row-locking strategy around the state decision. Recheck relevant deadlines and completion predicates within that protected operation. Define a consistent lock order for workflows touching both applications and attempts.

**Verification needed:** two-session PostgreSQL tests for withdrawal versus advancement, extension versus sweep, completion versus expiry, and simultaneous question starts. The existing live-answer uniqueness constraint prevents duplicate rows but does not provide a clean conflict response by itself.

### F03 — High: interview overlap checks are not enforced atomically

**Evidence:** [interviews/scheduling_service.py:177](../app/domains/interviews/scheduling_service.py#L177), [interviews/scheduling_service.py:204](../app/domains/interviews/scheduling_service.py#L204), and [interviews/models.py:212](../app/domains/interviews/models.py#L212).

The service checks overlapping intervals in Python. The database only guarantees unique selected **start instants**, not non-overlapping time ranges.

**Failure scenario:** two concurrent requests book 09:00–09:45 and 09:15–10:00. Both can observe no confirmed overlap and both can commit because their start times differ. Repeating the read immediately before commit does not close this race.

There is another path around the rule: `set_request()` preserves a selected slot while allowing its duration to change, without rechecking the expanded interval against other bookings.

**Recommendation:** enforce the chosen booking-resource rule atomically. Options include serializing reservations using an agreed lock or modeling a reservation interval with an appropriate database exclusion constraint. Include duration changes and rescheduling in the same invariant.

**Verification needed:** concurrent different-start overlapping bookings, editing a confirmed duration into another booking, and switching between two existing slots under the partial unique constraint.

### F04 — High: assessment history depends on mutable, deletable definitions

**Evidence:** [attempts/models.py:48](../app/domains/assessments/attempts/models.py#L48), [pre_assessment_templates/service.py:75](../app/domains/assessments/pre_assessment_templates/service.py#L75), [pre_assessment_templates/service.py:113](../app/domains/assessments/pre_assessment_templates/service.py#L113), and [attempts/service.py:343](../app/domains/assessments/attempts/service.py#L343). The other two template domains follow the same pattern.

Attempts reference a template ID without a foreign key, and answers reference question IDs without foreign keys. Reads and reviews reconstruct the questions from the current template. HR can edit prompts, answer types, order, and timers after attempts exist.

**Failure scenarios:** an old answer is displayed against a revised prompt; deleting a question hides its answer from the review; changing a timer changes an ongoing candidate's deadline. After detaching a template from its job posts, deleting it can succeed despite existing attempts. The delete error message mentions attempts, but no FK or explicit attempt lookup enforces that protection. Applicant detail/start/submit paths then dereference a missing template.

The repository guidance explicitly accepts mutable templates. That documents a tradeoff, but does not preserve the meaning of historical answers or prevent broken attempts.

**Recommendation:** version or snapshot the template, questions, and timing rules at issuance. Keep authoring editable while issued versions remain stable. As an interim measure, protect referenced definitions through a well-defined lifecycle boundary and return a domain error for missing references. A common template identity/version table is an option; merging all three domains is not a prerequisite.

**Verification needed:** edit, reorder, delete, and detach definitions after issuance and confirm an existing attempt remains readable and answerable against its original definition.

### F05 — High: assessment writes do not enforce parent application eligibility

**Evidence:** [attempts/service.py:95](../app/domains/assessments/attempts/service.py#L95), [attempts/service.py:153](../app/domains/assessments/attempts/service.py#L153), and [attempts/service.py:246](../app/domains/assessments/attempts/service.py#L246).

`_require_owned_attempt()` checks ownership but not application status or the outer assessment deadline. Start/submit enforce attempt timing but do not enforce the parent workflow. Reopen rejects a disqualified parent specifically, rather than requiring the intended eligible states.

**Confirmed:** an in-memory probe successfully reached `start_question()` for an owned, not-started attempt with a withdrawn parent and a past assessment deadline. No router dependency adds the missing parent-state check.

**Impact:** terminal applications can continue receiving assessment activity. Completion after the outer deadline but before the periodic sweep can also change whether an application gets disqualified.

**Recommendation:** define the allowed parent states and deadline policy once, and apply them to every assessment mutation. Keep access to historical results separate from permission to continue answering. If a grace period is intended, encode it explicitly rather than deriving it from scheduler timing.

### F06 — Medium: the test suite does not cover the riskiest boundaries

**Evidence:** [tests/unit](../tests/unit), especially [interviews/test_scheduling.py](../tests/unit/interviews/test_scheduling.py), [interviews/test_availability.py](../tests/unit/interviews/test_availability.py), and [analytics/test_service.py](../tests/unit/analytics/test_service.py).

The 205 tests are valuable, but their count overstates workflow coverage if read without context:

| Area | Current evidence | Important gap |
| --- | --- | --- |
| Applications and attempts | Substantial mocked service tests | Real transaction composition, persistence, races, SQL behavior. |
| Interviews | Schema/helper tests | Neither booking service nor availability generation is exercised. |
| Evaluations | Four packaging tests | Import, latest-selection queries, dimension integrity, CSV export. |
| Analytics | Aggregation helpers and a forwarding test | The 617-line query repository is not exercised against SQL. |
| Jobs | Publish-gate tests | Joins, hydration, CRUD, attachment constraints, concurrency. |
| Positions, tags, addresses | No dedicated test modules | Delete restrictions and validation behavior. |
| API and infrastructure | Throwaway exception-handler app | Real route composition, auth/permission dependencies, pagination, scheduler lifecycle, storage failure paths. |

Mocks commonly use bare `AsyncMock()` without an interface specification, so repository method/signature drift may go unnoticed. Tests also import globally instantiated settings; the suite requires configuration even when infrastructure is not contacted.

**Recommendation:** keep the fast unit tests, introduce explicit test settings, and add a focused PostgreSQL integration suite plus real-app API tests with controlled dependencies. Start with the failure cases in F01–F05. Use scoped/spec-based mocks or small typed fakes. Avoid spending the next testing effort on more forwarding-only tests.

### F07 — Medium: there are multiple competing architectural contracts

**Evidence:** [CLAUDE.md:76](../CLAUDE.md#L76), [interviews/scheduling_service.py:43](../app/domains/interviews/scheduling_service.py#L43), [evaluations/service.py:40](../app/domains/evaluations/service.py#L40), [applications/service.py:5](../app/domains/applications/service.py#L5), and [attempts/repository.py:74](../app/domains/assessments/attempts/repository.py#L74).

The stated convention is router → service → repository → ORM, using plain entities and a shared UoW. In practice:

- Interviews and evaluations accept `AsyncSession`, import other domains' ORM models, build responses, and commit directly.
- Applications passes SQLAlchemy `Select` objects through its service and catches `IntegrityError` there.
- The attempts repository returns ORM models to the service for scorecard summaries.
- Several list routers perform database pagination directly; applications routers assemble cross-domain business views.
- Services import concrete repositories and the concrete UoW, so the entities alone do not make the service dependency graph infrastructure-independent.

These choices are not individually invalid. The maintenance problem is that contributors must infer which rules actually apply. Moving files into new domain folders does not establish the dependency boundary by itself.

**Recommendation:** document two explicit paths: a transactional write/use-case path with clear ownership, and a read/query path that may use cross-domain projections. Bring interviews/evaluations writes into the chosen convention as they are changed. Use small protocols only where they help isolate real variability; do not introduce an interface for every trivial class. Keep analytics' deliberate cross-domain read boundary.

### F08 — Medium: entity mapping hides per-row database work

**Evidence:** [job_posts/repository.py:29](../app/domains/job_posts/repository.py#L29), [core/repository.py:43](../app/core/repository.py#L43), [attempts/repository.py:40](../app/domains/assessments/attempts/repository.py#L40), and [applications/router.py:181](../app/domains/applications/router.py#L181).

Each job-post `_to_entity()` performs five extra queries: tags, exclusions, and three template attachments. Mapping 50 job posts therefore adds **250 queries**, before the page/count queries and address/position eager loads. This is a source-derived query count, not a latency benchmark.

Template mapping retrieves questions per template. Attempt mapping retrieves answers and reopen history per attempt. The assessment-review endpoint loops over applicants, loads all assessment types for each, and then selects the requested type. Its page size bounds the row count but does not eliminate the query multiplication.

**Recommendation:** make mapping pure after data has been fetched; bulk-fetch related data per page or use explicit projections. Batch the selected assessment type for the page. Establish a query-count test for these endpoints. Do not parallelize operations on the same `AsyncSession` as a substitute for batching.

### F09 — Medium: exports and scheduling queries have unbounded workload

**Evidence:** [evaluations/router.py:43](../app/domains/evaluations/router.py#L43), [evaluations/pack.py:425](../app/domains/evaluations/pack.py#L425), [interviews/availability_service.py:350](../app/domains/interviews/availability_service.py#L350), and [evaluations/service.py:140](../app/domains/evaluations/service.py#L140).

Evaluation-pack export loads every applicant, downloads resumes sequentially, keeps all resume bytes in a list, and builds a complete compressed ZIP synchronously inside an async route. Hundreds of resumes can consume substantial memory; ZIP compression also occupies the event-loop thread. No export limit or background-job boundary is present.

Scheduling checks retrieve all confirmed bookings, including historical ones, then repeatedly compare intervals in Python. Evaluation list helpers retrieve all evaluation history for the selected applications and discard older rows in Python.

**Recommendation:** bound exports or move larger ones to a background task that writes to temporary/object storage; offload compression and batch database reads. Restrict booking queries to the requested horizon. Select latest evaluations in SQL and add supporting indexes based on query plans. Measure representative workloads before choosing broader infrastructure changes.

### F10 — Medium: validation is incomplete and sometimes raises runtime errors

**Evidence:** [core/question_types.py:75](../app/core/question_types.py#L75), [applications/schemas.py:40](../app/domains/applications/schemas.py#L40), [applications/service.py:222](../app/domains/applications/service.py#L222), [job_posts/schemas.py:11](../app/domains/job_posts/schemas.py#L11), and [pre_assessment_templates/schemas.py:9](../app/domains/assessments/pre_assessment_templates/schemas.py#L9).

**Confirmed with synthetic inputs:**

- A numeric question config containing `{"min": "low"}` is accepted; submitting a numeric answer raises `TypeError`.
- `{"min": "low", "max": 10}` raises `TypeError` during config validation rather than a domain validation error.
- Deadline extensions accept `-1` and `0` days, an empty reason, and a timezone-naive absolute datetime. The service does not require the computed deadline to extend the old one or lie in the future.

There are similar boundary gaps: unconstrained assessment-window days, question/template timers, salary order/range, and string fields whose database columns have smaller maximum lengths. For example, authentication accepts an unconstrained middle initial while the database column is length one. Invalid payloads can reach database failures instead of a clear client error.

**Recommendation:** use typed question configurations or explicit per-type checks; align schema bounds with database limits; validate positive durations and salary relationships; define an aware-datetime convention; validate deadline-extension invariants in the service as well as request shape in the schema. Add targeted malformed-input tests across the three template types.

### F11 — Medium: authentication performs blocking password work and accepts unsupported lengths

**Evidence:** [core/security.py:22](../app/core/security.py#L22), [auth/service.py:109](../app/domains/auth/service.py#L109), [auth/service.py:206](../app/domains/auth/service.py#L206), and [auth/router.py:54](../app/domains/auth/router.py#L54).

Synchronous bcrypt hashing and verification run directly inside async service methods. Each call occupies that event-loop thread until it finishes. MinIO operations are already offloaded, so the treatment is inconsistent.

Password inputs have no byte-length validation. The installed bcrypt implementation raises `ValueError` for a 73-byte password; this was reproduced locally. In signup, the upload occurs before password hashing, so this input can fail after writing a resume object. Multibyte Unicode makes character count an insufficient limit.

**Recommendation:** offload password operations through a bounded execution path and define a consistent password policy at signup, HR creation, login, and CLI bootstrap. Handle unsupported lengths as client validation failures. Do not silently truncate passwords.

### F12 — Medium: upload size and failure handling are incomplete

**Evidence:** [auth/router.py:61](../app/domains/auth/router.py#L61), [auth/service.py:83](../app/domains/auth/service.py#L83), [auth/service.py:91](../app/domains/auth/service.py#L91), and [core/storage.py](../app/core/storage.py).

The router reads the entire upload into bytes before enforcing the service's 5 MB limit. The limit therefore protects accepted storage size, but does not bound that read's memory use. No repository-level request-body limit is shown; an external proxy limit was not assessed.

MinIO upload precedes the database commit, with no compensation if hashing or persistence fails. Concurrent signup attempts for the same email can both pass the pre-check; the losing unique-key insert produces an unhandled database error and can leave an orphaned object.

**Recommendation:** perform a bounded read before loading the complete payload, validate before uploading, translate the specific duplicate-email constraint, and provide compensating deletion or a pending-upload cleanup mechanism. Define storage-failure behavior explicitly. Database UoW alone cannot make a MinIO write atomic with PostgreSQL.

### F13 — Medium: evaluation imports do not enforce their dimension contract

**Evidence:** [evaluations/schemas.py:9](../app/domains/evaluations/schemas.py#L9), [evaluations/service.py:44](../app/domains/evaluations/service.py#L44), [evaluations/models.py:51](../app/domains/evaluations/models.py#L51), and [evaluations/dimensions.py](../app/domains/evaluations/dimensions.py).

Ratings use an enum, but `dimension` is any string. There is no uniqueness constraint on `(evaluation_id, category, dimension)` and no duplicate validation within a category. A synthetic payload with two unknown, duplicate resume dimensions was accepted.

**Impact:** analytics can count duplicate ratings while CSV export collapses them into a dictionary or omits unknown dimensions. Different outputs can disagree about the same imported evaluation. Request text lengths also do not match the database's bounded fields.

**Recommendation:** validate each dimension against its category and rubric version, reject duplicates, enforce uniqueness in PostgreSQL, and align text bounds. Report why records are skipped. Treat a future vocabulary change as a versioned contract.

### F14 — Medium: “latest evaluation” is ambiguous for tied timestamps

**Evidence:** [evaluations/service.py:110](../app/domains/evaluations/service.py#L110), [evaluations/service.py:140](../app/domains/evaluations/service.py#L140), [evaluations/models.py:46](../app/domains/evaluations/models.py#L46), and [analytics/repository.py:515](../app/domains/analytics/repository.py#L515).

Latest-selection queries order only by `created_at`. Imports allow repeated entries for one application in a single transaction, and the timestamp uses PostgreSQL `now()`, so those entries can receive the same timestamp. Detail, batch, CSV, and analytics queries need not choose the same tied row.

**Recommendation:** reject duplicate application IDs in one import unless explicitly supported. Define a meaningful version/import sequence or a current-evaluation pointer, and reuse the same selection rule everywhere. A UUID tie-breaker makes selection deterministic but does not establish which import is newer. Define whether retrying the same import should create another historical run.

### F15 — Medium: self-scheduled interview requests lose their pending-action flag

**Evidence:** [interviews/scheduling_service.py:121](../app/domains/interviews/scheduling_service.py#L121), [interviews/scheduling_service.py:270](../app/domains/interviews/scheduling_service.py#L270), and [applications/router.py:67](../app/domains/applications/router.py#L67).

An empty slot list creates a self-scheduled request with no slot rows. `pending_selection_application_ids()` uses an inner join to slots, which excludes that request entirely. Therefore `/applications/me` will not set `pick_interview_time` for a newly created self-scheduled request.

**Verification:** captured the generated statement with a mocked session; it uses `JOIN interview_slots`, not an outer join or `NOT EXISTS` predicate.

**Recommendation:** query requests with no selected slot, including requests with zero slots. Add behavior tests covering zero slots, offered but unselected slots, and a selected slot. The `statuses_for_job_post()` method already uses an outer join and illustrates the inconsistency.

### F16 — Medium: background jobs inherit web-process scaling and failure behavior

**Evidence:** [main.py:17](../app/main.py#L17), [core/scheduler.py:16](../app/core/scheduler.py#L16), [scripts/disqualify_overdue_applications.py:32](../app/scripts/disqualify_overdue_applications.py#L32), and [attempts/repository.py:134](../app/domains/assessments/attempts/repository.py#L134).

Every web-process lifespan starts its own scheduler. With multiple workers or replicas, each process can run the same sweep. There is no enable/disable setting, leader election, or distributed execution lock in the repository. This increases the importance of F02 even if a single process is used today.

Sweeps load candidate rows broadly and perform per-record reads/writes. The expiry job's failure prevents disqualification from running that tick because both are awaited sequentially. That ordering may be intentional, but its failure semantics are not made operationally explicit. Scripts use `print()` and do not record a queryable last-success marker.

**Recommendation:** make scheduler ownership explicit, add a deployment switch, protect execution across replicas, and process bounded batches. Keep state changes safe under retries. Add structured job counts, duration, and last-success/failure visibility. Preserve the useful standalone job entry points; moving to Airflow is not required to fix ownership.

### F17 — Medium: the rate-limit counter and expiry are separate operations

**Evidence:** [core/rate_limit.py:17](../app/core/rate_limit.py#L17).

The code increments a Redis key, then sets its expiry only when the count is one. If the process is interrupted or the expiry command fails between these steps, the key can remain without a TTL. Later requests increment it but never attach the missing expiry; after the threshold, the IP can remain blocked indefinitely.

**Recommendation:** make increment-plus-first-expiry atomic, for example in a Redis script. Define failure behavior when Redis is unavailable and verify client-IP handling in the actual proxy deployment. Include a TTL invariant test with a real disposable Redis instance. Current proxy behavior was not inspected.

### F18 — Medium: migration history is development-oriented and offline generation is broken

**Evidence:** [449cadbbefb7:23](../alembic/versions/449cadbbefb7_split_assessment_templates_into_3_.py#L23), [f4d2d1f8394c:29](../alembic/versions/f4d2d1f8394c_add_assessments_pipeline_templates_.py#L29), and [f9d26d7ef36a:113](../alembic/versions/f9d26d7ef36a_add_jobs_domain_positions_tags_company_.py#L113).

The template-split upgrade explicitly deletes attempts, answers, and reopen history, then drops the old template/question/attachment tables without migration of their contents. Its comment says this was acceptable for disposable development data. The status migration replaces allowed values without backfilling old statuses.

These are **conditional deployment risks**, not evidence that a current production database lost data. They matter if an existing populated database must cross those revisions. A fresh empty database does not have historical data to preserve.

Separately, offline SQL generation was attempted and failed in the jobs migration because it requires query results while emitting SQL. The single valid revision head does not prove migration execution works.

**Recommendation:** define the first supported production baseline and supported upgrade paths. For populated deployments, design explicit data-preserving transitions; do not casually rewrite already-applied revisions. Test fresh upgrades and supported populated upgrades against disposable PostgreSQL. Either support offline SQL generation or clearly document that online migration execution is required. A schema downgrade is not automatically a data rollback.

### F19 — Medium: documentation and automated quality enforcement lag the code

**Evidence:** [README.md](../README.md) is empty; [CLAUDE.md](../CLAUDE.md) is approximately 47 KB; [pyproject.toml](../pyproject.toml) contains a placeholder project description. No checked-in CI workflow was found in this repository.

Useful knowledge exists in `CLAUDE.md`, but it mixes conventions, operational instructions, implementation details, and historical explanation. Some statements are stale: it says services never see SQLAlchemy types; it describes assessment attachments as optional while the publish gate requires all three; it cites 106 tests and says jobs has no tests despite the current publish-gate suite. The sync-engine comments also disagree with how Alembic and the admin script actually create/use sessions.

**Recommendation:** give humans a concise README covering setup, configuration, migrations, running, tests, bootstrap, and scheduler ownership. Put current architecture and deliberate exceptions in a short architecture document; keep dated plans clearly historical. Make agent guidance link to these sources. Add CI for tests, Ruff lint/format, and the focused integration suite. Introduce type checking incrementally for changed boundaries.

The formatting check currently flags four domain Python files, two scripts, two test files, and `docs/plans/applications-domain.md`. This is low-severity cleanup within a broader enforcement gap. Lint passing does not imply formatting passes.

### F20 — Low: repeated template code and vocabulary increase change cost

**Evidence:** [pre-assessment service](../app/domains/assessments/pre_assessment_templates/service.py), [culture-fit service](../app/domains/assessments/culture_fit_templates/service.py), [technical service](../app/domains/assessments/technical_assessment_templates/service.py), [evaluations/pack.py:295](../app/domains/evaluations/pack.py#L295), and [evaluations/dimensions.py:6](../app/domains/evaluations/dimensions.py#L6).

The template domains repeat nearly identical schemas, CRUD, ordering, validation, and mapping. Evaluation dimensions are also defined independently in the packaging module and the shared dimensions module. Changes must be synchronized manually.

**Recommendation:** retain domain-specific names and routes, but share the stable question-authoring policies and dimension vocabulary. Consider a small common template capability/protocol after identifying actual shared behavior. Avoid a highly configurable generic CRUD framework: three explicit short services can be easier to maintain than one abstraction with many switches.

### F21 — Low: configuration, lifecycle, and observability need explicit ownership

**Evidence:** [core/config.py](../app/core/config.py), [core/database.py](../app/core/database.py), [core/rate_limit.py](../app/core/rate_limit.py), [main.py](../app/main.py), [docker-compose.yml](../docker-compose.yml), and [scripts/create_admin.py:21](../app/scripts/create_admin.py#L21).

Settings, engines, Redis, MinIO, and the scheduler are created globally. Application shutdown stops the scheduler but does not explicitly close Redis or dispose database engines. `/health` is liveness only and does not assess dependency readiness or sweep health. There is no project-level request correlation, domain-event audit trail, or metrics setup visible here.

The compose file provides development infrastructure, not an application deployment definition. The MinIO image has no version tag. Default bootstrap credentials are supplied for local use. Also, `create_admin.py` reads `ADMIN_*` through `os.environ`; Pydantic's reading of `.env` into `Settings` does not export those values into the process environment, and `Settings` does not declare those admin fields. Editing only `.env` may therefore not configure bootstrap as its documentation implies.

**Recommendation:** manage long-lived clients in lifespan with injectable factories, close them explicitly, supply isolated test configuration, and document liveness versus readiness. Correct the admin configuration source. Pin development service versions deliberately, separate development defaults from deployment requirements, and schedule cleanup of expired revoked-token rows. Add operational instrumentation where it answers a real support question rather than as a large generic framework.

## Product-policy questions exposed by the structure

These are observed behaviors requiring an explicit contract. They are not automatically defects without knowing the intended product rules.

| Behavior | Evidence | Decision to record |
| --- | --- | --- |
| Unauthenticated users can list/read draft and closed job posts. | [job_posts/router.py:45](../app/domains/job_posts/router.py#L45), [job_posts/service.py:84](../app/domains/job_posts/service.py#L84): no mandatory published-only predicate or read permission. | If drafts are internal, separate public and staff read policies; do not rely on frontend filters. |
| Deleting a job post cascades to applications and then attempts, evaluations, interviews, and audit rows. | [applications/models.py:47](../app/domains/applications/models.py#L47) and child-model cascade FKs. | Decide whether historical hiring records may be erased by normal job deletion or whether archive/restrict is required. “Append-only” logs currently survive edits, not parent deletion. |
| All interviews share one organization-wide capacity rule; interviewer assignments are descriptive only. | [interviews/models.py:140](../app/domains/interviews/models.py#L140), `_booked_intervals()`, and `_overlaps_confirmed()`. | Confirm one shared calendar capacity is intentional. If capacity belongs to interviewers/rooms, model that resource before extending scheduling. |
| Interviewer assignment accepts any existing user ID, while staff discovery lists active HR/admin users. | [interviews/availability_service.py:308](../app/domains/interviews/availability_service.py#L308). | Decide whether assignment must enforce the same role/active rule as discovery. |
| Authentication refresh returns a new access token without rotating the refresh token; logout revokes refresh only. | [auth/service.py:218](../app/domains/auth/service.py#L218). | Document session semantics and whether they meet the application's requirements. This alone is not evidence of an implementation bug. |
| CSV exports contain user-authored names and imported text verbatim. | [evaluations/service.py:207](../app/domains/evaluations/service.py#L207), [evaluations/pack.py:335](../app/domains/evaluations/pack.py#L335). | Define spreadsheet-safe handling of formula-like text while preserving legitimate negative numeric values. CSV quoting alone does not define how spreadsheet applications interpret cells. |
| Analytics' `overdue_assessments` counts active applications with past deadlines, without checking for unfinished attempts. | [analytics/repository.py:141](../app/domains/analytics/repository.py#L141). | Confirm whether this means “unfinished and overdue” or merely “deadline has passed”; align the query and field description. |

## Recommended structure going forward

Keep the current top-level shape and introduce only boundaries that solve the identified problems:

```text
app/
  main.py                     application/lifespan setup
  api/                        versioned route assembly
  core/                       shared technical infrastructure and errors
  use_cases/                  workflows spanning domains, one transaction owner
    apply_to_job.py           application + assessment issuance
  domains/
    <domain>/
      router.py               HTTP translation and dependency entry points
      schemas.py              request/response contracts
      service.py              business decisions
      repository.py           persistence and mapping
      entities.py             plain business data where useful
      models.py               ORM definitions
      dependencies.py         construction/wiring
      exceptions.py           named domain errors
      queries.py              optional read projections when substantial
    analytics/                explicit cross-domain reporting boundary
  scripts/                    thin CLI adapters over reusable jobs/use cases
tests/
  unit/                       pure rules and service decisions
  integration/                real PostgreSQL constraints, queries, transactions
  api/                        real route wiring and authorization contracts
docs/
  architecture.md             current rules and approved exceptions
  decisions/                  short records of consequential design choices
```

This is a suggested direction, not a requirement to create every file immediately. `use_cases/` is justified by the actual cross-domain creation workflow. Read projections can stay in repositories until their size or ownership makes a separate module useful. Simple CRUD domains do not need additional layers merely for visual uniformity.

Apply these conventions consistently:

- One transactional business operation has one explicit commit owner.
- Repositories do not secretly commit; entity conversion does not secretly fetch large related graphs.
- Cross-domain writes go through defined operations; reporting may query models through an explicit read boundary.
- API shape validation and business invariants are separate responsibilities, with clear errors from both.
- Issued assessments and imported evaluations carry stable versions/history.
- Dependency factories are composition code; business decisions are independently testable.
- Use typed result objects for stable cross-domain contracts instead of loosely shaped `dict`, `Any`, or ORM rows. Keep flexible JSON only where the question/answer format actually requires it.

## Practical improvement sequence

| Phase | Work | Completion evidence |
| --- | --- | --- |
| 1. Protect core workflows | F01–F05: atomic application issuance, guarded transitions, booking overlap invariant, assessment snapshots/lifecycle, parent eligibility. | Targeted failure and two-session PostgreSQL tests reproduce the old risks and pass with the fixes. |
| 2. Close boundary defects | F10–F15 and F17: validation, password execution/length, upload cleanup, evaluation integrity/current selection, pending interview action, atomic rate limiting. | API tests return controlled errors; import/export agree; relevant infrastructure failure cases are covered. |
| 3. Make change safe | F06, F07, F18, F19: integration suite, documented write/read conventions, migration support policy, README and CI. | Clean checkout has documented repeatable setup; supported migrations run against disposable databases; checks run automatically. |
| 4. Control growth | F08, F09, F16: batch reads, bounded exports/sweeps, scheduler ownership, query-based indexes. | Representative page query counts stay bounded; exports have measured limits; multiple web replicas do not duplicate unprotected job execution. |
| 5. Reduce routine friction | F20–F21: shared policies/vocabulary, client lifecycle, bootstrap settings, formatting and incremental typing. | Fewer synchronized edits are needed for a rule change; test/production configuration and shutdown behavior are explicit. |

The most valuable next change is a small, thoroughly tested correction to application issuance and its transaction boundary. Cosmetic cleanup can follow without obscuring the behavior change. The existing domain organization is worth preserving while these guarantees are strengthened.
