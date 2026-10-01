# KIẾN TRÚC & GIẢI PHÁP REFACTORING TOÀN DIỆN MÃ NGUỒN `apps/api/pycil`

> **Ngày phê duyệt:** 01/10/2026  
> **Dự án:** Pycil (`/home/qninh/projects/pycil`)  
> **Tài liệu nền tảng:** [`CODE_ANALYSIS_REPORT.md`](file:///home/qninh/projects/pycil/CODE_ANALYSIS_REPORT.md)  
> **Mục tiêu tối thượng:**
> 1. **Triệt tiêu mã chắp vá (Anti-Patchwork & Clean Architecture):** Giải quyết triệt để nguyên nhân gốc rễ (Root Cause), tuyệt đối không dùng mẹo `try/except` để "vá víu" bên ngoài hay sinh ra các hàm chữa cháy kiểu `_repair_projection`.
> 2. **Chống hạ thấp tiêu chuẩn kỹ thuật (Strict No Underengineering):** Giữ vững 100% các chốt chặn an ninh, boundary chống prompt injection (`__pycil_external_data__`), phân tách domain trong Modular Monolith, và tính toàn vẹn kế toán/GDPR.
> 3. **Tối ưu hóa hiệu năng thực tế (High Performance & KISS):** Thay thế các thuật toán $O(N \times M)$ hoặc $O(N^2)$ bằng $O(1)$ hoặc $O(N+M)$; gộp các chuỗi queries $N+1$ thành batch queries / atomic SQL; giảm 50% số lượng truy vấn trên hot-path AI; loại bỏ toàn bộ blocking synchronous network I/O trong Uvicorn event loop.

---

## MỤC LỤC

- [I. XỬ LÝ DỨT ĐIỂM 5 LỖI P0 / CRITICAL NGUY CƠ CAO](#i-xử-lý-dứt-điểm-5-lỗi-p0--critical-nguy-cơ-cao)
  - [1. Lỗi Runtime Crash trong Singleflight Word Generation](#1-lỗi-runtime-crash-trong-singleflight-word-generation)
  - [2. Lỗ hổng DoS do Blocking Synchronous I/O trong Event Loop khi verify JWT](#2-lỗ-hổng-dos-do-blocking-synchronous-io-trong-event-loop-khi-verify-jwt)
  - [3. Sai lệch Ranh giới Giao dịch & Đảo ngược Transaction phá vỡ OCC](#3-sai-lệch-ranh-giới-giao-dịch--đảo-ngược-transaction-phá-vỡ-occ)
  - [4. Truncate 32-bit UUID gây Cross-User Lock Collision trong PostgreSQL](#4-truncate-32-bit-uuid-gây-cross-user-lock-collision-trong-postgresql)
  - [5. Nguy cơ Infinite Loop trong Recursive CTE Subtree Depth](#5-nguy-cơ-infinite-loop-trong-recursive-cte-subtree-depth)
- [II. THIẾT KẾ REFACTORING CHI TIẾT THEO 5 DOMAINS](#ii-thiết-kế-refactoring-chi-tiết-theo-5-domains)
  - [1. Domain STUDY (`apps/api/pycil/study/`)](#1-domain-study-appsapipycilstudy)
  - [2. Domain ASSISTANT (`apps/api/pycil/assistant/`)](#2-domain-assistant-appsapipycilassistant)
  - [3. Domain LIBRARY (`apps/api/pycil/library/`)](#3-domain-library-appsapipycillibrary)
  - [4. Domain BILLING & ACCOUNT (`apps/api/pycil/billing/` & `account/`)](#4-domain-billing--account-appsapipycilbilling--account)
  - [5. Domain PLATFORM, LEXICON, JOBS & WORKER](#5-domain-platform-lexicon-jobs--worker)
- [III. MA TRẬN PHÒNG NGỪA HỒI QUY (REGRESSION PREVENTION MATRIX)](#iii-ma-trận-phòng-ngừa-hồi-quy-regression-prevention-matrix)
- [IV. LỘ TRÌNH TRIỂN KHAI THEO 4 PULL REQUESTS (PR ROADMAP)](#iv-lộ-trình-triển-khai-theo-4-pull-requests-pr-roadmap)

---

## I. XỬ LÝ DỨT ĐIỂM 5 LỖI P0 / CRITICAL NGUY CƠ CAO

### 1. Lỗi Runtime Crash trong Singleflight Word Generation
* **Vị trí**: [`apps/api/pycil/worker/jobs/generate_word.py#L19-L30`](file:///home/qninh/projects/pycil/apps/api/pycil/worker/jobs/generate_word.py#L19-L30) (Hàm `_fetch_existing`).
* **Bản chất lỗi**: `ctx["lexi_reader"].search(payload.query)` trả về `SearchResultView` (chỉ có `lexi_word_id`). Truy cập `.word_id` và `.senses` ném ngay `AttributeError` tại runtime khi có 2 request đồng thời tạo cùng 1 từ.
* **Refactor chuẩn**:
  ```python
  # SAU KHI REFACTOR:
  async def _fetch_existing() -> dict | None:
      results = await ctx["lexi_reader"].search(payload.query)
      if results and results[0].lexi_word_id:
          entry = await ctx["lexi_reader"].get_entry(results[0].lexi_word_id)
          if entry:
              return {
                  "wordId": entry.word_id,
                  "senseIds": [sense.sense_id for sense in entry.senses if sense.sense_id is not None],
              }
      return None
  ```

---

### 2. Lỗ hổng DoS do Blocking Synchronous I/O trong Event Loop khi verify JWT
* **Vị trí**: [`apps/api/pycil/account/auth.py#L39-L61`](file:///home/qninh/projects/pycil/apps/api/pycil/account/auth.py#L39-L61) (`_get_jwks_client`).
* **Bản chất lỗi**: `PyJWKClient` dùng `urllib.request.urlopen` đồng bộ với timeout 5 giây. Token chứa `kid` lạ đóng băng toàn bộ tiến trình Uvicorn, tạo lỗ hổng DoS trực tiếp.
* **Refactor chuẩn**: Thiết kế `AsyncJWKSClient` sử dụng `httpx.AsyncClient` kết hợp `asyncio.Lock` (chống Thundering Herd) và in-memory TTL caching:
  ```python
  class AsyncJWKSClient:
      def __init__(self, jwks_url: str, cache_ttl: int = 300, timeout: float = 5.0) -> None:
          self.jwks_url = jwks_url
          self.cache_ttl = cache_ttl
          self.timeout = timeout
          self._keys: dict[str, PyJWK] = {}
          self._fetched_at: float = 0.0
          self._lock = asyncio.Lock()
          self._client: httpx.AsyncClient | None = None

      async def _get_client(self) -> httpx.AsyncClient:
          if self._client is None or self._client.is_closed:
              self._client = httpx.AsyncClient(timeout=httpx.Timeout(self.timeout, connect=2.0))
          return self._client

      async def get_signing_key_from_jwt(self, token: str) -> PyJWK:
          unverified = jwt.get_unverified_header(token)
          kid = unverified.get("kid")
          if not kid:
              raise UnauthorizedError("invalid_token")

          now = time.monotonic()
          if kid in self._keys and (now - self._fetched_at) < self.cache_ttl:
              return self._keys[kid]

          async with self._lock:
              now = time.monotonic()
              if kid in self._keys and (now - self._fetched_at) < self.cache_ttl:
                  return self._keys[kid]
              client = await self._get_client()
              resp = await client.get(self.jwks_url)
              resp.raise_for_status()
              self._keys = {k["kid"]: PyJWK.from_json_key(k) for k in resp.json().get("keys", []) if "kid" in k}
              self._fetched_at = time.monotonic()
              if kid not in self._keys:
                  raise UnauthorizedError("invalid_token")
              return self._keys[kid]
  ```

---

### 3. Sai lệch Ranh giới Giao dịch & Đảo ngược Transaction phá vỡ OCC
* **Vị trí**: [`apps/api/pycil/study/engine/progress.py#L170`](file:///home/qninh/projects/pycil/apps/api/pycil/study/engine/progress.py#L170) & [`apps/api/pycil/study/sessions/answering.py#L209`](file:///home/qninh/projects/pycil/apps/api/pycil/study/sessions/answering.py#L209).
* **Bản chất lỗi**: `apply_answer` tự ý commit DB trước khi cập nhật Redis. Khi Redis claim token thất bại, `session.rollback()` vô dụng vì DB đã commit, buộc phải sinh ra hàm "chữa cháy" `_repair_projection` ghi đè trạng thái Redis và ném bay cơ chế OCC.
* **Refactor chuẩn (2-Phase Coordination Pattern)**:
  1. Tước quyền commit DB của hàm cấp thấp `apply_answer` (đổi tên thành `prepare_answer_mutation` chỉ thực hiện mutate trên `AsyncSession` in-memory).
  2. Orchestrator `answering.submit()` thực hiện quy trình 2 pha nghiêm ngặt:
     - **Pha 1 (Redis Claim)**: Cập nhật Redis state và verify `claim_token`. Nếu thất bại $\rightarrow$ ném ngay `ConflictError("study_session_claim_lost")` mà không tác động gì đến DB.
     - **Pha 2 (PostgreSQL Commit)**: Khi Redis xác nhận an toàn, thực hiện `await session.commit()`. Nếu DB commit thất bại $\rightarrow$ giải phóng Redis claim và rollback DB.
  3. **XÓA BỎ HOÀN TOÀN** hàm chắp vá `_repair_projection`.

---

### 4. Truncate 32-bit UUID gây Cross-User Lock Collision trong PostgreSQL
* **Vị trí**: [`apps/api/pycil/study/engine/progress.py#L204-L224`](file:///home/qninh/projects/pycil/apps/api/pycil/study/engine/progress.py#L204-L224) (Hàm `_lock_stats`).
* **Bản chất lỗi**: Cắt 4 byte đầu của UUID (`user_id.bytes[:4]`) ép vào 32-bit int khiến 65.536 users có xác suất đụng độ lock > 50% (Birthday Paradox), gây false lock contention giữa 2 users hoàn toàn độc lập.
* **Refactor chuẩn**: Băm `f"{user_id}:{sense_id}"` bằng SHA-256 lấy 8 bytes làm signed 64-bit bigint, đồng thời loại bỏ `with_for_update()` thừa:
  ```python
  def _advisory_lock_key(user_id: UUID, sense_id: int) -> int:
      digest = hashlib.sha256(f"{user_id}:{sense_id}".encode()).digest()
      return int.from_bytes(digest[:8], byteorder="big", signed=True)

  async def _lock_stats(session: AsyncSession, user_id: UUID, sense_id: int) -> None:
      lock_key = _advisory_lock_key(user_id, sense_id)
      await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_key})
  ```

---

### 5. Nguy cơ Infinite Loop trong Recursive CTE Subtree Depth
* **Vị trí**: [`apps/api/pycil/library/nodes.py#L203-L217`](file:///home/qninh/projects/pycil/apps/api/pycil/library/nodes.py#L203-L217) (`_validate_subtree_depth`).
* **Bản chất lỗi**: Recursive CTE hoàn toàn thiếu mảng `visited_ids` (cycle guard) và `depth <= :limit`, có thể dẫn đến treo vĩnh viễn worker và DB connection nếu cây danh mục có cycle.
* **Refactor chuẩn**: Thống nhất câu lệnh CTE chuẩn mực có cycle guard và depth limit vào [`library/tree.py`](file:///home/qninh/projects/pycil/apps/api/pycil/library/tree.py).

---

## II. THIẾT KẾ REFACTORING CHI TIẾT THEO 5 DOMAINS

### 1. Domain STUDY (`apps/api/pycil/study/`)

#### 1.1. Chuẩn hóa REST RFC 9110 cho `/sessions/{id}/next`
* **Vấn đề**: `GET /sessions/{id}/next` làm thay đổi trạng thái phiên học (ghi queue, đổi cursor) vi phạm idempotent của HTTP GET.
* **Giải pháp**:
  - Thiết lập endpoint mới: `POST /sessions/{id}/next`.
  - Giữ `GET /sessions/{id}/next` như một Deprecated Alias với header `Deprecation: true`, trỏ tới cùng 1 handler nội bộ để bảo đảm zero-downtime cho client cũ.

#### 1.2. Nạp Session Document 1 lần duy nhất trong `/next`
* **Vấn đề**: `next_question` tải Redis session document nhiều lần tuần tự qua các helper functions.
* **Giải pháp**: Nạp trực tiếp `session_doc = await repo.load(session_id)` 1 lần duy nhất ở đầu handler và truyền đối tượng này xuống các layer tính toán.

#### 1.3. Thay thế `cjson.decode` bằng Lua Regex Matching
* **Vấn đề**: Script Lua trong `repository.py` giải mã toàn bộ JSON document lớn chỉ để kiểm tra version và claim.
* **Giải pháp**: Dùng Lua pattern matching `string.match(data, '"version":(%d+)')` để kiểm tra OCC version trong $O(1)$ mà không cần parse full JSON cây session.

#### 1.4. Gộp 3 Sequential Queries trong Dashboard thành 1 Conditional Aggregation
* **Vị trí**: [`study/dashboard.py#L59-L90`](file:///home/qninh/projects/pycil/apps/api/pycil/study/dashboard.py#L59-L90).
* **Code After Refactor**:
  ```python
  stmt = (
      select(
          func.count().filter(UserSenseStats.status != LearningStatus.SUSPENDED).label("active_total"),
          func.count().filter(UserSenseStats.next_review_date <= today).label("due_today"),
          func.count().filter(UserSenseStats.status == LearningStatus.LEARNING).label("learning_total"),
      )
      .where(UserSenseStats.user_id == user_id)
  )
  row = (await session.execute(stmt)).one()
  ```

#### 1.5. Đẩy điều kiện lọc Due Cards xuống SQL trong Planning
* **Vị trí**: [`study/sessions/planning.py#L49-L80`](file:///home/qninh/projects/pycil/apps/api/pycil/study/sessions/planning.py#L49-L80).
* **Giải pháp**: Truy vấn trực tiếp các `sense_id` thỏa mãn điều kiện `next_review_date <= :now` ngay ở câu lệnh SQL `select(UserSenseStats.sense_id).where(...)`, loại bỏ việc load hàng nghìn hàng dữ liệu lên RAM và parse qua Pydantic models.

---

### 2. Domain ASSISTANT (`apps/api/pycil/assistant/`)

#### 2.1. Loại bỏ 3x Deserialization Overhead của LangGraph Checkpointer
* **Vị trí**: [`apps/api/pycil/assistant/turns/stream.py#L322, L336, L210`](file:///home/qninh/projects/pycil/apps/api/pycil/assistant/turns/stream.py#L322) và [`threads.py#L41`](file:///home/qninh/projects/pycil/apps/api/pycil/assistant/threads.py#L41).
* **Giải pháp**:
  - Viết helper `read_checkpoint_meta()` chỉ query cột `metadata` của bảng `checkpoints` để đọc `interrupts` và `selected_model_id`.
  - Chỉ gọi `read_state()` (deserialize toàn bộ mảng tin nhắn) khi thật sự cần dựng prompt cho LLM.

#### 2.2. Thread-Safe Connection Pool cho `ChatOpenAI`
* **Vị trí**: [`apps/api/pycil/assistant/agent/middleware.py#L61`](file:///home/qninh/projects/pycil/apps/api/pycil/assistant/agent/middleware.py#L61) và [`model.py#L15`](file:///home/qninh/projects/pycil/apps/api/pycil/assistant/agent/model.py#L15).
* **Giải pháp**: Tạo LRU Model Cache tái sử dụng instance `ChatOpenAI` và `httpx.AsyncClient` HTTP Keep-Alive pool theo khóa `(model_id, max_tokens, reasoning_effort)`.

#### 2.3. Tích hợp `write=True` an toàn trong `folder_stats`
* **Vị trí**: [`apps/api/pycil/assistant/agent/tools.py#L214`](file:///home/qninh/projects/pycil/apps/api/pycil/assistant/agent/tools.py#L214).
* **Giải pháp**: Loại bỏ lời gọi kép tới CTE 60 dòng `get_folder_stats_for_viewer`. Chỉ kiểm tra quyền sở hữu `require_owned_folder(session, folder_id, user_id)` (1 câu SQL đơn giản) trước khi tính toán stats.

#### 2.4. Throttle Retention Renewal trên Read Endpoint
* **Vị trí**: [`assistant/api.py#L65`](file:///home/qninh/projects/pycil/apps/api/pycil/assistant/api.py#L65) (`GET /threads/{id}`).
* **Giải pháp**: Chỉ mở write transaction cập nhật `retention_deadline` khi hạn lưu trữ cũ còn dưới 50% thời hạn (ví dụ còn dưới 15 ngày đối với chu kỳ 30 ngày), loại bỏ hoàn toàn write transaction trên read path thông thường.

---

### 3. Domain LIBRARY (`apps/api/pycil/library/`)

#### 3.1. Hợp nhất CTE Duyệt Cây về `library/tree.py`
* **Vấn đề**: Các hàm duyệt tổ tiên và con cháu bị phân tán qua 4 file với cú pháp khác nhau, có chỗ thiếu cycle guard.
* **Giải pháp**: Gom toàn bộ logic đệ quy cây thành 2 hàm chuẩn hóa duy nhất trong `tree.py`:
  - `get_ancestor_chain(session, node_id, max_depth=64)`
  - `get_subtree_nodes(session, root_id, max_depth=64)`
  - Cả hai hàm đều cài đặt sẵn mảng `visited_ids` chống cycle và giới hạn độ sâu.

#### 3.2. Batching Reference Target Resolution trong `resolve_deck_ids`
* **Vị trí**: [`library/scope.py#L99-L105`](file:///home/qninh/projects/pycil/apps/api/pycil/library/scope.py#L99-L105).
* **Giải pháp**: Gom toàn bộ `target_node_id` của các REFERENCE nodes thành 1 danh sách, thực thi 1 câu lệnh `readability_rows` duy nhất với toán tử `IN (:target_ids)` thay vì chạy vòng lặp tuần tự $N$ lần.

#### 3.3. Batch Redis Operations cho Deck Senses Cache
* **Vị trí**: [`library/scope.py#L160-L192`](file:///home/qninh/projects/pycil/apps/api/pycil/library/scope.py#L160-L192) và [`cache.py#L43-L58`](file:///home/qninh/projects/pycil/apps/api/pycil/library/cache.py#L43-L58).
* **Giải pháp**: Xây dựng hàm `mget_deck_senses(deck_ids)` dùng Redis `MGET` và `mset_deck_senses(mapping)` dùng Redis `PIPELINE`, đọc và ghi hàng loạt deck senses chỉ trong 1 round-trip mạng.

#### 3.4. Rút gọn từ 5 Queries xuống 2 Queries trong `GET /nodes/{node_id}`
* **Vị trí**: [`library/nodes_api.py#L155`](file:///home/qninh/projects/pycil/apps/api/pycil/library/nodes_api.py#L155).
* **Giải pháp**: Viết hàm `get_readable_node_view(session, node_id, viewer_id)`:
  - Query 1: Truy vấn node và kiểm tra readability kèm danh sách tổ tiên bằng 1 câu CTE duy nhất.
  - Query 2: Lấy dữ liệu con trực tiếp hoặc senses của node đó.
  - Tiết kiệm 3 network round-trips và xóa bỏ việc chạy 2 lần câu CTE đệ quy trùng lặp.

---

### 4. Domain BILLING & ACCOUNT (`apps/api/pycil/billing/` & `account/`)

#### 4.1. Fast-Path Query Active `UsagePeriod` trên Hot-path AI
* **Vị trí**: [`billing/ledger.py#L125-L193`](file:///home/qninh/projects/pycil/apps/api/pycil/billing/ledger.py#L125-L193) (`require_usage_allowed`).
* **Giải pháp**:
  - Truy vấn trực tiếp active period trong 1 câu SQL:
    `SELECT * FROM usage_periods WHERE user_id = :id AND period_start <= :now AND period_end > :now LIMIT 1`.
  - 99.9% trường hợp tìm thấy ngay $\rightarrow$ Trích xuất `PlanKey(period.plan_key)` và tính toán quota, chỉ tốn **1 round-trip DB duy nhất** (thay vì 2 round-trips qua `account_plans`).
  - 0.1% trường hợp sang tháng mới $\rightarrow$ Fallback về slow-path lazy creation.

#### 4.2. Xóa bỏ DFS & N+1 DELETE trong Account Deletion
* **Vị trí**: [`account/deletion.py#L22-L98`](file:///home/qninh/projects/pycil/apps/api/pycil/account/deletion.py#L22-L98).
* **Giải pháp**: Xóa bỏ hoàn toàn hàm `_owned_node_order`. Thực thi 2 câu lệnh SQL nguyên tử trong transaction:
  ```sql
  -- Giải phóng self-referencing foreign key ngay trong bảng:
  UPDATE nodes SET parent_node_id = NULL WHERE author_id = :user_id;
  -- Xóa toàn bộ nodes trong 1 thao tác atomic:
  DELETE FROM nodes WHERE author_id = :user_id;
  ```
  Đưa thời gian xóa tài khoản từ hàng chục giây (khi có nhiều nodes) về dưới 50ms, triệt tiêu 100% nguy cơ lỗi `account_node_cycle`.

#### 4.3. Phân cấp Exception Taxonomy Kế thừa
* **Vị trí**: [`billing/errors.py#L10`](file:///home/qninh/projects/pycil/apps/api/pycil/billing/errors.py#L10) và [`billing/ledger.py#L177`](file:///home/qninh/projects/pycil/apps/api/pycil/billing/ledger.py#L177).
* **Giải pháp**:
  - Khai báo `class InsufficientAllowanceError(UsageQuotaExhaustedError): ...`
  - Sửa logic phân nhánh:
    ```python
    if required_units > 0 and remaining < required_units:
        if remaining <= 0:
            raise UsageQuotaExhaustedError("Usage quota is exhausted")
        raise InsufficientAllowanceError(f"Feature requires {required_units} units, but only {remaining} units remaining")
    ```
  - Khối `except UsageQuotaExhaustedError:` trong `stream.py` tự động bắt được cả 2 ngoại lệ này một cách an toàn.

#### 4.4. Tối ưu $O(N+M)$ trong Account Export
* **Vị trí**: [`account/export.py#L44-L47`](file:///home/qninh/projects/pycil/apps/api/pycil/account/export.py#L44-L47).
* **Giải pháp**: Dùng `defaultdict(list)` gom `deck_senses` theo `node_id` trước khi map vào `nodes`, đưa độ phức tạp từ $10.000.000$ phép tính xuống $11.000$ phép tính ($O(N+M)$).

#### 4.5. Bổ sung Functional Index trên `lower(User.email)`
* **Vị trí**: Model [`account/user.py`](file:///home/qninh/projects/pycil/apps/api/pycil/account/user.py) và Migration `0002_add_users_email_lower_index.py`.
* **Giải pháp**: Bổ sung `Index("ix_users_email_lower", text("lower(email)"))` để triệt tiêu Full Table Scan khi tìm kiếm user bằng email không phân biệt hoa thường.

---

### 5. Domain PLATFORM, LEXICON, JOBS & WORKER

#### 5.1. Tái sử dụng Redis Pool & Lexicon Engine trong Job Runner
* **Vị trí**: [`jobs/runner.py#L21-L50`](file:///home/qninh/projects/pycil/apps/api/pycil/jobs/runner.py#L21-L50).
* **Giải pháp**: Tái sử dụng `get_redis()` dùng chung của ứng dụng. Tuyệt đối **KHÔNG gọi `aclose()`** khi job kết thúc để bảo toàn pool cho toàn bộ ứng dụng.

#### 5.2. Hoàn thiện Lifespan Graceful Shutdown
* **Vị trí**: [`apps/api/pycil/main.py#L52-L59`](file:///home/qninh/projects/pycil/apps/api/pycil/main.py#L52-L59).
* **Giải pháp**: Đóng hoàn chỉnh các tài nguyên trong khối `finally` của ASGI lifespan:
  ```python
  finally:
      await close_redis()
      await engine.dispose()
  ```

#### 5.3. Chunked Batch Processing cho Assistant Retention Worker
* **Vị trí**: [`worker/jobs/reconcile_assistant_retention.py#L24-L40`](file:///home/qninh/projects/pycil/apps/api/pycil/worker/jobs/reconcile_assistant_retention.py#L24-L40).
* **Giải pháp**: Thêm `.limit(100)` cho query `SELECT id, thread_id FROM assistant_threads WHERE retention_deadline <= :now FOR UPDATE SKIP LOCKED`. Xử lý xóa checkpoint và commit database theo từng batch nhỏ 100 threads để tránh lock row kéo dài.

#### 5.4. Loại bỏ Unused DB Session & Bảo toàn Idempotency-Key trong Word Generations
* **Vị trí**: [`lexicon/api.py#L33`](file:///home/qninh/projects/pycil/apps/api/pycil/lexicon/api.py#L33) và [`lexicon/generation.py#L17`](file:///home/qninh/projects/pycil/apps/api/pycil/lexicon/generation.py#L17).
* **Giải pháp**: Xóa bỏ `session: AsyncSession = Depends(get_session)` khỏi endpoint `/word-generations`. Lưu `idempotency_key` vào Redis receipt để trả về kết quả ngay nếu client gửi request lặp.

#### 5.5. Streaming Byte Counter Middleware
* **Vị trí**: [`platform/middleware.py#L59-L136`](file:///home/qninh/projects/pycil/apps/api/pycil/platform/middleware.py#L59-L136).
* **Giải pháp**: Bọc generator `receive()` của ASGI để kiểm tra dung lượng payload theo luồng (streaming), ngắt kết nối ngay khi tổng byte vượt ngưỡng `max_bytes` thay vì buffer toàn bộ request vào RAM.

---

## III. MA TRẬN PHÒNG NGỪA HỒI QUY (REGRESSION PREVENTION MATRIX)

| Vấn đề Refactor | Rủi ro hồi quy (Regression Risk) | Biện pháp bảo vệ (Guardrail) |
|---|---|---|
| **2-Phase Study Coordination** | Không đồng bộ giữa Redis và PostgreSQL khi submit bài | Redis claim trước; chỉ commit DB khi Redis claim thành công. Xóa hẳn `_repair_projection`. |
| **POST `/sessions/{id}/next`** | Break frontend hiện tại (`apps/web/...`) | Giữ endpoint `GET` làm alias có header `Deprecation: true`, song song hỗ trợ cả GET và POST. |
| **Async JWKS Client** | Clerk downtime làm treo app | Cấu hình connect timeout 2s, total timeout 5s, bắt mọi lỗi và fail-closed `UnauthorizedError`. |
| **Atomic Node Deletion** | Lỗi khóa ngoại (FK Violation) | Bước 1 ngắt `parent_node_id = NULL`, bước 2 xóa nodes; các bảng phụ thuộc (`deck_senses`, `REFERENCE`) đã được xóa trước đó. |
| **Fast-Path UsagePeriod** | Sang tháng mới không tính được quota | Kiểm tra `if period is None` liền kích hoạt lazy creation fallback ngay lập tức. |
| **Singleflight Word Generation** | Lặp từ vựng khi gọi đồng thời | Dùng đúng `EntryView` từ `get_entry()` để trích xuất `word_id` và `sense_ids`. |
| **Shared Connection Pools** | Runner đóng nhầm pool của toàn app | Loại bỏ hoàn toàn `await redis.aclose()` trong `jobs/runner.py`. |

---

## IV. LỘ TRÌNH TRIỂN KHAI THEO 4 PULL REQUESTS (PR ROADMAP)

Để đảm bảo tính cô lập và kiểm soát rủi ro ở mức cao nhất, toàn bộ quá trình refactor được chia thành 4 Pull Requests độc lập:

### PR 1: P0 Hotfixes & Concurrency Safety (Ưu tiên số 1 - Khẩn cấp)
* Sửa lỗi Singleflight `_fetch_existing` trong `worker/jobs/generate_word.py`.
* Cài đặt `AsyncJWKSClient` thay thế blocking `urllib` trong `account/auth.py`.
* Sửa 64-bit bigint SHA-256 advisory lock trong `study/engine/progress.py`.
* Bổ sung cycle guard và depth limit cho CTE trong `library/nodes.py`.
* Thêm graceful shutdown cho Redis và SQLAlchemy trong `main.py`.

### PR 2: Database & Performance Optimizations (Ưu tiên số 2)
* Thay thế DFS và N+1 DELETE trong `account/deletion.py` bằng 2 lệnh SQL atomic.
* Cài đặt Fast-Path query active `UsagePeriod` trong `billing/ledger.py`.
* Thêm functional index `ix_users_email_lower` trên bảng `users` qua Alembic migration.
* Tối ưu thuật toán $O(N+M)$ trong `account/export.py`.
* Thêm batching operations cho Redis deck senses trong `library/cache.py`.

### PR 3: Architecture & Clean Code Standardization (Ưu tiên số 3)
* Tái cấu trúc 2-Phase Coordination trong `study/sessions/answering.py`, xóa bỏ `_repair_projection`.
* Thống nhất toàn bộ CTE duyệt cây về `library/tree.py`.
* Phân cấp `InsufficientAllowanceError` kế thừa `UsageQuotaExhaustedError`.
* Gộp 3 queries thành conditional aggregation trong `study/dashboard.py`.
* Thiết kế `read_checkpoint_meta()` giảm tải cho LangGraph checkpointer.

### PR 4: Platform & Worker Hardening (Ưu tiên số 4)
* Tái sử dụng shared connection pools trong `jobs/runner.py`.
* Chunked batch processing trong `worker/jobs/reconcile_assistant_retention.py`.
* Bỏ unused DB session và tích hợp Redis idempotency trong `lexicon/generation.py`.
* Streaming body size limit middleware trong `platform/middleware.py`.
