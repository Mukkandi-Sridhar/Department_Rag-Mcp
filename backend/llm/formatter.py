from backend.llm.intent import requested_student_field


def format_student_answer(query: str, student: dict) -> str:
    field = requested_student_field(query)

    if field == "backlogs":
        count = student["backlogs"]
        if count == 0:
            return "You currently have 0 backlogs."
        if count == 1:
            return "You currently have 1 backlog."
        return f"You currently have {count} backlogs."

    if field == "cgpa":
        return f"Your current CGPA is {student['cgpa']:.2f}."

    if field == "placement":
        return (
            f"Your placement status is: {student['placement']}. "
            f"Risk level: {student['risk']}."
        )

    return (
        f"{student['name']} has a CGPA of {student['cgpa']:.2f}, "
        f"{student['backlogs']} backlogs, and placement status: {student['placement']}."
    )
