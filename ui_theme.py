"""Giao diện cho Enterprise GenAI Assistant: CSS + các hàm dựng HTML.

Module này KHÔNG import streamlit để có thể kiểm thử độc lập. Mọi nội dung đến từ
người dùng / mô hình / tài liệu đều được escape trước khi chèn vào HTML.

Lưu ý khi sửa:
- Mỗi đoạn HTML trả về là MỘT dòng, bắt đầu bằng thẻ khối (div/ol/ul...). Markdown của
  Streamlit sẽ coi dòng đó là một khối HTML thô; nếu có dòng trống hoặc thụt đầu dòng
  >= 4 khoảng trắng bên trong, phần sau sẽ bị hiểu nhầm là markdown / code block.
- Điểm nhấn thiết kế là "thanh che" màu hổ phách (class gx-redact và logo): hình ảnh của
  việc che dữ liệu nhạy cảm, đúng với vai trò của Trust Layer.
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass, field

# --------------------------------------------------------------------------------------
# CSS
# --------------------------------------------------------------------------------------
CSS = """
@import url('https://fonts.googleapis.com/css2?family=Be+Vietnam+Pro:wght@400;500;600;700&display=swap');

:root {
  --gx-ink: #16243A;
  --gx-paper: #F2F5F7;
  --gx-surface: #FFFFFF;
  --gx-tint: #E7EDF2;
  --gx-line: #D9E1E8;
  --gx-line-strong: #C3CFDA;
  --gx-muted: #566879;
  --gx-body: #2C3E52;
  --gx-teal: #0F766E;
  --gx-teal-dark: #0B5F59;
  --gx-teal-soft: #E0F1EE;
  --gx-amber: #F5B83D;
  --gx-amber-soft: #FDF0D0;
  --gx-danger: #B42318;
  --gx-danger-soft: #FCE9E7;
  --gx-font: 'Be Vietnam Pro', 'Segoe UI', system-ui, -apple-system, Roboto, 'Helvetica Neue', Arial, sans-serif;
}

/* ---------- Nền tảng ---------- */
html, body, .stApp {
  font-family: var(--gx-font);
}
.stApp {
  background: var(--gx-paper);
  color: var(--gx-ink);
}
.stApp p, .stApp li, .stApp label, .stApp input, .stApp textarea, .stApp button,
.stApp h1, .stApp h2, .stApp h3, .stApp h4 {
  font-family: var(--gx-font);
}
[data-testid="stHeader"] { background: transparent; }
[data-testid="stAppDeployButton"], .stDeployButton { display: none; }
footer { visibility: hidden; height: 0; }

[data-testid="stMainBlockContainer"], .block-container {
  max-width: 1180px;
  padding: 2.4rem 2.6rem 3rem;
}

/* ---------- Đầu trang ---------- */
.stApp .gx-hero {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin: 0 0 .4rem;
}
/* Logo: ba dòng chữ, dòng giữa bị "che" bằng thanh hổ phách */
.gx-mark {
  flex: none;
  width: 46px;
  height: 46px;
  border-radius: 12px;
  background:
    linear-gradient(#FFFFFF, #FFFFFF) 11px 12px / 24px 5px no-repeat,
    linear-gradient(var(--gx-amber), var(--gx-amber)) 11px 21px / 19px 5px no-repeat,
    linear-gradient(#FFFFFF, #FFFFFF) 11px 30px / 12px 5px no-repeat,
    var(--gx-ink);
}
.stApp .gx-hero h1 {
  margin: 0;
  padding: 0;
  font-size: 1.75rem;
  line-height: 1.15;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--gx-ink);
}
.stApp .gx-hero p {
  margin: .3rem 0 0;
  max-width: 64ch;
  font-size: .95rem;
  line-height: 1.55;
  color: var(--gx-muted);
}

/* ---------- Thẻ nội dung (dùng st.container(key=...)) ---------- */
.st-key-ask_card,
.st-key-answer_card,
.st-key-sources_card {
  background: var(--gx-surface);
  border: 1px solid var(--gx-line);
  border-radius: 16px;
  padding: 1.3rem 1.5rem 1.4rem;
  gap: .9rem;
}
.st-key-trace_panel {
  background: var(--gx-tint);
  border-radius: 20px;
  padding: 1.4rem 1.4rem 1.5rem;
}
.st-key-ask_card [data-testid="stWidgetLabel"] p {
  font-size: .9rem;
  font-weight: 600;
  color: var(--gx-ink);
}

/* Tiêu đề trong thẻ */
.stApp .gx-h2 {
  margin: 0;
  padding: 0;
  font-size: 1.06rem;
  line-height: 1.35;
  font-weight: 600;
  letter-spacing: -0.005em;
  color: var(--gx-ink);
}
.stApp .gx-h3 {
  margin: 0 0 .5rem;
  padding: 0;
  font-size: .9rem;
  line-height: 1.4;
  font-weight: 600;
  color: var(--gx-ink);
}
.gx-count { font-weight: 500; color: var(--gx-muted); }

/* ---------- Ô nhập câu hỏi ---------- */
.st-key-ask_card [data-baseweb="textarea"],
.st-key-ask_card [data-baseweb="base-input"] {
  background: var(--gx-surface);
  border-radius: 10px;
}
.st-key-ask_card [data-baseweb="textarea"] {
  border: 1px solid var(--gx-line-strong);
}
.st-key-ask_card [data-baseweb="textarea"]:focus-within {
  border-color: var(--gx-teal);
  box-shadow: 0 0 0 3px rgba(15, 118, 110, .18);
}
.st-key-ask_card textarea {
  font-size: 1rem;
  line-height: 1.6;
  color: var(--gx-ink);
}
.st-key-ask_card textarea::placeholder { color: #7A8A9B; }

/* ---------- Nút ---------- */
.stApp [data-testid="stBaseButton-primary"],
.stApp button[kind="primary"] {
  background: var(--gx-teal);
  border: 1px solid var(--gx-teal);
  color: #FFFFFF;
  border-radius: 10px;
  min-height: 2.75rem;
  font-weight: 600;
  transition: background-color .15s ease, border-color .15s ease;
}
.stApp [data-testid="stBaseButton-primary"]:hover,
.stApp button[kind="primary"]:hover {
  background: var(--gx-teal-dark);
  border-color: var(--gx-teal-dark);
  color: #FFFFFF;
}
.stApp [data-testid="stBaseButton-primary"]:focus-visible,
.stApp button[kind="primary"]:focus-visible {
  outline: 3px solid rgba(15, 118, 110, .35);
  outline-offset: 2px;
}

/* Câu hỏi gợi ý: nút dạng viên thuốc, gọn */
.gx-suggest-label {
  margin: .1rem 0 0;
  font-size: .82rem;
  color: var(--gx-muted);
}
.st-key-suggest [data-testid="stBaseButton-secondary"],
.st-key-suggest button[kind="secondary"] {
  background: transparent;
  border: 1px solid var(--gx-line-strong);
  color: var(--gx-ink);
  border-radius: 999px;
  min-height: 2.1rem;
  padding: .2rem .8rem;
  font-size: .85rem;
  font-weight: 500;
  transition: background-color .15s ease, border-color .15s ease, color .15s ease;
}
.st-key-suggest [data-testid="stBaseButton-secondary"]:hover,
.st-key-suggest button[kind="secondary"]:hover {
  background: var(--gx-teal-soft);
  border-color: var(--gx-teal);
  color: var(--gx-teal-dark);
}
.st-key-suggest [data-testid="stBaseButton-secondary"]:focus-visible,
.st-key-suggest button[kind="secondary"]:focus-visible {
  outline: 3px solid rgba(15, 118, 110, .35);
  outline-offset: 2px;
}
.gx-api {
  margin: 0;
  padding-top: .7rem;
  font-size: .85rem;
  color: var(--gx-muted);
  overflow-wrap: anywhere;
}

/* ---------- Câu trả lời ---------- */
.st-key-answer_card [data-testid="stMarkdownContainer"] p,
.st-key-answer_card [data-testid="stMarkdownContainer"] li {
  font-size: 1rem;
  line-height: 1.75;
  color: var(--gx-body);
}
.st-key-answer_card [data-testid="stMarkdownContainer"] {
  max-width: 74ch;
}

/* ---------- Nguồn RAG ---------- */
.gx-sources {
  list-style: none;
  margin: .6rem 0 0;
  padding: 0;
  counter-reset: src;
}
.gx-src {
  counter-increment: src;
  padding: .95rem 0;
  border-top: 1px solid var(--gx-line);
}
.gx-src:first-child { border-top: 0; padding-top: .2rem; }
.gx-src:last-child { padding-bottom: 0; }
.gx-src-head {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: .15rem .55rem;
  margin-bottom: .35rem;
}
.gx-src-head::before {
  content: counter(src);
  min-width: 1.1em;
  font-size: .85rem;
  font-weight: 600;
  color: var(--gx-muted);
}
.gx-file { font-size: .9rem; font-weight: 600; color: var(--gx-ink); overflow-wrap: anywhere; }
.gx-chunk { font-size: .8rem; color: var(--gx-muted); }
.gx-src p {
  margin: 0;
  font-size: .92rem;
  line-height: 1.65;
  color: var(--gx-body);
}
.gx-none { margin: .5rem 0 0; font-size: .92rem; line-height: 1.6; color: var(--gx-muted); }

/* ---------- Chuỗi xử lý Trust Layer ---------- */
.gx-steps {
  list-style: none;
  margin: 1.05rem 0 1.4rem;
  padding: 0;
}
.gx-step {
  position: relative;
  display: grid;
  grid-template-columns: 20px 1fr;
  column-gap: .8rem;
  padding-bottom: 1.1rem;
}
.gx-step:last-child { padding-bottom: 0; }
.gx-step::before {            /* đường nối giữa các bước */
  content: "";
  position: absolute;
  left: 9px;
  top: 24px;
  bottom: 0;
  width: 2px;
  background: var(--gx-line-strong);
}
.gx-step:last-child::before { display: none; }
.gx-dot {
  position: relative;
  z-index: 1;
  box-sizing: border-box;
  width: 20px;
  height: 20px;
  margin-top: 1px;
  border-radius: 50%;
  border: 2px solid var(--gx-line-strong);
  background: var(--gx-tint);
}
.gx-step-top { display: flex; flex-wrap: wrap; align-items: center; gap: .3rem .6rem; }
.gx-step-title { font-size: .92rem; font-weight: 600; color: var(--gx-ink); }
.gx-step-detail {
  margin: .3rem 0 0;
  font-size: .85rem;
  line-height: 1.55;
  color: var(--gx-muted);
}
/* Mỗi trạng thái có hình dạng riêng (không chỉ dựa vào màu) */
.gx-step.is-ok .gx-dot { background: var(--gx-teal); border-color: var(--gx-teal); }
.gx-step.is-ok .gx-dot::after {            /* dấu tích */
  content: "";
  position: absolute;
  left: 5px; top: 1px;
  width: 4px; height: 8px;
  border: solid #FFFFFF;
  border-width: 0 2px 2px 0;
  transform: rotate(45deg);
}
.gx-step.is-amber .gx-dot { background: var(--gx-amber); border-color: var(--gx-amber); }
.gx-step.is-amber .gx-dot::after {         /* thanh che */
  content: "";
  position: absolute;
  left: 3px; top: 6px;
  width: 10px; height: 2px;
  background: var(--gx-ink);
}
.gx-step.is-bad .gx-dot { background: var(--gx-danger); border-color: var(--gx-danger); }
.gx-step.is-bad .gx-dot::after {           /* dấu gạch ngang */
  content: "";
  position: absolute;
  left: 3px; top: 6px;
  width: 10px; height: 2px;
  background: #FFFFFF;
}
.gx-step.is-off .gx-dot { background: transparent; border-color: #98A8B8; }

.gx-tag {
  display: inline-flex;
  align-items: center;
  padding: .1rem .55rem;
  border-radius: 999px;
  font-size: .78rem;
  font-weight: 600;
  line-height: 1.5;
}
.gx-tag-ok { background: var(--gx-teal-soft); color: var(--gx-teal-dark); }
.gx-tag-amber { background: var(--gx-amber-soft); color: #6B4200; }
.gx-tag-bad { background: var(--gx-danger-soft); color: var(--gx-danger); }
.gx-tag-off { background: #E4E9EE; color: #4A5B6D; }

/* ---------- Câu hỏi sau khi che dữ liệu ---------- */
.gx-masked-text {
  background: var(--gx-surface);
  border: 1px solid var(--gx-line);
  border-radius: 10px;
  padding: .8rem .95rem;
  font-size: .95rem;
  line-height: 1.85;
  color: var(--gx-body);
  overflow-wrap: anywhere;
}
.gx-redact {
  display: inline-block;
  padding: 0 .45em;
  border-radius: 4px;
  background: var(--gx-amber);
  color: var(--gx-ink);
  font-size: .82em;
  font-weight: 600;
  line-height: 1.55;
  white-space: nowrap;
}

/* ---------- Trạng thái trống ---------- */
.gx-empty {
  border: 1px dashed var(--gx-line-strong);
  border-radius: 16px;
  padding: 1.4rem 1.5rem 1.5rem;
}
.gx-empty p { margin: .35rem 0 0; max-width: 62ch; font-size: .95rem; line-height: 1.65; color: var(--gx-muted); }
.gx-empty .gx-demo { margin-top: 1rem; max-width: 62ch; }
.gx-empty .gx-demo-cap { margin-top: .5rem; font-size: .85rem; }

/* ---------- Sidebar (nền tối do .streamlit/config.toml; chữ kế thừa màu theme) ---------- */
.gx-side-title { margin: 0 0 .2rem; font-size: 1rem; font-weight: 600; line-height: 1.4; color: inherit; }
.gx-side-note {
  margin: .8rem 0 0;
  padding: .7rem .8rem;
  border-radius: 10px;
  background: rgba(255, 255, 255, .08);
  font-size: .83rem;
  line-height: 1.55;
  color: inherit;
}
.gx-side-block { margin-top: 1.3rem; padding-top: 1.1rem; border-top: 1px solid rgba(255, 255, 255, .16); }
.gx-side-list { list-style: none; margin: .55rem 0 0; padding: 0; }
.gx-side-list li {
  position: relative;
  padding: 0 0 .5rem 1.2rem;
  font-size: .86rem;
  line-height: 1.55;
  color: inherit;
}
.gx-side-list li::before {      /* thanh che nhỏ làm dấu đầu dòng */
  content: "";
  position: absolute;
  left: 0; top: .62em;
  width: 10px; height: 3px;
  border-radius: 1px;
  background: var(--gx-amber);
}
.gx-side-caution { margin: .3rem 0 0; font-size: .82rem; line-height: 1.5; color: inherit; opacity: .78; }

/* ---------- Chân trang ---------- */
.gx-foot {
  margin: 1.2rem 0 0;
  padding-top: 1rem;
  border-top: 1px solid var(--gx-line);
  font-size: .85rem;
  line-height: 1.55;
  color: var(--gx-muted);
}

/* ---------- Màn hình nhỏ ---------- */
@media (max-width: 768px) {
  [data-testid="stMainBlockContainer"], .block-container { padding: 1.4rem 1rem 2rem; }
  .stApp .gx-hero h1 { font-size: 1.4rem; }
  .gx-mark { width: 40px; height: 40px; background-position: 9px 10px, 9px 18px, 9px 26px; background-size: 22px 5px, 17px 5px, 11px 5px; }
  .st-key-ask_card, .st-key-answer_card, .st-key-sources_card { padding: 1.1rem 1rem 1.2rem; }
  .st-key-trace_panel { padding: 1.2rem 1rem 1.3rem; }
}
@media (prefers-reduced-motion: reduce) {
  .stApp * { transition: none !important; }
}
"""


# --------------------------------------------------------------------------------------
# Tiện ích escape
# --------------------------------------------------------------------------------------
def _e(value: object) -> str:
    """Escape văn bản để chèn an toàn vào HTML."""
    return html.escape(str(value), quote=True)


def _multiline(value: object) -> str:
    """Escape rồi đổi xuống dòng thành <br> (giữ HTML trên đúng MỘT dòng)."""
    text = _e(value).replace("\r\n", "\n").replace("\r", "\n")
    return text.replace("\n", "<br>")


# --------------------------------------------------------------------------------------
# Câu hỏi đã che: tô nổi các token [XXX_REDACTED]
# --------------------------------------------------------------------------------------
_REDACT_TOKEN = re.compile(r"\[[A-Z0-9_]+_REDACTED\]")


def redact_html(text: str) -> str:
    """Trả về HTML của câu hỏi đã che, các token bị che hiện dưới dạng thanh hổ phách.

    Token được hiển thị đúng nguyên văn (ví dụ [EMAIL_REDACTED]) để người xem thấy
    chính xác mô hình nhận được gì.
    """
    parts: list[str] = []
    last = 0
    for match in _REDACT_TOKEN.finditer(text):
        parts.append(_multiline(text[last:match.start()]))
        parts.append(f'<span class="gx-redact">{_e(match.group(0))}</span>')
        last = match.end()
    parts.append(_multiline(text[last:]))
    return "".join(parts)


# --------------------------------------------------------------------------------------
# Chuỗi xử lý của Trust Layer (suy ra từ dữ liệu mà API đã trả về)
# --------------------------------------------------------------------------------------
@dataclass
class Step:
    title: str
    tone: str                      # ok | amber | bad | off
    tag: str
    details: list[str] = field(default_factory=list)


_MASK_COUNT = re.compile(r"^Đã che (\d+)")


def split_notes(notes: list[str]) -> tuple[list[str], list[str]]:
    """Tách ghi chú thành (ghi chú che PII ở đầu vào, ghi chú của bộ lọc đầu ra).

    Backend tạo ghi chú che PII bắt đầu bằng "Đã che ..."; mọi ghi chú khác đến từ
    bước kiểm tra đầu ra.
    """
    pii = [n for n in notes if n.startswith("Đã che")]
    other = [n for n in notes if not n.startswith("Đã che")]
    return pii, other


def build_steps(safety_notes: list[str], sources: list[dict], use_rag: bool, model: str) -> list[Step]:
    pii_notes, output_notes = split_notes(safety_notes)

    masked_total = 0
    for note in pii_notes:
        found = _MASK_COUNT.match(note)
        if found:
            masked_total += int(found.group(1))

    if pii_notes:
        step_input = Step(
            "Che dữ liệu cá nhân", "amber",
            f"Đã che {masked_total}" if masked_total else "Đã che",
            list(pii_notes),
        )
    else:
        step_input = Step(
            "Che dữ liệu cá nhân", "ok", "Không phát hiện",
            ["Không phát hiện mẫu PII theo các quy tắc demo."],
        )

    if not use_rag:
        step_rag = Step(
            "Truy xuất tài liệu (RAG)", "off", "Đang tắt",
            ["Mô hình trả lời mà không có đoạn tài liệu nào làm ngữ cảnh."],
        )
    elif sources:
        step_rag = Step("Truy xuất tài liệu (RAG)", "ok", f"{len(sources)} đoạn nguồn")
    else:
        step_rag = Step("Truy xuất tài liệu (RAG)", "off", "Không có đoạn phù hợp")

    step_model = Step("Mô hình trả lời", "ok", str(model))

    if output_notes:
        step_output = Step("Kiểm tra đầu ra", "bad", "Đã can thiệp", list(output_notes))
    else:
        step_output = Step("Kiểm tra đầu ra", "ok", "Đạt quy tắc demo")

    return [step_input, step_rag, step_model, step_output]


def steps_html(steps: list[Step]) -> str:
    items = []
    for step in steps:
        details = "".join(f'<p class="gx-step-detail">{_e(d)}</p>' for d in step.details)
        items.append(
            f'<li class="gx-step is-{_e(step.tone)}">'
            '<span class="gx-dot" aria-hidden="true"></span>'
            '<div class="gx-step-main">'
            '<div class="gx-step-top">'
            f'<span class="gx-step-title">{_e(step.title)}</span>'
            f'<span class="gx-tag gx-tag-{_e(step.tone)}">{_e(step.tag)}</span>'
            "</div>"
            f"{details}"
            "</div></li>"
        )
    return f'<ol class="gx-steps">{"".join(items)}</ol>'


def trace_html(masked_input: str, steps: list[Step]) -> str:
    """Khối bên phải: chuỗi xử lý + câu hỏi sau khi che."""
    return (
        '<div class="gx-trace">'
        '<h2 class="gx-h2">Trust Layer đã xử lý yêu cầu</h2>'
        f"{steps_html(steps)}"
        '<div class="gx-masked">'
        '<h3 class="gx-h3">Câu hỏi sau khi che dữ liệu</h3>'
        f'<div class="gx-masked-text">{redact_html(masked_input)}</div>'
        "</div></div>"
    )


# --------------------------------------------------------------------------------------
# Nguồn RAG
# --------------------------------------------------------------------------------------
_SOURCE_NAME = re.compile(r"^(?P<file>.+?)#chunk-(?P<n>\d+)$")


def split_source(name: str) -> tuple[str, str]:
    """'01_paper_summary.md#chunk-3' -> ('01_paper_summary.md', 'đoạn 3')."""
    found = _SOURCE_NAME.match(name)
    if found:
        return found.group("file"), f"đoạn {found.group('n')}"
    return name, ""


def sources_html(sources: list[dict], use_rag: bool) -> str:
    heading = (
        f'<h2 class="gx-h2">Nguồn RAG <span class="gx-count">({len(sources)})</span></h2>'
    )
    if not sources:
        message = (
            "RAG đang tắt nên không có đoạn tài liệu nào được dùng làm nguồn."
            if not use_rag
            else "Không có đoạn tài liệu nào phù hợp với câu hỏi này."
        )
        return f'<div class="gx-sources-wrap">{heading}<p class="gx-none">{_e(message)}</p></div>'

    items = []
    for src in sources:
        file_name, chunk = split_source(src.get("source", ""))
        chunk_html = f'<span class="gx-chunk">{_e(chunk)}</span>' if chunk else ""
        items.append(
            '<li class="gx-src">'
            f'<div class="gx-src-head"><span class="gx-file">{_e(file_name)}</span>{chunk_html}</div>'
            f'<p>{_multiline(src.get("excerpt", ""))}</p>'
            "</li>"
        )
    return f'<div class="gx-sources-wrap">{heading}<ol class="gx-sources">{"".join(items)}</ol></div>'


# --------------------------------------------------------------------------------------
# Các mảnh nhỏ khác
# --------------------------------------------------------------------------------------
def hero_html(title: str, subtitle: str) -> str:
    return (
        '<header class="gx-hero">'
        '<span class="gx-mark" aria-hidden="true"></span>'
        f"<div><h1>{_e(title)}</h1><p>{_e(subtitle)}</p></div>"
        "</header>"
    )


def heading_html(text: str) -> str:
    return f'<h2 class="gx-h2">{_e(text)}</h2>'


def suggest_label_html(text: str) -> str:
    return f'<div class="gx-suggest-label">{_e(text)}</div>'


def api_caption_html(text: str) -> str:
    return f'<div class="gx-api">{_e(text)}</div>'


def empty_state_html(title: str, body: str, demo_before: str, demo_token: str, demo_after: str, demo_caption: str) -> str:
    """Trạng thái trống: giải thích sẽ thấy gì và minh họa nhỏ về việc che dữ liệu."""
    return (
        '<div class="gx-empty">'
        f'<h2 class="gx-h2">{_e(title)}</h2>'
        f"<p>{_e(body)}</p>"
        f'<div class="gx-masked-text gx-demo">{_e(demo_before)}<span class="gx-redact">{_e(demo_token)}</span>{_e(demo_after)}</div>'
        f'<p class="gx-demo-cap">{_e(demo_caption)}</p>'
        "</div>"
    )


def sidebar_title_html(text: str) -> str:
    return f'<div class="gx-side-title">{_e(text)}</div>'


def sidebar_note_html(text: str) -> str:
    return f'<div class="gx-side-note">{_e(text)}</div>'


def sidebar_trust_html(title: str, items: list[str], caution: str) -> str:
    lis = "".join(f"<li>{_e(i)}</li>" for i in items)
    return (
        '<div class="gx-side-block">'
        f'<div class="gx-side-title">{_e(title)}</div>'
        f'<ul class="gx-side-list">{lis}</ul>'
        f'<p class="gx-side-caution">{_e(caution)}</p>'
        "</div>"
    )


def footer_html(text: str) -> str:
    return f'<div class="gx-foot">{_e(text)}</div>'
