# ruff: noqa: E501  (the embedded markdown rubric has long table rows)
"""Builds the "evaluation pack" ZIP for one job post — everything an external
AI agent needs to score its applicants: the job spec, a scoring rubric, and
per-applicant résumé + assessment answers.

Pure packaging: callers load the data (job, applicants, résumé bytes,
assessment reviews) and hand it here; this module never touches the DB or
object storage.
"""

import csv
import io
import json
import re
import zipfile
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import Any

from app.core.csv_safe import csv_safe

# Bounds on one evaluation pack (review F09/F26, decision D05). Over either, the
# route returns 413; a background-job path is the follow-up.
EVALUATION_PACK_MAX = 200
EVALUATION_PACK_MAX_BYTES = 300 * 1024 * 1024  # 300 MiB of résumé bytes

_TEMPLATE_LABELS = {
    "pre_assessment": "Pre-assessment",
    "culture_fit": "Culture fit",
    "technical": "Technical assessment",
}


def _html_to_text(value: str) -> str:
    """Job copy is authored as HTML (TipTap). Flatten it to readable plain
    text for the pack — list items become '- ', blocks become newlines."""
    if not value or "<" not in value:
        return value or ""
    text = re.sub(r"(?i)<li[^>]*>", "\\n- ", value)
    text = re.sub(r"(?i)<(/p|/h[1-6]|br\\s*/?)>", "\\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = (
        text.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
    )
    return re.sub(r"\\n{3,}", "\\n\\n", text).strip()


def _slug(text: str) -> str:
    out = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return out or "item"


def _fmt(value: Any) -> str:
    if value is None or value == "":
        return "_(no answer)_"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    return str(value)


RUBRIC_MD = """# Applicant evaluation rubric

You are an expert technical recruiter. Score every applicant in this pack
**against the specific role** described in `job/description.md` — its
description, requirements, qualifications and responsibilities are the bar,
not a generic standard.

## 1. Calibrate to the role's seniority FIRST

Infer the seniority level from the job title and responsibilities
(Intern / Junior / Associate / Mid / Senior / Lead / Principal / Manager).
Apply the rubric **relative to that level**:

- **Intern / Junior / Associate / Mid** — weight trajectory, learning ability
  and potential over depth. Do **not** mark down for: limited total years of
  experience, little or no industry-specific experience, few or no
  certifications, only 1–2 prior employers, or a single employment gap under
  12 months. Treat 2–3 year average tenure as **Strong** at this level.
- **Senior / Lead / Principal / Manager** — apply the bands below as written.
  Weight Career Progression, Tenure Stability, Technical Skills Match and
  Industry Experience heavily. Unexplained job-hopping and thin progression
  are real risks here.

State the seniority level you inferred at the top of each applicant's result.

## 2. Résumé dimensions

Rate each **Strong / Qualified / Below bar / N/A** with a one-line reason.

| # | Dimension | Guidance |
|---|-----------|----------|
| 1 | Relevant Work Experience | Depth and recency of experience doing the work this role requires. |
| 2 | Industry Experience | Experience in the same industry / domain as the hiring company. |
| 3 | Employment Gap | **Strong:** continuous employment, no gaps. **Qualified:** one gap under 6 months. **Below bar:** any gap longer than 6 months (unless clearly explained, e.g. education, caregiving, layoff). |
| 4 | Tenure Stability (avg length of stay per employer) | **Strong:** > 5 years. **Qualified:** 3–5 years. **Below bar:** < 2 years. |
| 5 | Career Progression | Evidence of promotions and increasing scope / responsibility over time. |
| 6 | Job-Hopping Risk | Frequency of short (< 18 month) stints. More frequent = higher risk. |
| 7 | Educational Background | College graduate in a field relevant to the position (or equivalent demonstrated capability). |
| 8 | Relevant Certifications / Licenses | Certifications or licenses the role calls for. |
| 9 | Technical Skills Match | Overlap between the candidate's demonstrated technical skills and the role's required stack / competencies. |

Remember the seniority calibration in section 1 when applying dimensions
2, 3, 4, 6 and 8.

## 3. Assessment dimensions

Each applicant folder has `assessments.md` with their answers to up to three
assessments (Pre-assessment, Culture fit, Technical). For **each assessment
that has answers**, rate **Strong / Qualified / Below bar / Not taken**:

- **Completion** — did they finish it? Partial or abandoned attempts count against.
- **Answer quality & depth** — specific, thoughtful, concrete vs. vague or generic.
- **Role alignment** — do the answers fit what this role and company need
  (compensation expectations within range, availability, motivation,
  retention signals, technical correctness)?
- **Red flags** — contradictions with the résumé, unrealistic expectations,
  evasiveness.

## 4. Output — a human summary AND a machine file

Write a readable summary for the recruiter: per applicant give the inferred
seniority, the résumé table (9 rows), the assessment table, the recommendation
with 2–3 sentences of role-tied justification, and a fit score 0–100
(calibrated to seniority — a strong junior can score high). End with a ranked
shortlist, best fit first.

**Then also produce `evaluation-results.csv`** — imported back into the ATS for
comparison + analytics, so it must match `RESULTS-FORMAT.md` exactly. Start from
`evaluation-template.csv` (already keyed by `application_id`). For every one of
the 12 dimensions fill BOTH the rating column (`strong` / `qualified` /
`below_bar` / `na`) AND its `__reason` column (one specific sentence citing the
résumé or the answers). Recommendation is `advance` / `hold` / `reject`.
"""


RESULTS_FORMAT_MD = """# evaluation results format

The ATS imports **CSV** (Compare tab → "Import evaluation results"). Start from
`evaluation-template.csv` — it is pre-filled with one row per applicant
(`application_id` + `applicant_name`). Fill the remaining columns; do not change
`application_id`. Save the result as `evaluation-results.csv`.

## Columns

| column | values |
|--------|--------|
| `application_id` | keep exactly as given — identifies the applicant |
| `applicant_name` | keep as given (reference only) |
| `seniority_assessed` | the level you inferred (e.g. `Mid`) |
| `fit_score` | integer 0–100, calibrated to seniority |
| `recommendation` | `advance` \\| `hold` \\| `reject` |
| `summary` | 2–3 sentences, role-tied (quote it if it contains commas) |
| `resume__<dimension>` (9 rating columns) | `strong` \\| `qualified` \\| `below_bar` \\| `na` |
| `resume__<dimension>__reason` (9 text columns) | one sentence justifying that rating — cite the résumé/role |
| `assessment__<pre_assessment\\|culture_fit\\|technical>` (3 rating columns) | `strong` \\| `qualified` \\| `below_bar` \\| `na` |
| `assessment__<name>__reason` (3 text columns) | one sentence justifying that rating — cite the answers |

Every rating column is immediately followed by its `__reason` column. Fill
**both** for every dimension. Quote any `__reason` or `summary` value that
contains a comma. Leave a rating blank only if the row should be skipped
entirely; use `na` for "not applicable / not taken".

## JSON alternative

A richer JSON form (with a `reason` per dimension) is also accepted — see
`evaluation-results.template.json`. The importer takes either a `.csv` or a
`.json` file.

```jsonc
{
  "job_post_id": "<uuid>",            // keep as-is from the template
  "model": "gpt-5",                   // the model/agent you used
  "rubric_version": "1",
  "evaluations": [
    {
      "application_id": "<uuid>",     // keep as-is; identifies the applicant
      "seniority_assessed": "Mid",    // level you inferred
      "fit_score": 78,                // 0-100, calibrated to seniority
      "recommendation": "advance",    // advance | hold | reject
      "summary": "2-3 sentences, role-tied.",
      "resume_scores": [
        { "dimension": "relevant_work_experience", "rating": "strong",    "reason": "..." },
        { "dimension": "industry_experience",      "rating": "qualified", "reason": "..." },
        { "dimension": "employment_gap",           "rating": "strong",    "reason": "..." },
        { "dimension": "tenure_stability",         "rating": "qualified", "reason": "..." },
        { "dimension": "career_progression",       "rating": "strong",    "reason": "..." },
        { "dimension": "job_hopping_risk",         "rating": "strong",    "reason": "..." },
        { "dimension": "educational_background",   "rating": "qualified", "reason": "..." },
        { "dimension": "certifications_licenses",  "rating": "na",        "reason": "..." },
        { "dimension": "technical_skills_match",   "rating": "strong",    "reason": "..." }
      ],
      "assessment_scores": [
        { "dimension": "pre_assessment", "rating": "qualified", "reason": "..." },
        { "dimension": "culture_fit",    "rating": "strong",    "reason": "..." },
        { "dimension": "technical",      "rating": "below_bar",  "reason": "..." }
      ]
    }
  ]
}
```

- `rating`: one of `strong`, `qualified`, `below_bar`, `na`.
- `recommendation`: one of `advance`, `hold`, `reject`.
- Keep the 9 résumé dimensions above (add more only if useful — unknown
  dimensions are still stored). Assessment dimensions: `pre_assessment`,
  `culture_fit`, `technical`.
"""


PROMPT_MD = """# Paste this into ChatGPT (with this ZIP attached)

You are an expert technical recruiter evaluating applicants for one job opening.

I've uploaded a ZIP ("evaluation pack"). Unzip it and read EVERY file:
- `job/description.md` — the role: description, requirements, qualifications, responsibilities. This is the bar. Score everyone against THIS role, not a generic standard.
- `evaluation-rubric.md` — the full rubric (authoritative if anything below is unclear).
- `applicants/<n>-<name>/resume.pdf` (or `RESUME-NOT-AVAILABLE.txt`) — the résumé.
- `applicants/<n>-<name>/assessments.md` — their answers to up to 3 assessments.
- `applicants/<n>-<name>/profile.json` — status, dates, and the `application_id` you must use as the key.
- `evaluation-template.csv` — one row per applicant, pre-filled with `application_id` + `applicant_name`. Your CSV output is this file with the other columns filled in.

## Step 1 — Calibrate to seniority FIRST (per applicant)

Infer the seniority level from the job title + responsibilities: Intern / Junior / Associate / Mid / Senior / Lead / Principal / Manager.

- Intern / Junior / Associate / Mid: weight trajectory, learning ability, and potential over depth. Do NOT mark down for: limited total years of experience, little/no industry experience, few/no certifications, only 1-2 prior employers, or a single employment gap under 12 months. Treat 2-3 year average tenure as "strong" at this level.
- Senior / Lead / Principal / Manager: apply the bands below as written. Weight Career Progression, Tenure Stability, Technical Skills Match, and Industry Experience heavily.

## Step 2 — Résumé (rate each: strong / qualified / below_bar / na)

1. relevant_work_experience — depth and recency of doing the work this role requires
2. industry_experience — experience in the same industry/domain as the hiring company
3. employment_gap — strong: no gaps; qualified: one gap < 6 months; below_bar: any gap > 6 months (unless clearly explained: education, caregiving, layoff)
4. tenure_stability — avg stay per employer. strong: > 5 yrs; qualified: 3-5 yrs; below_bar: < 2 yrs
5. career_progression — promotions and increasing scope/responsibility over time
6. job_hopping_risk — frequency of short (< 18 month) stints; more frequent = worse
7. educational_background — college graduate in a field relevant to the position (or equivalent demonstrated capability)
8. certifications_licenses — certifications/licenses the role calls for
9. technical_skills_match — overlap between demonstrated skills and the role's required stack/competencies

Apply the Step 1 calibration when scoring dimensions 2, 3, 4, 6, and 8.

## Step 3 — Assessments (rate each: strong / qualified / below_bar / na)

For each of `pre_assessment`, `culture_fit`, `technical` that has answers, judge: completion (finished vs partial), answer quality & depth (specific vs generic), role alignment (comp expectations in range, availability, motivation, retention signals, technical correctness), and red flags (contradicts the résumé, unrealistic, evasive). If an assessment wasn't taken, rating = "na".

## Step 4 — Output

**(A) A readable summary** for me: per applicant give the inferred seniority, the 9-row résumé table (dimension -> rating -> one-line reason), the assessment table, an overall recommendation (advance / hold / reject) with 2-3 sentences tied to the role, and a fit score 0-100 (calibrated to seniority — a strong junior can score high). End with a ranked shortlist, best fit first, one line each.

**(B) A downloadable file named `evaluation-results.csv`** — take `evaluation-template.csv` and fill in every column for every row.

The template has, for each of the 9 résumé dimensions and 3 assessment dimensions, a RATING column immediately followed by a `__reason` column — e.g. `resume__tenure_stability` then `resume__tenure_stability__reason`. Fill BOTH: the rating AND a one-sentence justification that cites the résumé / answers / the role.

Rules for the CSV:
- Every rating cell is exactly one of: `strong`, `qualified`, `below_bar`, `na`.
- Every `__reason` cell has a short, specific sentence — never leave it blank.
- `recommendation` is exactly one of: `advance`, `hold`, `reject`.
- `fit_score` is an integer 0-100.
- Keep every `application_id` exactly as given — do not add, rename, reorder, or drop rows.
- Every applicant row must be filled, even if a résumé or assessment is missing (use `na` + a reason saying so).
- Wrap any `__reason` or `summary` value that contains a comma in double quotes.
"""


def _results_template(job_id: str, applicants: list[dict]) -> str:
    template = {
        "job_post_id": job_id,
        "model": "",
        "rubric_version": "1",
        "evaluations": [
            {
                "application_id": str(entry["row"].id),
                "applicant_name": (
                    f"{entry['row'].applicant_first_name} "
                    f"{entry['row'].applicant_last_name}"
                ),
                "seniority_assessed": "",
                "fit_score": None,
                "recommendation": "",
                "summary": "",
                "resume_scores": [
                    {"dimension": d, "rating": "", "reason": ""}
                    for d in _RESUME_DIMENSIONS
                ],
                "assessment_scores": [
                    {"dimension": d, "rating": "", "reason": ""}
                    for d in _ASSESSMENT_DIMENSIONS
                ],
            }
            for entry in applicants
        ],
    }
    return json.dumps(template, indent=2)


_RESUME_DIMENSIONS = [
    "relevant_work_experience",
    "industry_experience",
    "employment_gap",
    "tenure_stability",
    "career_progression",
    "job_hopping_risk",
    "educational_background",
    "certifications_licenses",
    "technical_skills_match",
]
_ASSESSMENT_DIMENSIONS = ["pre_assessment", "culture_fit", "technical"]


# The round-trip CSV columns — kept in sync with the CSV importer + analytics
# export (evaluations.py). Order matters: this is the file header.
# Each dimension gets a rating column AND a reason column, e.g.
# `resume__tenure_stability` + `resume__tenure_stability__reason`.
def _dimension_columns() -> list[str]:
    cols: list[str] = []
    for dimension in _RESUME_DIMENSIONS:
        cols += [f"resume__{dimension}", f"resume__{dimension}__reason"]
    for dimension in _ASSESSMENT_DIMENSIONS:
        cols += [f"assessment__{dimension}", f"assessment__{dimension}__reason"]
    return cols


EVAL_CSV_COLUMNS = [
    "application_id",
    "applicant_name",
    "seniority_assessed",
    "fit_score",
    "recommendation",
    "summary",
    *_dimension_columns(),
]


def _results_template_csv(applicants: list[dict]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(EVAL_CSV_COLUMNS)
    for entry in applicants:
        row = entry["row"]
        name = f"{row.applicant_first_name} {row.applicant_last_name}"
        writer.writerow(
            [str(row.id), csv_safe(name), *[""] * (len(EVAL_CSV_COLUMNS) - 2)]
        )
    return buffer.getvalue()


def _readme_md(job_title: str, count: int, generated_at: datetime) -> str:
    return f"""# Evaluation pack — {job_title}

Generated: {generated_at.isoformat()}
Applicants: {count}

## Contents

```
PROMPT.md                 Copy-paste instruction for ChatGPT (start here)
job/description.md        The role: description, requirements, qualifications, responsibilities
evaluation-rubric.md      How to score applicants (feed this to the AI agent)
RESULTS-FORMAT.md         The columns the agent must fill for re-import
evaluation-template.csv   Pre-filled rows — fill the columns, import it back (CSV)
evaluation-results.template.json   Same, richer JSON alternative
applicants/<n>-<name>/
    resume.<ext>          The applicant's résumé (missing file noted if not on record)
    assessments.md        Their answers to the 3 assessments
    profile.json          Status, dates, contact, assessment completion summary
manifest.json             Machine-readable index of everything in this pack
```

## How to use

Attach this whole ZIP to ChatGPT and paste the contents of `PROMPT.md`.
It produces a readable summary plus `evaluation-results.csv` — import that
file back on the Compare tab ("Import evaluation results").
"""


def _job_md(job: Any) -> str:
    salary = ""
    if job.salary_min or job.salary_max:
        lo = f"{job.salary_min:,.0f}" if job.salary_min else "?"
        hi = f"{job.salary_max:,.0f}" if job.salary_max else "?"
        salary = f"\n- **Salary range:** {job.currency} {lo} – {hi}"
    return f"""# {job.job_title}

- **Position:** {job.position_title}
- **Employment type:** {job.employment_type}{salary}
- **Status:** {job.status}

## Description

{_html_to_text(job.description)}

## Requirements

{_html_to_text(job.requirements)}

## Qualifications

{_html_to_text(job.qualifications)}
"""


def _assessments_md(name: str, reviews: list[dict]) -> str:
    lines = [f"# Assessment answers — {name}", ""]
    if not reviews:
        lines.append("_No assessments are attached to this role._")
        return "\n".join(lines) + "\n"

    order = {"pre_assessment": 0, "culture_fit": 1, "technical": 2}
    for review in sorted(reviews, key=lambda r: order.get(r["template_type"], 9)):
        label = _TEMPLATE_LABELS.get(review["template_type"], review["template_type"])
        lines.append(f"## {label} — {review['template_title']}")
        lines.append("")
        lines.append(
            f"- Status: **{review['status']}** "
            f"({review['answered_count']}/{review['total_questions']} answered)"
        )
        if review.get("completed_at"):
            lines.append(f"- Completed: {review['completed_at']}")
        lines.append("")
        if not review["questions"]:
            lines.append("_No questions._")
            lines.append("")
            continue
        for i, q in enumerate(review["questions"], 1):
            lines.append(f"**{i}. {q['prompt']}**  _({q['question_type']})_")
            lines.append("")
            lines.append(_fmt(q.get("answer_value")))
            lines.append("")
    return "\n".join(lines) + "\n"


def build_evaluation_pack(*, job: Any, applicants: list[dict]) -> bytes:
    """`applicants`: list of ``{"row", "resume": (bytes, filename) | None,
    "reviews": list[dict]}`` — `row` has id / applicant_first_name /
    applicant_last_name / applicant_email / status / created_at."""
    generated_at = datetime.now(UTC)
    buf = io.BytesIO()
    manifest: dict[str, Any] = {
        "job_id": str(job.id),
        "job_title": job.job_title,
        "generated_at": generated_at.isoformat(),
        "applicant_count": len(applicants),
        "applicants": [],
    }

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "README.md", _readme_md(job.job_title, len(applicants), generated_at)
        )
        archive.writestr("job/description.md", _job_md(job))
        archive.writestr("PROMPT.md", PROMPT_MD)
        archive.writestr("evaluation-rubric.md", RUBRIC_MD)
        archive.writestr("RESULTS-FORMAT.md", RESULTS_FORMAT_MD)
        archive.writestr("evaluation-template.csv", _results_template_csv(applicants))
        archive.writestr(
            "evaluation-results.template.json",
            _results_template(str(job.id), applicants),
        )

        for i, entry in enumerate(applicants, 1):
            row = entry["row"]
            name = f"{row.applicant_first_name} {row.applicant_last_name}"
            folder = f"applicants/{i:02d}-{_slug(name)}"

            resume_file: str | None = None
            if entry["resume"] is not None:
                data, filename = entry["resume"]
                ext = PurePosixPath(filename).suffix or ".pdf"
                resume_file = f"resume{ext}"
                archive.writestr(f"{folder}/{resume_file}", data)
            else:
                archive.writestr(
                    f"{folder}/RESUME-NOT-AVAILABLE.txt",
                    "No résumé file is on record for this application.\n",
                )

            archive.writestr(
                f"{folder}/assessments.md", _assessments_md(name, entry["reviews"])
            )
            profile = {
                "name": name,
                "email": row.applicant_email,
                "application_id": str(row.id),
                "pipeline_status": row.status,
                "applied_at": row.created_at.isoformat() if row.created_at else None,
                "assessments": [
                    {
                        "type": r["template_type"],
                        "status": r["status"],
                        "answered": r["answered_count"],
                        "total": r["total_questions"],
                    }
                    for r in entry["reviews"]
                ],
            }
            archive.writestr(f"{folder}/profile.json", json.dumps(profile, indent=2))
            manifest["applicants"].append(
                {
                    "folder": folder,
                    "name": name,
                    "email": row.applicant_email,
                    "resume": resume_file,
                    "pipeline_status": row.status,
                }
            )

        archive.writestr("manifest.json", json.dumps(manifest, indent=2))

    return buf.getvalue()
