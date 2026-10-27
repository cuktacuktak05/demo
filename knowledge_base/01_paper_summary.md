# Tóm tắt bài báo — nguồn nền tảng demo

Nguồn: Kazem Haki, Dorsa Safaei, Adolfo Magan, Martin Griffiths, “Integrating Generative AI Into Enterprise Platforms: Insights From Salesforce”, Information Systems Journal (2025), DOI: 10.1111/isj.12593.

## Ba lĩnh vực khuyến nghị
Bài báo tổ chức các khuyến nghị thành Platform Capability, Platform Architecture và Platform Governance. Nghiên cứu xem xét các thách thức tích hợp GenAI ở cấp nền tảng doanh nghiệp, sử dụng trường hợp Salesforce để phát triển các khuyến nghị.

## Trust Layer
Theo bài báo, môi trường tin cậy cần quản lý quyền truy cập dữ liệu, bảo vệ tính ẩn danh, giám sát đầu ra GenAI đối với vấn đề như nội dung độc hại và thiên lệch, cũng như thực thi chính sách không lưu giữ dữ liệu (zero data retention) phù hợp với thỏa thuận của nhà cung cấp.

## Prompt architecture và grounding
Bài báo mô tả việc bổ sung ngữ cảnh vào prompt, dùng prompt template được định nghĩa trước và hướng dẫn người dùng xây dựng prompt. Trường hợp Salesforce sử dụng dynamic grounding để bổ sung dữ liệu ngữ cảnh từ các nguồn phù hợp; RAG được nêu như một cách đưa dữ liệu có cấu trúc và phi cấu trúc vào prompt.

## Phạm vi của demo
Demo hiện thực hóa một lát cắt giáo dục gồm truy xuất đoạn tài liệu (RAG đơn giản bằng TF-IDF), chèn ngữ cảnh vào prompt, che một số mẫu PII bằng regex, kiểm tra đầu ra bằng quy tắc, và audit log tối thiểu. Các thành phần này là thiết kế triển khai đề xuất để minh họa một số ý tưởng trong bài báo; chúng không phải mã nguồn chính thức của Salesforce và không tái tạo đầy đủ Trust Layer thương mại.
