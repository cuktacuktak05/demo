from datetime import datetime, timezone
import json
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from .schemas import (
    AskRequest,
    AskResponse,
    CitationItem,
    RetrievalInfo,
    HealthResponse,
    ErrorResponse,
    MaskTestRequest,
    MaskTestResponse,
)
from .trust import mask_pii, check_role, check_output
from .rag import retrieve, get_min_score, count_kb_chunks
from .llm import (
    generate_answer,
    is_llm_configured,
    is_general_knowledge_allowed,
    LLMConfigError,
    LLMCallError,
)
from dotenv import load_dotenv

load_dotenv()
app = FastAPI(
    title="Enterprise GenAI Assistant API",
    version="0.1.0",
    description="Educational demo: RAG + Trust Layer inspired by the cited research paper.",
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
    # Do not log raw prompts or generated answers; log minimal metadata only.
    event["timestamp_utc"] = datetime.now(timezone.utc).isoformat()
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


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


@app.post(
    "/ask",
    response_model=AskResponse,
    responses={
        503: {
            "model": ErrorResponse,
            "description": "LLM service unavailable or unconfigured",
        }
    },
)
def ask(payload: AskRequest):
    try:
        check_role(payload.role)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))

    if not is_llm_configured():
        audit({"event": "llm_config_error", "role": payload.role})
        return JSONResponse(
            status_code=503,
            content={
                "error_code": "LLM_NOT_CONFIGURED",
                "message": "Chưa cấu hình OPENAI_API_KEY trong file .env.",
            },
        )

    safe_question, safety_notes = mask_pii(payload.question)
    chunks = retrieve(safe_question, top_k=3) if payload.use_rag else []
    threshold = get_min_score()

    try:
        answer, model = generate_answer(safe_question, chunks, payload.role)
    except LLMConfigError as exc:
        audit({"event": "llm_config_error", "role": payload.role, "error": str(exc)})
        return JSONResponse(
            status_code=503,
            content={"error_code": "LLM_NOT_CONFIGURED", "message": str(exc)},
        )
    except Exception as exc:
        audit({"event": "generation_error", "role": payload.role, "error_type": type(exc).__name__})
        return JSONResponse(
            status_code=503,
            content={"error_code": "LLM_ERROR", "message": f"Không gọi được mô hình LLM: {exc}"},
        )

    answer, output_notes = check_output(answer)
    warnings = list(safety_notes) + list(output_notes)

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

    audit({
        "event": "answer_generated",
        "role": payload.role,
        "rag_enabled": payload.use_rag,
        "source_type": source_type,
        "retrieved_chunks": len(chunks),
        "pii_masked": any("che " in n for n in safety_notes),
        "output_filtered": bool(output_notes),
        "model": model,
    })

    return AskResponse(
        answer=answer,
        source_type=source_type,
        citations=citations,
        retrieval=retrieval_meta,
        warnings=warnings,
    )


@app.post("/mask-test", response_model=MaskTestResponse)
def mask_test(payload: MaskTestRequest):
    masked, notes = mask_pii(payload.text)
    return MaskTestResponse(original=payload.text, masked=masked, notes=notes)


@app.get("/audit")
def get_audit(limit: int = 50):
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
