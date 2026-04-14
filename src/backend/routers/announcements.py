"""
Announcement endpoints for banner content management.
"""

from datetime import datetime, date
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query

from ..database import announcements_collection, teachers_collection

router = APIRouter(
    prefix="/announcements",
    tags=["announcements"]
)


def _normalize_date(value: Optional[str], field_name: str, required: bool = False) -> Optional[str]:
    """Validate date strings and normalize to YYYY-MM-DD."""
    if value is None or value == "":
        if required:
            raise HTTPException(status_code=400, detail=f"{field_name} is required")
        return None

    try:
        parsed = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"{field_name} must use YYYY-MM-DD format"
        ) from exc

    return parsed.isoformat()


def _require_signed_in_user(teacher_username: Optional[str]) -> Dict[str, Any]:
    if not teacher_username:
        raise HTTPException(status_code=401, detail="Authentication required for this action")

    teacher = teachers_collection.find_one({"_id": teacher_username})
    if not teacher:
        raise HTTPException(status_code=401, detail="Invalid teacher credentials")

    return teacher


def _serialize_announcement(doc: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": doc.get("_id"),
        "message": doc.get("message", ""),
        "start_date": doc.get("start_date"),
        "expiration_date": doc.get("expiration_date"),
        "created_by": doc.get("created_by")
    }


@router.get("", response_model=List[Dict[str, Any]])
@router.get("/", response_model=List[Dict[str, Any]])
def get_announcements(include_expired: bool = Query(False)) -> List[Dict[str, Any]]:
    """Return announcements; by default only active announcements."""
    today = date.today().isoformat()
    query: Dict[str, Any] = {}

    if not include_expired:
        query = {
            "$and": [
                {
                    "$or": [
                        {"start_date": None},
                        {"start_date": {"$exists": False}},
                        {"start_date": {"$lte": today}}
                    ]
                },
                {"expiration_date": {"$gte": today}}
            ]
        }

    docs = announcements_collection.find(query).sort("expiration_date", 1)
    return [_serialize_announcement(doc) for doc in docs]


@router.post("", response_model=Dict[str, Any])
def create_announcement(
    message: str,
    expiration_date: str,
    start_date: Optional[str] = None,
    teacher_username: Optional[str] = Query(None)
) -> Dict[str, Any]:
    """Create a new announcement (signed-in users only)."""
    teacher = _require_signed_in_user(teacher_username)

    clean_message = message.strip()
    if not clean_message:
        raise HTTPException(status_code=400, detail="message is required")

    normalized_start = _normalize_date(start_date, "start_date", required=False)
    normalized_exp = _normalize_date(expiration_date, "expiration_date", required=True)

    if normalized_start and normalized_start > normalized_exp:
        raise HTTPException(status_code=400, detail="start_date cannot be after expiration_date")

    announcement = {
        "_id": str(uuid4()),
        "message": clean_message,
        "start_date": normalized_start,
        "expiration_date": normalized_exp,
        "created_by": teacher.get("_id")
    }

    announcements_collection.insert_one(announcement)
    return _serialize_announcement(announcement)


@router.put("/{announcement_id}", response_model=Dict[str, Any])
def update_announcement(
    announcement_id: str,
    message: str,
    expiration_date: str,
    start_date: Optional[str] = None,
    teacher_username: Optional[str] = Query(None)
) -> Dict[str, Any]:
    """Update an announcement (signed-in users only)."""
    _require_signed_in_user(teacher_username)

    existing = announcements_collection.find_one({"_id": announcement_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Announcement not found")

    clean_message = message.strip()
    if not clean_message:
        raise HTTPException(status_code=400, detail="message is required")

    normalized_start = _normalize_date(start_date, "start_date", required=False)
    normalized_exp = _normalize_date(expiration_date, "expiration_date", required=True)

    if normalized_start and normalized_start > normalized_exp:
        raise HTTPException(status_code=400, detail="start_date cannot be after expiration_date")

    update_doc = {
        "message": clean_message,
        "start_date": normalized_start,
        "expiration_date": normalized_exp
    }

    announcements_collection.update_one(
        {"_id": announcement_id},
        {"$set": update_doc}
    )

    updated = announcements_collection.find_one({"_id": announcement_id})
    return _serialize_announcement(updated)


@router.delete("/{announcement_id}")
def delete_announcement(
    announcement_id: str,
    teacher_username: Optional[str] = Query(None)
) -> Dict[str, str]:
    """Delete an announcement (signed-in users only)."""
    _require_signed_in_user(teacher_username)

    result = announcements_collection.delete_one({"_id": announcement_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")

    return {"message": "Announcement deleted"}
