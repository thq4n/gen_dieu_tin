# Deploy lên Streamlit Community Cloud (gen_dieu_tin)

## Điều kiện

- Repo trên GitHub (Community Cloud miễn phí thường yêu cầu repo **public**).
- File ở root: `streamlit_app.py`, `requirements.txt`.
- File tùy chọn: `packages.txt` (gói apt trên máy chủ Cloud).

## Bước 1 — Đẩy code lên GitHub

```bash
git add .
git commit -m "Chuẩn bị deploy Streamlit Cloud"
git push origin main
```

Không commit file `.streamlit/secrets.toml` (đã có trong `.gitignore`). Chỉ commit `secrets.toml.example`.

## Bước 2 — Tạo app trên Streamlit Cloud

1. Đăng nhập [share.streamlit.io](https://share.streamlit.io) bằng GitHub.
2. **New app** → chọn repo `gen_dieu_tin`, branch `main`.
3. **Main file path**: `streamlit_app.py`.
4. **App URL**: đặt tên subdomain (nếu trùng sẽ phải đổi).
5. **Deploy**.

Lần build đầu có thể mất vài phút (cài `requirements.txt` và các gói trong `packages.txt`).

## Bước 3 — Secrets (RabbitMQ mặc định, tùy chọn)

Trên dashboard app: **Settings** (răng cưa) → **Secrets**.

Dán nội dung TOML (có thể copy từ `.streamlit/secrets.toml.example` rồi sửa giá trị thật), ví dụ:

```toml
[rabbitmq]
base_url = "https://rabbit.example.com:15672"
username = "your_user"
password = "your_pass"
routing_key = "pickuptasks_queue"
verify_ssl = true
```

- **Lưu** → app sẽ restart.
- Các trường này chỉ là **mặc định** trên form “Vào ứng dụng”; người dùng vẫn có thể sửa trước khi lưu profile.
- `verify_ssl = false` chỉ khi Management API dùng chứng chỉ tự ký và bạn chấp nhận rủi ro.

Chạy local: tạo file `.streamlit/secrets.toml` (cùng nội dung), không đẩy lên git.

## Bước 4 — Kiểm tra sau deploy

- Mở URL app → nhập tên + RabbitMQ (hoặc dùng default từ secrets) → **Vào ứng dụng**.
- RabbitMQ phải **truy cập được từ internet** (URL public, firewall cho phép). Địa chỉ LAN như `192.168.x.x` sẽ không chạy từ Cloud.

## Ghi chú

- Thư mục `state/` và `output/` trên Cloud là **không bền**: restart có thể mất counter/file đã lưu trên disk.
- Nếu build lỗi, xem **Manage app** → **Logs** trên Streamlit Cloud.
