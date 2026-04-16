from backend.database.firestore import db_client
from backend.rag.retrieve import retrieve_documents as retrieve_documents_from_rag


def get_student_data(reg_no: str) -> dict | None:
    return db_client.get_student_data(reg_no)


def retrieve_documents(query: str) -> list[dict]:
    return retrieve_documents_from_rag(query)
