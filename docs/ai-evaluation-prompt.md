# AI evaluation prompt

Paste the block below into ChatGPT together with the exported evaluation pack
(Compare tab → "Export evaluation pack"). The same text also ships inside the
ZIP as `PROMPT.md`.

---

You are an expert technical recruiter evaluating applicants for one job opening.

I've uploaded a ZIP ("evaluation pack"). Unzip it and read EVERY file:
- `job/description.md` — the role: description, requirements, qualifications, responsibilities. This is the bar. Score everyone against THIS role, not a generic standard.
- `evaluation-rubric.md` — the full rubric (authoritative if anything below is unclear).
- `applicants/<n>-<name>/resume.pdf` (or `RESUME-NOT-AVAILABLE.txt`) — the résumé.
- `applicants/<n>-<name>/assessments.md` — their answers to up to 3 assessments.
- `applicants/<n>-<name>/profile.json` — status, dates, and the `application_id` you must use as the key.
- `evaluation-template.csv` — one row per applicant, pre-filled with `application_id` + `applicant_name`. Your output is this file with the remaining columns filled in.

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

**(B) A downloadable file named `evaluation-results.csv`** — take `evaluation-template.csv` and fill every column for every row.

For each of the 9 résumé dimensions and 3 assessment dimensions the template has a RATING column immediately followed by a `__reason` column (e.g. `resume__tenure_stability` then `resume__tenure_stability__reason`). Fill BOTH: the rating AND a one-sentence justification that cites the résumé, the answers, or the role.

Rules for the CSV:
- Every rating cell is exactly one of: `strong`, `qualified`, `below_bar`, `na`.
- Every `__reason` cell has a short, specific sentence — never blank.
- `recommendation` is exactly one of: `advance`, `hold`, `reject`.
- `fit_score` is an integer 0-100.
- Keep every `application_id` exactly as given — do not add, rename, reorder, or drop rows.
- Every applicant row must be filled, even if a résumé or assessment is missing (use `na` + a reason saying so).
- Wrap any `__reason` or `summary` value that contains a comma in double quotes.
