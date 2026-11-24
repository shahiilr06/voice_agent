from sqlalchemy import Column, Integer, String, Text
from api.database import Base, CompatibleVector


class FAQ(Base):
    __tablename__ = "faqs"

    id = Column(Integer, primary_key=True, index=True)
    category = Column(String(50), index=True, default="general")
    question_en = Column(Text, nullable=False)
    answer_en = Column(Text, nullable=False)
    question_ta = Column(Text, nullable=True)
    answer_ta = Column(Text, nullable=True)
    embedding = Column(CompatibleVector(384), nullable=True)
