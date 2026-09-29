# Repository structure review

Reviewed: 2026-09-17

Original review scope: the working tree on 2026-09-17, including existing uncommitted changes. The original review was read-only. The user subsequently authorized all fixes; the implementation status below supersedes the historical findings and verification further down. This is not a complete security, performance, or production-readiness audit.

## Remediation status — 2026-09-17

All eight findings have been addressed. Existing user changes were retained.

| Finding | Implemented change | Verification |
| --- | --- | --- |
| R01 | `TransitionApplication` owns one commit for status, interview request, and booking deadline; participating services can stage without committing. Application reads explicitly reload server-generated timestamps before mapping. | Unit failure-path tests and HTTP/database tests cover success and failures at request provisioning, deadline assignment, and commit. |
| R02 | Interview repositories return plain application/address entities and typed staff, job-setting, and request-setting projections. | Database tests verify detached dataclasses, alongside existing interview integration tests. |
| R03 | Geocoding client, cache repository, and `GeocodingService` are separate; the service commits through a UoW. Cache insertion tolerates concurrent duplicates. Transient provider failures remain retryable. | Unit tests cover cached values, duplicate queries, definitive misses, transient failure/retry, and rollback. |
| R04 | Auth/RBAC/evaluation read services return plain entities/results. Interview and evaluation-import validation lives in transport-independent `contracts.py`; API facades retain existing payload names. Time helpers moved to `interviews/time_utils.py`. | Existing service/schema tests, response serialization checks, and architecture checks. |
| R05 | Architecture, README, and contributor guidance now describe the implemented workflows, contracts, cache writes, snapshots, and DAG. The earlier maintainability report is labeled historical. | Local documentation/link review. |
| R06 | HTTP and worker exports share `PrepareEvaluationExport` and `EvaluationExportRepository`; authorization and limits are supplied by each entry point. Worker over-limit exports fail explicitly instead of silently truncating. | Shared workflow tests cover filters, missing resumes, count/byte limits, and missing jobs; database tests cover status and HR-assessed exclusions and verify both HTTP/worker ZIP contents. |
| R07 | Template-service and question-validation modules moved from `core/` to `assessments/shared/`; imports and the question-validation test location were updated. | Assessment tests and lint. |
| R08 | Added architecture tests for forbidden service imports, cross-domain service dependencies, entity/contract independence, and repository commits. They run in the existing CI unit suite. | `tests/unit/test_architecture.py`. |

Formatting findings were also corrected. No new migration or dependency was needed
for these fixes; the migrations already staged by the user remain intact.

### Verification after remediation

- Unit suite: **336 passed** (including architecture and response-contract checks).
- PostgreSQL integration suite: **68 passed**, using a uniquely named disposable
  database created for verification and removed afterward. Existing databases
  were not reset.
- Ruff lint and formatting: **passed**.
- Existing unit-test dependency deprecation and JWT key-length warnings remain.
- External storage/geocoding calls were mocked. Live queue delivery, Airflow
  execution/cutover, and deployment were not exercised;
  their runtime behavior is not certified by these checks.

## Original review (historical)

## Overall assessment

**Yes—the repository has a good overall structure for a growing FastAPI application.** Its domain-based modular monolith is appropriate for this ATS. Related functionality is easy to find, persistence and business logic are usually separated, and dedicated use cases already provide a pattern for coordinating multiple domains.

The main weakness is inconsistent enforcement of those boundaries. Some workflows still live in routers, some repositories return ORM objects to services, and the architecture documentation describes stronger separation than the code currently achieves. Improve these specific boundaries while keeping the overall layout.

| Area | Assessment |
| --- | --- |
| Domain organization | Good: cohesive feature packages and predictable module names. |
| API composition | Good: explicit versioned router aggregation. |
| Service/persistence separation | Mostly good, with concrete leaks described below. |
| Cross-domain workflows | Partially consistent: good use-case examples exist, but not every write workflow follows them. |
| Shared infrastructure | Useful centralization; assessment-specific business rules also live in `core/`. |
| Tests and CI | Good foundation: separate unit/integration suites and CI checks. Architecture rules are not automatically enforced. |
| Documentation | Extensive, but several statements are stale or contradict the current code. |

## What is working well

- **Vertical domain slices:** packages such as `auth`, `applications`, and `job_posts` keep models, entities, schemas, repositories, services, dependencies, and routes together. This makes feature changes easier to navigate than a single application-wide folder for each layer.
- **Explicit composition:** [app/main.py](../app/main.py), [app/api/router.py](../app/api/router.py), and [app/api/v1.py](../app/api/v1.py) clearly separate application startup from API versioning and domain routes.
- **Persistence mapping:** [BaseRepository](../app/core/repository.py) establishes ORM-to-entity mapping, while [UnitOfWork](../app/core/unit_of_work.py) gives writes an explicit transaction boundary. Domain-specific exceptions are mapped centrally by [exception handlers](../app/core/exception_handlers.py).
- **A reusable workflow pattern:** [ApplyToJob](../app/use_cases/apply_to_job.py) coordinates application creation and assessment issuance with one commit and rollback handling. Its [unit tests](../tests/unit/use_cases/test_apply_to_job.py) cover failure paths. This is a useful model for other multi-domain writes.
- **Separate execution entry points:** HTTP routes, [CLI commands](../app/cli.py), [workers](../app/workers/evaluation_export.py), and [Airflow DAGs](../airflow/dags/assessment_sweep_dag.py) have identifiable homes. Airflow validation has a separate CI job and environment.
- **Deliberate testing layers:** `tests/unit/` broadly mirrors the domain layout; `tests/integration/` covers database constraints, migrations, races, and query behavior that mocks cannot establish.
- **Recorded design decisions:** `docs/decisions/`, `docs/plans/`, and `uv.lock` provide useful context and reproducibility. The presence of documented exceptions is a strength when those exceptions accurately describe the implementation.

## Findings, in priority order

### R01 — High: the interview transition has multiple transaction owners

**Evidence:** [applications/router.py](../app/domains/applications/router.py), `update_application_status` route around lines 250–280; [applications/service.py](../app/domains/applications/service.py), `update_status` and `set_interview_booking_deadline_for_transition`; [interviews/scheduling_service.py](../app/domains/interviews/scheduling_service.py), `ensure_default_request` and `set_request`.

The route changes the application status, provisions an interview request, and sets the booking deadline. These operations commit separately: `update_status` at line 263, `set_request` at line 217, and the deadline setter at line 394.

**Why it matters:** if provisioning fails after the status commit, an application can remain in `interview` without the intended request. If setting the deadline fails later, the earlier writes remain committed. Retrying the same status change is not a reliable recovery path because `update_status` validates transitions from the now-updated status. This is a failure scenario inferred from the transaction boundaries; it was not reproduced against a database during this review.

This contradicts the repository's documented rule that a cross-domain write has one transaction owner in `app/use_cases/`.

**Recommendation:** introduce a transition use case that stages all three changes and commits once. Follow the existing `ApplyToJob` pattern, including rollback on failure. Add failure-path tests that establish that neither the status nor the interview request persists when a later step fails.

### R02 — Medium: interview repositories leak ORM objects into services

**Evidence:** [interviews/repository.py](../app/domains/interviews/repository.py), `get_application` and `get_company_address` around lines 68–77; [interviews/availability_repository.py](../app/domains/interviews/availability_repository.py), `company_addresses_by_id`, `list_staff`, `get_job_post`, `interviewers`, and `get_application`. Consumers include `_require_application_in_interview` in [scheduling_service.py](../app/domains/interviews/scheduling_service.py) and `_presets_out` in [availability_service.py](../app/domains/interviews/availability_service.py).

These methods return SQLAlchemy `Application`, `CompanyAddress`, `User`, or `JobPost` instances directly. Mapping the interview domain's own request and slot objects does not prevent these other ORM objects from crossing the same boundary.

**Why it matters:** services become dependent on persistence object behavior and session state. This weakens the stated guarantee that services operate on plain entities and makes tests less representative when their substitutes do not behave like real ORM instances.

**Recommendation:** return existing domain entities or small, explicitly typed read projections containing the fields the caller needs. Cross-domain reporting queries can remain in repositories; the concern is the object exposed to the service, not the existence of a join.

### R03 — Medium: analytics cache writes bypass the stated transaction structure

**Evidence:** [analytics/service.py](../app/domains/analytics/service.py), constructor and `locations`; [analytics/geocoding.py](../app/domains/analytics/geocoding.py), `geocode_many`; [analytics/dependencies.py](../app/domains/analytics/dependencies.py).

`AnalyticsService` receives an `AsyncSession` and passes it into a helper that both calls an external geocoder and reads/writes ORM cache rows. `geocode_many` commits that session directly. The architecture document describes analytics as read-only and owning no writes, but it owns the `geocoded_locations` cache in practice.

**Why it matters:** network access, caching, persistence, and commit ownership are coupled in one helper. A caller cannot compose it safely into a larger transaction without accounting for its internal commit.

**Recommendation:** separate the geocoder client from a cache repository and give cache writes an explicit transaction owner. Document that reporting is read-only with respect to hiring records while its cache is writable. Retain analytics' intentional permission to query other domains' models for reporting.

### R04 — Medium: service contracts depend on API response schemas

**Evidence:** [auth/service.py](../app/domains/auth/service.py) imports `SignupResponse`, `TokenResponse`, and `UserOut`; [rbac/service.py](../app/domains/rbac/service.py) builds `RoleOut` and `PermissionOut`; [interviews/availability_service.py](../app/domains/interviews/availability_service.py) accepts and constructs many request/response schemas and imports private formatting helpers from `schemas.py`.

**Why it matters:** an API response-shape change can require changes to business services, and CLI/worker callers inherit API-specific contracts. This is inconsistent with [docs/architecture.md](architecture.md), which assigns response mapping to routers and plain entities to services.

Pydantic objects are not inherently inappropriate inside services. The issue is that API schemas and application-level data contracts are currently the same objects without a documented decision to make them so.

**Recommendation:** use entities or application-level input/result types for business operations, with response conversion at the router. Put reusable time-formatting helpers in a domain utility module. Alternatively, explicitly document selected schema types as shared application contracts and keep transport-only fields out of them.

### R05 — Medium: architecture and onboarding documentation have drifted

**Evidence:** [docs/architecture.md](architecture.md), [README.md](../README.md), and [docs/maintainability-review-pending.md](maintainability-review-pending.md).

Specific discrepancies:

- Architecture documentation says analytics owns no writes; its geocoding helper writes and commits cache rows.
- The template snapshot fix is described as tracked future work, but [attempts/service.py](../app/domains/assessments/attempts/service.py) already creates and reads snapshots. [DeleteAssessmentTemplate](../app/use_cases/delete_assessment_template.py) also provides a referenced-template deletion guard.
- The README says no DAGs exist and `airflow/dags/` is empty, while `assessment_sweep_dag.py` exists and CI contains a DAG validation job. Actual deployment/cutover status was not verified.
- The README calls plain `uv run pytest` a unit-test command, but `pyproject.toml` points collection at all of `tests/`; integration tests are also collected and run when their database prerequisite is available.
- The prior review's completion and test-count statements describe an earlier snapshot. They do not establish that the current working tree fully conforms to the architecture.

**Why it matters:** contributors can reasonably follow the documentation and still make incompatible implementation choices or repeat already completed work.

**Recommendation:** keep `docs/architecture.md` as the concise source of architectural rules, update its real exceptions, and label old review results as historical snapshots. Make README commands explicit about which test suite they run. No existing documentation was rewritten as part of this review.

### R06 — Medium: export orchestration is duplicated across HTTP and worker entry points

**Evidence:** [evaluations/router.py](../app/domains/evaluations/router.py), `export_evaluation_pack`; [workers/evaluation_export.py](../app/workers/evaluation_export.py), `_run_export`.

Both paths select eligible applications, apply the HR-assessed exclusion, fetch resumes, collect assessment reviews, and prepare the inputs to `build_evaluation_pack`. The ZIP builder is already shared in `evaluations/pack.py`, but the business selection and collection workflow is still implemented twice.

**Why it matters:** eligibility and data-collection changes must be maintained in multiple places. The existing uncommitted changes touch both paths for the same exclusion rule, demonstrating that maintenance cost.

**Recommendation:** extract a shared export preparation use case or query service. Keep HTTP authorization and response construction at the router, and queue handling and job status updates in the worker. Preserve the intentionally different synchronous/asynchronous size limits and authorization context as explicit inputs or policies.

### R07 — Low: `core/` contains assessment-specific business logic

**Evidence:** [core/template_service.py](../app/domains/assessments/shared/template_service.py) implements assessment template CRUD and question authoring; [core/question_types.py](../app/domains/assessments/shared/question_types.py) defines assessment question types and answer-validation rules.

**Why it matters:** `core/` mixes application-wide infrastructure with logic shared only by the assessment subdomains. As features grow, this makes ownership less obvious.

**Recommendation:** when these modules next need substantive changes, consider an assessment-owned shared package such as `app/domains/assessments/shared/`. Retain the existing deduplication across template services. A rename-only restructuring is lower priority than R01–R06.

### R08 — Low: architectural rules are documented but not checked automatically

**Evidence:** [pyproject.toml](../pyproject.toml) enables Ruff's `E`, `F`, and `I` rules; [.github/workflows/ci.yml](../.github/workflows/ci.yml) runs lint, formatting, tests, and DAG validation. No dedicated architecture/import-boundary checks were found in the reviewed test and CI configuration.

**Why it matters:** ordinary linting can pass while services import API schemas or orchestration bypasses the intended use-case boundary. The findings above illustrate this gap.

**Recommendation:** after reconciling the conventions, add a few targeted checks for forbidden dependency directions and unwanted service imports. Preserve the explicitly allowed reporting/query exceptions. Use behavioral failure tests for transaction ownership; import checks alone cannot prove atomicity.

## Structural choices worth preserving

- Keep the modular monolith. The reviewed structure does not establish a need to split this application into microservices.
- Keep `assessments/` as a grouping namespace and the two cohesive interview services. Identical folder depth or exactly one service per domain is not a useful requirement here.
- Keep the documented projection/query path. Requiring every aggregate reporting query to hydrate full entities would add unnecessary work.
- Do not require every repository to inherit the generic base. Composite-key associations and specialized query repositories can legitimately have different contracts.
- `analytics/repository.py` is currently 1,109 lines. Consider splitting it by report family as it grows, but line count alone is not evidence of a defect; prioritize clear responsibilities and shared query semantics.

## Verification performed

Reviewed source modules, imports, transaction boundaries, dependency providers, migrations setup, test organization, CI configuration, and architecture/onboarding documentation.

| Check | Result |
| --- | --- |
| `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/unit -q -p no:cacheprovider` | **315 passed**, 23 warnings, 8.05 seconds. |
| `.venv/bin/ruff check . --no-cache --output-format concise` | **Passed.** |
| `.venv/bin/ruff format --check . --no-cache` | **Failed:** 14 files would be reformatted; 259 already formatted. Ruff 0.16.6. No formatting was applied. |
| Integration tests, live migrations, worker execution, and Airflow runtime | **Not run.** The integration harness drops/recreates its configured test database; this review used unit tests and static inspection. |

The unit run reported dependency deprecation warnings and JWT key-length warnings. These were not investigated as part of this structure review. Formatting findings are current working-tree hygiene issues, not proof of a poor architecture. Passing unit tests does not establish database-backed workflow atomicity or production readiness.

## Suggested order of follow-up work

1. Fix the interview transition's transaction ownership and verify rollback behavior (R01).
2. Align the documentation with the actual boundaries, then address ORM leakage and analytics cache ownership (R02, R03, R05).
3. Consolidate export preparation and clarify service data contracts (R04, R06).
4. Add focused architecture checks; move assessment-specific shared code when convenient (R07, R08).
5. Apply formatting separately when code changes are authorized.

The repository already provides the right foundation. The most valuable improvements are consistent transaction ownership, explicit service contracts, and documentation that accurately reflects the code.
