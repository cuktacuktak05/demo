"""Small educational Trust Layer; not a production security boundary."""
import re
from typing import Any

# Demonstration patterns only. Real systems should use a vetted PII detector/DLP.
PII_PATTERNS = [
    (re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I), "[EMAIL_REDACTED]"),
    (re.compile(r"\b(?:\+?84|0)(?:\s|-)?(?:\d[\s-]?){8,10}\b"), "[PHONE_REDACTED]"),
    (re.compile(r"\b\d{12}\b"), "[ID_NUMBER_REDACTED]"),
]

def mask_pii(text: str) -> tuple[str, list[str]]:
    masked = text
    notes = []
    for pattern, replacement in PII_PATTERNS:
        masked, n = pattern.subn(replacement, masked)
        if n:
            notes.append(f"Đã che {n} trường có khả năng là dữ liệu cá nhân ({replacement}).")
    return masked, notes

def check_role(role: str) -> None:
    # Demo policy: only these two explicit roles are accepted.
    if role not in {"employee", "admin"}:
        raise PermissionError("Vai trò không hợp lệ.")

def check_output(text: str) -> tuple[str, list[str]]:
    notes = []
    # A lightweight demonstration check, not a comprehensive toxicity classifier.
    risky_phrases = ["kill yourself", "build a bomb", "make a weapon"]
    if any(p in text.lower() for p in risky_phrases):
        notes.append("Đầu ra bị chặn bởi bộ lọc quy tắc demo.")
        return ("Tôi không thể cung cấp nội dung nguy hiểm. Hãy đặt câu hỏi an toàn hơn.", notes)
    if not text.strip():
        notes.append("Mô hình trả về nội dung rỗng.")
        return ("Chưa tạo được câu trả lời. Hãy thử diễn đạt lại câu hỏi.", notes)
    return text, notes
