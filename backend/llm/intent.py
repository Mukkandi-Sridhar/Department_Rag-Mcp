BACKLOG_KEYWORDS = [
    "backlog",
    "backlogs",
    "fail",
    "failed",
    "failing",
    "arrear",
    "arrears",
    "pending",
    "pending subject",
    "pending subjects",
]

CGPA_KEYWORDS = [
    "cgpa",
    "gpa",
    "grade",
    "grades",
    "score",
    "academic score",
]

PLACEMENT_KEYWORDS = [
    "placement",
    "place",
    "job ready",
    "placement ready",
    "ready for placement",
    "employability",
]

DOCUMENT_KEYWORDS = [
    "policy",
    "syllabus",
    "circular",
    "pdf",
    "document",
    "documents",
    "rules",
    "regulation",
    "regulations",
]


def normalize_query(message: str | None) -> str:
    return " ".join((message or "").lower().strip().split())


def detect_intent(query: str) -> str:
    if any(keyword in query for keyword in BACKLOG_KEYWORDS):
        return "student_data_query"

    if any(keyword in query for keyword in CGPA_KEYWORDS):
        return "student_data_query"

    if any(keyword in query for keyword in PLACEMENT_KEYWORDS):
        return "student_data_query"

    if any(keyword in query for keyword in DOCUMENT_KEYWORDS):
        return "document_query"

    return "unclear_query"


def requested_student_field(query: str) -> str:
    if any(keyword in query for keyword in BACKLOG_KEYWORDS):
        return "backlogs"

    if any(keyword in query for keyword in CGPA_KEYWORDS):
        return "cgpa"

    if any(keyword in query for keyword in PLACEMENT_KEYWORDS):
        return "placement"

    return "summary"
