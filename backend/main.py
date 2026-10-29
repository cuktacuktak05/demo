from datetime import datetime, timezone
import json
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from .schemas import AskRequest, AskResponse, SourceItem, MaskTestRequest, MaskTestResponse
from .trust import mask_pii, check_role, check_output
from .rag import retrieve
from .llm import generate_answer
from dotenv import load_dotenv

load_dotenv()
app = FastAPI(
    title="Enterprise GenAI Assistant API",
    version="0.1.0",
    description="Educational demo: RAG + Trust Layer inspired by the cited research paper."
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

@app.get("/health")
def health():
    return {"status": "ok", "service": "enterprise-genai-demo"}

@app.post("/ask", response_model=AskResponse)
def ask(payload: AskRequest):
    try:
        check_role(payload.role)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    safe_question, safety_notes = mask_pii(payload.question)
    chunks = retrieve(safe_question, top_k=3) if payload.use_rag else []
    try:
        answer, model = generate_answer(safe_question, chunks, payload.role)
    except Exception as exc:
        audit({"event": "generation_error", "role": payload.role, "error_type": type(exc).__name__})
        message = str(exc)
        # Keep configuration/network errors understandable without exposing secrets.
        raise HTTPException(status_code=502, detail=message if "OPENAI_API_KEY" in message or "OPENAI_MODEL" in message else "Không gọi được mô hình API. Kiểm tra kết nối, model và API key trong .env.")
    answer, output_notes = check_output(answer)
    safety_notes.extend(output_notes)
    audit({
        "event": "answer_generated",
        "role": payload.role,
        "rag_enabled": payload.use_rag,
        "retrieved_chunks": len(chunks),
        "pii_masked": any("che " in n for n in safety_notes),
        "output_filtered": bool(output_notes),
        "model": model,
    })
    return AskResponse(
        answer=answer,
        sources=[SourceItem(source=c["source"], excerpt=c["text"][:500]) for c in chunks],
        masked_input=safe_question,
        safety_notes=safety_notes,
        model=model,
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
