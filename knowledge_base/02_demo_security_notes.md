# Ghi chú bảo mật dùng cho demo

Đây là tài liệu demo, không phải chính sách doanh nghiệp thực tế.

1. Chỉ sử dụng tài liệu giả lập hoặc đã được phép sử dụng.
2. Che PII theo regex chỉ là minh họa; có thể bỏ sót nhiều định dạng và có thể nhận diện nhầm.
3. Lựa chọn role trên giao diện không phải xác thực danh tính. Hệ thống thực tế cần SSO/OAuth, xác minh token ở backend và phân quyền theo tài nguyên.
4. Audit log không ghi prompt thô hay câu trả lời; chỉ ghi metadata tối thiểu.
5. Lọc đầu ra theo danh sách từ khóa không thay thế bộ phân loại an toàn chuyên dụng hoặc đánh giá con người.
6. Zero data retention không thể được đảm bảo chỉ bằng code client. Cần kiểm tra điều khoản, cấu hình và chính sách lưu giữ của nhà cung cấp mô hình API.
