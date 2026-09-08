from enum import StrEnum


class EmploymentType(StrEnum):
    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACT = "contract"
    INTERNSHIP = "internship"
    TEMPORARY = "temporary"


class JobPostStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    CLOSED = "closed"


class Currency(StrEnum):
    """ISO-4217 codes offered for job-post salary ranges. PHP is the default."""

    PHP = "PHP"
    USD = "USD"
    EUR = "EUR"
    GBP = "GBP"
    SGD = "SGD"
    AUD = "AUD"
    CAD = "CAD"
    JPY = "JPY"
    HKD = "HKD"
    MYR = "MYR"
    INR = "INR"
    CNY = "CNY"
