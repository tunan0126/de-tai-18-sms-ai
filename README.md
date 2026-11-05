---
title: SMS Spam Detector AI
emoji: 🛡️
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

# Gói runtime cloud - đề tài 18

Trạng thái: đã chuẩn bị mã và model; CHƯA triển khai, đang chờ tài khoản cloud.
Giao diện gọn mới nhất, ML Việt v2, DL Việt bản giữ lại, hai model UCI.
Chỉ chứa file cần chạy; không có DB, phiên đăng nhập, mật khẩu local, dữ liệu
huấn luyện hoặc môi trường .venv. Bản đầy đủ riêng ở D:/Capstone.

## Cấu hình triển khai dự kiến

- Build Dockerfile ở gốc gói này. Không đặt root directory vào thư mục app con.
- HOST=0.0.0.0, cổng dùng biến PORT của nền tảng, healthcheck /api/health,
  chờ tối đa 300 giây để TensorFlow khởi động. Một replica.
- Gắn volume bền vững /data, TV4_DATABASE=/data/tv4.sqlite3.
- Điền domain thật vào APP_ORIGIN và ALLOWED_HOSTS; COOKIE_SECURE=1.
- Với Railway, thêm healthcheck.railway.app vào ALLOWED_HOSTS và
  RAILWAY_RUN_UID=0 theo hướng dẫn quyền volume của Railway. Không dùng biến
  Railway này để đổi cấu hình chạy Docker local nếu không cần.
- Không bật đăng ký công khai khi demo bằng các tài khoản riêng.

Sau khi có volume, chạy một lần trong runtime:
python cloud_app/bo_sung_tv4_app/manage.py create-demo-users
Thông tin đăng nhập sinh riêng ở /data/Tai_khoan_demo.txt. Giữ riêng file này.
CMD mặc định chạy Waitress sau khi làm nóng bốn nhánh model.

Nghiệm thu: HTTPS từ hai máy, ML/DL Việt/UCI, lịch sử và luật riêng, feedback,
chặn ID của tài khoản khác, dữ liệu còn sau restart. Chỉ công bố URL khi
deployment và kiểm tra thực tế đạt. Máy hiện tại chưa có Docker Engine;
kiểm tra file runtime trên Windows không thay thế build/chạy Linux container.

Tài liệu chính thức đã đối chiếu:
https://docs.railway.com/volumes
https://docs.railway.com/builds/dockerfiles
https://docs.railway.com/deployments/healthchecks
Không dùng railway.json cũ: tài liệu hiện tại thông báo Config as Code đã deprecated.
