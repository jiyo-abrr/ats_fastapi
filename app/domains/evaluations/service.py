"""AI evaluation import + read side.

HR exports the evaluation pack (see pack.py), runs it through an external
agent, then imports the agent's JSON here. Each import is stored as one
`ApplicationEvaluation` (+ normalised per-dimension `ApplicationEvaluationScore`
rows) so it can drive analytics later. The newest row per application is
"current".
"""

import csv
import io
import uuid

from app.core.csv_safe import csv_safe
from app.core.unit_of_work import UnitOfWork
from app.domains.evaluations import entities
from app.domains.evaluations.dimensions import (
    ASSESSMENT_DIMENSIONS,
    RESUME_DIMENSIONS,
)
from app.domains.evaluations.exceptions import (
    EmptyEvaluationImportError,
    EvaluationNotFoundError,
)
from app.domains.evaluations.repository import EvaluationRepository
from app.domains.evaluations.schemas import (
    ApplicationEvaluationOut,
    EvaluationImportIn,
    EvaluationImportResultOut,
)


class EvaluationService:
    def __init__(self, evaluations: EvaluationRepository, uow: UnitOfWork):
        self.evaluations = evaluations
        self.uow = uow

    async def import_results(
        self, payload: EvaluationImportIn, *, imported_by_user_id: uuid.UUID
    ) -> EvaluationImportResultOut:
        if not payload.evaluations:
            raise EmptyEvaluationImportError("No evaluations in payload")

        # Only accept applications that actually belong to this job post.
        valid_ids = await self.evaluations.valid_application_ids(payload.job_post_id)

        imported = 0
        skipped: list[str] = []
        for item in payload.evaluations:
            if item.application_id not in valid_ids:
                skipped.append(str(item.application_id))
                continue
            is_empty = (
                item.recommendation is None
                and item.fit_score is None
                and not item.resume_scores
                and not item.assessment_scores
                and not item.summary
            )
            if is_empty:
                skipped.append(str(item.application_id))
                continue

            evaluation_id = uuid.uuid4()
            scores = [
                entities.EvaluationScore(
                    id=uuid.uuid4(),
                    evaluation_id=evaluation_id,
                    category=category,
                    dimension=score.dimension,
                    rating=score.rating,
                    reason=score.reason,
                )
                for category, category_scores in (
                    ("resume", item.resume_scores),
                    ("assessment", item.assessment_scores),
                )
                for score in category_scores
            ]
            await self.evaluations.add(
                entities.ApplicationEvaluation(
                    id=evaluation_id,
                    application_id=item.application_id,
                    imported_by_user_id=imported_by_user_id,
                    recommendation=item.recommendation,
                    fit_score=item.fit_score,
                    seniority_assessed=item.seniority_assessed,
                    summary=item.summary,
                    model=payload.model,
                    rubric_version=payload.rubric_version,
                    scores=scores,
                )
            )
            imported += 1

        await self.uow.commit()
        return EvaluationImportResultOut(imported=imported, skipped=skipped)

    async def get_for_application(
        self, application_id: uuid.UUID
    ) -> ApplicationEvaluationOut:
        evaluation = await self.evaluations.get_latest(application_id)
        if evaluation is None:
            raise EvaluationNotFoundError(
                f"No evaluation imported for application '{application_id}'"
            )
        return ApplicationEvaluationOut.model_validate(evaluation)

    async def latest_full_for_applications(
        self, application_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, ApplicationEvaluationOut]:
        full = await self.evaluations.latest_full_for_applications(application_ids)
        return {
            app_id: ApplicationEvaluationOut.model_validate(evaluation)
            for app_id, evaluation in full.items()
        }

    async def latest_summaries_for_applications(
        self, application_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, dict]:
        return await self.evaluations.latest_summaries_for_applications(application_ids)

    async def evaluation_csv(self, job_post_id: uuid.UUID) -> str:
        """Flat CSV of the latest evaluation per applicant for one job post —
        one row per applicant, one column per dimension rating. For analytics /
        spreadsheets."""
        app_rows = await self.evaluations.application_rows_for_job_post(job_post_id)
        app_ids = [r[0] for r in app_rows]
        latest = await self.evaluations.latest_full_for_applications(app_ids)

        dimensions = [("resume", d) for d in RESUME_DIMENSIONS] + [
            ("assessment", d) for d in ASSESSMENT_DIMENSIONS
        ]
        dimension_headers: list[str] = []
        for category, dimension in dimensions:
            dimension_headers += [
                f"{category}__{dimension}",
                f"{category}__{dimension}__reason",
            ]
        header = [
            "application_id",
            "applicant_name",
            "applicant_email",
            "pipeline_status",
            "recommendation",
            "fit_score",
            "seniority_assessed",
            "model",
            "rubric_version",
            "evaluated_at",
            *dimension_headers,
        ]

        buffer = io.StringIO()
        writer = csv.writer(buffer)

        def _row(cells: list) -> None:
            # Guard user-authored names / free text against spreadsheet formula
            # injection — see docs/decisions/D09.
            writer.writerow([csv_safe(c) for c in cells])

        _row(header)
        for app_id, first, last, email, status in app_rows:
            evaluation = latest.get(app_id)
            base = [str(app_id), f"{first} {last}", email, status]
            if evaluation is None:
                _row(base + [""] * (len(header) - len(base)))
                continue
            smap = {
                (s.category, s.dimension): (s.rating, s.reason or "")
                for s in evaluation.scores
            }
            dimension_values: list[str] = []
            for key in dimensions:
                rating, reason = smap.get(key, ("", ""))
                dimension_values += [rating, reason]
            _row(
                [
                    *base,
                    evaluation.recommendation or "",
                    "" if evaluation.fit_score is None else evaluation.fit_score,
                    evaluation.seniority_assessed or "",
                    evaluation.model or "",
                    evaluation.rubric_version or "",
                    evaluation.created_at.isoformat() if evaluation.created_at else "",
                    *dimension_values,
                ]
            )
        return buffer.getvalue()
