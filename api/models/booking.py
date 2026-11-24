from sqlalchemy import Column, Integer, String, Date, Numeric, DateTime, Text, ForeignKey
from sqlalchemy.sql import func
from api.database import Base


class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)
    confirmation_code = Column(String(20), unique=True, index=True, nullable=False)
    room_id = Column(Integer, ForeignKey("rooms.id"), nullable=False)
    guest_name = Column(String(200), nullable=False, index=True)
    guest_phone = Column(String(30), nullable=False, index=True)
    guest_email = Column(String(100), nullable=True)
    check_in = Column(Date, nullable=False, index=True)
    check_out = Column(Date, nullable=False, index=True)
    num_guests = Column(Integer, default=1, nullable=False)
    total_price = Column(Numeric(10, 2), nullable=False)
    status = Column(String(30), default="confirmed", index=True)  # confirmed, cancelled, completed
    language_used = Column(String(20), default="en-IN")  # ta-IN, en-IN, tanglish
    raw_conversation = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
