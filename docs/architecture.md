# Architecture — conventions and deliberate exceptions

This is the source of architectural conventions for the ATS modular monolith.
[CLAUDE.md](../CLAUDE.md) provides additional domain context. Earlier review
reports are historical snapshots, not statements of current conformance.

## Write path — one transaction owner

- **Routers** handle HTTP input, authorization dependencies, and response
  serialization. They pass plain values or validated application contracts to
  a service/use case, never `Request`, `Response`, or `UploadFile` objects.
- **Services** make business decisions using repositories, entities, application
  contracts, and a `UnitOfWork`. They never import API `schemas.py`, ORM models,
  or `AsyncSession`. SQLAlchemy constraint exceptions may be translated into
  domain errors; the application listing service may expose a `Select` for the
  explicitly supported query path below.
- **Repositories** query/stage persistence and return entities or plain read
  projections. They may flush for ordering/constraint checks, but never commit.
- **UnitOfWork** flushes, commits, and rolls back the shared session.
- **Cross-domain writes** belong in `app/use_cases/` or a composition-root
  script. `ApplyToJob` creates an application and its assessment attempts with
  one commit. `TransitionApplication` changes status, provisions an interview,
  and sets the booking deadline with one commit. Its participating service
  methods use `commit=False` to flush without committing. A failure rolls back
  the whole operation.
- A domain service may use repositories from other domains. It must not import
  another domain's service or a use case. The two interview services may call
  each other in one direction because they belong to the same domain.

## Entities, application contracts, and HTTP schemas

`entities.py` contains plain dataclasses representing business data and read
projections. Auth and RBAC services return entities/dataclass results; FastAPI's
explicit `response_model` or router mapping performs HTTP serialization. Auth's
`UserOut` owns field filtering, including hiding passwords and resume keys.

`contracts.py` contains transport-independent application inputs/results:

- Auth token/signup results are dataclasses.
- Interview commands and views are Pydantic contracts shared by services and
  HTTP callers. The existing `In`/`Out` class names remain for compatibility;
  `interviews/schemas.py` explicitly re-exports them. Domain validation belongs
  in these contracts. HTTP headers, status codes, and request objects do not.
- Evaluation import commands/results use validated Pydantic contracts. Evaluation
  read responses remain HTTP schemas, mapped from service-returned entities.

Reusable clock-time conversions live in `interviews/time_utils.py`, not schema
modules. Assessment question/answer validation and common template service
logic live in `assessments/shared/`, owned by the assessment feature.

## Read path — explicit projections allowed

- List routes may build `QueryBuilder(Model)` / `Select` queries and use
  `apaginate(..., transformer=repo.map_many)` for entity-backed lists.
- `ApplicationRepository.list_for_review` / `list_for_applicant` and their
  service wrappers expose `Select` projections for router pagination.
- Reporting repositories may join other domains' tables. Interview services
  receive plain entities/projections from those queries, never live ORM rows.
- Cross-domain view composition may happen in routers, such as assessment
  scorecards. Reusable orchestration belongs in a use case: both the HTTP
  export and worker call `PrepareEvaluationExport`, using the same applicant
  query, eligibility rules, HR-assessed exclusion, and assessment collection.
  The caller supplies count/byte limits and authorized resume access. The HTTP
  route checks the current user; the worker uses authorization granted when
  the job was enqueued. Exceeding the worker's 5,000-applicant ceiling fails
  explicitly instead of silently producing a partial export.

## Infrastructure and deliberate exceptions

| Exception | Location | Contract |
| --- | --- | --- |
| Cross-domain reporting SQL | `analytics/repository.py` | Reporting is read-only with respect to hiring records; direct model imports are intentional. |
| Analytics geocoding cache | `analytics/geocoding.py`, `geocoding_repository.py`, `geocoding_client.py` | `GeocodingService` owns the cache transaction through a UoW. The cache repository stages writes; the external client has no database access. Transient provider failures are not cached as permanent misses. |
| Specialized repositories | RBAC joins, interviews, export queries/jobs | Generic base inheritance is optional when the operation does not match single-entity CRUD. |
| Assessment namespaces and interview services | `assessments/`, `interviews/` | Several cohesive subdomains/services may share a feature namespace. |
| Polymorphic template/question references | `assessments/attempts/models.py` | No cross-table FK can cover the three template types. New attempts snapshot template content; legacy attempts without snapshots read live templates. `DeleteAssessmentTemplate` guards referenced-template deletion through supported application paths. These safeguards do not create a database FK or protect against arbitrary direct SQL. |
| HTTP rate-limit exceptions | `core/rate_limit.py` | This module operates at the HTTP boundary. |
| Blocking storage/password work | Auth/application services | Existing Starlette thread-pool helpers wrap synchronous MinIO/bcrypt operations; this does not allow HTTP request/response types into services. |

## Enforcement and verification

`tests/unit/test_architecture.py` checks service import boundaries, cross-domain
service dependencies, entity/contract independence, and repository commit
ownership. It runs with the normal unit suite in CI and permits the explicit
query/infrastructure exceptions above.

Transaction behavior is checked separately: unit tests exercise use-case failure
paths, and `tests/integration/test_transition_atomicity.py` verifies the HTTP
transition and database rollback. `test_repository_boundaries.py` verifies plain
interview projections and shared export filtering against PostgreSQL. Static
import checks do not prove runtime atomicity.
