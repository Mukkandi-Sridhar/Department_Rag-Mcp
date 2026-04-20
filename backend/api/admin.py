import asyncio
import time
from typing import Any

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel

from backend.auth.firebase_auth import verify_firebase_token
from backend.core.config import settings
from backend.database.neo4j_client import db_client
from backend.database.validation import validate_student, validate_student_update
from backend.core.audit import log_action

router = APIRouter(prefix="/admin", tags=["admin"])

def _require_hod(authorization: str | None) -> str:
    auth_user = verify_firebase_token(authorization)
    role = auth_user.role_hint or "student"
    if role != "hod":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="HOD role required to access this endpoint."
        )
    return auth_user.uid

@router.get("/students")
async def list_students(authorization: str | None = Header(default=None)):
    _require_hod(authorization)
    students = await asyncio.to_thread(db_client.list_all_students)
    return {"status": "ok", "students": students}

class AddStudentReq(BaseModel):
    data: dict[str, Any]

@router.post("/students")
async def add_student(req: AddStudentReq, authorization: str | None = Header(default=None)):
    uid = _require_hod(authorization)
    validated = validate_student(req.data)
    reg_no = validated.get("reg_no")
    if not reg_no:
        raise HTTPException(status_code=400, detail="Valid reg_no required")
        
    success = await asyncio.to_thread(db_client.add_student, validated)
    log_action(uid, "hod", "add_student", reg_no, validated, "success" if success else "failed")
    
    if not success:
        raise HTTPException(status_code=400, detail="Failed to add student. May already exist.")
    return {"status": "ok", "message": f"Student {reg_no} added successfully."}
    
class UpdateStudentReq(BaseModel):
    fields: dict[str, Any]

@router.patch("/students/{reg_no}")
async def update_student(reg_no: str, req: UpdateStudentReq, authorization: str | None = Header(default=None)):
    uid = _require_hod(authorization)
    valid_fields = validate_student_update(req.fields)
    if not valid_fields:
        raise HTTPException(status_code=400, detail="No valid updatable fields provided")
        
    success = await asyncio.to_thread(db_client.update_student_data, reg_no, valid_fields)
    log_action(uid, "hod", "update_student", reg_no, valid_fields, "success" if success else "failed")
    
    if not success:
        raise HTTPException(status_code=404, detail=f"Student {reg_no} not found")
        
    return {"status": "ok", "message": f"Student {reg_no} updated."}

@router.delete("/students/{reg_no}")
async def remove_student(reg_no: str, authorization: str | None = Header(default=None)):
    uid = _require_hod(authorization)
    success = await asyncio.to_thread(db_client.remove_student, reg_no)
    log_action(uid, "hod", "remove_student", reg_no, None, "success" if success else "failed")
    
    if not success:
        raise HTTPException(status_code=404, detail=f"Student {reg_no} not found")
        
    return {"status": "ok", "message": f"Student {reg_no} removed."}
