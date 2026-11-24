from sqlalchemy import Column, Integer, String, Numeric, Boolean, Text, JSON
from api.database import Base, CompatibleVector


class Room(Base):
    __tablename__ = "rooms"

    id = Column(Integer, primary_key=True, index=True)
    room_number = Column(String(20), unique=True, index=True, nullable=False)
    name = Column(String(100), nullable=False)
    type = Column(String(50), index=True, nullable=False)  # deluxe, suite, standard, family
    floor = Column(Integer, default=1)
    max_guests = Column(Integer, default=2, nullable=False)
    price_per_night = Column(Numeric(10, 2), nullable=False)
    amenities = Column(JSON, default=list)  # Stored as JSON list of strings
    description = Column(Text, nullable=False)
    description_ta = Column(Text, nullable=True)  # Tamil description
    description_vector = Column(CompatibleVector(384), nullable=True)
    is_active = Column(Boolean, default=True, index=True)
