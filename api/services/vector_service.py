"""
Semantic search service leveraging pgvector or fallback cosine similarity.
"""
from typing import List, Tuple
from sqlalchemy.orm import Session
from api.models.room import Room
from api.models.faq import FAQ
from api.database import is_sqlite
from api.services.embedding_service import embed_text, cosine_similarity


def semantic_room_search(
    db: Session,
    query: str,
    limit: int = 5,
) -> List[Tuple[Room, float]]:
    """
    Search rooms matching natural language description (e.g. 'peaceful sea view with balcony').
    Returns tuples of (Room, similarity_score).
    """
    if not query.strip():
        rooms = db.query(Room).filter(Room.is_active == True).limit(limit).all()
        return [(r, 1.0) for r in rooms]

    query_vector = embed_text(query)

    # If PostgreSQL with native vector extension is active:
    if not is_sqlite:
        try:
            from pgvector.sqlalchemy import Vector # noqa
            results = (
                db.query(Room, (1 - Room.description_vector.cosine_distance(query_vector)).label("sim"))
                .filter(Room.is_active == True, Room.description_vector != None)
                .order_by(Room.description_vector.cosine_distance(query_vector).asc())
                .limit(limit)
                .all()
            )
            return [(r, float(sim)) for r, sim in results]
        except Exception:
            pass

    # High-performance fallback for SQLite / local testing
    all_rooms = db.query(Room).filter(Room.is_active == True).all()
    scored: List[Tuple[Room, float]] = []

    for room in all_rooms:
        vec = room.description_vector
        if vec and isinstance(vec, (list, tuple)):
            score = cosine_similarity(query_vector, list(vec))
        else:
            # Lexical fallback score if vector not set
            match_count = sum(1 for w in query.lower().split() if w in room.description.lower())
            score = float(match_count) / max(len(query.split()), 1)
        scored.append((room, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:limit]


def semantic_faq_search(
    db: Session,
    query: str,
    limit: int = 3,
) -> List[Tuple[FAQ, float]]:
    """Search hotel policies and FAQs matching user voice question."""
    if not query.strip():
        faqs = db.query(FAQ).limit(limit).all()
        return [(f, 1.0) for f in faqs]

    query_vector = embed_text(query)

    all_faqs = db.query(FAQ).all()
    scored: List[Tuple[FAQ, float]] = []

    for faq in all_faqs:
        vec = faq.embedding
        if vec and isinstance(vec, (list, tuple)):
            score = cosine_similarity(query_vector, list(vec))
        else:
            text = f"{faq.question_en} {faq.answer_en} {faq.question_ta or ''}"
            match_count = sum(1 for w in query.lower().split() if w in text.lower())
            score = float(match_count) / max(len(query.split()), 1)
        scored.append((faq, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:limit]
