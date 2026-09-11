# Maintainability review — remediation progress

Tracks work against the findings in [maintainability-review.md](maintainability-review.md).
Baseline: commit `5469231`. Started 2026-09-10.

**Second review, 2026-09-10:** statuses below were checked against the staged
working tree, not just HEAD. The second pass changes documentation only.
See the current assessment and new F22–F29 findings in
[maintainability-review.md](maintainability-review.md#second-review--current-assessment).
“Done” means the stated implementation is present; it does not substitute for
the explicitly pending real-database or hosted-CI verification. Earlier batch
notes below are historical implementation claims and are superseded by this
status table where they disagree.

Legend: ✅ done · 🟡 partial (scope noted) · ⛔ deferred (reason noted) · 🔵 decision recorded (`docs/decisions/`) · ⬜ not started

The earlier remediation pass targeted changes without a live-Postgres
two-session test harness and recorded product decisions in ADRs. Its deferred
integration work (F02, F03-full, F04-full, F08) remains a recommended next phase.
This second review verifies those changes and documents remaining work; it
does not implement fixes or make new product decisions.

**Batches 6–9 (after the second review) then addressed most of the corrections
and new F22–F29 findings — see the change log. The status table rows below are
updated to reflect that; the "Second-pass verification notes" section is a
frozen snapshot of the review and is not re-run per batch.**

## Findings

| ID | Severity | Status | Notes |
| --- | --- | --- | --- |
| F01 | High | ✅ | Stages both services with `commit=False`, one commit. Batch 6: `ApplyToJob.execute` now rolls back on *any* exception (not just commit `IntegrityError`), owning its transaction for non-request callers. Real-DB persistence test still pending (F06). |
| F02 | High | ⛔ | Transition races. Needs integration harness (F06) — deferred. |
| F03 | High | 🟡 | Batch 6: `select_slot` rejects past slots + arbitrary times against a hand-picked offer. The different-start overlap race and an atomic exclusion constraint still need F06. |
| F04 | High | 🟡 | `_require_template` raises `MissingAssessmentTemplateError` (404) instead of `AttributeError` when a template was deleted after an attempt. Live-attempt delete block + snapshot versioning deferred — see D03 (would break the template↔attempts independence without a design change). |
| F05 | High | ✅ | Start/answer parent-status + deadline checks, and (batch 6) `reopen()` now rejects a non-answerable parent too. Concurrent races still fall under F02. |
| F06 | Medium | 🟡 | 239 unit cases pass; CI added. Committed Postgres integration + real-app API tests remain the recommended next phase. |
| F07 | Medium | 🟡 | `docs/architecture.md` written (write/read paths + approved exceptions + known gaps). Bringing interviews/evaluations onto the repository/entity path stays deferred (Phase 2/3, needs F06). |
| F08 | Medium | ⛔ | `_to_entity` N+1 — needs F06. |
| F09 | Medium | 🟡 | Batch 7: `?status=` filter, SQL `limit`, and a 300 MiB byte budget on the export (F26 addressed). Booking-horizon query bound + background-export path still open. |
| F10 | Medium | ✅ | Deadline invariants, auth widths, numeric-config `TypeError`→500 fix, and (batch 7) salary order, assessment-window/timer/prompt/reason bounds across all template domains, multi-choice distinct-selection semantics. `date` answer re-parse of an unvalidated config is the only residual edge. |
| F11 | Medium | ✅ | HTTP auth hashing/verification is offloaded. Signup/HR-create reject overlong passwords before upload; login returns invalid credentials for overlong input. Friendly CLI length handling remains a follow-up. |
| F12 | Medium | 🟡 | Batch 6: constraint-specific dup-email translation. Batch 9: bounded chunked upload read (`read_upload_bounded`). Orphaned-object compensation on a post-upload failure remains. |
| F13 | Medium | ✅ | Batch 7: wrong-category dimension rejected (unknown strings still allowed by design), schema text bounds aligned to DB, and DB `uq_application_evaluation_scores_dimension` added (migration). |
| F14 | Medium | ✅ | Duplicate application IDs rejected; all inspected latest selectors use `(created_at DESC, id DESC)`. Original nondeterminism addressed; UUID tie-breaking does not define import chronology or retry semantics. |
| F15 | Medium | ✅ | Done (Batch 1). |
| F16 | Medium | 🔵 🟡 | Flag + advisory lock + script lock (F29). Batch 9: per-tick timing/success/failure logging. Batch processing and a real-Postgres cancellation test remain. |
| F17 | Medium | ✅ | Atomic Lua INCR+EXPIRE; batch 6 also heals a key that lost its TTL. Real-Redis verification still pending. Fail-open on Redis error is deliberate. |
| F18 | Medium | 🔵 🟡 | D07 documents empty production baseline and unsupported offline SQL. Supported fresh/populated upgrade execution still unverified. |
| F19 | Medium | 🟡 | README, architecture, decisions, CI workflow added; local lint/format clean (219 files). Hosted-runner CI verification and integration-test enforcement still pending. |
| F20 | Low | ⛔ | Template dedup — deferred, not correctness. |
| F21 | Low | 🟡 | Admin bootstrap via Settings; lifespan client shutdown + expired-token purge (batch 8); `GET /health/ready` (batch 9). Request-correlation IDs and a metrics framework remain. |

## Additional second-pass findings

Detailed evidence, reproduction limits, and acceptance checks are in the main review.

| ID | Severity | Status | Remaining work |
| --- | --- | --- | --- |
| F22 | Medium | ✅ | Batch 7: publish gate rejects a question-less template; the layer-2 sweep completes an in-progress attempt whose sequence is fully consumed. Still no *explicit* finalize endpoint (transition happens via the sweep, as recommended). |
| F23 | Medium | 🟡 | Past-slot + manual-mode enforcement (batch 6) + idempotent re-confirmation of the already-confirmed slot (batch 9). The interview domain still has no *service* tests (schema-only) — the remaining gap. |
| F24 | Medium | ✅ | `24:01`–`24:59` rejected (`24:00` kept); generated slots de-duplicated by start instant. Overlapping-window *authoring* still accepted (normalisation not added). |
| F25 | Medium | ✅ | `content_disposition_attachment()` — ASCII fallback + `filename*`. |
| F26 | Medium | 🟡 | Batch 7: `?status=` subset filter, SQL `limit`, 300 MiB byte budget with actionable 413. Async/background export path is the remaining piece. |
| F27 | Medium | ✅ | Constraint-specific translation via `violated_constraint()`; profile-email collisions handled; unrelated `IntegrityError`s re-raised. |
| F28 | Medium, policy-dependent | ✅ | Decision recorded (D-note: auto-release). Batch 7: withdrawn/denied/disqualified applications are filtered out of every capacity + calendar query, freeing the slot immediately while keeping the rows. |
| F29 | Medium | ✅ | Shared `sweep_advisory_lock` across the scheduler tick and both `main()` entry points. Cancellation/unlock behaviour still needs a real-Postgres test. |

## Second-pass verification notes

- `.venv/bin/pytest -q`: **221 passed**, 22 warnings, 4.37 seconds.
- `.venv/bin/ruff check .`: **passed**.
- `.venv/bin/ruff format --check .`: **passed**, 213 files already formatted.
- ORM configuration and OpenAPI generation: **passed**, 33 tables / 76 paths.
- Temporary real-route probes with mocked I/O reproduced numeric-config and
  Unicode-filename HTTP 500s. Pure/service probes confirmed the reopen,
  availability, booking-mode, and final-question-timeout observations.
- No live database/Redis/MinIO operations, migration execution, load benchmark,
  or hosted-CI execution occurred in this second review. Review probes did not
  create committed tests or change application code.
- The staging-failure use-case test asserts no commit, **not rollback**, despite
  its name. Request-session cleanup currently provides rollback for the normal
  API path; the use-case's standalone contract needs clarification and testing.

## Product-decision records (`docs/decisions/`)

| ID | Question | Default chosen |
| --- | --- | --- |
| D01 | Draft/closed job post visibility | ✅ Public reads → `published` only (draft + closed hidden); `GET /job-posts/manage` for staff. |
| D02 | Interview capacity model | One shared org calendar (provisional). |
| D03 | Assessment history vs mutable templates | Missing-template read-time error implemented; delete/lifecycle protection and versioning remain pending. |
| D04 | Cascade-delete of hiring history | ✅ `delete_job_post` use case — 409 when applications exist. |
| D05 | Export bounding | Count cap implemented; byte bound and usable filtered/background path pending (F26). |
| D06 | Scheduler ownership | Flag + scheduler-tick lock implemented; standalone entry points remain unguarded (F29). |
| D07 | Migration baseline | First supported baseline documented; offline `--sql` unsupported. |
| D08 | Refresh-token rotation | Current behaviour documented; rotation is a follow-up. |
| D09 | CSV formula injection | Prefix-guard risky cells in exports. |

## Change log

### Batch 9 — smaller follow-ups (F12, F16, F21, F23)
- **F23 ✅** `select_slot` — selecting the slot that is already confirmed is now
  an idempotent no-op (returns it unchanged, even if that time is now past).
- **F21 ✅ (readiness)** `GET /health/ready` pings Postgres + Redis → 200/503
  with a per-dependency `checks` map. `/health` stays pure liveness.
- **F16 ✅ (metrics-lite)** `_run_periodic_jobs` times each tick and logs a
  structured `periodic sweep ok in Xs` / `FAILED` line; failures re-raise.
- **F12 ✅ (bounded read)** `app/core/uploads.py::read_upload_bounded` streams
  the résumé upload in 64 KiB chunks and 413s as soon as it crosses
  `MAX_RESUME_SIZE_BYTES + 64 KiB` — an oversized upload no longer balloons
  memory before the service's size check.
- Tests: `test_uploads.py`.
- Still open: F12 orphaned-object compensation; F16 batching + real-Postgres
  cancellation test; F21 request-correlation / metrics framework;
  F23 interview *service* tests (whole domain still schema-tests-only).

### Batch 8 — D01 + D04 + F21 (partial) + F10 date edge
- **D01 ✅** Public `GET /job-posts` and `GET /job-posts/{id}` are
  `published`-only (draft **and** closed hidden — `service.get_public` 404s).
  New `GET /job-posts/manage` + `GET /job-posts/manage/{id}` (manage_jobs) for
  HR/admin, all statuses. Routes ordered before `/{job_post_id}`.
- **D04 ✅** `app/use_cases/delete_job_post.py` — `DELETE /job-posts/{id}` now
  409s (`JobPostInUseError`) when the post has any application. Close instead.
  `ApplicationRepository.job_post_has_applications` added.
- **F21 🟡** `RevokedRefreshTokenRepository.delete_expired()` runs each
  scheduler tick (drops denylist rows for already-expired tokens). `main.py`
  lifespan now closes the Redis client and disposes both engines on shutdown.
  Readiness probe / request-correlation / metrics still open.
- **F10 (date) ✅** `validate_answer_value` DATE branch parses config bounds
  via `_iso_date` instead of a raw `date.fromisoformat` that could 500.
- Tests: `test_delete_job_post.py`, `TestGetPublic` in the publish-gate suite.

### Batch 7 — doable-now correctness (F22, F13, F10-rem, F26, F28)
- **F13 ✅** `EvaluationScoreIn`/`ApplicationEvaluationIn` schema bounds match
  DB column widths; a dimension *known* to the other category is rejected
  (unknown strings still allowed); per-category dedup. New DB constraint
  `uq_application_evaluation_scores_dimension` (migration `9ed2874b2593`).
- **F10 (rem) ✅** salary `min <= max` + `ge=0` (`_SalaryRangeMixin`);
  `assessment_window_days` 1–90; extension `reason` 1–1000 + `extend_by_days`
  1–365; template `time_limit_minutes` 1–480, `time_limit_seconds` 5–3600,
  question `prompt` 1–4000, `order_index >= 0` (all 3 template domains);
  multiple-choice answers reject duplicate selections and count *distinct*.
- **F28 ✅ (auto-release)** `INTERVIEW_RELEASED_APPLICATION_STATUSES`
  (withdrawn/denied/disqualified). `_booked_intervals`, `_overlaps_confirmed`,
  `statuses_for_job_post`, and the upcoming/calendar query now filter those
  out — a released application's slot frees capacity and drops off the
  calendar; the rows stay for history.
- **F22 ✅** publish gate now also rejects an attached template with zero
  questions (`_assert_templates_have_questions`). `expire_overdue_attempts`
  now also *completes* any in-progress attempt whose question sequence is
  fully consumed (answered or per-question timer lapsed) — no more permanent
  `in_progress` → wrongful disqualification.
- **F26 ✅** `/applications/export` takes `?status=` (repeatable), SQL-limits
  the initial query to `EVALUATION_PACK_MAX + 1`, and enforces a 300 MiB
  résumé-byte budget (413 with actionable guidance). Background-job path is
  still the follow-up.
- Tests: evaluations schema (category/bounds), question-types (numeric,
  multi-choice), job-post empty-template publish gate.

### Batch 6 — second-review remediation
Addresses the corrections and the tractable new findings from the second review.

- **F05 (reopen) ✅** `AssessmentService.reopen()` now also rejects a parent
  application that is not answerable (withdrawn / denied / success / failed),
  via the shared `_parent_is_answerable` helper — so answers aren't superseded
  and an audit row isn't written for an attempt no one can continue. Test:
  `test_rejects_when_application_is_withdrawn`.
- **F27 ✅** `app/core/db_errors.py::violated_constraint()`. `ApplyToJob`,
  `ApplicationService.create`, and `AuthService` (signup / HR-create /
  profile-update, via `_commit_translating_email_conflict`) now translate
  **only** their specific unique-index violation and re-raise anything else.
  Profile-email update collisions are now handled too. Tests: unrelated
  `IntegrityError` is re-raised, not masked.
- **F01 (contract) ✅** `ApplyToJob.execute` now rolls back on *any* exception
  (not just the commit `IntegrityError`), so the use case owns its transaction
  for non-request callers. Test renamed + asserts rollback.
- **F25 ✅** `app/core/http_headers.py::content_disposition_attachment()` —
  RFC 6266 ASCII fallback + percent-encoded `filename*`; used by the résumé
  download. A `张伟.pdf` filename no longer 500s.
- **F24 ✅** `_hhmm_to_minutes` rejects `24:01`–`24:59` (keeps `24:00`);
  `open_slots_for_application` de-duplicates generated start instants
  (overlapping windows / duplicate overrides no longer emit repeat slots).
- **F23 ✅ (partial)** `InterviewRequestIn` rejects past slots (validator
  renamed `_dedupe_and_require_future`). `select_slot` rejects a `slot_id`
  whose time is now past, and rejects an arbitrary `starts_at` when HR
  hand-picked slots (`self_scheduled=False`) — the restrictive interpretation
  (D-note: revisit if open-availability should always be allowed).
- **F29 ✅** `app/core/sweep_lock.py::sweep_advisory_lock` — one shared lock
  for the scheduler tick *and* both standalone scripts (`main()` takes it,
  `run()` is the lock-free work the scheduler composes under one lock).
- **F10 (numeric) ✅** `question_types._number_or_none` — a non-number
  `min`/`max` in a numeric question config is now `InvalidQuestionConfigError`
  (was `TypeError` → HTTP 500).
- **F17 (heal) ✅** the rate-limit Lua also re-attaches a TTL to any key that
  lost one (`PTTL == -1`), so a stuck counter can't block an IP forever.
- **F07 (doc) ✅** `docs/architecture.md` polymorphic-integrity row reworded —
  `_require_template` *detects*, does not *enforce*.
- Still open from the second review: **F02, F03, F04-full, F06, F08, F13
  (vocab/DB constraint), F22, F26, F28, F20, F21 (lifecycle)**; **D01, D04**
  code.

### Batch 1 — safe correctness fixes
- **F15 ✅** `InterviewService.pending_selection_application_ids` → renamed
  `applications_awaiting_slot_pick`; now a `NOT IN (confirmed request ids)`
  check instead of an inner join to slots, so zero-slot self-scheduled
  requests are included. Caller in `applications/router.py` updated.
- **F17 ✅** `rate_limit` INCR + first-window EXPIRE now one atomic Redis Lua
  script (`_INCR_WITH_EXPIRY`). Redis unavailable → fail-open + warning log.
- **F11 ✅** `security.MAX_PASSWORD_BYTES` + `password_exceeds_max_length`;
  `verify_password` returns `False` (never raises) for overlong input;
  `AuthService._validate_password` raises `PasswordTooLongError` at signup /
  HR-create / (implicitly) login; bcrypt hash+verify offloaded via
  `run_in_threadpool` (`_hash_password` / `_verify_password`). Password length
  is checked before the résumé upload in signup.
- **F12 🟡** duplicate-email `IntegrityError` now translated to
  `EmailAlreadyRegisteredError` on commit in signup + HR-create (closes the
  get-then-insert race). Bounded-read / orphan-object compensation still TODO.
- Tests: `tests/unit/core/test_security.py` length-guard + no-raise cases.

### Batch 2 — F01 atomic application issuance
- New `app/use_cases/` package. `ApplyToJob.execute()` stages the application
  (`create(commit=False)` → flush, so the FK target exists and the duplicate
  index is caught early) then the attempts (`commit=False`) then one
  `uow.commit()`; `IntegrityError` → `DuplicateApplicationError`, rollback on
  any failure. `POST /applications` now depends on `ApplyToJob` only.
- Both service methods gained `commit: bool = True` (default preserves all
  existing callers/tests).
- Tests: `tests/unit/use_cases/test_apply_to_job.py` (single commit, rollback
  on attempt failure, duplicate translation).

### Batch 5 — validation, scheduler, docs, decisions
- **F10 ✅** deadline-extension invariants; auth field bounds (schemas + form).
- **F13/F14 ✅** evaluation import dup rejection + deterministic latest select.
- **F16 ✅** `SCHEDULER_ENABLED` + advisory lock; `SCHEDULER_INTERVAL_MINUTES`.
- **F21 ✅** `create_admin.py` bootstrap config via `Settings`.
- **F19 ✅** `README.md`, `docs/architecture.md`, `.github/workflows/ci.yml`,
  CLAUDE.md corrections (SQLAlchemy-in-service caveat, publish gate, test count
  219→221, jobs-tests, deadline rules, `apply_to_job` composition), whole-repo
  `ruff format` (was 9 drift files, now 0).
- **F09/D05 ✅(partial)** `EVALUATION_PACK_MAX = 200` → 413.
- **D09 ✅** `app/core/csv_safe.py` prefix-guards formula-like cells in both CSV
  producers (`evaluation_csv`, the pack template CSV).
- **Decisions:** `docs/decisions/D01…D09` written. D01/D04 are decided but need
  a code follow-up (both blocked on avoiding a domain cycle / optional-auth).
- Tests: `test_csv_safe.py`, `test_schemas.py` (evaluations), deadline-invariant
  cases in `test_service.py`.

### Batch 3 — F05 parent eligibility + F04 (partial)
- **F05 ✅** `AssessmentService._require_answerable_parent(attempt)` — called by
  `start_question` and `submit_answer` (not by any read path). Blocks if the
  parent application status ∉ {applied, prescreening, interview} or the outer
  `assessment_deadline` has passed. New errors
  `ParentApplicationNotAcceptingAssessmentsError`, `AssessmentDeadlinePassedError`.
- **F04 🟡** `_require_template` — `start_question` / `submit_answer` /
  `get_attempt_detail` now raise `MissingAssessmentTemplateError` (404) rather
  than dereferencing `None` when the template was deleted after the attempt.
- Tests: withdrawn-parent, past-deadline, deleted-template cases in
  `tests/unit/assessments/attempts/test_service.py`.
