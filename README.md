# Face Attendance — Nhận diện khuôn mặt chấm công tích hợp Odoo

Hệ thống chấm công bằng nhận diện khuôn mặt cho ~200 nhân viên, dùng model
pretrained **InsightFace `buffalo_l`** (không cần train), chụp ảnh bằng điện
thoại, xác thực và tự động tạo bản ghi `hr.attendance` trên **Odoo**.

## Kiến trúc

```
app/
 ├── api/            # FastAPI routers (HTTP layer only)
 │    ├── register.py    POST /register
 │    ├── verify.py       POST /verify (verify + tạo chấm công Odoo)
 │    ├── health.py
 │    └── deps.py         Dependency injection (DB session, services)
 ├── services/       # Business logic
 │    ├── face_service.py       InsightFace: detect + align + embedding
 │    ├── embedding_service.py  So khớp embedding (cosine similarity)
 │    └── odoo_service.py       XML-RPC client cho Odoo hr.attendance
 ├── repositories/
 │    └── face_repository.py    CRUD thuần cho bảng employee_face
 ├── models/         # SQLAlchemy ORM models
 ├── schemas/        # Pydantic request/response models
 ├── database/       # engine, session, declarative base
 ├── utils/          # logger, image decode/save, custom exceptions
 └── main.py         # App factory, lifespan, exception handlers
```

**Luồng /register**: decode ảnh → `FaceService` detect 1 khuôn mặt (InsightFace
tự làm alignment qua landmark trước khi sinh embedding) → lưu embedding 512
chiều vào bảng `employee_face` (kèm ảnh gốc nếu bật `STORE_ORIGINAL_IMAGE`).

**Luồng /verify**: decode ảnh → sinh embedding → so sánh cosine similarity với
toàn bộ embedding đã đăng ký → nếu điểm cao nhất ≥ `FACE_MATCH_THRESHOLD` thì
gọi `OdooService` để tạo/đóng bản ghi `hr.attendance` (tự động toggle
check-in/check-out dựa trên bản ghi đang mở của nhân viên đó trên Odoo).

> **Giả định quan trọng**: `employee_id` dùng trong hệ thống này được coi là
> trùng với `id` của bản ghi `hr.employee` trên Odoo. Nếu hai hệ thống dùng ID
> khác nhau, sửa `OdooService._resolve_odoo_employee_id()` trong
> `app/services/odoo_service.py` để map sang đúng ID Odoo (ví dụ tra theo mã
> nhân viên/barcode).

## Cài đặt & chạy bằng Docker Compose

1. Copy file môi trường mẫu:

   ```bash
   cp .env.example .env
   ```

2. Sửa `.env`: đặt `ODOO_URL`, `ODOO_DB`, `ODOO_USERNAME`, `ODOO_PASSWORD` trỏ
   tới Odoo instance đang chạy (Odoo Attendance app phải được cài).

3. Build & chạy:

   ```bash
   docker compose up --build
   ```

   Lần đầu chạy sẽ tự tải model `buffalo_l` (~300MB) trong lúc build image
   (nếu build máy không có mạng, model sẽ tự tải lúc container khởi động lần
   đầu — xem log `Loading InsightFace model pack...`).

4. Mở Swagger UI: http://localhost:8000/docs
5. Giao diện kiosk (mở camera, tự động quét mặt, chấm công): http://localhost:8000/

## Chạy không dùng Docker (local dev)

Yêu cầu Python 3.12+, PostgreSQL đang chạy.

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt

# Sửa .env: DATABASE_URL trỏ tới postgres local, ví dụ
# postgresql+psycopg2://postgres:postgres@localhost:5432/face_attendance

uvicorn app.main:app --reload --port 8000
```

## Giao diện Kiosk

`GET /` (`app/static/index.html`) là một trang tĩnh, tự chứa (không phụ thuộc
CDN ngoài), mở webcam bằng `getUserMedia`, tự động chụp & gọi `/verify` mỗi
~1.8s (dừng 5s sau khi chấm công thành công để tránh check-in/out liên tục),
và có khung con để đăng ký nhân viên mới bằng ảnh chụp trực tiếp thay vì upload
file.

> **Trình duyệt yêu cầu HTTPS để cấp quyền camera**, trừ khi truy cập qua
> `localhost`. Nếu định dùng điện thoại truy cập qua domain/IP LAN, bắt buộc
> phải chạy sau HTTPS (xem mục "Triển khai lên domain" bên dưới) — nếu không
> trình duyệt trên điện thoại sẽ từ chối mở camera.

## API

### `POST /register` — Đăng ký khuôn mặt

Yêu cầu header `X-API-Key` khớp với `REGISTER_API_KEY` trong `.env` (nếu biến
này được set — xem mục Bảo mật bên dưới). Không có auth cho `/verify` vì đây
là thao tác chấm công công khai tại kiosk, tương tự máy chấm công vật lý.

`multipart/form-data`:

| field         | type | mô tả                                  |
|---------------|------|------------------------------------------|
| `employee_id` | int  | ID nhân viên (= `hr.employee` id trên Odoo) |
| `file`        | file | Ảnh chứa đúng 1 khuôn mặt                |

```bash
curl -X POST http://localhost:8000/register \
  -H "X-API-Key: $REGISTER_API_KEY" \
  -F "employee_id=15" \
  -F "file=@employee15.jpg"
```

Response:

```json
{ "success": true, "employee_id": 15, "face_id": 1, "message": "Face registered successfully" }
```

### `POST /verify` — Xác thực + chấm công

`multipart/form-data`:

| field       | type  | bắt buộc | mô tả                        |
|-------------|-------|----------|------------------------------|
| `file`      | file  | có       | Ảnh chụp từ điện thoại        |
| `latitude`  | float | không    | Vị trí GPS lúc chấm công       |
| `longitude` | float | không    | Vị trí GPS lúc chấm công       |

```bash
curl -X POST http://localhost:8000/verify \
  -F "file=@probe.jpg" \
  -F "latitude=10.7769" \
  -F "longitude=106.7009"
```

Response khi thành công (tự động tạo `hr.attendance` trên Odoo):

```json
{
  "success": true,
  "employee_id": 15,
  "score": 0.91,
  "attendance": {
    "action": "check_in",
    "odoo_attendance_id": 342,
    "timestamp": "2026-07-16T02:15:00Z",
    "gps": { "latitude": 10.7769, "longitude": 106.7009 }
  },
  "message": "Attendance recorded"
}
```

Response khi không nhận diện được:

```json
{ "success": false, "message": "Face not recognized" }
```

Lần gọi `/verify` thứ hai trong ngày cho cùng nhân viên sẽ tự động là
`check_out` (dịch vụ tự kiểm tra bản ghi `hr.attendance` đang mở trên Odoo).

Test nhanh bằng script có sẵn:

```bash
./scripts/test_api.sh register 15 employee15.jpg
./scripts/test_api.sh verify probe.jpg 10.7769 106.7009
```

Hoặc import `scripts/postman_collection.json` vào Postman.

## Kết nối Odoo thật

1. **Lấy thông tin kết nối**:
   - `ODOO_URL`: địa chỉ Odoo (vd `https://your-odoo.example.com`, không có dấu `/` cuối)
   - `ODOO_DB`: tên database Odoo — xem ở trang đăng nhập Odoo (nếu có nhiều DB)
     hoặc `https://<odoo>/web/database/manager`
   - `ODOO_USERNAME` / `ODOO_PASSWORD`: **nên tạo một user riêng cho API**
     (Settings → Users → New), không dùng tài khoản cá nhân. User này cần
     quyền **Attendances: Administrator** (không chỉ "Employee" tự chấm công
     cho chính mình) — vì service ghi `hr.attendance` thay cho bất kỳ
     `employee_id` nào, Odoo sẽ chặn nếu user chỉ có quyền tự-phục-vụ.

2. **Test kết nối trước khi cắm vào app**, dùng script có sẵn:

   ```bash
   python scripts/test_odoo_connection.py https://your-odoo.example.com odoo_db api_user api_password
   ```

   Script sẽ in ra: version Odoo, xác thực thành công hay không, danh sách
   `hr.employee` (id + tên) để bạn đối chiếu `employee_id` dùng khi gọi
   `/register`, và kiểm tra user có quyền ghi `hr.attendance` hay không.

3. Sửa `ODOO_URL`, `ODOO_DB`, `ODOO_USERNAME`, `ODOO_PASSWORD` trong `.env`,
   rồi `docker compose up -d --build` lại.

4. Test thật: `/register` một nhân viên, sau đó `/verify` — kiểm tra trong
   Odoo (Attendances app) đã xuất hiện bản ghi check-in chưa.

> Nếu `employee_id` trong hệ thống này không trùng `id` của `hr.employee`
> trên Odoo, sửa `OdooService._resolve_odoo_employee_id()` trong
> `app/services/odoo_service.py` để map đúng.

## Triển khai lên domain (HTTPS)

Trạng thái hiện tại: app **chạy được** bằng Docker Compose ngay, nhưng
**chưa nên đưa domain public** nếu thiếu 2 điều dưới đây — cả hai đã được
chuẩn bị sẵn trong repo, chỉ cần bật lên:

1. **HTTPS** — bắt buộc để trình duyệt điện thoại cho phép mở camera trên
   domain thật (không phải `localhost`). Repo đã có `Caddyfile` +
   `docker-compose.prod.yml` dùng Caddy để tự lấy chứng chỉ Let's Encrypt.
2. **API key cho `/register`** — nếu không có, bất kỳ ai truy cập được domain
   cũng đăng ký được khuôn mặt giả cho `employee_id` bất kỳ. Đã thêm
   `REGISTER_API_KEY` + header `X-API-Key` (xem mục Bảo mật).

### Các bước deploy với domain `attendance.quocbui.dev`

1. **Trỏ DNS**: tạo bản ghi `A` cho `attendance.quocbui.dev` trỏ về IP public
   của server sẽ chạy Docker (làm ở nhà cung cấp domain/DNS của bạn — bước
   này tôi không làm thay được). `Caddyfile` trong repo đã sẵn domain này,
   nếu đổi domain khác thì sửa `Caddyfile`.

2. **Mở port 80 và 443** trên firewall/security group của server.

3. Trên server, clone/copy repo, rồi:

   ```bash
   cp .env.example .env
   # sửa .env: ODOO_*, REGISTER_API_KEY (bắt buộc, dùng: openssl rand -hex 32),
   # và đổi POSTGRES_PASSWORD khỏi giá trị mặc định

   docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
   ```

   Overlay `docker-compose.prod.yml` sẽ: thêm service `caddy` (nhận port
   80/443, tự xin cert cho domain trong `Caddyfile`, reverse proxy vào
   `api:8000`), đồng thời **ngừng expose** port `8000` và `5432` ra ngoài
   internet — chỉ Caddy mới public.

4. Truy cập `https://attendance.quocbui.dev/` — nên hoạt động ngay nếu DNS
   đã trỏ đúng và port 80/443 mở (Caddy tự cấp cert trong vài giây, không cần
   thao tác thủ công gì thêm).

5. Kiểm tra log nếu có lỗi cert: `docker compose logs caddy`.

## Cấu hình (`.env`)

| Biến                     | Mặc định                | Ghi chú                                                        |
|--------------------------|-------------------------|-----------------------------------------------------------------|
| `DATABASE_URL`           | —                        | Chuỗi kết nối PostgreSQL (SQLAlchemy)                           |
| `INSIGHTFACE_MODEL_PACK` | `buffalo_l`              | Model pack pretrained, không cần train                          |
| `INSIGHTFACE_DET_SIZE`   | `640`                    | Kích thước ảnh đưa vào detector (càng lớn càng chính xác, chậm hơn) |
| `INSIGHTFACE_CTX_ID`     | `-1`                     | `-1` = CPU, `0` = GPU đầu tiên (cần onnxruntime-gpu)             |
| `FACE_MATCH_THRESHOLD`   | `0.5`                    | Ngưỡng cosine similarity để chấp nhận khớp — **nên test thực tế và tinh chỉnh** (0.4–0.6 là khoảng phổ biến với ArcFace/buffalo_l) |
| `STORE_ORIGINAL_IMAGE`   | `true`                   | Có lưu ảnh gốc lúc đăng ký hay không                            |
| `ODOO_URL/DB/USERNAME/PASSWORD` | —                 | Thông tin kết nối XML-RPC tới Odoo                              |
| `ODOO_ATTACH_IMAGE`      | `false`                  | Đính kèm ảnh chấm công vào `hr.attendance` dưới dạng `ir.attachment` |
| `ODOO_TIMEOUT`           | `10`                     | Timeout (giây) cho mỗi lệnh XML-RPC tới Odoo — chặn `/verify` bị treo nếu Odoo chậm/đứng |
| `REGISTER_API_KEY`       | rỗng                     | Header `X-API-Key` bắt buộc cho `/register`. **Để trống chỉ khi dev local** — bắt buộc set trước khi public domain |

## Database

Bảng `employee_face` (tự tạo lúc app khởi động qua `Base.metadata.create_all`):

| Cột           | Kiểu           | Ghi chú                          |
|---------------|----------------|-----------------------------------|
| `id`          | serial PK      |                                    |
| `employee_id` | integer, index | ID nhân viên (nhiều dòng/nhân viên nếu đăng ký lại) |
| `embedding`   | float[]        | Vector 512 chiều (ArcFace)         |
| `image_path`  | varchar        | Đường dẫn ảnh gốc (tùy chọn)        |
| `created_at`  | timestamptz    |                                    |

So khớp dùng brute-force cosine similarity trên toàn bộ embedding trong
Python — với quy mô ~200 nhân viên (có thể nhiều embedding/người), việc này
chỉ mất vài mili-giây nên không cần `pgvector` hay index chuyên dụng. Nếu quy
mô tăng lên hàng chục nghìn người, cân nhắc bổ sung extension `pgvector`.

## Bảo mật (đọc trước khi public domain)

- **`REGISTER_API_KEY` phải được set** trước khi mở domain ra internet — nếu
  không, bất kỳ ai cũng gọi được `/register` để gán khuôn mặt của họ vào
  `employee_id` của người khác. `/verify` cố tình để mở (không cần key) vì đó
  là thao tác chấm công công khai tại kiosk.
- Đổi `POSTGRES_PASSWORD` và `ODOO_PASSWORD` khỏi giá trị mặc định trong
  `.env.example`.
- Dùng `docker-compose.prod.yml` để không expose Postgres (5432) và API
  (8000) trực tiếp ra internet — chỉ Caddy (80/443) mới public.
- HTTPS là bắt buộc (không tùy chọn) vì trình duyệt chặn `getUserMedia` trên
  origin không an toàn — không có HTTPS thì trang kiosk không mở được camera
  trên điện thoại.

## Giới hạn & mở rộng

- Mỗi lần `/register` hoặc `/verify` yêu cầu ảnh chứa **đúng 1 khuôn mặt**
  (theo đúng yêu cầu "mỗi lần chỉ 1 người trước camera"); ảnh có 0 hoặc >1
  khuôn mặt sẽ trả lỗi 422.
- Trường GPS (`in_latitude`/`in_longitude`/`out_latitude`/`out_longitude`)
  trên `hr.attendance` chỉ tồn tại nếu Odoo có bật tính năng định vị của app
  Attendances (Odoo 16+). Nếu không có, `OdooService` tự động thử lại không
  kèm GPS thay vì báo lỗi toàn bộ request.
- Không có migration tool (Alembic) — schema hiện tại đơn giản nên dùng
  `create_all` lúc khởi động; thêm Alembic nếu schema sẽ tiến hóa thường xuyên.
