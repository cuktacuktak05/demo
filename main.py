import os
import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()
API_BASE = os.getenv("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")

st.set_page_config(page_title="Enterprise GenAI Assistant", page_icon="🛡️", layout="wide")
st.title("🛡️ Enterprise GenAI Assistant")
st.caption("Demo học thuật: RAG + Trust Layer, lấy cảm hứng từ bài báo về tích hợp GenAI vào nền tảng doanh nghiệp.")

with st.sidebar:
    st.header("Cấu hình truy vấn")
    role = st.selectbox("Vai trò demo", ["employee", "admin"], format_func=lambda x: {"employee": "Nhân viên", "admin": "Quản trị viên"}[x])
    use_rag = st.toggle("Bật RAG (truy xuất tài liệu)", value=True)
    st.info("Vai trò ở đây chỉ mô phỏng lựa chọn giao diện. Chưa có đăng nhập thật; không dùng làm kiểm soát truy cập production.")
    st.markdown("**Trust Layer trong demo**")
    st.write("• Che email / số điện thoại / số định danh theo regex")
    st.write("• Kiểm tra đầu ra bằng quy tắc đơn giản")
    st.write("• Audit log tối thiểu, không ghi prompt thô")
    st.caption("Không gửi dữ liệu nhạy cảm thật vào demo.")

question = st.text_area(
    "Câu hỏi",
    placeholder="Ví dụ: Trust Layer có vai trò gì trong kiến trúc GenAI doanh nghiệp?",
    height=120,
)
col1, col2 = st.columns([1, 4])
with col1:
    submit = st.button("Gửi câu hỏi", type="primary", use_container_width=True)
with col2:
    st.caption("API backend: " + API_BASE)

if submit:
    if len(question.strip()) < 3:
        st.warning("Hãy nhập câu hỏi dài ít nhất 3 ký tự.")
    else:
        with st.spinner("Đang truy xuất tài liệu và gọi mô hình..."):
            try:
                response = requests.post(
                    f"{API_BASE}/ask",
                    json={"question": question, "role": role, "use_rag": use_rag},
                    timeout=90,
                )
                if response.status_code != 200:
                    st.error(f"API lỗi ({response.status_code}): {response.text}")
                else:
                    data = response.json()
                    st.subheader("Câu trả lời")
                    st.write(data["answer"])
                    st.caption(f"Mô hình: {data['model']}")
                    with st.expander("Trust Layer — đầu vào sau khi che dữ liệu"):
                        st.code(data["masked_input"])
                        if data["safety_notes"]:
                            for note in data["safety_notes"]:
                                st.write("• " + note)
                        else:
                            st.write("Không phát hiện mẫu PII theo các quy tắc demo.")
                    with st.expander(f"Nguồn RAG ({len(data['sources'])})", expanded=True):
                        if not data["sources"]:
                            st.write("Không có đoạn nguồn phù hợp hoặc RAG đang tắt.")
                        for i, src in enumerate(data["sources"], start=1):
                            st.markdown(f"**{i}. `{src['source']}`**")
                            st.write(src["excerpt"])
            except requests.RequestException as exc:
                st.error("Không kết nối được FastAPI. Hãy khởi động backend trước. Chi tiết: " + str(exc))

st.divider()
st.caption("Lưu ý: Đây là prototype phục vụ môn học, không phải triển khai Salesforce hay hệ thống bảo mật hoàn chỉnh.")
