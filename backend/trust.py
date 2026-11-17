"""Trust Layer for Enterprise GenAI Assistant — Session 2.

Comprehensive Security, Safety, and Privacy Pipeline:
1. Role-Based Access Control (RBAC): Identification and authorization (user, employee, admin).
2. PII Detection & Masking: Detects and redacts Email, Vietnamese Phone numbers, CCCD (12 digits), CMND (9 digits)
   with placeholder mapping for demasking.
3. Prompt Safety: Multi-layer pattern and heuristic detection for Prompt Injection, System Prompt extraction/bypass,
   unauthorized access, and safety violations.
4. Output Filtering: Rule-based verification for harmful content, policy violations, sensitive data leaks,
   and ungrounded legal information.
5. Demasking: Restores masked entities to their original form safely when requested.

Limitations acknowledged:
- PII detection uses optimized regular expressions and contextual patterns rather than a specialized NER model.
- Prompt safety uses multi-layer heuristic and pattern analysis rather than an external fine-tuned safety classifier.
- Output filtering uses deterministic rule-based policies. Toxicity or sentiment ML models are not included in this demo.
"""

from datetime import datetime, timezone
import json
import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

# ============================================================================
# 1. ROLE CHECKING & ACCESS CONTROL
# ============================================================================

VALID_ROLES: Set[str] = {"user", "employee", "admin"}

ROLE_PERMISSIONS: Dict[str, Set[str]] = {
    "user": {"access", "query", "ask", "mask_test"},
    "employee": {"access", "query", "ask", "mask_test"},
    "admin": {
        "access",
        "query",
        "ask",
        "mask_test",
        "admin_panel",
        "view_audit",
        "manage_system",
        "system_stats",
        "view_all_history",
        "delete_data",
    },
}


def check_role(role: str) -> None:
    """Validate that *role* is an accepted user role.

    Supports: 'user', 'employee' (standard user alias), and 'admin'.
    Raises PermissionError (which maps to HTTP 403) if role is missing or invalid.
    """
    if not role or not isinstance(role, str):
        raise PermissionError("Vai trò không hợp lệ: thiếu thông tin định danh vai trò.")
    cleaned_role = role.strip().lower()
    if cleaned_role not in VALID_ROLES:
        raise PermissionError(
            f"Vai trò '{role}' không được cấp quyền truy cập. "
            f"Hệ thống chỉ hỗ trợ: {', '.join(sorted(VALID_ROLES))}."
        )


def evaluate_role_access(role: str, action: str = "access") -> Dict[str, Any]:
    """Evaluate whether a given role is authorized to perform a protected action.

    Returns:
        dict: {"allowed": bool, "role": str, "action": str, "message": str}
    """
    try:
        check_role(role)
    except PermissionError as exc:
        return {
            "allowed": False,
            "role": role,
            "action": action,
            "message": f"Từ chối truy cập: {str(exc)}",
        }

    cleaned_role = role.strip().lower()
    allowed_actions = ROLE_PERMISSIONS.get(cleaned_role, set())

    if cleaned_role == "admin" or action in allowed_actions:
        return {
            "allowed": True,
            "role": cleaned_role,
            "action": action,
            "message": f"Quyền truy cập hợp lệ cho vai trò '{cleaned_role}'.",
        }

    return {
        "allowed": False,
        "role": cleaned_role,
        "action": action,
        "message": (
            f"Từ chối truy cập: Vai trò '{cleaned_role}' không có quyền thực hiện thao tác '{action}' "
            f"(yêu cầu quyền quản trị viên)."
        ),
    }


def require_admin(role: str) -> None:
    """Enforce admin-only access control.

    Raises PermissionError if role is not 'admin'.
    """
    check_role(role)
    if role.strip().lower() != "admin":
        raise PermissionError(
            "Chức năng này yêu cầu quyền quản trị viên (admin). Người dùng hiện tại không đủ quyền."
        )


# ============================================================================
# 2. PII DETECTION & MASKING
# ============================================================================

# Order is strictly planned:
# 1. Email (contains letters and possible digits)
# 2. CCCD 12 digits (checked before phone and CMND so 12-digit number is never split)
# 3. Vietnamese Phone numbers (starts with 0 or +84, 10 or 11 digits)
# 4. CMND 9 digits (checked after phone to avoid matching phone prefixes/suffixes)

_EMAIL_RE = re.compile(
    r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b", re.IGNORECASE
)

_CCCD_RE = re.compile(r"(?<!\d)\d{12}(?!\d)")

_PHONE_RE = re.compile(
    r"(?<!\d)"
    r"(?:\+84|0)"
    r"(?:(?:3[2-9]|5[25689]|7[06-9]|8[1-9]|9\d)(?:[\s.\-]?\d){7}|2\d{1,2}(?:[\s.\-]?\d){7,8})"
    r"(?!\d)"
)

# CMND: exactly 9 digits, not followed by common currency markers (đồng, vnd, vnđ)
_CMND_RE = re.compile(
    r"(?<!\d)\d{9}(?!\d)(?!\s*(?:đồng|vnd|vnđ|đ\b|k\b|triệu|tỷ))", re.IGNORECASE
)

_PII_PATTERNS: List[Tuple[re.Pattern, str, str]] = [
    (_EMAIL_RE, "EMAIL", "email"),
    (_CCCD_RE, "CCCD", "CCCD (12 số)"),
    (_PHONE_RE, "PHONE", "số điện thoại"),
    (_CMND_RE, "CMND", "CMND (9 số)"),
]


class MaskResult(tuple):
    """Tuple subclass (masked_text, notes, pii_mapping) with helper attributes."""

    def __new__(
        cls,
        masked: str,
        notes: List[str],
        pii_mapping: Dict[str, str],
        stats: Optional[Dict[str, int]] = None,
    ):
        obj = super().__new__(cls, (masked, notes, pii_mapping))
        obj.masked = masked
        obj.notes = notes
        obj.pii_mapping = pii_mapping
        obj.stats = stats or {}
        obj.pii_count = len(pii_mapping)
        return obj


def mask_pii(text: str) -> MaskResult:
    """Detect and mask PII in text with indexed placeholders.

    Supports:
    - Email addresses -> [EMAIL_1], [EMAIL_2], ...
    - Vietnamese phone numbers -> [PHONE_1], [PHONE_2], ...
    - CCCD 12-digit identification -> [CCCD_1], [CCCD_2], ...
    - CMND 9-digit identification -> [CMND_1], [CMND_2], ...

    Returns:
        MaskResult (3-tuple): (masked_text, notes, pii_mapping)
    """
    masked = text
    notes: List[str] = []
    pii_mapping: Dict[str, str] = {}
    stats: Dict[str, int] = {}

    for pattern, tag, vi_label in _PII_PATTERNS:
        counter = 0

        def _replacer(m: re.Match, _tag=tag) -> str:
            nonlocal counter
            counter += 1
            placeholder = f"[{_tag}_{counter}]"
            pii_mapping[placeholder] = m.group(0)
            return placeholder

        masked, n = pattern.subn(_replacer, masked)
        if n > 0:
            stats[tag] = n
            notes.append(f"Đã che {n} trường {vi_label} ({tag}).")

    return MaskResult(masked, notes, pii_mapping, stats)


# ============================================================================
# 3. DEMASKING
# ============================================================================

def demask_pii(text: str, pii_mapping: Dict[str, str]) -> str:
    """Restore PII placeholders to their original values when verified safe.

    Parameters:
        text (str): Output text containing placeholders like [EMAIL_1], [PHONE_1].
        pii_mapping (dict): Mapping from placeholder to original value.

    Returns:
        str: Demasked text.
    """
    if not pii_mapping or not text:
        return text

    result = text
    for placeholder, original in pii_mapping.items():
        result = result.replace(placeholder, original)
    return result


# ============================================================================
# 4. PROMPT SAFETY & INJECTION DETECTION
# ============================================================================

_INJECTION_PATTERNS: List[Tuple[re.Pattern, int, str]] = [
    # Direct instruction override
    (re.compile(r"ignore\s+(all\s+)?(previous|above|prior)\s+(instructions?|rules?|prompts?)", re.I), 50, "prompt_injection_override"),
    (re.compile(r"bỏ\s+qua\s+(tất\s+cả\s+)?(hướng\s+dẫn|quy\s+tắc|chỉ\s+dẫn|lệnh|prompt)", re.I), 50, "prompt_injection_override_vi"),
    (re.compile(r"hãy\s+quên\s+(tất\s+cả|mọi)\s+(quy\s+tắc|hướng\s+dẫn|lệnh|chỉ\s+dẫn)", re.I), 50, "prompt_injection_forget_vi"),
    (re.compile(r"forget\s+(all\s+)?(your\s+)?(instructions?|rules?|guidelines?|prompts?)", re.I), 50, "prompt_injection_forget"),
    (re.compile(r"disregard\s+(all\s+)?(previous|prior|system)\s+(instructions?|rules?)", re.I), 50, "prompt_injection_disregard"),

    # Jailbreak / Roleplay mode
    (re.compile(r"you\s+are\s+now\s+(DAN|evil|unrestricted|jailbroken|unfiltered)", re.I), 60, "jailbreak_role_switch"),
    (re.compile(r"từ\s+giờ\s+bạn\s+là\s+(DAN|evil|không\s+giới\s+hạn|hacker)", re.I), 60, "jailbreak_role_switch_vi"),
    (re.compile(r"(act|pretend|behave)\s+(as|like)\s+(if\s+)?(you\s+)?(have\s+)?no\s+(rules?|restrictions?|limits?|filters?)", re.I), 50, "jailbreak_unrestricted"),
    (re.compile(r"(DAN|Do\s+Anything\s+Now)\s+mode", re.I), 60, "jailbreak_dan"),
    (re.compile(r"developer\s+mode\s+(enabled|on|activated)", re.I), 50, "jailbreak_dev_mode"),
    (re.compile(r"đóng\s+vai\s+(một\s+)?(hacker|kẻ\s+tấn\s+công|ai\s+không\s+quy\s+tắc)", re.I), 50, "jailbreak_roleplay_vi"),

    # System prompt extraction & leakage attempts
    (re.compile(r"(show|reveal|display|print|output|repeat|echo|tell\s+me)\s+(the\s+|your\s+)?(system\s+prompt|hidden\s+prompt|initial\s+instructions?|system\s+message)", re.I), 55, "system_prompt_extraction"),
    (re.compile(r"(hiển\s+thị|cho\s+xem|cho\s+tôi\s+biết|tiết\s+lộ|in\s+ra|xuất)\s+(system\s+prompt|prompt\s+hệ\s+thống|lệnh\s+hệ\s+thống|hướng\s+dẫn\s+ẩn)", re.I), 55, "system_prompt_extraction_vi"),
    (re.compile(r"what\s+(is|are)\s+(your|the)\s+(system\s+prompt|initial\s+instructions?|hidden\s+instructions?)", re.I), 45, "system_prompt_query"),
    (re.compile(r"nội\s+dung\s+(prompt|lệnh|chỉ\s+dẫn)\s+hệ\s+thống\s+(là\s+gì|của\s+bạn)", re.I), 45, "system_prompt_query_vi"),
    (re.compile(r"repeat\s+the\s+words\s+above", re.I), 40, "prompt_leakage_echo"),

    # Security rule bypass & filter disabling
    (re.compile(r"bypass\s+(the\s+)?(security|safety|filter|restriction|guard|trust\s+layer)", re.I), 50, "security_bypass"),
    (re.compile(r"(vượt|bỏ)\s+qua\s+(bảo\s+mật|bộ\s+lọc|lớp\s+tin\s+cậy|trust\s+layer|hệ\s+thống\s+an\s+toàn)", re.I), 50, "security_bypass_vi"),
    (re.compile(r"turn\s+off\s+(the\s+)?(safety|security|filter|content\s+filter)", re.I), 50, "security_disable"),
    (re.compile(r"(tắt|vô\s+hiệu\s+hóa)\s+(bảo\s+mật|bộ\s+lọc|an\s+toàn|trust\s+layer|kiểm\s+duyệt)", re.I), 50, "security_disable_vi"),

    # Unauthorized data access & database exfiltration
    (re.compile(r"(access|read|show|dump|export)\s+(the\s+)?(database|all\s+users?|admin\s+panel|server\s+config|api\s+keys?|credentials?|passwords?)", re.I), 45, "unauthorized_data_access"),
    (re.compile(r"(truy\s+cập|đọc|hiển\s+thị|xuất|xem)\s+(cơ\s+sở\s+dữ\s+liệu|tất\s+cả\s+người\s+dùng|cấu\s+hình\s+máy\s+chủ|khóa\s+API|mật\s+khẩu|dữ\s+liệu\s+mật)", re.I), 45, "unauthorized_data_access_vi"),
    (re.compile(r"(đọc|xem|tải)\s+file\s+(\.env|config|secrets)", re.I), 50, "sensitive_file_access"),

    # Structural prompt markers
    (re.compile(r"\[SYSTEM\]|\[INST\]|<<SYS>>|</s>|<\|im_start\|>|<\|im_end\|>", re.I), 40, "structural_injection_markers"),
    (re.compile(r"###\s*(System|Human|Assistant|Instruction)\s*:", re.I), 35, "structural_role_markers"),
]

_SUSPICIOUS_PATTERNS: List[Tuple[re.Pattern, int, str]] = [
    (re.compile(r"(API|api)\s*key", re.I), 15, "api_key_mention"),
    (re.compile(r"(khóa|chìa\s+khóa)\s*API", re.I), 15, "api_key_mention_vi"),
    (re.compile(r"(secret|token|password|credential)\s*(is|:)", re.I), 20, "credential_probe"),
    (re.compile(r"(simulate|emulate|pretend)\s+(an?\s+)?(attack|hack|exploit|injection)", re.I), 25, "attack_simulation"),
    (re.compile(r"(giả\s+lập|mô\s+phỏng)\s+(tấn\s+công|hack|khai\s+thác)", re.I), 25, "attack_simulation_vi"),
]


def check_prompt_safety(prompt: str) -> Dict[str, Any]:
    """Evaluate prompt safety using a multi-layered detection matrix.

    Returns:
        dict: {
            "is_safe": bool,
            "risk_level": "none" | "low" | "medium" | "high" | "critical",
            "reason": str,
            "action": "allow" | "warn" | "block",
            "matched_categories": list[str]
        }
    """
    if not prompt or not prompt.strip():
        return {
            "is_safe": True,
            "risk_level": "none",
            "reason": "Prompt hợp lệ (rỗng).",
            "action": "allow",
            "matched_categories": [],
        }

    total_score = 0
    matched_categories: List[str] = []

    for pattern, weight, label in _INJECTION_PATTERNS:
        if pattern.search(prompt):
            total_score += weight
            matched_categories.append(label)

    for pattern, weight, label in _SUSPICIOUS_PATTERNS:
        if pattern.search(prompt):
            total_score += weight
            matched_categories.append(label)

    if total_score >= 45:
        risk_level = "critical" if total_score >= 70 else "high"
        action = "block"
        is_safe = False
    elif total_score >= 25:
        risk_level = "medium"
        action = "warn"
        is_safe = False
    elif total_score > 0:
        risk_level = "low"
        action = "allow"
        is_safe = True
    else:
        risk_level = "none"
        action = "allow"
        is_safe = True

    if matched_categories:
        reason_text = (
            f"Phát hiện {len(matched_categories)} dấu hiệu rủi ro: {', '.join(matched_categories)}. "
            f"Điểm rủi ro an toàn: {total_score}."
        )
    else:
        reason_text = "Prompt an toàn, không phát hiện dấu hiệu can thiệp bất thường."

    return {
        "is_safe": is_safe,
        "risk_level": risk_level,
        "reason": reason_text,
        "action": action,
        "matched_categories": matched_categories,
    }


# ============================================================================
# 5. OUTPUT FILTERING
# ============================================================================

_HARMFUL_OUTPUT_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"(kill\s+yourself|tự\s+tử|tự\s+sát|kết\s+thúc\s+cuộc\s+sống)", re.I), "Nội dung khuyến khích tự hại / tự sát."),
    (re.compile(r"(build\s+a\s+bomb|make\s+a\s+weapon|chế\s+tạo\s+bom|chế\s+tạo\s+vũ\s+khí|thuốc\s+nổ)", re.I), "Nội dung chế tạo vũ khí hoặc vật liệu nổ nguy hiểm."),
    (re.compile(r"(how\s+to\s+hack|cách\s+hack|hướng\s+dẫn\s+tấn\s+công\s+mạng|viết\s+mã\s+độc|trojan|ransomware)", re.I), "Nội dung liên quan đến mã độc và tấn công mạng."),
]

_SENSITIVE_LEAK_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"sk-[A-Za-z0-9_-]{20,}", re.I), "Rò rỉ OpenAI API key."),
    (re.compile(r"(OPENAI_API_KEY|API_KEY|SECRET_KEY)\s*[:=]", re.I), "Rò rỉ biến môi trường hoặc khóa bí mật."),
    (re.compile(r"LEGAL_REASONING_INSTRUCTIONS", re.I), "Rò rỉ chỉ dẫn nội bộ của System Prompt."),
    (re.compile(r"Step\s+[1-6]\s*-\s*(Identify\s+the\s+Legal|Retrieve\s+Legal|Verify\s+Legal|Analyze\s+Legal|Evaluate\s+Evidence|Formulate\s+the\s+Answer)", re.I), "Rò rỉ quy trình suy luận ẩn của hệ thống."),
]


def check_output(
    text: str, context_sources: Optional[List[str]] = None
) -> Tuple[str, Dict[str, Any]]:
    """Verify LLM output before delivering to frontend.

    Detects:
    1. Harmful content (self-harm, weapons, cyber attacks)
    2. Policy violations and sensitive secrets leaks (API keys, System Prompts)
    3. Empty response handling

    Returns:
        tuple: (filtered_text, filter_result_dict)
    """
    violations: List[str] = []
    is_safe = True
    action = "pass"
    filtered = text

    # Check empty
    if not text or not text.strip():
        violations.append("Mô hình trả về nội dung rỗng.")
        safe_fallback = "Chưa tạo được câu trả lời. Hãy thử diễn đạt lại câu hỏi."
        return (
            safe_fallback,
            {
                "is_safe": False,
                "violations": violations,
                "action": "replace",
                "filtered_response": safe_fallback,
            },
        )

    # Check harmful content
    for pattern, reason in _HARMFUL_OUTPUT_PATTERNS:
        if pattern.search(text):
            violations.append(reason)
            is_safe = False

    # Check sensitive data leakage
    for pattern, reason in _SENSITIVE_LEAK_PATTERNS:
        if pattern.search(text):
            violations.append(reason)
            is_safe = False

    if not is_safe:
        action = "block"
        filtered = (
            "Nội dung phản hồi vi phạm chính sách an toàn của Trust Layer và đã bị chặn. "
            "Vui lòng đặt câu hỏi an toàn và phù hợp với quy chuẩn pháp lý."
        )

    return filtered, {
        "is_safe": is_safe,
        "violations": violations,
        "action": action,
        "filtered_response": filtered,
    }
