# BẢNG KẾT LUẬN & QUYẾT ĐỊNH REFACTORING CUỐI CÙNG (FINAL AUDIT DECISIONS)

> **Dự án:** Pycil (`/home/qninh/projects/pycil`)  
> **Người duyệt:** User & Tech Lead  
> **Nguyên tắc:** Review từng hạng mục, triệt tiêu mã overengineering / chắp vá, tối ưu hiệu năng nhưng không làm mất an toàn hệ thống.

---

## DANH SÁCH CÁC PHÁN QUYẾT THEO TỪNG MỤC

### 1. Bỏ bọc chuỗi đệ quy `__pycil_external_data__` trong Assistant
* **Vị trí liên quan**:
  - [`apps/api/pycil/assistant/agent/external_data.py`](file:///home/qninh/projects/pycil/apps/api/pycil/assistant/agent/external_data.py)
  - [`apps/api/pycil/assistant/agent/middleware.py#L17-L38`](file:///home/qninh/projects/pycil/apps/api/pycil/assistant/agent/middleware.py#L17-L38)
  - [`apps/api/pycil/assistant/agent/prompts/system.jinja#L38-L41`](file:///home/qninh/projects/pycil/apps/api/pycil/assistant/agent/prompts/system.jinja#L38-L41)
  - [`apps/api/tests/unit/assistant/test_boundaries.py#L23-L65`](file:///home/qninh/projects/pycil/apps/api/tests/unit/assistant/test_boundaries.py#L23-L65)
* **Đề xuất ban đầu (Analyzer)**: Gỡ bỏ việc bọc chuỗi đệ quy vì gây lãng phí 30-50% token và double JSON serialization trên mọi tool call.
* **Lập luận phản biện (Verifier)**: Bác bỏ vì cho rằng đây là chốt chặn bảo vệ chống Indirect Prompt Injection.
* **PHÁN QUYẾT CUỐI CÙNG CỦA USER**: **ĐỒNG Ý VỚI ANALYZER - GỠ BỎ HOÀN TOÀN**.
* **Lý do & Rationale**:
  - Hệ thống đã có cơ chế **HITL (Human-in-the-Loop)** bảo vệ ở tầng quyết định: Mọi hành động phá hủy, nhạy cảm hoặc thay đổi dữ liệu (`delete_folder`, `delete_deck`, thay đổi quyền truy cập...) bắt buộc phải được người dùng xác nhận trực tiếp qua `ResumeDecision` trước khi tool được thực thi.
  - Việc bọc đệ quy từng leaf string thành `{"__pycil_external_data__": value}` là overengineering rườm rà, tiêu tốn token vô ích và làm chậm vòng lặp SSE streaming của trợ lý ảo.
* **Kế hoạch triển khai (Action Items)**:
  1. Xóa file [`apps/api/pycil/assistant/agent/external_data.py`](file:///home/qninh/projects/pycil/apps/api/pycil/assistant/agent/external_data.py).
  2. Gỡ bỏ `ExternalDataBoundaryMiddleware` khỏi [`apps/api/pycil/assistant/agent/middleware.py`](file:///home/qninh/projects/pycil/apps/api/pycil/assistant/agent/middleware.py) và đồ thị agent LangGraph.
  3. Làm sạch `prompts/system.jinja` và `prompts.py`: Bỏ biến `external_data_key`.
  4. Cập nhật unit test trong `tests/unit/assistant/test_boundaries.py`.
* **Trạng thái**: **HOÀN TẤT (DONE)** - 90/90 assistant tests pass.

---

### 2. [CRITICAL P0 - RUNTIME CRASH] Sửa lỗi Singleflight Word Generation `AttributeError`
* **Vị trí**: [`apps/api/pycil/worker/jobs/generate_word.py#L19-L30`](file:///home/qninh/projects/pycil/apps/api/pycil/worker/jobs/generate_word.py#L19-L30) (Hàm `_fetch_existing`)
* **Bản chất lỗi**: `SearchResultView` không có thuộc tính `.word_id` và `.senses`. Request thứ hai trong Singleflight truy cập sẽ ném `AttributeError` làm sập background job.
* **PHÁN QUYẾT**: **XÁC NHẬN SỬA TRIỆT ĐỂ**.
* **Giải pháp**: Gọi `entry = await ctx["lexi_reader"].get_entry(results[0].lexi_word_id)` để lấy đầy đủ đối tượng `EntryView` trước khi trả về.

---
### 3. Migration Xác thực Clerk sang Official Backend SDK (`clerk-backend-api`)
* **Vị trí**:
  - [`apps/api/pyproject.toml`](file:///home/qninh/projects/pycil/apps/api/pyproject.toml)
  - [`apps/api/pycil/account/auth.py`](file:///home/qninh/projects/pycil/apps/api/pycil/account/auth.py)
* **Hiện trạng cũ**:
  - Tự viết logic xác thực token bằng `PyJWKClient` kết hợp `jwt.decode` đồng bộ.
  - `PyJWKClient` gọi mạng bằng `urllib` đồng bộ, chặn (block) toàn bộ event loop của FastAPI trong tối đa 5 giây khi fetch hoặc refresh signing key từ Clerk JWKS, tạo lỗ hổng DoS.
* **PHÁN QUYẾT**: **XÁC NHẬN MIGRATION SANG OFFICIAL CLERK SDK (`clerk-backend-api`)**.
* **Lý do & Rationale**:
  - `clerk-backend-api` là SDK chính thức được Clerk hỗ trợ, cung cấp `clerk_backend_api.security.verify_token_async`.
  - SDK sử dụng `httpx.AsyncClient` kết hợp `AsyncHTTPTransport(retries=10)` hoàn toàn non-blocking trên async event loop.
  - Tích hợp sẵn cơ chế in-memory caching (`__jwkcache`) với TTL 300 giây và tự động xoay khóa (automatic key rotation retry) khi gặp lỗi chữ ký cũ mà không cần can thiệp thủ công.
  - Wheel size chỉ 584 KB, hoàn toàn dùng lại các thư viện hiện có (`cryptography`, `httpx`, `pydantic`, `pyjwt`), không làm phình app.
* **Kết quả Triển khai & Review**:
  - Cài đặt `clerk-backend-api>=7.0.0`.
  - Refactor [`apps/api/pycil/account/auth.py`](file:///home/qninh/projects/pycil/apps/api/pycil/account/auth.py): Chuyển `_decode_claims` sang async với `verify_token_async`.
  - Giữ lại chốt chặn bảo mật xác thực `settings.clerk_issuer` bắt buộc.
  - **Code Review**: Subagent phát hiện 2 điểm cần tối ưu: dead code nhánh `else` và nguy cơ double slash `//jwks` khi parse URL; đã fix hoàn chỉnh cơ chế chuẩn hóa URL endpoint cho cả production và test stub.
  - **Kết quả Kiểm thử**: 100% test pass (22/22 tests `test_clerk_identity.py` chạy trong 6.00s, nhanh hơn gấp đôi so với 12.77s ban đầu; 42/42 account integration tests pass).
* **Trạng thái**: **HOÀN TẤT (DONE)**.

---

## CÁC HẠNG MỤC TẠM THỜI SKIP (Đang Redesign Lại `lexi-ai`)

> **Ghi chú**: Người dùng đang tiến hành redesign lại toàn bộ `lexi-ai`, do đó các vấn đề/bug liên quan trực tiếp đến Lexicon và Content Worker tạm thời bỏ qua (skip), sẽ được xử lý đồng bộ cùng đợt redesign `lexi-ai`:
1. Sửa lỗi Singleflight Word Generation `AttributeError` trong [`apps/api/pycil/worker/jobs/generate_word.py`](file:///home/qninh/projects/pycil/apps/api/pycil/worker/jobs/generate_word.py).
2. Tối ưu vòng lặp N+1 chuẩn bị câu hỏi trong [`apps/api/pycil/worker/jobs/generate_question.py`](file:///home/qninh/projects/pycil/apps/api/pycil/worker/jobs/generate_question.py).
3. Thừa `AsyncSession` và hủy bỏ `idempotency_key` trong [`apps/api/pycil/lexicon/generation.py`](file:///home/qninh/projects/pycil/apps/api/pycil/lexicon/generation.py) & `api.py`.
4. N+1 search query và wrapper `_ApiLexiReader` trong [`apps/api/pycil/lexicon/embedded.py`](file:///home/qninh/projects/pycil/apps/api/pycil/lexicon/embedded.py).

---
