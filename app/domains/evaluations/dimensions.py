from typing import Literal

# Canonical dimensions — the agent SHOULD use these, but unknown strings are
# still stored (analytics groups on whatever is there). Kept here so the
# export pack's schema file and the importer never drift.
RESUME_DIMENSIONS = [
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
ASSESSMENT_DIMENSIONS = ["pre_assessment", "culture_fit", "technical"]

# Not a rated dimension — a single standardized field on the evaluation
# itself (like seniority_assessed). Free text, but the agent is told to keep
# to this shape so `application_evaluations.location` stays groupable for
# location analytics without a controlled enum.
LOCATION_FORMAT_HINT = (
    '"City, Province" (e.g. "Quezon City, Metro Manila"), "Remote" if the '
    "résumé states no fixed/remote location, or leave blank if not stated. "
    "Use full official place names, no abbreviations."
)

Rating = Literal["strong", "qualified", "below_bar", "na"]
Recommendation = Literal["advance", "hold", "reject"]
