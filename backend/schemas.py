from pydantic import BaseModel, Field
from typing import Literal


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    role: Literal["employee", "admin"] = "employee"
    use_rag: bool = True


class SourceItem(BaseModel):
    source: str
    excerpt: str


class AskResponse(BaseModel):
    answer: str
    sources: list[SourceItem]
    masked_input: str
    safety_notes: list[str]
    model: str
