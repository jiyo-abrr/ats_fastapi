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

Rating = Literal["strong", "qualified", "below_bar", "na"]
Recommendation = Literal["advance", "hold", "reject"]
