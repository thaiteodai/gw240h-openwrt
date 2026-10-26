# Research helpers / Script thăm dò

Công cụ dùng trong quá trình tìm hiểu thiết bị, không nằm trong quy trình flash.
Research helpers from the bring-up phase; not part of the flashing flow.

| File | Việc |
|---|---|
| `create_ubi_manual.py` | tạo ảnh UBI v1 thủ công (thử nghiệm ban đầu) |
| `embed_ubi.py` | nhúng UBI vào `tclinux.trx` (trước khi dùng hybrid 2RDH) |
| `fix_ubi_persistence.py` | thử sửa overlay UBI không ghi được |
| `fix_uart_issue.py`, `troubleshoot_uart.sh` | chẩn đoán vì sao không thấy prompt `bldr>` |
| `try_passwords.py` | thử mật khẩu mặc định qua SSH trên firmware gốc |

Kết quả của giai đoạn này nằm trong `docs/bootloader_tips.txt` và README.
