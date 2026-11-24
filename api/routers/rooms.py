from typing import List, Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from api.database import get_db
from api.schemas.room import RoomResponse, RoomAvailabilityRequest
from api.services.room_service import check_availability, get_all_rooms, get_room_by_id
from api.services.vector_service import semantic_room_search

router = APIRouter(prefix="/rooms", tags=["rooms"])


@router.get("", response_model=List[RoomResponse])
def list_rooms(db: Session = Depends(get_db)):
    """List all active hotel rooms."""
    return get_all_rooms(db)


@router.post("/availability")
def check_room_availability(
    request: RoomAvailabilityRequest,
    db: Session = Depends(get_db),
):
    """
    Check if rooms are available for the selected dates and guest count.
    """
    available_rooms = check_availability(
        db=db,
        room_type=request.room_type,
        check_in=request.check_in,
        check_out=request.check_out,
        num_guests=request.num_guests,
    )
    return {
        "success": True,
        "available_count": len(available_rooms),
        "is_available": len(available_rooms) > 0,
        "rooms": [RoomResponse.model_validate(r) for r in available_rooms],
    }


@router.get("/search", response_model=List[RoomResponse])
def search_rooms_semantically(
    q: str = Query(..., min_length=1, description="Natural language search e.g. 'romantic room with balcony'"),
    limit: int = Query(default=5, ge=1, le=20),
    db: Session = Depends(get_db),
):
    """Semantic room search using vector similarity."""
    results = semantic_room_search(db=db, query=q, limit=limit)
    response_list = []
    for room, score in results:
        res = RoomResponse.model_validate(room)
        res.similarity_score = round(score, 4)
        response_list.append(res)
    return response_list


@router.get("/{room_id}", response_model=RoomResponse)
def get_room_details(room_id: int, db: Session = Depends(get_db)):
    room = get_room_by_id(db, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    return RoomResponse.model_validate(room)
