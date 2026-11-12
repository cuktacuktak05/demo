from typing import Literal, Optional
from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    role: Literal["employee", "admin"] = "employee"
    use_rag: bool = True


class CitationItem(BaseModel):
    title: str
    source: str
    snippet: str
    score: float
    chunk_id: Optional[str] = None
    document_id: Optional[str] = None
    article: Optional[str] = None
    effective_from: Optional[str] = None
    effective_to: Optional[str] = None
    legal_status: Optional[str] = None
    retrieval_method: Optional[str] = None
    citation: Optional[str] = None


class SourceItem(BaseModel):
    source: str
    excerpt: str


class RetrievalInfo(BaseModel):
    top_score: Optional[float] = None
    threshold: float
    n_chunks: int
    status: Optional[str] = "relevant"
    method: Optional[str] = "hybrid"


class AskResponse(BaseModel):
    answer: str
    source_type: Literal["kb", "web", "none"]
    citations: list[CitationItem] = Field(default_factory=list)
    retrieval: RetrievalInfo
    warnings: list[str] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str = "ok"
    llm_configured: bool
    kb_chunks: int


class ErrorResponse(BaseModel):
    error_code: str
    message: str


class MaskTestRequest(BaseModel):
    text: str = Field(min_length=1, max_length=5000)


class MaskTestResponse(BaseModel):
    original: str
    masked: str
    notes: list[str]
