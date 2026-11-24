from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class FAQBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    category: str = Field(default="general")
    question_en: str
    answer_en: str
    question_ta: Optional[str] = None
    answer_ta: Optional[str] = None


class FAQCreate(FAQBase):
    pass


class FAQResponse(FAQBase):
    id: int
    similarity_score: Optional[float] = None
