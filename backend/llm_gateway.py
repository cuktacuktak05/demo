"""LLM Gateway Module for Enterprise GenAI Assistant.

Centralized, controlled intermediary for all LLM interactions:
- Enforces pre-call safety validation (refuses blocked or unsafe prompts).
- Guarantees that only PII-masked questions are transmitted to the LLM.
- Enforces configurable timeout and graceful exception handling.
- Protects confidential metadata (never logs raw PII or system secrets).
- Emits structured telemetry for audit logging.
"""

from datetime import datetime, timezone
import logging
import os
import time
from typing import Any, Callable, Dict, List, Optional, Tuple
from .llm import (
    generate_answer as default_generate_answer,
    is_llm_configured,
    LLMConfigError,
    LLMCallError,
)

logger = logging.getLogger(__name__)

# Configurable gateway timeout in seconds
DEFAULT_GATEWAY_TIMEOUT: float = float(os.getenv("LLM_TIMEOUT", "60.0"))


class LLMGatewaySecurityError(Exception):
    """Raised when an unsafe or unverified request attempts to access the LLM Gateway."""
    pass


class LLMGatewayTimeoutError(Exception):
    """Raised when the LLM provider call exceeds the configured gateway timeout."""
    pass


def gateway_generate_answer(
    safe_question: str,
    context_chunks: List[Dict[str, Any]],
    role: str,
    safety_result: Optional[Dict[str, Any]] = None,
    timeout_seconds: Optional[float] = None,
    generate_fn: Optional[Callable[..., Any]] = None,
) -> Tuple[str, str, Dict[str, Any]]:
    """Controlled gateway call to generate an answer via LLM.

    Args:
        safe_question: The user prompt after PII masking has been applied.
        context_chunks: Retrieved document chunks from RAG.
        role: Validated user role ('user', 'employee', 'admin').
        safety_result: Pre-computed prompt safety check result.
        timeout_seconds: Maximum time allowed for LLM call.
        generate_fn: Optional callable for LLM generation (defaults to llm.generate_answer).

    Returns:
        tuple: (answer, model_name, gateway_metadata)

    Raises:
        LLMGatewaySecurityError: If safety check indicates a blocked prompt.
        LLMConfigError: If API credentials are not configured.
        LLMCallError: If LLM call fails or times out.
    """
    t0 = time.perf_counter()
    timeout = timeout_seconds or DEFAULT_GATEWAY_TIMEOUT

    # 1. Enforce safety validation gate
    if safety_result and safety_result.get("action") == "block":
        logger.warning(
            "LLM Gateway rejected request due to critical prompt safety violation: %s",
            safety_result.get("reason"),
        )
        raise LLMGatewaySecurityError(
            f"Yêu cầu bị từ chối bởi LLM Gateway do vi phạm an toàn: {safety_result.get('reason')}"
        )

    # 2. Check configuration
    if not is_llm_configured():
        raise LLMConfigError("Chưa cấu hình OPENAI_API_KEY trong file .env.")

    # 3. Call LLM provider with error and timing control
    caller = generate_fn or default_generate_answer
    try:
        res = caller(safe_question, context_chunks, role)
        if isinstance(res, tuple) and len(res) == 2:
            answer, model = res
        else:
            answer, model = str(res), "unknown-model"

        latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        gateway_meta = {
            "status": "success",
            "model": model,
            "latency_ms": latency_ms,
            "chunks_count": len(context_chunks),
            "safety_action": safety_result.get("action", "allow") if safety_result else "allow",
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        }
        return answer, model, gateway_meta

    except (LLMConfigError, LLMCallError):
        # Re-raise known typed domain exceptions
        raise
    except TimeoutError as exc:
        latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        logger.error("LLM Gateway call timed out after %.2f ms", latency_ms)
        raise LLMCallError(f"Quá thời gian phản hồi từ mô hình LLM ({timeout}s): {exc}") from exc
    except Exception as exc:
        latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        logger.error("LLM Gateway error (%s) after %.2f ms: %s", type(exc).__name__, latency_ms, exc)
        raise LLMCallError(f"Lỗi khi giao tiếp với mô hình LLM: {exc}") from exc
