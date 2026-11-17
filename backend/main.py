"""FastAPI Backend for Enterprise GenAI Assistant with Trust Layer — Session 2.

Comprehensive Pipeline:
User Request
→ Role Checking
→ PII Masking
→ Prompt Safety
→ RAG Retrieval
→ LLM Gateway
→ Output Filtering
→ Demasking
→ Response
→ Audit Log
"""

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import time
from typing import Any, Dict, List, Optional
import uuid

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse

from .schemas import (
    AskRequest,
    AskResponse,
    CitationItem,
    DemaskRequest,
    DemaskResponse,
    ErrorResponse,
    HealthResponse,
    MaskTestRequest,
    MaskTestResponse,
    OutputFilterRequest,
    OutputFilterResponse,
    PromptSafetyRequest,
    PromptSafetyResponse,
    RetrievalInfo,
    RoleCheckRequest,
    RoleCheckResponse,
)
from .trust import (
    check_output,
    check_prompt_safety,
    check_role,
    demask_pii,
    evaluate_role_access,
    mask_pii,
    require_admin,
)
from .rag import count_kb_chunks, get_min_score, retrieve
from .llm import (
    generate_answer,
    is_general_knowledge_allowed,
    is_llm_configured,
    LLMCallError,
    LLMConfigError,
)
from .llm_gateway import (
    gateway_generate_answer,
    LLMGatewaySecurityError,
    LLMGatewayTimeoutError,
)

load_dotenv()
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Enterprise GenAI Assistant API with Trust Layer",
    version="0.2.0",
    description="Educational demo: RAG + Multi-layered Trust Layer (Role Checking, PII Masking, Prompt Safety, LLM Gateway, Output Filtering).",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

LOG_PATH = Path(__file__).resolve().parent.parent / "audit.log"


def audit(event: dict):
    """Write sanitized telemetry log to audit.log.

    NEVER writes:
    - Raw unmasked PII (CCCD, Phone, Email)
    - Raw API keys or confidential system prompts
    - Raw user secrets
    """
    event["timestamp_utc"] = datetime.now(timezone.utc).isoformat()
    try:
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.error("Failed to write to audit log: %s", exc)


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/docs")


@app.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse(
        status="ok",
        llm_configured=is_llm_configured(),
        kb_chunks=count_kb_chunks(),
    )


# ============================================================================
# MAIN SECURE PIPELINE: /ask
# ============================================================================

@app.post(
    "/ask",
    response_model=AskResponse,
    responses={
        403: {"model": ErrorResponse, "description": "Quyền truy cập bị từ chối"},
        503: {"model": ErrorResponse, "description": "LLM service unavailable or unconfigured"},
    },
)
def ask(payload: AskRequest):
    request_id = str(uuid.uuid4())
    t0 = time.perf_counter()

    # 1. Role Checking
    try:
        check_role(payload.role)
        role_status = "allowed"
    except PermissionError as exc:
        audit({
            "request_id": request_id,
            "user_id": f"anon-{abs(hash(payload.role)) % 10000:04d}",
            "user_role": payload.role,
            "role_check": "denied",
            "pii_count": 0,
            "prompt_safety": "skipped",
            "rag_chunks": 0,
            "llm_status": "skipped",
            "output_filter": "skipped",
            "final_status": "403_forbidden",
            "event": "role_denied",
            "error": str(exc),
        })
        raise HTTPException(status_code=403, detail=str(exc))

    # 2. PII Masking
    mask_res = mask_pii(payload.question)
    safe_question = mask_res.masked
    safety_notes = mask_res.notes
    pii_mapping = mask_res.pii_mapping
    pii_count = len(pii_mapping)

    # 3. Prompt Safety Checking
    safety_eval = check_prompt_safety(safe_question)
    prompt_safety_code = f"{safety_eval['risk_level']}_{safety_eval['action']}"

    if safety_eval["action"] == "block":
        audit({
            "request_id": request_id,
            "user_id": f"user-{payload.role}",
            "user_role": payload.role,
            "role_check": "allowed",
            "pii_count": pii_count,
            "prompt_safety": prompt_safety_code,
            "rag_chunks": 0,
            "llm_status": "blocked",
            "output_filter": "skipped",
            "final_status": "blocked_prompt_safety",
            "event": "prompt_safety_blocked",
            "reason": safety_eval["reason"],
        })
        return AskResponse(
            answer=(
                "Yêu cầu của bạn đã bị Trust Layer từ chối xử lý do vi phạm chính sách an toàn hệ thống "
                f"({safety_eval['reason']}). Vui lòng nhập câu hỏi hợp lệ liên quan đến nghiệp vụ pháp lý."
            ),
            source_type="none",
            citations=[],
            retrieval=RetrievalInfo(
                top_score=None,
                threshold=get_min_score(),
                n_chunks=0,
                status="blocked",
                method="none",
            ),
            warnings=list(safety_notes) + [f"Chặn bởi Prompt Safety: {safety_eval['reason']}"],
            trust_metadata={
                "request_id": request_id,
                "role": payload.role,
                "pii_count": pii_count,
                "prompt_safety": safety_eval,
                "output_filter": {"is_safe": False, "action": "blocked"},
            },
        )

    # 4. RAG Retrieval
    chunks = retrieve(safe_question, top_k=3) if payload.use_rag else []
    threshold = get_min_score()

    # 5. LLM Gateway
    if not is_llm_configured():
        audit({
            "request_id": request_id,
            "user_id": f"user-{payload.role}",
            "user_role": payload.role,
            "role_check": "allowed",
            "pii_count": pii_count,
            "prompt_safety": prompt_safety_code,
            "rag_chunks": len(chunks),
            "llm_status": "unconfigured",
            "output_filter": "skipped",
            "final_status": "503_llm_not_configured",
            "event": "llm_config_error",
        })
        return JSONResponse(
            status_code=503,
            content={
                "error_code": "LLM_NOT_CONFIGURED",
                "message": "Chưa cấu hình OPENAI_API_KEY trong file .env.",
            },
        )

    try:
        raw_answer, model, gateway_meta = gateway_generate_answer(
            safe_question, chunks, payload.role, safety_eval, generate_fn=generate_answer
        )
        llm_status = "success"
    except LLMConfigError as exc:
        audit({
            "request_id": request_id,
            "user_id": f"user-{payload.role}",
            "user_role": payload.role,
            "role_check": "allowed",
            "pii_count": pii_count,
            "prompt_safety": prompt_safety_code,
            "rag_chunks": len(chunks),
            "llm_status": "config_error",
            "output_filter": "skipped",
            "final_status": "503_config_error",
            "event": "llm_config_error",
            "error": str(exc),
        })
        return JSONResponse(
            status_code=503,
            content={"error_code": "LLM_NOT_CONFIGURED", "message": str(exc)},
        )
    except Exception as exc:
        audit({
            "request_id": request_id,
            "user_id": f"user-{payload.role}",
            "user_role": payload.role,
            "role_check": "allowed",
            "pii_count": pii_count,
            "prompt_safety": prompt_safety_code,
            "rag_chunks": len(chunks),
            "llm_status": "error",
            "output_filter": "skipped",
            "final_status": "503_llm_error",
            "event": "generation_error",
            "error_type": type(exc).__name__,
        })
        return JSONResponse(
            status_code=503,
            content={"error_code": "LLM_ERROR", "message": f"Không gọi được mô hình LLM: {exc}"},
        )

    # 6. Output Filtering
    context_sources = [c["source"] for c in chunks] if chunks else []
    filtered_answer, filter_result = check_output(raw_answer, context_sources=context_sources)
    output_violations = filter_result.get("violations", [])

    # 7. Demasking (Restores PII in response only if requested, preserves masked state otherwise)
    if payload.demask and pii_mapping:
        final_answer = demask_pii(filtered_answer, pii_mapping)
    else:
        final_answer = filtered_answer

    # 8. Construct Response
    warnings = list(safety_notes) + list(output_violations)

    if chunks:
        source_type = "kb"
        citations = [
            CitationItem(
                title=c.get("title", c["source"]),
                source=c["source"],
                snippet=c["text"][:500],
                score=round(c["score"], 4),
                chunk_id=c.get("chunk_id", c["source"]),
                document_id=c.get("document_id"),
                article=c.get("article"),
                effective_from=c.get("effective_from"),
                effective_to=c.get("effective_to"),
                legal_status=c.get("legal_status"),
                retrieval_method=c.get("retrieval_method"),
                citation=c.get("citation"),
            )
            for c in chunks
        ]
        top_score = round(chunks[0]["score"], 4)
    else:
        source_type = "none"
        citations = []
        top_score = None
        if is_general_knowledge_allowed():
            warnings.append("Thông tin tham khảo chung, không trích từ tài liệu")
        elif payload.use_rag:
            warnings.append("Không đủ ngữ cảnh phù hợp từ tài liệu (insufficient_context)")

    retrieval_status = getattr(
        chunks, "status", "insufficient_context" if payload.use_rag and not chunks else "relevant"
    )
    retrieval_method = getattr(chunks, "method", "hybrid")
    retrieval_thresh = getattr(chunks, "threshold", threshold)

    retrieval_meta = RetrievalInfo(
        top_score=top_score,
        threshold=retrieval_thresh,
        n_chunks=len(chunks),
        status=retrieval_status,
        method=retrieval_method,
    )

    # 9. Audit Logging (Compliant with Section 4)
    audit({
        "request_id": request_id,
        "user_id": f"user-{payload.role}",
        "user_role": payload.role,
        "role_check": "allowed",
        "pii_count": pii_count,
        "prompt_safety": prompt_safety_code,
        "rag_chunks": len(chunks),
        "llm_status": llm_status,
        "output_filter": "passed" if not output_violations else "violations_found",
        "final_status": "200_ok",
        "event": "answer_generated",
        "rag_enabled": payload.use_rag,
        "source_type": source_type,
        "retrieved_chunks": len(chunks),
        "pii_masked": pii_count > 0,
        "output_filtered": bool(output_violations),
        "model": model,
    })

    return AskResponse(
        answer=final_answer,
        source_type=source_type,
        citations=citations,
        retrieval=retrieval_meta,
        warnings=warnings,
        trust_metadata={
            "request_id": request_id,
            "role": payload.role,
            "pii_count": pii_count,
            "safety_risk": safety_eval.get("risk_level", "none"),
            "output_action": filter_result.get("action", "pass"),
        },
    )


# ============================================================================
# TRUST LAYER SECURITY DEMO ENDPOINTS (PHẦN 5)
# ============================================================================

@app.post("/mask-test", response_model=MaskTestResponse)
def mask_test_endpoint(payload: MaskTestRequest):
    """Test PII detection and masking on raw input."""
    mask_res = mask_pii(payload.text)
    return MaskTestResponse(
        original=payload.text,
        masked=mask_res.masked,
        notes=mask_res.notes,
        pii_count=mask_res.pii_count,
        pii_types=list(mask_res.stats.keys()),
        mapping=mask_res.pii_mapping,
    )


@app.post("/demask-test", response_model=DemaskResponse)
def demask_test_endpoint(payload: DemaskRequest):
    """Test demasking placeholders using provided mapping."""
    demasked = demask_pii(payload.text, payload.mapping)
    return DemaskResponse(demasked=demasked)


@app.post("/check-role", response_model=RoleCheckResponse)
def check_role_endpoint(payload: RoleCheckRequest):
    """Test Role Checking & Access Control."""
    res = evaluate_role_access(payload.role, payload.action)
    return RoleCheckResponse(
        allowed=res["allowed"],
        role=res["role"],
        action=res["action"],
        message=res["message"],
    )


@app.post("/check-prompt-safety", response_model=PromptSafetyResponse)
def check_prompt_safety_endpoint(payload: PromptSafetyRequest):
    """Test Prompt Safety and Injection detection."""
    res = check_prompt_safety(payload.prompt)
    return PromptSafetyResponse(
        is_safe=res["is_safe"],
        risk_level=res["risk_level"],
        reason=res["reason"],
        action=res["action"],
        matched_categories=res.get("matched_categories", []),
    )


@app.post("/check-output", response_model=OutputFilterResponse)
def check_output_endpoint(payload: OutputFilterRequest):
    """Test Output Filtering and Content Policy enforcement."""
    filtered, res = check_output(payload.text, context_sources=payload.context_sources)
    return OutputFilterResponse(
        is_safe=res["is_safe"],
        violations=res["violations"],
        action=res["action"],
        original=payload.text,
        filtered=filtered,
    )


@app.get("/admin/stats")
def admin_stats_endpoint(role: str = Query(..., description="Role to test authorization")):
    """Protected Admin-only resource to test Role-based Access Control (T1 & T2)."""
    try:
        require_admin(role)
    except PermissionError as exc:
        audit({
            "event": "admin_access_denied",
            "role": role,
            "resource": "/admin/stats",
            "status": "403_forbidden",
        })
        raise HTTPException(status_code=403, detail=str(exc))

    audit({
        "event": "admin_access_granted",
        "role": role,
        "resource": "/admin/stats",
        "status": "200_ok",
    })
    return {
        "status": "success",
        "role": role,
        "message": "Truy cập tài nguyên quản trị viên thành công (Access Granted).",
        "system_status": {
            "trust_layer_active": True,
            "kb_chunks": count_kb_chunks(),
            "rbac_policy": "enforced",
        },
    }


@app.get("/audit")
def get_audit(limit: int = 50):
    """Retrieve audit log entries (recent first)."""
    if not LOG_PATH.exists():
        return {"logs": [], "total": 0}
    lines = LOG_PATH.read_text(encoding="utf-8").strip().splitlines()
    logs = []
    for line in reversed(lines):
        if line.strip():
            try:
                logs.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        if len(logs) >= limit:
            break
    return {"logs": logs, "total": len(lines)}
