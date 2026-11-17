from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    role: str = "employee"
    use_rag: bool = True
    demask: bool = False


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
    trust_metadata: Optional[Dict[str, Any]] = None


class HealthResponse(BaseModel):
    status: str = "ok"
    llm_configured: bool
    kb_chunks: int


class ErrorResponse(BaseModel):
    error_code: str
    message: str


# ============================================================================
# TRUST LAYER SECURITY DEMO SCHEMAS
# ============================================================================

class MaskTestRequest(BaseModel):
    text: str = Field(min_length=1, max_length=5000)


class MaskTestResponse(BaseModel):
    original: str
    masked: str
    notes: list[str]
    pii_count: int = 0
    pii_types: list[str] = Field(default_factory=list)
    mapping: Dict[str, str] = Field(default_factory=dict)


class DemaskRequest(BaseModel):
    text: str = Field(min_length=1, max_length=10000)
    mapping: Dict[str, str] = Field(default_factory=dict)


class DemaskResponse(BaseModel):
    demasked: str


class RoleCheckRequest(BaseModel):
    role: str = Field(min_length=1, max_length=50)
    action: str = Field(default="access", max_length=50)


class RoleCheckResponse(BaseModel):
    allowed: bool
    role: str
    action: str
    message: str


class PromptSafetyRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=5000)


class PromptSafetyResponse(BaseModel):
    is_safe: bool
    risk_level: str
    reason: str
    action: str
    matched_categories: list[str] = Field(default_factory=list)


class OutputFilterRequest(BaseModel):
    text: str = Field(min_length=1, max_length=10000)
    context_sources: list[str] = Field(default_factory=list)


class OutputFilterResponse(BaseModel):
    is_safe: bool
    violations: list[str]
    action: str
    original: str
    filtered: str
