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

## API

### `POST /register` — Đăng ký khuôn mặt

`multipart/form-data`:

| field         | type | mô tả                                  |
|---------------|------|------------------------------------------|
| `employee_id` | int  | ID nhân viên (= `hr.employee` id trên Odoo) |
| `file`        | file | Ảnh chứa đúng 1 khuôn mặt                |

```bash
curl -X POST http://localhost:8000/register \
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
